"""Temperature-only sampling strata and reproducible independent-group splits.

Climate normals must already be verified as raw ERA5-Land monthly means for one
common normal period. These functions never inspect observed phenological dates.
Clustering preprocessing defines sampling strata; it is not predictive fitting.
"""
import hashlib

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

MONTHLY_COLUMNS = [f'tmean_month_{month:02d}_c' for month in range(1, 13)]
STAGES = ('07', '65', '81', '89')
DEFAULT_SEED = 20260909
MAX_ATTEMPTS = 1000


def _sites(sites, *, zoned=False):
    columns = ['site', 'group_id', 'era5_grid_id']
    if zoned:
        columns.append('temperature_zone_id')
    if not set(columns).issubset(sites.columns):
        raise ValueError(f'Sites require columns {columns}')
    result = sites.copy()
    for col in columns:
        if result[col].isna().any() or result[col].astype(str).str.strip().eq('').any():
            raise ValueError(f'Missing {col}')
        result[col] = result[col].astype(str)
    if result.empty or result.site.duplicated().any():
        raise ValueError('Sites must be nonempty with unique site identities')
    if result.groupby('era5_grid_id').group_id.nunique().max() != 1:
        raise ValueError('An ERA5 grid cannot cross independent groups')
    if zoned and result.groupby('group_id').temperature_zone_id.nunique().max() != 1:
        raise ValueError('An independent group cannot cross temperature zones')
    return result


def cluster_temperature_zones(sites, monthly_normals, *, seed=DEFAULT_SEED,
                              initial_clusters=5, min_groups_per_zone=5):
    """Return unchanged site rows plus zones, and JSON-serializable fit metadata.

    StandardScaler and KMeans weight each represented ERA5 grid exactly once.
    Groups spanning grids use the mean of their distinct standardized grid
    profiles for nearest-centre assignment. Sparse zones trigger a complete
    refit with one fewer cluster, without reference to any phenology outcomes.
    """
    sites = _sites(sites)
    if initial_clusters < 1 or min_groups_per_zone < 5:
        raise ValueError('Require positive cluster count and at least 5 groups per zone')
    if sites.group_id.nunique() < min_groups_per_zone:
        raise ValueError(f'Need at least {min_groups_per_zone} independent groups')
    required = ['era5_grid_id', *MONTHLY_COLUMNS]
    if not set(required).issubset(monthly_normals.columns):
        raise ValueError('Monthly climate profiles require grid ID and all 12 monthly temperatures')
    climate = monthly_normals[required].copy()
    if climate.era5_grid_id.isna().any():
        raise ValueError('Missing climate grid ID')
    climate['era5_grid_id'] = climate.era5_grid_id.astype(str)
    if climate.era5_grid_id.duplicated().any():
        raise ValueError('Duplicate climate grid IDs')
    grids = sorted(sites.era5_grid_id.unique())
    climate = climate.set_index('era5_grid_id').reindex(grids)
    climate = climate.apply(pd.to_numeric, errors='raise')
    if not np.isfinite(climate.to_numpy(dtype=float)).all():
        raise ValueError('Missing or nonfinite monthly climate profile for represented grid')
    scaler = StandardScaler()
    standardized = scaler.fit_transform(climate)
    grid_profiles = pd.DataFrame(standardized, index=climate.index, columns=MONTHLY_COLUMNS)
    group_profiles = (sites[['group_id', 'era5_grid_id']].drop_duplicates()
                      .sort_values(['group_id', 'era5_grid_id'])
                      .merge(grid_profiles, on='era5_grid_id', validate='many_to_one')
                      .groupby('group_id', sort=True)[MONTHLY_COLUMNS].mean())
    max_k = min(initial_clusters, len(np.unique(standardized, axis=0)))
    attempts = []
    for k in range(max_k, 0, -1):
        model = KMeans(n_clusters=k, random_state=seed, n_init=20, algorithm='lloyd')
        model.fit(standardized)
        labels = model.predict(group_profiles.to_numpy())
        counts = np.bincount(labels, minlength=k)
        attempts.append({'n_clusters': int(k), 'independent_group_counts': counts.tolist()})
        if counts.min() >= min_groups_per_zone:
            break
    else:
        raise ValueError('No temperature clustering supports the required independent groups')
    centers_c = scaler.inverse_transform(model.cluster_centers_)
    order = sorted(range(k), key=lambda i: (float(centers_c[i].mean()), *centers_c[i].tolist()))
    canonical = {old: f'TZ{new + 1:02d}' for new, old in enumerate(order)}
    group_zones = {group: canonical[int(label)] for group, label in zip(group_profiles.index, labels)}
    sites['temperature_zone_id'] = sites.group_id.map(group_zones)
    metadata = dict(
        features=MONTHLY_COLUMNS.copy(), temperature_input='RAW',
        algorithm='KMeans', scaling='StandardScaler', clustering_seed=int(seed),
        n_init=20, initial_clusters=int(initial_clusters), n_clusters=int(k),
        min_groups_per_zone=int(min_groups_per_zone), cluster_reduction_attempts=attempts,
        fit_weight_unit='unique_era5_grid', group_profile_weight_unit='unique_era5_grid',
        group_assignment='nearest centre of mean standardized unique-grid profile',
        canonical_label_order='ascending annual mean centre, monthly profile breaks ties',
        zone_ids=[canonical[i] for i in order], n_fit_grids=len(grids),
        scaler_mean_c=scaler.mean_.tolist(), scaler_scale_c=scaler.scale_.tolist(),
        scaler_variance_c2=scaler.var_.tolist(),
        cluster_centers_standardized=model.cluster_centers_[order].tolist(),
        cluster_centers_c=centers_c[order].tolist(),
        profile_sha256=hashlib.sha256(climate.to_csv().encode('utf-8')).hexdigest(),
        group_zone_map=group_zones,
        zone_group_counts=sites.groupby('temperature_zone_id').group_id.nunique().to_dict(),
    )
    return sites, metadata


def _allocation_data(zoned_sites, observations):
    sites = _sites(zoned_sites, zoned=True)
    if not {'site', 'BBCH'}.issubset(observations.columns):
        raise ValueError('Stage-support checks require observation site and BBCH')
    observed = observations[['site', 'BBCH']].copy()
    observed['site'] = observed.site.astype(str)
    observed['BBCH'] = observed.BBCH.astype(str).str.zfill(2)
    observed = observed.drop_duplicates().merge(sites[['site', 'group_id']], on='site', validate='many_to_one')
    stage_groups = {stage: set(observed.loc[observed.BBCH.eq(stage), 'group_id']) for stage in STAGES}
    sizes = sites.groupby('group_id', sort=True).size()
    zones = sites.groupby('group_id', sort=True).temperature_zone_id.first()
    return sites, sizes, zones, stage_groups


def assign_temperature_folds(zoned_sites, observations, *, seed=DEFAULT_SEED, n_folds=4):
    """Return group -> fold, balancing site counts within fixed climate zones.

    Randomized greedy attempts prioritize rare-stage groups, ensure each zone
    reaches all folds when it contains enough groups, and check all four stages
    in every validation fold. Only stage presence influences feasibility.
    """
    _, sizes, zones, stage_groups = _allocation_data(zoned_sites, observations)
    if n_folds != 4:
        raise ValueError('The protocol requires exactly four inner folds')
    if any(len(groups) < n_folds for groups in stage_groups.values()):
        raise ValueError('Four inner folds require four independent groups per stage')
    rng = np.random.default_rng(seed)
    zone_ids = sorted(zones.unique())
    zone_group_counts = zones.value_counts().to_dict()
    support = {g: {b for b, groups in stage_groups.items() if g in groups} for g in sizes.index}
    rarity = {g: min((len(stage_groups[b]) for b in support[g]), default=len(sizes) + 1) for g in sizes.index}
    for _ in range(MAX_ATTEMPTS):
        groups = list(rng.permutation(sizes.index.to_numpy()))
        groups.sort(key=lambda g: rarity[g])  # randomized stable ties
        totals = np.zeros(n_folds, dtype=int)
        zone_totals = {z: np.zeros(n_folds, dtype=int) for z in zone_ids}
        zone_counts = {z: np.zeros(n_folds, dtype=int) for z in zone_ids}
        stage_folds = {b: set() for b in STAGES}
        mapping = {}
        for group in groups:
            zone = zones[group]
            candidates = list(rng.permutation(n_folds))
            remaining = zone_group_counts[zone] - int(zone_counts[zone].sum())
            empty = set(np.flatnonzero(zone_counts[zone] == 0))
            if remaining == len(empty):
                candidates = [f for f in candidates if f in empty]
            fold = min(candidates, key=lambda f: (
                -sum(1 / len(stage_groups[b]) for b in support[group] if f not in stage_folds[b]),
                zone_totals[zone][f], totals[f]))
            mapping[group] = int(fold)
            totals[fold] += sizes[group]
            zone_totals[zone][fold] += sizes[group]
            zone_counts[zone][fold] += 1
            for stage in support[group]:
                stage_folds[stage].add(int(fold))
        if all(len(folds) == n_folds for folds in stage_folds.values()):
            return mapping
    raise ValueError(f'No stage-complete climate-balanced four-fold allocation found in {MAX_ATTEMPTS} attempts')


def split_temperature_groups(zoned_sites, observations, *, seed=DEFAULT_SEED, test_fraction=.2):
    """Return test group IDs for a seeded, zone-stratified whole-group holdout.

    Each zone uses a randomized group order and the prefix closest to its target
    number of source-qualified sites, retaining at least four calibration groups.
    Rejection checks require all four stages in testing and four independent
    calibration groups per stage, plus feasible stage-complete inner folds.
    """
    sites, sizes, zones, stage_groups = _allocation_data(zoned_sites, observations)
    if not 0 < test_fraction < 1:
        raise ValueError('Test fraction must lie strictly between zero and one')
    if any(len(groups) < 5 for groups in stage_groups.values()):
        raise ValueError('Outer testing and four inner folds require five independent groups per stage')
    zone_groups = {z: sorted(zones.index[zones.eq(z)]) for z in sorted(zones.unique())}
    if any(len(groups) < 5 for groups in zone_groups.values()):
        raise ValueError('Each temperature zone needs five independent groups for both partitions')
    rng = np.random.default_rng(seed)
    for _ in range(MAX_ATTEMPTS):
        test = set()
        for groups in zone_groups.values():
            order = rng.permutation(groups)
            cumulative = sizes.loc[order].to_numpy().cumsum()[:len(groups) - 4]
            count = int(np.argmin(abs(cumulative - test_fraction * sizes.loc[groups].sum()))) + 1
            test.update(order[:count])
        if not all(groups & test and len(groups - test) >= 4 for groups in stage_groups.values()):
            continue
        try:
            assign_temperature_folds(sites.loc[~sites.group_id.isin(test)], observations, seed=seed)
        except ValueError:
            continue
        return test
    raise ValueError(f'No stage-complete temperature-zone split found in {MAX_ATTEMPTS} attempts')
