from pathlib import Path

import pandas as pd

from src.descriptive_phenology.download_copernicus_dem_site_tiles import site_tiles
from src.descriptive_phenology.plot_site_topography_overlay import load_sites
from src.plot_phenology_sites_by_source_with_pep725 import load_data
from src.plot_phenology_sites_dem_overlap import load_observations, resolve_local_path


def write_observations(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "source_system": "test",
                "source_dataset": "test",
                "country_name": "France",
                "site_id": "historical-only",
                "site_name": "Historical",
                "latitude": 48.0,
                "longitude": 2.0,
                "altitude": 100,
                "year": 1950,
                "stage_event": "budburst",
                "bbch_code": 7,
                "cultivar_group": "wine",
                "doy": 100,
            },
            {
                "source_system": "test",
                "source_dataset": "test",
                "country_name": "France",
                "site_id": "retained",
                "site_name": "Retained",
                "latitude": 47.0,
                "longitude": 3.0,
                "altitude": 120,
                "year": 1951,
                "stage_event": "budburst",
                "bbch_code": 7,
                "cultivar_group": "wine",
                "doy": 101,
            },
        ]
    ).to_csv(path, index=False)


def test_map_and_dem_site_inputs_exclude_pre_1951_observations(tmp_path):
    path = tmp_path / "observations.csv"
    write_observations(path)

    overlap = load_observations([path], start_year=1951)
    source_map = load_data([path], start_year=1951)
    topo_sites = load_sites([path], start_year=1951)
    tiles = site_tiles([path], max_tiles=0, start_year=1951)

    assert overlap["site_id"].tolist() == ["retained"]
    assert source_map["site_id"].tolist() == ["retained"]
    assert topo_sites["site_id"].tolist() == ["retained"]
    assert tiles[["tile_lat", "tile_lon"]].to_records(index=False).tolist() == [(47, 3)]


def test_raw_dem_manifest_accepts_windows_paths(tmp_path):
    raster_path = tmp_path / "dem" / "tile.tif"
    raster_path.parent.mkdir()
    raster_path.touch()
    windows_style = str(raster_path).replace("/", "\\")
    assert resolve_local_path(windows_style).exists()
