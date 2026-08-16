import h5py
import numpy as np
import pandas as pd

from src.base_table.build_site_era5_grid_crosswalk import (
    STANDARD_GRAVITY_M_S2,
    attach_era5_invariants,
    grid_id,
    nearest_grid_center,
    spatial_block_id,
    tile_keys_for_bounds,
)


def test_nearest_grid_center_handles_negative_longitude_without_bankers_rounding():
    assert nearest_grid_center(-3.24) == -3.2
    assert nearest_grid_center(-3.26) == -3.3
    assert nearest_grid_center(47.46) == 47.5
    assert nearest_grid_center(46.75) == 46.7
    assert nearest_grid_center(6.65) == 6.6


def test_grid_and_spatial_block_ids_are_stable():
    assert grid_id(47.5, -3.2) == "ERA5L_0.1_lat+47.5_lon-3.2"
    assert spatial_block_id(47.5, -3.2, 1.0) == "block_1_lat+47.0_lon-4.0"


def test_grid_bounds_cross_integer_dem_tiles():
    assert set(tile_keys_for_bounds(2.95, 47.95, 3.05, 48.05)) == {
        (47, 2), (47, 3), (48, 2), (48, 3)
    }


def test_official_invariants_are_sampled_and_geopotential_is_converted(tmp_path):
    geopotential = tmp_path / "geo.nc"
    land_sea_mask = tmp_path / "lsm.nc"
    for path, variable, values in (
        (geopotential, "z", np.array([[[100.0 * STANDARD_GRAVITY_M_S2, 200.0 * STANDARD_GRAVITY_M_S2]]])),
        (land_sea_mask, "lsm", np.array([[[1.0, 0.5]]])),
    ):
        with h5py.File(path, "w") as handle:
            handle.create_dataset("latitude", data=np.array([47.5]))
            handle.create_dataset("longitude", data=np.array([3.0, 3.1]))
            handle.create_dataset(variable, data=values)

    grids = pd.DataFrame({"era5_grid_lat": [47.5], "era5_grid_lon": [3.1]})
    sampled = attach_era5_invariants(grids, geopotential, land_sea_mask)

    assert sampled.loc[0, "era5_grid_elevation_m"] == 200.0
    assert sampled.loc[0, "era5_grid_land_fraction"] == 0.5
    assert bool(sampled.loc[0, "era5_grid_is_coastal"])
