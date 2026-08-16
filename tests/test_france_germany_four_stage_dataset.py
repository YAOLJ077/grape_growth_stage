import pandas as pd

from src.base_table.build_france_germany_four_stage_dataset import (
    TARGETS,
    build_elevation_band_summary,
    build_long,
    build_wide,
    weather_ids_without_point_weather,
)


def test_four_stage_builder_filters_exact_targets_and_adds_elevation_fields():
    events = pd.DataFrame(
        {
            "record_id": ["f7", "f65", "f81", "f89", "f60", "a65"],
            "country": ["France"] * 5 + ["Austria"],
            "source": ["tempo"] * 5 + ["pep725"],
            "site_id": ["1"] * 6,
            "site_name": ["site"] * 6,
            "lat": [48.0] * 6,
            "lon": [2.0] * 6,
            "alt_m": [100.0] * 6,
            "year": [2000] * 6,
            "event_date": ["2000-04-01", "2000-05-01", "2000-07-01", "2000-09-01", "2000-04-20", "2000-05-01"],
            "event_doy": [92, 122, 183, 245, 111, 122],
            "bbch": [7, 65, 81, 89, 60, 65],
            "bbch_major": [0, 6, 8, 8, 6, 6],
            "phenophase": ["budburst", "flowering", "veraison", "maturity_or_harvest", "flowering", "flowering"],
            "phenophase_order": [1, 2, 3, 4, 2, 2],
            "bbch_confidence": ["high"] * 6,
            "aggregation_method": ["min", "median", "min", "median", "min", "median"],
            "n_obs": [1] * 6,
            "doy_min": [92, 122, 183, 245, 111, 122],
            "doy_median": [92, 122, 183, 245, 111, 122],
            "doy_max": [92, 122, 183, 245, 111, 122],
            "doy_range": [0] * 6,
            "date_min": ["2000-01-01"] * 6,
            "date_max": ["2000-01-01"] * 6,
            "n_years_site_bbch": [10] * 6,
            "n_observations_site_bbch": [10] * 6,
            "model_tier": ["core"] * 6,
        }
    )
    topography = pd.DataFrame(
        {
            "site_uid": ["France|tempo|1"], "site_id": ["1"], "dem_elevation_m": [105.0],
            "era5_grid_elevation_m": [80.0], "site_minus_grid_elevation_m": [25.0],
        }
    )
    result = build_long(events, topography)

    assert set(result["bbch"]) == set(TARGETS)
    assert len(result) == 4
    assert result["four_stage_site_year_complete"].all()
    assert result["site_minus_grid_elevation_m"].eq(25.0).all()

    wide = build_wide(result)
    assert len(wide) == 1
    assert bool(wide.loc[0, "four_stage_complete"])
    assert bool(wide.loc[0, "chronology_valid"])
    assert bool(wide.loc[0, "recommended_for_sequential_model"])
    assert wide.loc[0, "flowering_to_veraison_days"] == 61


def test_elevation_band_summary_counts_each_site_year_once_and_retains_empty_bands():
    wide = pd.DataFrame(
        {
            "country": ["France", "France", "France", "Germany"],
            "site_uid": ["f1", "f1", "f2", "g1"],
            "year": [2000, 2001, 2000, 2000],
            "dem_elevation_m": [99.9, 99.9, 250.0, 500.0],
        }
    )

    result = build_elevation_band_summary(wide)
    france = result.set_index(["country", "elevation_band"]).loc["France"]
    germany = result.set_index(["country", "elevation_band"]).loc["Germany"]

    assert france.loc["<100 m", "n_sites"] == 1
    assert france.loc["<100 m", "n_site_years"] == 2
    assert france.loc["250–499 m", "n_site_years"] == 1
    assert germany.loc["500–999 m", "n_site_years"] == 1
    assert germany.loc["≥1000 m", "n_site_years"] == 0
    assert france["n_site_years"].sum() == 3
    assert germany["n_site_years"].sum() == 1
    assert france["site_year_share_pct"].sum() == 100.0
    assert germany["site_year_share_pct"].sum() == 100.0


def test_weather_qc_exclusion_is_applied_at_site_year_level():
    qc = pd.DataFrame(
        {
            "weather_id": ["France|tempo|1|2000", "France|tempo|1|2001"],
            "has_buffer_fill": [True, False],
        }
    )

    assert weather_ids_without_point_weather(qc) == {"France|tempo|1|2000"}
