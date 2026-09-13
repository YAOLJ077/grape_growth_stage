import numpy as np
import pandas as pd
import pytest

from src.weather_processing.publication_climate import make_grids, publish_tables, MONTHS, YEARS


def test_grid_assignment_preserves_lower_boundary_ties_and_deduplicates():
    sites = pd.DataFrame({'lat': [45.05, 45.05, 46.01], 'lon': [5.05, 5.05, -1.05]})
    grids = make_grids(sites)
    assert set(grids.era5_grid_id) == {'ERA5L_0.1_lat+45.0_lon+5.0', 'ERA5L_0.1_lat+46.0_lon-1.1'}
    with pytest.raises(ValueError, match='range'):
        make_grids(pd.DataFrame({'lat': [95], 'lon': [5]}))


def test_export_requires_all_grids_and_all_climate_values_before_writing(tmp_path):
    frame = pd.DataFrame({'era5_grid_id': ['g1', 'g2'], **{c: [10., 20.] for c in MONTHS},
                          **{f'summer_{y}': [15., 25.] for y in YEARS}})
    grids = frame[['era5_grid_id']]
    masked = frame.copy()
    masked.loc[1, 'summer_1951'] = np.nan
    with pytest.raises(ValueError, match='incomplete'):
        publish_tables(masked, grids, tmp_path)
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError, match='identities'):
        publish_tables(frame.iloc[:1], grids, tmp_path)
    publish_tables(frame, grids, tmp_path)
    annual = pd.read_csv(tmp_path/'annual_summer.csv')
    assert len(annual) == 150
    assert set(annual.year) == set(range(1951, 2026))
    assert annual.groupby('era5_grid_id').tmean_apr_sep_c.first().to_dict() == {'g1': 15., 'g2': 25.}
    normals = pd.read_csv(tmp_path/'monthly_normals.csv')
    assert list(normals.columns) == ['era5_grid_id', *MONTHS]


def test_authoritative_native_assignment_overrides_geometric_boundary_guess():
    sites = pd.DataFrame(dict(site=['FR:pep725:13:7032'], lat=['43.35'], lon=['3.53333']))
    native = sites.assign(era5_grid_lat=43.4, era5_grid_lon=3.5,
                          era5_grid_id='ERA5L_0.1_lat+43.4_lon+3.5')
    grids = make_grids(sites, native)
    assert grids.iloc[0].lat == 43.4
    assert grids.iloc[0].era5_grid_id == 'ERA5L_0.1_lat+43.4_lon+3.5'
    with pytest.raises(ValueError, match='coordinates'):
        make_grids(sites, native.assign(lat='43.36'))
    with pytest.raises(ValueError, match='identit'):
        make_grids(sites, native.assign(site='different'))
