import pandas as pd

from src.base_table.build_weather_download_index import build_weather_index


def test_weather_index_groups_site_year_and_builds_full_weather_window():
    frame = pd.DataFrame(
        [
            {
                "record_id": "a",
                "country": "France",
                "source": "test_source",
                "site_id": "site-1",
                "site_name": "Test site",
                "lat": 48.0,
                "lon": 2.0,
                "alt_m": 100.0,
                "year": 2000,
                "event_date": "2000-04-09",
                "event_doy": 100,
                "bbch": "07",
                "phenophase": "budburst",
                "model_tier": "core",
            },
            {
                "record_id": "b",
                "country": "France",
                "source": "test_source",
                "site_id": "site-1",
                "site_name": "Test site",
                "lat": 48.0,
                "lon": 2.0,
                "alt_m": 100.0,
                "year": 2000,
                "event_date": "2000-06-23",
                "event_doy": 175,
                "bbch": "65",
                "phenophase": "flowering",
                "model_tier": "extended",
            },
        ]
    )

    result = build_weather_index(frame, start_month=9, start_day=1)

    assert len(result) == 1
    row = result.iloc[0]
    assert row["weather_id"] == "France|test_source|site-1|2000"
    assert row["weather_start_date"] == "1999-09-01"
    assert row["weather_end_date"] == "2000-12-31"
    assert row["n_events"] == 2
    assert row["bbch_list"] == "07;65"
    assert row["model_tier"] == "core"
