from pathlib import Path

import pandas as pd

from src.base_table.build_site_topography import resolve_manifest_path, summarize_sites


def test_site_summary_filters_year_and_preserves_altitude_source(tmp_path):
    frame = pd.DataFrame(
        [
            {
                "country_name": "France",
                "source_system": "france_tempo",
                "site_id": "1",
                "site_name": "Old",
                "latitude": 48,
                "longitude": 2,
                "altitude": 100,
                "altitude_source": "tempo_ign",
                "year": 1950,
            },
            {
                "country_name": "France",
                "source_system": "france_tempo",
                "site_id": "2",
                "site_name": "Current",
                "latitude": 47.5,
                "longitude": 3.2,
                "altitude": 240,
                "altitude_source": "tempo_ign",
                "year": 1951,
            },
        ]
    )

    result = summarize_sites(frame, 1951)

    assert result["site_id"].tolist() == ["2"]
    assert result.loc[0, "source_altitude_m"] == 240
    assert result.loc[0, "altitude_source"] == "tempo_ign"
    assert (result.loc[0, "tile_lat"], result.loc[0, "tile_lon"]) == (47, 3)


def test_manifest_path_accepts_windows_separators(tmp_path):
    expected = tmp_path / "tile.tif"
    expected.touch()
    windows_style = str(expected).replace("/", "\\")
    assert resolve_manifest_path(windows_style) == Path(expected)
