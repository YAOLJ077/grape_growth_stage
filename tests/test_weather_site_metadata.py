import pandas as pd

from src.weather_processing.update_weather_site_metadata import refresh_chunk


def test_refresh_chunk_replaces_stale_site_metadata():
    chunk = pd.DataFrame(
        [{"weather_id": "x", "site_name": "A", "lat": 0, "lon": 0, "alt_m": pd.NA, "temperature_2m": 280}]
    )
    lookup = pd.DataFrame([{"weather_id": "x", "lat": 48, "lon": 2, "alt_m": 135}])

    result = refresh_chunk(chunk, lookup)

    assert result.loc[0, ["lat", "lon", "alt_m"]].tolist() == [48, 2, 135]
