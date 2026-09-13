#!/usr/bin/env python3
"""Build publication-site terrain from exact donors and official raster inputs.

Offline by default. --sample-missing reads small remote GLO-30 COG windows and
caches each coordinate independently for resumption. Existing weather, terrain
and observations are read only. No coordinates, elevations or missing pixels
are interpolated. Raster edge neighbourhoods are explicitly partial.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile

import h5py
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.base_table.build_site_era5_grid_crosswalk import grid_id, nearest_grid_center
from src.base_table.build_site_topography import terrain_metrics
from src.descriptive_phenology.download_copernicus_dem_site_tiles import tile_url

METRICS = ['dem_elevation_m', 'slope_deg', 'aspect_deg', 'northness', 'eastness',
           'dem_local_std_m', 'dem_local_median_m', 'dem_local_range_m',
           'dem_local_valid_pixels']
REQUIRED_METRICS = METRICS[:6]
LEGACY_ALGORITHM = 'publication_terrain_v1_3x3_gradient_11x11_std'
ALGORITHM = 'publication_terrain_v2_containing_pixel_3x3_gradient_11x11_std'
BOUNDARY_SCREEN_DEGREES = 1 / 1200
GRAVITY = 9.80665
METRIC_ABSOLUTE_TOLERANCE = 1e-10
GEO_HASH = '6fe9d064e7eae98bfe20348430bc4290bc94daa838b560c355999cd85cb1a559'
LSM_HASH = '9df65151d1608990851e2aa8d0e1e4ca063b5181b0568493c42676d2572b202c'


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_info(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha256_file(path)}


def finite_number(value):
    if pd.isna(value) or value == '':
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def validate_coordinates(frame, lat='lat', lon='lon'):
    result = frame.copy()
    for column, bound in [(lat, 90), (lon, 180)]:
        # Python conversion avoids pandas' non-round-trip CSV float parser.
        result[column] = result[column].map(float)
        if not (np.isfinite(result[column]) & result[column].between(-bound, bound)).all():
            raise ValueError(f'Invalid coordinates in {column}')
    return result


def build_site_index(observations, crosswalk):
    work = validate_coordinates(observations[['site', 'lat', 'lon']])
    if work.site.isna().any() or work.site.astype(str).eq('').any():
        raise ValueError('Empty site identifier')
    work = work.drop_duplicates()
    if work.site.duplicated().any():
        raise ValueError('A site has multiple coordinates; resolve identity before terrain sampling')
    weather = crosswalk[['site', 'filename', 'weather_uid']].copy()
    if weather.site.duplicated().any():
        raise ValueError('Duplicate weather crosswalk site')
    result = work.merge(weather, on='site', how='left', validate='one_to_one')
    for column in ['filename', 'weather_uid']:
        if result[column].isna().any() or result[column].astype(str).eq('').any():
            raise ValueError(f'Missing weather crosswalk {column}')
        if result[column].duplicated().any():
            raise ValueError(f'Colliding weather {column}')
    if any(Path(name).name != name or '/' in name or '\\' in name for name in result.filename):
        raise ValueError('Weather filename must be a basename')
    return result.sort_values('site').reset_index(drop=True)


def reuse_terrain(sites, sources):
    lookup = {}
    target_keys = set(zip(sites.lat, sites.lon))
    for table, provenance in sources:
        work = validate_coordinates(table, 'latitude', 'longitude')
        for row in work.to_dict('records'):
            key = (row['latitude'], row['longitude'])
            if key not in target_keys:
                continue
            values = {name: finite_number(row.get(name)) for name in METRICS}
            pixel_count = values['dem_local_valid_pixels']
            if pixel_count is not None and (pixel_count < 0 or not pixel_count.is_integer()):
                raise ValueError(f'Invalid terrain pixel count at {key}: {pixel_count}')
            if not any(value is not None for value in values.values()):
                continue
            identity = row.get('site_uid')
            if not identity:
                raise ValueError('Terrain donor lacks source-qualified site_uid')
            evidence = {**provenance, 'site_uid': str(identity)}
            for name in ['dem_tile_name', 'dem_sample_status', 'coordinate_instability_flag']:
                if name in row and pd.notna(row[name]):
                    evidence[name] = str(row[name])
            if key not in lookup:
                lookup[key] = ({}, [])
            merged, donors = lookup[key]
            for name, value in values.items():
                if value is None:
                    continue
                if name in merged and merged[name] != value:
                    tolerance = 0 if name == 'dem_local_valid_pixels' else METRIC_ABSOLUTE_TOLERANCE
                    if not math.isclose(merged[name], value, abs_tol=tolerance, rel_tol=0):
                        raise ValueError(f'Conflicting terrain donors at {key}: {name}: '
                                         f'{merged[name]} versus {value}')
                    evidence.setdefault('tolerated_metric_discrepancies', []).append({
                        'metric': name, 'retained_value': merged[name], 'donor_value': value,
                        'absolute_difference': abs(merged[name] - value), 'absolute_tolerance': tolerance,
                        'relative_tolerance': 0})
                # Preserve the first nonmissing donor value, including its precision.
                merged.setdefault(name, value)
            donors.append(evidence)
    result = sites.copy()
    for name in METRICS:
        result[name] = np.nan
    result['terrain_status'] = 'missing_dem'
    result['terrain_donors'] = '[]'
    result['terrain_sampling_provenance'] = ''
    for index, row in result.iterrows():
        match = lookup.get((row.lat, row.lon))
        if match is None:
            continue
        values, donors = match
        for name, value in values.items():
            result.at[index, name] = value
        complete = all(name in values for name in REQUIRED_METRICS)
        result.at[index, 'terrain_status'] = 'reused_exact_coordinates' if complete else 'reused_partial_terrain'
        result.at[index, 'terrain_donors'] = canonical_json(donors)
    return result


def _units(dataset):
    value = dataset.attrs.get('units', '')
    if isinstance(value, bytes):
        value = value.decode()
    return str(value).strip()


def screen_legacy_terrain(sites):
    """Quarantine entire legacy metric bundles when authoritative resampling is needed."""
    result = sites.copy()
    result['terrain_legacy_qa'] = ''
    result['terrain_requires_native_resample'] = False
    result['terrain_resample_reason'] = ''
    for index, row in result.iterrows():
        values = {name: finite_number(row[name]) for name in METRICS}
        if not any(value is not None for value in values.values()):
            continue
        # Conservative screening, not geometric tile selection. The live raster
        # bounds decide containment. Covers native half-pixel shifts in Europe.
        boundary = any(abs(value - round(value)) <= BOUNDARY_SCREEN_DEGREES
                       for value in (row.lat, row.lon))
        partial = any(values[name] is None for name in REQUIRED_METRICS)
        if not boundary and not partial:
            continue
        reason = 'potential_tile_boundary' if boundary else 'partial_legacy_terrain'
        result.at[index, 'terrain_legacy_qa'] = canonical_json({
            'metrics': values, 'donors': json.loads(row.terrain_donors), 'reason': reason})
        result.at[index, 'terrain_requires_native_resample'] = True
        result.at[index, 'terrain_resample_reason'] = reason
        result.loc[index, METRICS] = np.nan
        result.at[index, 'terrain_status'] = 'pending_native_resample'
    return result


def _sample_invariant(handle, variable, latitude, longitude):
    latitudes = handle['latitude'][:]
    longitudes = handle['longitude'][:]
    lat_index = int(np.abs(latitudes - latitude).argmin())
    distances = np.abs((longitudes - longitude + 180) % 360 - 180)
    lon_index = int(distances.argmin())
    if abs(float(latitudes[lat_index]) - latitude) > 1e-5 or distances[lon_index] > 1e-5:
        raise ValueError(f'Official grid center absent for {latitude}, {longitude}')
    dataset = handle[variable]
    if dataset.ndim < 2 or any(size != 1 for size in dataset.shape[:-2]):
        raise ValueError(f'Unexpected invariant dimensions for {variable}: {dataset.shape}')
    raw = float(dataset[(0,) * (dataset.ndim - 2) + (lat_index, lon_index)])
    for attr in ['_FillValue', 'missing_value']:
        if attr in dataset.attrs and np.any(raw == np.asarray(dataset.attrs[attr])):
            raise ValueError(f'Missing invariant {variable} at grid center')
    value = raw * float(dataset.attrs.get('scale_factor', 1)) + float(dataset.attrs.get('add_offset', 0))
    if not math.isfinite(value):
        raise ValueError(f'Nonfinite invariant {variable} at grid center')
    return value


def attach_invariants(sites, geopotential, land_sea_mask, native_grids=None):
    result = sites.copy()
    result['era5_grid_lat'] = result.lat.map(nearest_grid_center)
    result['era5_grid_lon'] = result.lon.map(nearest_grid_center)
    result['era5_grid_id'] = [grid_id(lat, lon) for lat, lon in zip(result.era5_grid_lat, result.era5_grid_lon)]
    result['era5_grid_boundary_ambiguity_flag'] = [
        any(math.isclose(value / .1 % 1, .5, abs_tol=1e-8, rel_tol=0) for value in pair)
        for pair in zip(result.lat, result.lon)]
    result['era5_grid_assignment_method'] = 'nearest_regular_0.1_degree_center_lower_coordinate_tie'
    result['legacy_era5_grid_id'] = result.era5_grid_id
    result['era5_grid_differs_from_legacy'] = False
    if native_grids is not None:
        native = validate_coordinates(native_grids)
        required = {'site', 'era5_grid_lat', 'era5_grid_lon', 'era5_grid_id'}
        if not required.issubset(native) or native.site.duplicated().any() or set(native.site) != set(result.site):
            raise ValueError('Authoritative native grid must match all sites exactly once')
        native = native.set_index('site').loc[result.site].reset_index()
        if not np.array_equal(native[['lat', 'lon']].to_numpy(), result[['lat', 'lon']].to_numpy()):
            raise ValueError('Authoritative native grid coordinates differ from site coordinates')
        for name in ['era5_grid_lat', 'era5_grid_lon']:
            native[name] = native[name].map(float)
            if not np.isfinite(native[name]).all() or not np.allclose(native[name], native[name].round(1), atol=1e-8, rtol=0):
                raise ValueError('Authoritative native grid centers must lie on the regular 0.1 degree grid')
        if ((native.era5_grid_lat - native.lat).abs() > .05 + 1e-8).any() or (
                np.abs((native.era5_grid_lon - native.lon + 180) % 360 - 180) > .05 + 1e-8).any():
            raise ValueError('Authoritative native grid centers do not contain site coordinates')
        ids = [grid_id(lat, lon) for lat, lon in zip(native.era5_grid_lat, native.era5_grid_lon)]
        if ids != native.era5_grid_id.tolist():
            raise ValueError('Authoritative native grid IDs disagree with centers')
        for name in ['era5_grid_lat', 'era5_grid_lon', 'era5_grid_id']:
            result[name] = native[name].to_numpy()
        result['era5_grid_differs_from_legacy'] = result.era5_grid_id != result.legacy_era5_grid_id
        result['era5_grid_assignment_method'] = 'authoritative_GEE_native_pixel_centers'
    with h5py.File(geopotential, 'r') as geo, h5py.File(land_sea_mask, 'r') as lsm:
        if _units(geo['z']).replace(' ', '') not in {'m**2s**-2', 'm2s-2', 'm^2s^-2', 'm2/s2', 'm^2/s^2'}:
            raise ValueError(f'Geopotential units must be m2 s-2, found {_units(geo["z"])}')
        if _units(lsm['lsm']) not in {'1', '(0 - 1)', '0-1', 'dimensionless'}:
            raise ValueError(f'Land-sea-mask units are not dimensionless: {_units(lsm["lsm"])}')
        sampled = {}
        for lat, lon in zip(result.era5_grid_lat, result.era5_grid_lon):
            if (lat, lon) not in sampled:
                z = _sample_invariant(geo, 'z', lat, lon)
                fraction = _sample_invariant(lsm, 'lsm', lat, lon)
                if not 0 <= fraction <= 1:
                    raise ValueError('Land-sea mask outside [0, 1]')
                sampled[(lat, lon)] = (z, fraction)
    result['era5_grid_geopotential_m2_s2'] = [sampled[key][0] for key in zip(result.era5_grid_lat, result.era5_grid_lon)]
    result['era5_grid_elevation_m'] = result.era5_grid_geopotential_m2_s2 / GRAVITY
    result['era5_grid_land_fraction'] = [sampled[key][1] for key in zip(result.era5_grid_lat, result.era5_grid_lon)]
    return result


class OutsideTileError(ValueError):
    def __init__(self, source, bounds):
        super().__init__(f'Site lies outside the selected native DEM tile: {source}')
        self.bounds = bounds


def sample_dem_window(source, latitude, longitude):
    """Read actual native pixels only; keep border/nodata neighbours missing."""
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_MAX_RETRY=2,
                      GDAL_HTTP_TIMEOUT=45, CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif'):
        with rasterio.open(source) as src:
            if src.crs != rasterio.crs.CRS.from_epsg(4326) or src.transform.b != 0 or src.transform.d != 0:
                raise ValueError('DEM requires an unrotated EPSG:4326 native grid')
            raster_row, raster_col = src.index(longitude, latitude)
            if not (0 <= raster_row < src.height and 0 <= raster_col < src.width):
                raise OutsideTileError(source, src.bounds)
            row_start, col_start = max(raster_row - 5, 0), max(raster_col - 5, 0)
            row_stop, col_stop = min(raster_row + 6, src.height), min(raster_col + 6, src.width)
            window = Window(col_start, row_start, col_stop - col_start, row_stop - row_start)
            raw = src.read(1, window=window)
            valid_mask = src.read_masks(1, window=window)
            raw_bytes = raw.tobytes(order='C')
            mask_bytes = valid_mask.tobytes(order='C')
            provenance = {
                'source': str(source), 'algorithm': ALGORITHM, 'latitude': latitude, 'longitude': longitude,
                'window': [int(window.col_off), int(window.row_off), int(window.width), int(window.height)],
                'requested_window': [raster_col - 5, raster_row - 5, 11, 11],
                'transform': list(src.window_transform(window))[:6], 'crs': str(src.crs),
                'nodata': finite_number(src.nodata), 'raw_dtype': raw.dtype.str, 'raw_shape': list(raw.shape),
                'raw_pixels_base64': base64.b64encode(raw_bytes).decode(),
                'valid_mask_base64': base64.b64encode(mask_bytes).decode(),
                'pixel_sha256': hashlib.sha256(raw_bytes).hexdigest(),
                'valid_mask_sha256': hashlib.sha256(mask_bytes).hexdigest(),
                'boundary_truncated': raw.shape != (11, 11),
                'boundary_coordinate_clamped': False,
                'tile_bounds': list(src.bounds), 'raster_shape': [src.height, src.width],
                'limitations': 'Single-tile native pixels; no edge stitching, interpolation or gap filling. '
                               'Derivatives require complete 3x3 support; variability uses valid 11x11 pixels. '
                               'Flat-pixel aspect follows the historical gradient convention.',
            }
            values = raw.astype('float64')
            invalid = (valid_mask == 0) | ~np.isfinite(values) | (values < -500) | (values > 9000)
            if src.nodata is not None:
                invalid |= values == src.nodata
            values[invalid] = np.nan
            local = np.full((11, 11), np.nan)
            row_offset, col_offset = row_start - (raster_row - 5), col_start - (raster_col - 5)
            local[row_offset:row_offset + raw.shape[0], col_offset:col_offset + raw.shape[1]] = values
            elevation, slope, aspect = terrain_metrics(local[4:7, 4:7], src.transform, latitude)
    finite = local[np.isfinite(local)]
    result = {
        'dem_elevation_m': finite_number(elevation), 'slope_deg': finite_number(slope),
        'aspect_deg': finite_number(aspect), 'northness': finite_number(np.cos(np.deg2rad(aspect))),
        'eastness': finite_number(np.sin(np.deg2rad(aspect))),
        'dem_local_std_m': float(np.std(finite)) if finite.size else None,
        'dem_local_median_m': float(np.median(finite)) if finite.size else None,
        'dem_local_range_m': float(np.ptp(finite)) if finite.size else None,
        'dem_local_valid_pixels': int(finite.size), 'sampling_provenance': provenance,
    }
    result['terrain_status'] = ('sampled' if all(result[name] is not None for name in REQUIRED_METRICS)
                                else 'sampled_partial_terrain' if result['dem_elevation_m'] is not None
                                else 'invalid_dem_value')
    return result


def sample_containing_dem(source, latitude, longitude):
    """Select adjacent tiles from actual bounds; never clamp to a wrong pixel."""
    try:
        result = sample_dem_window(source, latitude, longitude)
        attempts = []
    except OutsideTileError as error:
        left, bottom, right, top = error.bounds
        lat_step = -1 if latitude <= bottom else 1 if latitude > top else 0
        lon_step = -1 if longitude < left else 1 if longitude >= right else 0
        if not lat_step and not lon_step:
            raise
        selected = tile_url(math.floor(latitude) + lat_step, math.floor(longitude) + lon_step)
        attempts = [{'source': str(source), 'bounds': list(error.bounds), 'status': 'point_outside'}]
        result = sample_dem_window(selected, latitude, longitude)
    result['sampling_provenance']['tile_selection'] = {
        'requested_source': str(source), 'selected_source': result['sampling_provenance']['source'],
        'rejected_tiles': attempts, 'method': 'actual_native_raster_bounds_and_containing_pixel'}
    return result


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, suffix='.tmp', delete=False) as handle:
        handle.write(canonical_json(value) + '\n')
        temporary = Path(handle.name)
    temporary.replace(path)


def sample_cache_location(source, latitude, longitude, cache, algorithm=ALGORITHM):
    request = {'source': str(source), 'latitude': float(latitude), 'longitude': float(longitude), 'algorithm': algorithm}
    key = hashlib.sha256(canonical_json(request).encode()).hexdigest()
    return request, Path(cache) / f'{key}.json'


def read_validated_cache(path, request):
    saved = json.loads(path.read_text())
    if saved.get('request') != request or saved.get('result_sha256') != hashlib.sha256(canonical_json(saved['result']).encode()).hexdigest():
        raise ValueError(f'Corrupt or incompatible terrain cache: {path}')
    result = saved['result']
    provenance = result['sampling_provenance']
    for content, hash_name in [('raw_pixels_base64', 'pixel_sha256'), ('valid_mask_base64', 'valid_mask_sha256')]:
        if hashlib.sha256(base64.b64decode(provenance[content])).hexdigest() != provenance[hash_name]:
            raise ValueError(f'Corrupt pixel cache: {path}')
    if provenance['latitude'] != request['latitude'] or provenance['longitude'] != request['longitude']:
        raise ValueError(f'Wrong coordinates in pixel cache: {path}')
    return result


def cached_pixel_contains_site(result, latitude, longitude):
    provenance = result['sampling_provenance']
    if provenance.get('boundary_coordinate_clamped'):
        return False
    transform = rasterio.Affine(*provenance['transform'])
    col, row = (~transform) @ (longitude, latitude)
    col, row = math.floor(col), math.floor(row)
    height, width = provenance['raw_shape']
    expected_col = provenance['requested_window'][0] + 5 - provenance['window'][0]
    expected_row = provenance['requested_window'][1] + 5 - provenance['window'][1]
    return 0 <= col < width and 0 <= row < height and col == expected_col and row == expected_row


def cached_sample(source, latitude, longitude, cache, allow_remote=True, reuse_cache=None):
    request, path = sample_cache_location(source, latitude, longitude, cache)
    if path.exists():
        return read_validated_cache(path, request)
    if reuse_cache is not None:
        for algorithm in (ALGORITHM, LEGACY_ALGORITHM):
            old_request, old_path = sample_cache_location(source, latitude, longitude, reuse_cache, algorithm)
            if not old_path.exists():
                continue
            result = read_validated_cache(old_path, old_request)
            if not cached_pixel_contains_site(result, latitude, longitude):
                continue
            result['sampling_provenance']['cache_reuse'] = {
                'source_file': str(old_path.resolve()), 'source_file_sha256': sha256_file(old_path),
                'original_algorithm': algorithm, 'validation': 'request_result_pixel_mask_hashes_and_containing_pixel'}
            atomic_json(path, {'request': request, 'result': result,
                              'result_sha256': hashlib.sha256(canonical_json(result).encode()).hexdigest()})
            return result
    if not allow_remote:
        return None
    result = sample_containing_dem(str(source), float(latitude), float(longitude))
    atomic_json(path, {'request': request, 'result': result,
                      'result_sha256': hashlib.sha256(canonical_json(result).encode()).hexdigest()})
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations', type=Path, default=ROOT / 'data/phenology/derived/paper_targets/observations.csv')
    parser.add_argument('--crosswalk', type=Path, default=ROOT / 'data/weather/sites/metadata/paper_site_weather_crosswalk_20260908.csv')
    parser.add_argument('--terrain-sources', type=Path, nargs='+', default=[
        ROOT / 'data/phenology/derived/descriptive_phenology/site_topography.csv',
        ROOT / 'data/topography/processed/site_era5_land_grid_crosswalk.csv'])
    parser.add_argument('--geopotential', type=Path, default=ROOT / 'data/topography/raw/era5_land_invariant/geopotential_0p1deg.nc')
    parser.add_argument('--land-sea-mask', type=Path, default=ROOT / 'data/topography/raw/era5_land_invariant/land_sea_mask_0p1deg.nc')
    parser.add_argument('--geopotential-sha256', default=GEO_HASH)
    parser.add_argument('--land-sea-mask-sha256', default=LSM_HASH)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--native-grids', type=Path,
                        help='Authoritative site_native_grid.csv with exact site coordinates and sampled GEE centers')
    parser.add_argument('--reuse-pixel-cache', type=Path,
                        help='Read-only cache directory from a prior run; import only verified containing pixels')
    parser.add_argument('--sample-missing', action='store_true', help='Enable remote native GLO-30 COG window reads')
    parser.add_argument('--sample-limit', type=int, default=0, help='Maximum uncached coordinate reads this invocation; 0 means all; cached results always reused')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.sample_limit < 0:
        raise ValueError('--sample-limit cannot be negative')
    for path, expected in [(args.geopotential, args.geopotential_sha256), (args.land_sea_mask, args.land_sea_mask_sha256)]:
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f'Invariant SHA-256 mismatch: {path}: {actual} != {expected}')
    sources = [source_info(path) for path in args.terrain_sources]
    inputs = {'algorithm': ALGORITHM,
              'terrain_metric_absolute_tolerance': METRIC_ABSOLUTE_TOLERANCE,
              'terrain_metric_relative_tolerance': 0, 'pixel_counts_require_exact_equality': True,
              'legacy_boundary_screen_degrees': BOUNDARY_SCREEN_DEGREES,
              'native_grids': source_info(args.native_grids) if args.native_grids else None,
              'observations': source_info(args.observations),
              'weather_crosswalk': source_info(args.crosswalk), 'terrain_sources': sources,
              'geopotential': source_info(args.geopotential), 'land_sea_mask': source_info(args.land_sea_mask),
              'implementation': [source_info(Path(__file__)),
                                 source_info(ROOT / 'src/base_table/build_site_topography.py'),
                                 source_info(ROOT / 'src/base_table/build_site_era5_grid_crosswalk.py'),
                                 source_info(ROOT / 'src/descriptive_phenology/download_copernicus_dem_site_tiles.py')]}
    if args.reuse_pixel_cache is not None:
        if not args.reuse_pixel_cache.is_dir():
            raise ValueError('Reuse pixel cache directory is missing')
        inputs['reuse_pixel_cache'] = {
            'path': str(args.reuse_pixel_cache.resolve()),
            'files': [source_info(path) for path in sorted(args.reuse_pixel_cache.glob('*.json'))]}
    record_path = args.output_dir / 'inputs.json'
    if record_path.exists():
        if json.loads(record_path.read_text()) != inputs:
            raise ValueError('Output directory inputs or implementation differ; select a new output directory')
    elif args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise ValueError('Output directory contains unrecognized files; select a new output directory')
    observations = pd.read_csv(args.observations, dtype=str, keep_default_na=False)
    weather = pd.read_csv(args.crosswalk, dtype=str, keep_default_na=False)
    sites = build_site_index(observations, weather)
    donors = [(pd.read_csv(path, dtype=str, keep_default_na=False), info)
              for path, info in zip(args.terrain_sources, sources)]
    result = reuse_terrain(sites, donors)
    result = screen_legacy_terrain(result)
    native = pd.read_csv(args.native_grids, dtype=str, keep_default_na=False) if args.native_grids else None
    result = attach_invariants(result, args.geopotential, args.land_sea_mask, native_grids=native)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(record_path, inputs)
    errors = []
    missing = result[REQUIRED_METRICS].isna().any(axis=1)
    groups = result.loc[missing].groupby(['lat', 'lon'], sort=True)
    remote_attempts = 0
    for number, ((latitude, longitude), group) in enumerate(groups, start=1):
        url = tile_url(math.floor(latitude), math.floor(longitude))
        cache = args.output_dir / 'pixel_cache'
        _, cache_path = sample_cache_location(url, latitude, longitude, cache)
        allow_remote = args.sample_missing and (not args.sample_limit or remote_attempts < args.sample_limit)
        try:
            # Import validated old pixels before counting new remote work.
            sampled = cached_sample(url, latitude, longitude, cache, allow_remote=False,
                                    reuse_cache=args.reuse_pixel_cache)
            if sampled is None and allow_remote:
                remote_attempts += 1
                sampled = cached_sample(url, latitude, longitude, cache, allow_remote=True)
        except rasterio.errors.RasterioIOError as error:
            # Remote failures are retryable on the next invocation, not cached as successes.
            errors.append({'latitude': latitude, 'longitude': longitude, 'url': url, 'error': str(error)})
            result.loc[group.index, 'terrain_status'] = 'remote_read_failed'
        else:
            if sampled is None:
                continue
            for index in group.index:
                sampling_provenance = dict(sampled['sampling_provenance'])
                for name in METRICS:
                    prior = finite_number(result.at[index, name])
                    incoming = sampled[name]
                    if prior is not None and incoming is not None and prior != incoming:
                        tolerance = 0 if name == 'dem_local_valid_pixels' else METRIC_ABSOLUTE_TOLERANCE
                        if not math.isclose(prior, incoming, abs_tol=tolerance, rel_tol=0):
                            raise ValueError(f'Conflicting terrain donor and sampled pixel at {latitude}, {longitude}: {name}')
                        sampling_provenance.setdefault('tolerated_metric_discrepancies', []).append({
                            'metric': name, 'retained_value': prior, 'sampled_value': incoming,
                            'absolute_difference': abs(prior - incoming), 'absolute_tolerance': tolerance,
                            'relative_tolerance': 0})
                    if prior is None and incoming is not None:
                        result.at[index, name] = incoming
                result.at[index, 'terrain_status'] = sampled['terrain_status']
                result.at[index, 'terrain_sampling_provenance'] = canonical_json(sampling_provenance)
        if number % 25 == 0 or number == len(groups):
            print(f'Terrain coordinate groups: {number}/{len(groups)}; remote attempts: {remote_attempts}; failures: {len(errors)}', flush=True)
    result['site_minus_grid_elevation_m'] = result.dem_elevation_m - result.era5_grid_elevation_m
    result['terrain_complete'] = result[REQUIRED_METRICS].notna().all(axis=1)
    result['geopotential_source_sha256'] = inputs['geopotential']['sha256']
    result['land_sea_mask_source_sha256'] = inputs['land_sea_mask']['sha256']
    front = ['site', 'filename', 'weather_uid', 'lat', 'lon', 'era5_grid_id',
             'era5_grid_elevation_m', *REQUIRED_METRICS]
    result = result[front + [column for column in result if column not in front]]
    manifest = args.output_dir / 'terrain_manifest.csv'
    with tempfile.NamedTemporaryFile('w', dir=args.output_dir, suffix='.tmp', delete=False) as handle:
        result.to_csv(handle, index=False)
        temporary = Path(handle.name)
    temporary.replace(manifest)
    summary = {'inputs': inputs, 'site_count': len(result),
               'coordinate_count': len(result[['lat', 'lon']].drop_duplicates()),
               'complete_terrain_count': int(result.terrain_complete.sum()),
               'grid_elevation_count': int(result.era5_grid_elevation_m.notna().sum()),
               'native_grid_override_count': int(result.era5_grid_differs_from_legacy.sum()),
               'legacy_native_resample_count': int(result.terrain_requires_native_resample.sum()),
               'terrain_status_counts': {key: int(value) for key, value in result.terrain_status.value_counts().items()},
               'manifest_sha256': sha256_file(manifest), 'remote_errors': errors,
               'standard_gravity_m_s2': GRAVITY, 'sample_missing': args.sample_missing,
               'terrain_metric_absolute_tolerance': METRIC_ABSOLUTE_TOLERANCE,
               'terrain_metric_relative_tolerance': 0, 'pixel_counts_require_exact_equality': True,
               'sample_limit': args.sample_limit,
               'limitations': ['Source-qualified sites are not proven independent physical locations.',
                               'Exact-coordinate historical terrain reuse retains original extraction provenance.',
                               'Remote GLO-30 windows preserve actual pixel bytes and masks; no entire-tile checksum is claimed.',
                               'Single-tile edges or nodata can leave incomplete 3x3 derivatives or fewer than 121 variability pixels.',
                               'Local variability is population standard deviation (ddof=0) of finite native pixels.',
                               'Grid elevation uses official ERA5-Land geopotential / 9.80665; GLO-30 grid means are not substituted.']}
    atomic_json(args.output_dir / 'provenance.json', summary)
    print(f'Sites: {len(result)}; complete terrain: {summary["complete_terrain_count"]}; manifest: {manifest}', flush=True)
    return 0 if result.terrain_complete.all() else 2


if __name__ == '__main__':
    raise SystemExit(main())
