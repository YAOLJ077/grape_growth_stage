"""Immutable observation-level cohort and conservative independence groups."""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

CANONICAL = ['site', 'variety', 'country', 'lat', 'lon', 'Date', 'BBCH']


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def assign_groups(sites, *, spatial=False):
    """Transitive union of grid, coordinates, rounded coordinates and optional 1° blocks.

    Rounded coordinates establish conservative independence only. They never
    authorize meteorological reuse or a coordinate match for eligibility.
    """
    result = sites.sort_values('site').reset_index(drop=True).copy()
    if result.site.duplicated().any():
        raise ValueError('Duplicate site identities')
    parents = list(range(len(result)))

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    seen = {}
    for i, row in enumerate(result.itertuples()):
        keys = [('grid', str(row.era5_grid_id)), ('exact', float(row.lat), float(row.lon)),
                ('rounded', round(float(row.lat), 4), round(float(row.lon), 4))]
        if hasattr(row, 'group_id'):
            keys.append(('existing', row.group_id))
        if spatial:
            keys.append(('block', int(np.floor(float(row.lat))), int(np.floor(float(row.lon)))))
        for key in keys:
            if key in seen:
                parents[find(i)] = find(seen[key])
            else:
                seen[key] = i
    members = {}
    for i in range(len(result)):
        members.setdefault(find(i), []).append(str(result.site.iloc[i]))
    names = {root: 'group_' + hashlib.sha256('\n'.join(sorted(s)).encode()).hexdigest()[:16]
             for root, s in members.items()}
    result['group_id'] = [names[find(i)] for i in range(len(result))]
    return result


def _coordinate_float(value):
    """One exact Python conversion on both input sides; invalid values are audited."""
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return float('nan')


def prepare_cohort(observations_path, weather_dir, terrain_path):
    """Keep complete site-seasons over prior June 4–current December 31.

    No observations are aggregated and no missing temperatures are repaired.
    Terrain derivatives can remain missing; both elevations must be finite.
    """
    observations_path, terrain_path, weather_dir = map(Path, (observations_path, terrain_path, weather_dir))
    obs = pd.read_csv(observations_path, dtype=str, keep_default_na=False)
    if list(obs.columns) != CANONICAL:
        raise ValueError('Require exact canonical seven-column observations')
    obs['observation_id'] = [hashlib.sha256(json.dumps(list(row), ensure_ascii=False,
         separators=(',', ':')).encode()).hexdigest() for row in obs.itertuples(index=False, name=None)]
    if obs.observation_id.duplicated().any():
        raise ValueError('Exact duplicate canonical observations')
    obs['Date'] = pd.to_datetime(obs.Date, errors='raise')
    obs['season'] = obs.Date.dt.year.astype(int)
    obs['BBCH'] = obs.BBCH.str.zfill(2)
    if not set(obs.BBCH).issubset({'07', '65', '81', '89'}):
        raise ValueError('Non-target BBCH in cohort input')
    terrain = pd.read_csv(terrain_path, dtype={'site': str, 'weather_uid': str, 'filename': str,
        'era5_grid_id': str, 'lat': str, 'lon': str})
    for column in ['lat', 'lon']:
        terrain[column + '_source'] = terrain[column].copy()
        terrain[column] = terrain[column].map(_coordinate_float)
    if terrain.site.duplicated().any():
        raise ValueError('Duplicate terrain site')
    terrain = terrain.set_index('site', drop=False)
    hashes = {str(observations_path.resolve()): file_hash(observations_path),
              str(terrain_path.resolve()): file_hash(terrain_path)}
    audits, retained_sites, weather_parts = [], [], []
    for site, records in obs.groupby('site', sort=True):
        reason, w, row = '', None, None
        if site not in terrain.index:
            reason = 'missing_terrain'
        else:
            row = terrain.loc[site]
            coords = records[['lat', 'lon']].apply(lambda column: column.map(_coordinate_float)).to_numpy()
            target = row[['lat', 'lon']].to_numpy(float)
            elev = row[['dem_elevation_m', 'era5_grid_elevation_m', 'site_minus_grid_elevation_m']].to_numpy(float)
            if not np.isfinite(coords).all() or not np.isfinite(target).all() or not (coords == target).all():
                reason = 'coordinate_mismatch'
            elif not np.isfinite(elev).all():
                reason = 'nonfinite_elevation'
            elif not np.isclose(elev[0] - elev[1], elev[2], rtol=0, atol=1e-6):
                reason = 'elevation_difference_mismatch'
            elif pd.isna(row.era5_grid_id) or not str(row.era5_grid_id):
                reason = 'missing_grid_identity'
            else:
                path = weather_dir / str(row.filename)
                if not path.is_file():
                    reason = 'missing_weather_file'
                else:
                    hashes[str(path.resolve())] = file_hash(path)
                    w = pd.read_csv(path)
                    if not {'Date', 'Tmean', 'Tmean_DEM'}.issubset(w.columns):
                        reason = 'missing_weather_columns'
                    else:
                        w = w[['Date', 'Tmean', 'Tmean_DEM']].copy()
                        w['Date'] = pd.to_datetime(w.Date, errors='coerce')
                        for col in ['Tmean', 'Tmean_DEM']:
                            w[col] = pd.to_numeric(w[col], errors='coerce')
                        if w.Date.isna().any() or w.Date.duplicated().any():
                            reason = 'invalid_or_duplicate_weather_dates'
                        else:
                            finite = np.isfinite(w[['Tmean', 'Tmean_DEM']]).all(axis=1)
                            if not np.allclose(w.loc[finite, 'Tmean_DEM'], w.loc[finite, 'Tmean'] - .0065 * elev[2], rtol=0, atol=1e-6):
                                reason = 'dem_equation_mismatch'
                            w = w.set_index('Date').sort_index()
        eligible_years = []
        for season, events in records.groupby('season', sort=True):
            start, end = pd.Timestamp(int(season)-1, 6, 4), pd.Timestamp(int(season), 12, 31)
            wanted = pd.date_range(start, end)
            season_reason, missing = reason, len(wanted)
            if not reason:
                values = w.reindex(wanted)[['Tmean', 'Tmean_DEM']]
                missing = int((~np.isfinite(values).all(axis=1)).sum())
                if missing:
                    season_reason = 'incomplete_weather_window'
            good = not season_reason
            audits.append(dict(site=site, season=int(season), eligible=good, reason=season_reason or 'eligible',
                               n_observations=len(events), window_start=start, window_end=end,
                               expected_days=len(wanted), missing_days=missing))
            if good:
                eligible_years.append(int(season))
        if eligible_years:
            site_row = row.to_dict()
            countries = records.country.unique()
            if len(countries) != 1:
                raise ValueError(f'Conflicting countries for {site}')
            site_row['country'] = countries[0]
            retained_sites.append(site_row)
            # Full actual history spanning the eligible windows supports predicted-date features.
            start = pd.Timestamp(min(eligible_years)-1, 6, 4)
            end = pd.Timestamp(max(eligible_years), 12, 31)
            weather_parts.append(w.loc[start:end].reset_index().assign(site=site)[['site','Date','Tmean','Tmean_DEM']])
    eligibility = pd.DataFrame(audits)
    selected = eligibility.loc[eligibility.eligible, ['site', 'season']]
    observations = obs.merge(selected, on=['site', 'season'], how='inner', validate='many_to_one')
    sites = pd.DataFrame(retained_sites, columns=[*terrain.columns, *([] if 'country' in terrain.columns else ['country'])])
    sites = assign_groups(sites)
    observations = observations.merge(sites[['site', 'group_id']], on='site', how='left', validate='many_to_one')
    weather = pd.concat(weather_parts, ignore_index=True) if weather_parts else pd.DataFrame(columns=['site','Date','Tmean','Tmean_DEM'])
    metadata = dict(schema_version=1, input_hashes=hashes, window='prior-June-04/current-December-31',
                    lapse_rate_c_per_m=.0065, grouping='transitive_grid_exact_coordinates_rounded_4_decimals',
                    coordinate_match='exact equality after Python float conversion of both source strings',
                    coordinate_source_fields=['observations.lat','observations.lon','sites.lat_source','sites.lon_source'],
                    n_input_observations=len(obs), n_observations=len(observations), n_sites=len(sites),
                    n_groups=sites.group_id.nunique(), excluded_site_seasons=int((~eligibility.eligible).sum()))
    return dict(observations=observations, sites=sites, weather=weather, eligibility=eligibility, metadata=metadata)


def save_cohort(cohort, directory):
    """Write once, with both original-input and frozen-artifact SHA-256 hashes."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = dict(metadata=cohort['metadata'], files={}, dtypes={})
    for name in ['observations', 'sites', 'weather', 'eligibility']:
        frame = cohort[name]
        filename = name + ('.csv.gz' if name == 'weather' else '.csv')
        frame.to_csv(directory / filename, index=False)
        manifest['files'][filename] = file_hash(directory / filename)
        manifest['dtypes'][name] = {c: str(t) for c, t in frame.dtypes.items()}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')


def load_cohort(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    result = dict(metadata=manifest['metadata'])
    for filename, expected in manifest['files'].items():
        path = directory / filename
        if file_hash(path) != expected:
            raise ValueError(f'Frozen cohort hash mismatch: {filename}')
        name = filename.split('.')[0]
        types = manifest['dtypes'][name]
        dates = [c for c, t in types.items() if t.startswith('datetime')]
        # Preserve exact empty cultivar strings and leading zero stage codes.
        frame = pd.read_csv(path, dtype={c: str for c,t in types.items() if t in ('object', 'str', 'string')},
                            keep_default_na=False, float_precision='round_trip')
        for col, dtype in types.items():
            if col in dates:
                frame[col] = pd.to_datetime(frame[col])
            elif dtype not in ('object', 'str', 'string'):
                if dtype == 'bool':
                    frame[col] = frame[col].astype(str).map({'True': True, 'False': False}).astype(bool)
                else:
                    frame[col] = pd.to_numeric(frame[col], errors='coerce').astype(dtype)
        result[name] = frame
    return result
