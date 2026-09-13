"""Deterministic site, spatial and historical climate transfer protocols."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .cohort import assign_groups, file_hash
from .climate_zones import cluster_temperature_zones, split_temperature_groups, assign_temperature_folds

STAGES = {'07', '65', '81', '89'}


def _folds(sites, observations, seed):
    sizes = sites.groupby('group_id').size().sort_index()
    if len(sizes) < 4:
        raise ValueError('Need at least four independent calibration groups')
    observed = observations[['site','BBCH']].drop_duplicates().merge(sites[['site','group_id']], on='site')
    stage_groups = {stage: set(observed.loc[observed.BBCH.astype(str).str.zfill(2).eq(stage),'group_id']) for stage in STAGES}
    if any(len(groups) < 4 for groups in stage_groups.values()):
        raise ValueError('Four inner folds require four independent groups per stage')
    rng = np.random.default_rng(seed)
    for _ in range(1000):
        totals = np.zeros(4, dtype=int)
        mapping = {}
        for group in rng.permutation(sizes.index.to_numpy()):
            fold = int(np.argmin(totals))
            mapping[group] = fold
            totals[fold] += sizes[group]
        # Every held-out fold includes each stage; consequently all ordinary
        # and pair-excluded nested training subsets retain all four stages.
        if all({mapping[g] for g in groups} == {0,1,2,3} for groups in stage_groups.values()):
            return mapping
    raise ValueError('Cannot allocate four grouped folds with collective stage coverage')


def _outer_spatial(sites, observations):
    grouped = assign_groups(sites, spatial=True)
    groups = grouped.group_id.unique()
    if len(groups) < 5:
        raise ValueError('Need five independent spatial block groups')
    rng = np.random.default_rng(20260804)
    sizes = grouped.groupby('group_id').size()
    for _ in range(1000):
        totals, mapping = np.zeros(5, dtype=int), {}
        for group in rng.permutation(sorted(groups)):
            fold = int(np.argmin(totals))
            mapping[group] = fold
            totals[fold] += sizes[group]
        try:
            for fold in range(5):
                train = grouped.loc[grouped.group_id.map(mapping).ne(fold)]
                _folds(train, observations, 20260804 + fold)
        except ValueError:
            continue
        return grouped, mapping
    raise ValueError('Spatial folds cannot support four-stage inner calibration')


def _climate_selection(sites, climate):
    source_hash = None
    if isinstance(climate, (str, Path)):
        source_hash = file_hash(climate)
        climate = pd.read_csv(climate, dtype={'era5_grid_id':str})
    climate = climate.copy()
    climate['era5_grid_id'] = climate.era5_grid_id.astype(str)
    climate['year'] = pd.to_numeric(climate.year, errors='raise').astype(int)
    if climate.duplicated(['era5_grid_id','year']).any():
        raise ValueError('Duplicate grid/year climate')
    grids = sorted(sites.era5_grid_id.astype(str).unique())
    needed = pd.MultiIndex.from_product([grids, range(1951,2026)], names=['era5_grid_id','year'])
    values = climate.set_index(['era5_grid_id','year']).reindex(needed).tmean_apr_sep_c
    if not np.isfinite(pd.to_numeric(values, errors='coerce')).all():
        raise ValueError('Incomplete climate grid/year coverage including 1991–2020 reference')
    values = values.astype(float).unstack('year')
    reference = values.loc[:,1991:2020].mean(axis=1)
    anomalies = values.sub(reference, axis=0).mean(axis=0)  # equal unique grids, never site frequency
    threshold = float(np.quantile(anomalies.loc[1991:2020], .9))
    warm_years = sorted(int(y) for y in anomalies.index[anomalies.gt(threshold)])
    group_climate = sites[['group_id','era5_grid_id']].drop_duplicates().assign(
        reference=lambda x:x.era5_grid_id.astype(str).map(reference)).groupby('group_id').reference.mean()
    ranked = group_climate.rename('reference').reset_index().sort_values(['reference','group_id'], ascending=[False,True])
    n_test = max(1, int(np.ceil(.2 * len(ranked))))
    warm_groups = set(ranked.group_id.iloc[:n_test])
    metadata = dict(climate_sha256=source_hash or hashlib.sha256(climate.sort_values(['era5_grid_id','year']).to_csv(index=False).encode()).hexdigest(),
        reference_years=[1991,2020], available_years=[1951,2025], equal_weight_unit='unique_era5_grid',
        warm_year=dict(anomaly_threshold_c=threshold, quantile=.9, threshold_population='1991–2020 annual equal-grid anomalies',
                       selected_years=warm_years, annual_anomaly_c={str(y):float(v) for y,v in anomalies.items()}),
        warm_site=dict(fraction=.2, n_test_groups=n_test, tie_rule='group_id ascending',
                       boundary_reference_c=float(ranked.reference.iloc[n_test-1]), selected_groups=sorted(warm_groups)))
    return warm_years, warm_groups, metadata


def _normal_zones(sites, monthly_normals, normal_metadata=None):
    """Validate a source-described common RAW normal period before zoning."""
    path = Path(monthly_normals).resolve()
    metadata_path = Path(normal_metadata).resolve() if normal_metadata is not None else path.with_name('request.json')
    if not metadata_path.is_file():
        raise ValueError('Monthly normals require common-period RAW source metadata/provenance')
    source = json.loads(metadata_path.read_text())
    if source.get('normal_period') != [1991, 2020]:
        raise ValueError('Monthly normal period must be the common 1991–2020 period')
    if source.get('units') not in ('degrees Celsius', 'Celsius', 'degC'):
        raise ValueError('Monthly normals must be in Celsius')
    if (source.get('temperature_input', 'RAW') != 'RAW' or
            source.get('collection') != 'ECMWF/ERA5_LAND/MONTHLY_AGGR' or
            source.get('band') != 'temperature_2m'):
        raise ValueError('Monthly normals require RAW ERA5-Land temperature_2m provenance')
    inputs = {str(path): file_hash(path), str(metadata_path): file_hash(metadata_path)}
    provenance_path = path.with_name('export_provenance.json')
    if provenance_path.is_file():
        source['export_provenance'] = json.loads(provenance_path.read_text())
        inputs[str(provenance_path)] = file_hash(provenance_path)
    normals = pd.read_csv(path, dtype={'era5_grid_id': str})
    zoned, metadata = cluster_temperature_zones(sites, normals)
    metadata.update(normal_period=[1991, 2020], normal_source=source,
                    monthly_normals_sha256=inputs[str(path)], normal_metadata_path=str(metadata_path))
    return zoned, metadata, inputs


def make_protocols(cohort, climate=None, *, monthly_normals=None, normal_metadata=None):
    """Return one row per experiment/site/season; no outcome dates select splits.

    Calibration labels are ``calibration``; test inner_fold is -1. Warm-year
    calibration may contain the same sites in different, non-test years.
    Monthly normals enable the publication primary split and a separate
    unstratified sensitivity. Without normals, the legacy primary is explicitly
    unstratified and does not implement the publication primary design.
    """
    sites, observations = cohort['sites'].copy(), cohort['observations'].copy()
    if sites.site.duplicated().any():
        raise ValueError('Duplicate site identities')
    if not set(observations.site).issubset(set(sites.site)):
        raise ValueError('Observation site missing from sites')
    units = observations[['site','season']].drop_duplicates().sort_values(['site','season']).reset_index(drop=True)
    group_lookup = sites.set_index('site').group_id
    groups = sorted(sites.group_id.unique())
    n_test = max(1,int(np.ceil(.2 * len(groups))))
    rng = np.random.default_rng(20260909)
    primary = None
    for _ in range(1000):
        test = set(rng.permutation(groups)[:n_test])
        try:
            _folds(sites.loc[~sites.group_id.isin(test)], observations,20260909)
        except ValueError:
            continue
        primary = test
        break
    if primary is None:
        raise ValueError('Primary group split cannot support four-stage inner calibration')
    unstratified = primary
    zoning_metadata, normal_inputs = None, {}
    if monthly_normals is not None:
        sites, zoning_metadata, normal_inputs = _normal_zones(sites, monthly_normals, normal_metadata)
        primary = split_temperature_groups(sites, observations)
    elif normal_metadata is not None:
        raise ValueError('Normal metadata requires monthly_normals')
    spatial, spatial_map = _outer_spatial(sites, observations)
    spatial_lookup = spatial.set_index('site').group_id.map(spatial_map)
    definitions = [('site_holdout', units.site.map(group_lookup).isin(primary), sites, 20260909)]
    if monthly_normals is not None:
        definitions.append(('unstratified_site_holdout', units.site.map(group_lookup).isin(unstratified), sites, 20260909))
    definitions.extend((f'spatial_{f}', units.site.map(spatial_lookup).eq(f), spatial,20260804+f) for f in range(5))
    metadata = dict(primary_seed=20260909, primary_fraction=.2, spatial_seed=20260804,
        spatial_block_degrees=1, inner_folds=4, stage_coverage='all_four_stages_in_each_inner_fold',
        stratification='clustered_temperature_zones' if monthly_normals is not None else 'none',
        publication_primary_design=monthly_normals is not None,
        primary_design='temperature_zone_stratified' if monthly_normals is not None else 'legacy_unstratified',
        warm_protocols_available=climate is not None,
        primary_test_groups=sorted(primary), spatial_groups=spatial[['site','group_id']].to_dict('records'),
        spatial_fold_map={str(k):int(v) for k,v in spatial_map.items()})
    if zoning_metadata is not None:
        metadata.update(temperature_zones=zoning_metadata, normal_input_hashes=normal_inputs,
            site_temperature_zones=sites[['site','group_id','temperature_zone_id']].to_dict('records'),
            unstratified_test_groups=sorted(unstratified),
            primary_inner_stratification='temperature_zone',
            other_inner_stratification='none; preserve independent spatial groups and legacy sensitivity')
    if climate is not None:
        warm_years, warm_groups, climate_metadata = _climate_selection(sites, climate)
        if not set(units.season.astype(int)).issubset(set(range(1951,2026))):
            raise ValueError('Observation seasons extend beyond verified climate years')
        metadata.update(climate_metadata)
        definitions.extend([('warm_year',units.season.isin(warm_years),sites,20260909),
                            ('warm_site',units.site.map(group_lookup).isin(warm_groups),sites,20260909)])
    result = []
    for experiment, test_mask, grouping, seed in definitions:
        part = units.copy()
        part['experiment'] = experiment
        part['partition'] = np.where(test_mask,'test','calibration')
        if not test_mask.any() or test_mask.all():
            raise ValueError(f'{experiment} has an empty calibration or test partition')
        calibration_units = part.loc[~test_mask,['site','season']]
        train_obs = observations.merge(calibration_units,on=['site','season'],validate='many_to_one')
        train_sites = grouping.loc[grouping.site.isin(train_obs.site)]
        if experiment == 'site_holdout' and zoning_metadata is not None:
            folds = assign_temperature_folds(train_sites, train_obs, seed=seed)
        else:
            folds = _folds(train_sites,train_obs,seed)
        part['inner_fold'] = part.site.map(grouping.set_index('site').group_id).map(folds).fillna(-1).astype(int)
        part.loc[test_mask,'inner_fold'] = -1
        columns = ['experiment','site','season','partition','inner_fold']
        if zoning_metadata is not None:
            part['temperature_zone_id'] = part.site.map(sites.set_index('site').temperature_zone_id)
            columns.append('temperature_zone_id')
        result.append(part[columns])
    output = pd.concat(result,ignore_index=True)
    output.attrs['metadata'] = metadata
    return output


def save_protocol_metadata(protocols, path):
    Path(path).write_text(json.dumps(protocols.attrs.get('metadata',{}),indent=2,sort_keys=True)+'\n')
