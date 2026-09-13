"""Terrain identity, provenance and sampling regression tests (synthetic inputs)."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

import h5py
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODULE = ROOT / 'src/weather_processing/prepare_publication_terrain.py'


def terrain_module():
    assert MODULE.exists(), 'Publication terrain preparation has not been implemented'
    spec = importlib.util.spec_from_file_location('publication_terrain', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sites():
    return pd.DataFrame({'site': ['FR:tempo:0001', 'DE:dwd:0002'],
                         'lat': ['45.0', '45.000000001'], 'lon': ['7', '7']})


def crosswalk():
    return pd.DataFrame({'site': ['FR:tempo:0001', 'DE:dwd:0002'],
                         'weather_uid': ['France|tempo|0001', 'Germany|dwd|0002'],
                         'filename': ['0001.csv', '0002.csv']})


def donor(elevation='0'):
    return pd.DataFrame({'site_uid': ['France|tempo|0001'], 'latitude': ['45'],
                         'longitude': ['7.000'], 'dem_elevation_m': [elevation],
                         'slope_deg': ['0'], 'aspect_deg': ['0'], 'northness': ['1'],
                         'eastness': ['0'], 'dem_local_std_m': ['0']})


def invariant(path, variable, values, units, lat=(45, 45.1), lon=(7, 7.1)):
    with h5py.File(path, 'w') as f:
        f['latitude'] = lat
        f['longitude'] = lon
        z = f.create_dataset(variable, data=np.asarray(values, dtype=float)[None])
        z.attrs['units'] = units
    return path


def raster(path, values=None, nodata=-9999):
    values = np.zeros((21, 21), dtype=np.float32) if values is None else values
    with rasterio.open(path, 'w', driver='GTiff', width=values.shape[1],
                       height=values.shape[0], count=1, dtype=values.dtype,
                       crs='EPSG:4326', transform=from_origin(7, 46, 0.001, 0.001),
                       nodata=nodata) as dst:
        dst.write(values, 1)
    return path


def test_identity_and_only_exact_numeric_coordinate_reuse():
    m = terrain_module()
    obs = pd.concat([sites(), sites().iloc[[0]]], ignore_index=True)
    index = m.build_site_index(obs, crosswalk())
    result = m.reuse_terrain(index, [(donor(), {'path': 'donor.csv', 'sha256': 'a' * 64})])
    assert list(result.site) == ['DE:dwd:0002', 'FR:tempo:0001']
    french = result.set_index('site').loc['FR:tempo:0001']
    assert french.filename == '0001.csv'
    assert french.weather_uid == 'France|tempo|0001'
    assert french.dem_elevation_m == 0
    assert french.terrain_status == 'reused_exact_coordinates'
    assert json.loads(french.terrain_donors)[0]['site_uid'] == 'France|tempo|0001'
    assert np.isnan(result.set_index('site').loc['DE:dwd:0002'].dem_elevation_m)


def test_changing_coordinates_within_site_is_rejected():
    m = terrain_module()
    obs = pd.concat([sites(), sites().iloc[[0]].assign(lat='45.001')])
    with pytest.raises(ValueError, match='multiple coordinates'):
        m.build_site_index(obs, crosswalk())


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'collision'])
def test_weather_identity_requires_unique_complete_match(change):
    m = terrain_module()
    weather = crosswalk()
    if change == 'missing':
        weather = weather.iloc[[0]]
    elif change == 'duplicate':
        weather = pd.concat([weather, weather.iloc[[0]]])
    else:
        weather.loc[1, 'filename'] = '0001.csv'
    with pytest.raises(ValueError):
        m.build_site_index(sites(), weather)


@pytest.mark.parametrize('latitude', ['NaN', '91', '-inf', 'bad'])
def test_invalid_coordinates_are_rejected(latitude):
    m = terrain_module()
    obs = sites()
    obs.loc[0, 'lat'] = latitude
    with pytest.raises(ValueError):
        m.build_site_index(obs, crosswalk())


def test_disagreeing_exact_coordinate_donors_are_rejected():
    m = terrain_module()
    with pytest.raises(ValueError, match='Conflicting terrain donors'):
        m.reuse_terrain(m.build_site_index(sites(), crosswalk()), [
            (donor('0'), {'path': 'a', 'sha256': '1'}),
            (donor('1'), {'path': 'b', 'sha256': '2'})])


def test_official_geopotential_conversion_and_lower_ties(tmp_path):
    m = terrain_module()
    geo = invariant(tmp_path / 'geo.nc', 'z', [[0, 98.0665], [196.133, 294.1995]], 'm**2 s**-2')
    lsm = invariant(tmp_path / 'lsm.nc', 'lsm', [[1, 0.5], [0, 1]], '(0 - 1)')
    frame = pd.DataFrame({'lat': [45.05, 45.051], 'lon': [7.05, 7.051]})
    got = m.attach_invariants(frame, geo, lsm)
    assert list(got.era5_grid_id) == ['ERA5L_0.1_lat+45.0_lon+7.0', 'ERA5L_0.1_lat+45.1_lon+7.1']
    np.testing.assert_allclose(got.era5_grid_elevation_m, [0, 30])
    assert list(got.era5_grid_land_fraction) == [1, 1]
    assert got.era5_grid_boundary_ambiguity_flag.iloc[0]


def test_invariant_rejects_wrong_units_and_off_grid_centres(tmp_path):
    m = terrain_module()
    lsm = invariant(tmp_path / 'lsm.nc', 'lsm', [[1, 1], [1, 1]], '1')
    geo = invariant(tmp_path / 'geo.nc', 'z', [[0, 1], [2, 3]], 'm')
    with pytest.raises(ValueError, match='units'):
        m.attach_invariants(pd.DataFrame({'lat': [45], 'lon': [7]}), geo, lsm)
    geo = invariant(tmp_path / 'geo.nc', 'z', [[0, 1], [2, 3]], 'm**2 s**-2')
    with pytest.raises(ValueError, match='center'):
        m.attach_invariants(pd.DataFrame({'lat': [47], 'lon': [7]}), geo, lsm)


def test_raster_retains_zero_and_raw_pixel_hash(tmp_path):
    m = terrain_module()
    path = raster(tmp_path / 'flat.tif')
    got = m.sample_dem_window(str(path), 45.9895, 7.0105)
    assert got['dem_elevation_m'] == 0
    assert got['slope_deg'] == 0
    assert got['dem_local_std_m'] == 0
    assert got['dem_local_valid_pixels'] == 121
    assert got['terrain_status'] == 'sampled'
    provenance = got['sampling_provenance']
    assert provenance['source'] == str(path)
    assert provenance['window'] == [5, 5, 11, 11]
    assert len(provenance['pixel_sha256']) == 64
    assert provenance['pixel_sha256'] != hashlib.sha256(b'').hexdigest()


def test_raster_nodata_and_boundary_do_not_invent_neighbours(tmp_path):
    m = terrain_module()
    values = np.zeros((21, 21), dtype=np.float32)
    values[10, 9] = -9999
    path = raster(tmp_path / 'masked.tif', values)
    got = m.sample_dem_window(str(path), 45.9895, 7.0105)
    assert got['dem_elevation_m'] == 0
    assert got['slope_deg'] is None
    assert got['dem_local_valid_pixels'] == 120
    edge = m.sample_dem_window(str(path), 45.9995, 7.0005)
    assert edge['sampling_provenance']['boundary_truncated']
    assert edge['dem_local_valid_pixels'] == 36
    assert edge['slope_deg'] is None
    with pytest.raises(ValueError, match='outside'):
        m.sample_dem_window(str(path), 44, 6)


def test_raster_derivatives_use_real_pixel_spacing(tmp_path):
    m = terrain_module()
    values = np.tile(np.arange(21, dtype=np.float32), (21, 1))
    got = m.sample_dem_window(str(raster(tmp_path / 'ramp.tif', values)), 45.9895, 7.0105)
    assert got['dem_elevation_m'] == 10
    assert got['aspect_deg'] == 270
    # 1 m rise / 77.34404 m east-west pixel spacing at 45.9895 degrees.
    assert got['slope_deg'] == pytest.approx(0.74074983, abs=1e-7)
    assert got['dem_local_std_m'] == pytest.approx(np.sqrt(10))


def test_cache_resumes_without_opening_source_and_rejects_tampering(tmp_path):
    m = terrain_module()
    path = raster(tmp_path / 'flat.tif')
    cache = tmp_path / 'cache'
    got = m.cached_sample(str(path), 45.9895, 7.0105, cache)
    path.unlink()
    resumed = m.cached_sample(str(path), 45.9895, 7.0105, cache)
    assert resumed == got
    record = next(cache.glob('*.json'))
    payload = json.loads(record.read_text())
    payload['result']['dem_elevation_m'] = 99
    record.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='cache'):
        m.cached_sample(str(path), 45.9895, 7.0105, cache)


def test_cli_full_manifest_hashes_and_partial_offline_resume(tmp_path):
    m = terrain_module()
    obs = tmp_path / 'observations.csv'
    weather = tmp_path / 'weather.csv'
    donors = tmp_path / 'donors.csv'
    sites().assign(lat=['45.001', '45.001000001'], lon='7.001').to_csv(obs, index=False)
    crosswalk().to_csv(weather, index=False)
    donor().assign(latitude='45.001', longitude='7.001').to_csv(donors, index=False)
    geo = invariant(tmp_path / 'geo.nc', 'z', [[0, 98.0665], [196.133, 294.1995]], 'm**2 s**-2')
    lsm = invariant(tmp_path / 'lsm.nc', 'lsm', [[1, 0.5], [0, 1]], '1')
    output = tmp_path / 'output'
    native_path = tmp_path / 'native.csv'
    pd.read_csv(obs, dtype=str).assign(era5_grid_lat=45, era5_grid_lon=7,
        era5_grid_id='ERA5L_0.1_lat+45.0_lon+7.0').to_csv(native_path, index=False)
    args = ['--observations', str(obs), '--crosswalk', str(weather),
            '--terrain-sources', str(donors), '--geopotential', str(geo),
            '--land-sea-mask', str(lsm), '--geopotential-sha256', hashlib.sha256(geo.read_bytes()).hexdigest(),
            '--land-sea-mask-sha256', hashlib.sha256(lsm.read_bytes()).hexdigest(),
            '--output-dir', str(output), '--native-grids', str(native_path)]
    assert m.main(args) == 2
    table = pd.read_csv(output / 'terrain_manifest.csv', dtype={'site': str})
    assert set(table.site) == {'FR:tempo:0001', 'DE:dwd:0002'}
    assert table.era5_grid_elevation_m.tolist() == [0, 0]
    assert table.dem_elevation_m.notna().sum() == 1
    report = json.loads((output / 'provenance.json').read_text())
    assert report['site_count'] == 2
    assert report['complete_terrain_count'] == 1
    assert report['terrain_metric_absolute_tolerance'] == 1e-10
    assert report['inputs']['terrain_metric_relative_tolerance'] == 0
    assert report['inputs']['native_grids']['sha256'] == hashlib.sha256(native_path.read_bytes()).hexdigest()
    assert set(table.era5_grid_assignment_method) == {'authoritative_GEE_native_pixel_centers'}
    assert report['manifest_sha256'] == hashlib.sha256((output / 'terrain_manifest.csv').read_bytes()).hexdigest()
    assert m.main(args) == 2
    obs.write_text(obs.read_text().replace('45.001,', '45.1,'))
    with pytest.raises(ValueError, match='inputs'):
        m.main(args)


def test_cli_rejects_wrong_official_input_hash_before_writing(tmp_path):
    m = terrain_module()
    geo = invariant(tmp_path / 'geo.nc', 'z', [[1]], 'm**2 s**-2', lat=(45,), lon=(7,))
    with pytest.raises(ValueError, match='SHA-256'):
        m.main(['--geopotential', str(geo), '--output-dir', str(tmp_path / 'out')])
    assert not (tmp_path / 'out').exists()


def test_outer_tile_boundary_does_not_clamp_to_a_noncontaining_pixel(tmp_path):
    m = terrain_module()
    path = raster(tmp_path / 'flat.tif')
    with pytest.raises(ValueError, match='outside'):
        m.sample_dem_window(str(path), 45.979, 7.0105)


def test_cli_sample_missing_uses_pixel_cache_on_resume(tmp_path, monkeypatch):
    m = terrain_module()
    obs, weather, donors = [tmp_path / name for name in ['obs.csv', 'weather.csv', 'donors.csv']]
    pd.DataFrame({'site': ['FR:tempo:0001'], 'lat': ['45.9895'], 'lon': ['7.0105']}).to_csv(obs, index=False)
    crosswalk().iloc[[0]].to_csv(weather, index=False)
    donor().assign(latitude='45.9895', longitude='7.0105', dem_local_std_m='',
                   slope_deg='0.0000000000000035').to_csv(donors, index=False)
    geo = invariant(tmp_path / 'geo.nc', 'z', [[98.0665]], 'm**2 s**-2', lat=(46,), lon=(7,))
    lsm = invariant(tmp_path / 'lsm.nc', 'lsm', [[1]], '1', lat=(46,), lon=(7,))
    local = raster(tmp_path / 'local.tif')
    # URL selection is the external boundary; sampling, cache and CLI remain real.
    monkeypatch.setattr(m, 'tile_url', lambda lat, lon: str(local))
    args = ['--observations', str(obs), '--crosswalk', str(weather), '--terrain-sources', str(donors),
            '--geopotential', str(geo), '--land-sea-mask', str(lsm),
            '--geopotential-sha256', hashlib.sha256(geo.read_bytes()).hexdigest(),
            '--land-sea-mask-sha256', hashlib.sha256(lsm.read_bytes()).hexdigest(),
            '--output-dir', str(tmp_path / 'out'), '--sample-missing']
    assert m.main(args) == 0
    local.unlink()
    assert m.main(args) == 0
    # Offline reruns retain completed cached terrain without network access.
    assert m.main(args[:-1]) == 0
    manifest = pd.read_csv(tmp_path / 'out/terrain_manifest.csv')
    assert manifest.loc[0, 'site_minus_grid_elevation_m'] == pytest.approx(-10)
    assert manifest.loc[0, 'slope_deg'] == 0
    provenance = json.loads(manifest.loc[0, 'terrain_sampling_provenance'])
    assert provenance['raw_shape'] == [11, 11]
    assert json.loads(manifest.loc[0, 'terrain_legacy_qa'])['metrics']['slope_deg'] == 3.5e-15


def test_metric_serialization_ulp_is_audited_without_replacing_first_donor():
    m = terrain_module()
    first = donor().assign(slope_deg='25.541465896297154')
    second = donor().assign(slope_deg='25.54146589629715')
    result = m.reuse_terrain(m.build_site_index(sites(), crosswalk()), [
        (first, {'path': 'first.csv', 'sha256': '1'}),
        (second, {'path': 'second.csv', 'sha256': '2'})])
    row = result.set_index('site').loc['FR:tempo:0001']
    assert row.slope_deg == 25.541465896297154
    evidence = json.loads(row.terrain_donors)[1]['tolerated_metric_discrepancies'][0]
    assert evidence['metric'] == 'slope_deg'
    assert evidence['retained_value'] == 25.541465896297154
    assert evidence['donor_value'] == 25.54146589629715
    assert evidence['absolute_tolerance'] == 1e-10
    with pytest.raises(ValueError, match='Conflicting terrain donors'):
        m.reuse_terrain(m.build_site_index(sites(), crosswalk()), [
            (first, {'path': 'first.csv', 'sha256': '1'}),
            (donor().assign(slope_deg='25.5414658965'), {'path': 'bad.csv', 'sha256': '3'})])


def test_integer_valid_pixel_counts_still_require_exact_equality():
    m = terrain_module()
    with pytest.raises(ValueError, match='Conflicting terrain donors'):
        m.reuse_terrain(m.build_site_index(sites(), crosswalk()), [
            (donor().assign(dem_local_valid_pixels='121'), {'path': 'first.csv', 'sha256': '1'}),
            (donor().assign(dem_local_valid_pixels='120'), {'path': 'bad.csv', 'sha256': '2'})])


def test_fractional_valid_pixel_counts_are_rejected():
    m = terrain_module()
    with pytest.raises(ValueError, match='pixel count'):
        m.reuse_terrain(m.build_site_index(sites(), crosswalk()), [
            (donor().assign(dem_local_valid_pixels='121.00000000001'), {'path': 'bad.csv', 'sha256': '1'})])


def test_authoritative_native_grid_overrides_legacy_lower_tie(tmp_path):
    m = terrain_module()
    geo = invariant(tmp_path / 'geo.nc', 'z', [[0], [196.133]], 'm**2 s**-2', lat=(43.3, 43.4), lon=(3.5,))
    lsm = invariant(tmp_path / 'lsm.nc', 'lsm', [[1], [1]], '1', lat=(43.3, 43.4), lon=(3.5,))
    frame = pd.DataFrame({'site': ['FR:tempo:0001'], 'lat': [43.35], 'lon': [3.53333]})
    native = frame.assign(era5_grid_lat=43.4, era5_grid_lon=3.5,
                          era5_grid_id='ERA5L_0.1_lat+43.4_lon+3.5')
    got = m.attach_invariants(frame, geo, lsm, native_grids=native)
    assert got.era5_grid_elevation_m.iloc[0] == pytest.approx(20)
    assert got.era5_grid_lat.iloc[0] == 43.4
    assert got.era5_grid_differs_from_legacy.iloc[0]
    assert got.era5_grid_assignment_method.iloc[0] == 'authoritative_GEE_native_pixel_centers'
    with pytest.raises(ValueError, match='coordinates'):
        m.attach_invariants(frame, geo, lsm, native_grids=native.assign(lat=43.350001))
    with pytest.raises(ValueError, match='native grid'):
        m.attach_invariants(frame, geo, lsm, native_grids=native.iloc[:0])


def shifted_raster(path, lat, lon, elevation):
    with rasterio.open(path, 'w', driver='GTiff', width=20, height=20, count=1,
                       dtype='float32', crs='EPSG:4326',
                       transform=from_origin(lon - .025, lat + 1.025, .05, .05)) as dst:
        dst.write(np.full((20, 20), elevation, dtype='float32'), 1)
    return path


@pytest.mark.parametrize('latitude,longitude,wanted_tile', [
    (44.0, 4.68, (43, 4)), (44.0, 4.99, (43, 5))])
def test_actual_containing_adjacent_tile_and_corner(tmp_path, monkeypatch, latitude, longitude, wanted_tile):
    m = terrain_module()
    tiles = {(44, 4): shifted_raster(tmp_path / 'nominal.tif', 44, 4, 999),
             wanted_tile: shifted_raster(tmp_path / 'containing.tif', *wanted_tile, 10)}
    monkeypatch.setattr(m, 'tile_url', lambda lat, lon: str(tiles[(lat, lon)]))
    got = m.sample_containing_dem(str(tiles[(44, 4)]), latitude, longitude)
    assert got['dem_elevation_m'] == 10
    assert got['sampling_provenance']['source'] == str(tiles[wanted_tile])
    assert got['sampling_provenance']['tile_selection']['requested_source'] == str(tiles[(44, 4)])
    assert not got['sampling_provenance']['boundary_coordinate_clamped']


def test_boundary_complete_and_partial_donors_become_qa_before_native_resampling():
    m = terrain_module()
    index = m.build_site_index(sites(), crosswalk())
    reused = m.reuse_terrain(index, [(donor(), {'path': 'legacy.csv', 'sha256': '1'})])
    screened = m.screen_legacy_terrain(reused)
    row = screened.set_index('site').loc['FR:tempo:0001']
    assert row.terrain_requires_native_resample
    assert np.isnan(row.dem_elevation_m)
    assert json.loads(row.terrain_legacy_qa)['metrics']['dem_elevation_m'] == 0
    assert 'tile_boundary' in row.terrain_resample_reason
    # An interior complete donor remains unchanged.
    frame = reused.iloc[[1]].assign(lat=45.1234, lon=7.1234)
    assert m.screen_legacy_terrain(frame).dem_elevation_m.iloc[0] == 0
    partial = frame.copy()
    partial.loc[:, 'dem_local_std_m'] = np.nan
    screened_partial = m.screen_legacy_terrain(partial)
    assert screened_partial.dem_elevation_m.isna().all()
    assert screened_partial.terrain_resample_reason.iloc[0] == 'partial_legacy_terrain'


def test_v1_cache_import_checks_pixels_and_containing_geometry(tmp_path):
    m = terrain_module()
    path = raster(tmp_path / 'flat.tif')
    old = tmp_path / 'old'
    new = tmp_path / 'new'
    request = {'source': str(path), 'latitude': 45.9895, 'longitude': 7.0105,
               'algorithm': 'publication_terrain_v1_3x3_gradient_11x11_std'}
    result = m.sample_dem_window(str(path), 45.9895, 7.0105)
    result['sampling_provenance']['algorithm'] = request['algorithm']
    payload = {'request': request, 'result': result,
               'result_sha256': hashlib.sha256(m.canonical_json(result).encode()).hexdigest()}
    old.mkdir()
    file = old / (hashlib.sha256(m.canonical_json(request).encode()).hexdigest() + '.json')
    file.write_text(m.canonical_json(payload))
    path.unlink()
    got = m.cached_sample(str(path), 45.9895, 7.0105, new, allow_remote=False, reuse_cache=old)
    assert got['dem_elevation_m'] == 0
    assert got['sampling_provenance']['cache_reuse']['source_file_sha256'] == hashlib.sha256(file.read_bytes()).hexdigest()
    assert list(new.glob('*.json'))
    # Recompute wrapper hash after moving the sample transform: pixel containment must still be verified.
    payload['result']['sampling_provenance']['transform'][2] = 1
    payload['result_sha256'] = hashlib.sha256(m.canonical_json(payload['result']).encode()).hexdigest()
    file.write_text(m.canonical_json(payload))
    assert m.cached_sample(str(path), 45.9895, 7.0105, tmp_path / 'other',
                           allow_remote=False, reuse_cache=old) is None
