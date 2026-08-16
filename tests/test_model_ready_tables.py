import pandas as pd

from src.base_table.build_model_ready_tables import (
    OUTPUT_OBSERVATION_COLUMNS,
    aggregation_method,
    build_event_table,
    model_tier,
)


def observation(**overrides):
    row = {
        "record_id": "record",
        "country": "France",
        "source": "test_source",
        "site_id": "site-1",
        "site_name": "Test site",
        "lat": 48.0,
        "lon": 2.0,
        "alt_m": 100.0,
        "year": 2000,
        "date": "2000-04-09",
        "doy": 100.0,
        "bbch": "07",
        "bbch_major": "0",
        "phenophase": "budburst",
        "phenophase_order": 1,
        "bbch_confidence": "high",
        "n_years_site_bbch": 12,
        "n_observations_site_bbch": 20,
        "model_tier": "core",
    }
    row.update(overrides)
    return row


def test_model_tier_uses_phase_confidence_and_continuity():
    assert model_tier(
        pd.Series(
            {
                "phenophase_standard": "budburst",
                "bbch_mapping_confidence": "high",
                "n_years_site_bbch": 10,
            }
        )
    ) == "core"
    assert model_tier(
        pd.Series(
            {
                "phenophase_standard": "flowering",
                "bbch_mapping_confidence": "medium",
                "n_years_site_bbch": 5,
            }
        )
    ) == "extended"


def test_event_aggregation_uses_min_for_start_and_median_for_later_stages():
    frame = pd.DataFrame(
        [
            observation(record_id="a", date="2000-04-09", doy=100),
            observation(record_id="b", date="2000-04-11", doy=102),
            observation(
                record_id="c",
                date="2000-06-18",
                doy=170,
                bbch="65",
                bbch_major="6",
                phenophase="flowering",
                phenophase_order=4,
            ),
            observation(
                record_id="d",
                date="2000-06-28",
                doy=180,
                bbch="65",
                bbch_major="6",
                phenophase="flowering",
                phenophase_order=4,
            ),
        ],
        columns=OUTPUT_OBSERVATION_COLUMNS,
    )

    result = build_event_table(frame).set_index("bbch")

    assert aggregation_method("07") == "min"
    assert aggregation_method("65") == "median"
    assert result.loc["07", "event_doy"] == 100
    assert result.loc["07", "event_date"] == "2000-04-09"
    assert result.loc["65", "event_doy"] == 175
    assert result.loc["65", "event_date"] == "2000-06-23"
