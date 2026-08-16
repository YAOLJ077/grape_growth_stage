import numpy as np
import pandas as pd

from src.modeling.build_residual_ml_dataset import (
    daylength_hours,
    feature_masks,
    feature_set_manifest,
    predicted_stage_window_mask,
    summarize_window,
)


def weather_frame() -> pd.DataFrame:
    dates = pd.date_range("2000-01-01", periods=10, freq="D")
    return pd.DataFrame(
        {
            "weather_date": dates,
            "temperature_2m_c": np.arange(10.0, 20.0),
            "temperature_2m_c_adjusted_main_6p5c_km": np.arange(8.0, 18.0),
            "temperature_2m_min_c_adjusted_main_6p5c_km": np.arange(-1.0, 9.0),
            "temperature_2m_max_c_adjusted_main_6p5c_km": np.arange(20.0, 30.0),
            "dewpoint_temperature_2m_c": np.arange(5.0, 15.0),
            "total_precipitation_mm": 1.0,
            "surface_solar_radiation_downwards_mj_m2": 2.0,
            "wind_speed_10m_m_s": 3.0,
        }
    )


def test_weather_windows_end_at_mechanistic_prediction_date():
    frame = weather_frame()
    masks = feature_masks(frame, year=2000, cutoff_doy=5, start_doy=3)

    assert masks["target_year"].sum() == 5
    assert masks["model_start"].sum() == 3
    assert masks["trailing_15d"].sum() == 5
    assert masks["trailing_30d"].sum() == 5
    assert masks["previous_aug"].sum() == 5
    assert not masks["target_year"][5:].any()


def test_weather_summary_uses_adjusted_temperature_and_raw_grid_vpd():
    frame = weather_frame()
    mask = np.arange(len(frame)) < 5
    result = summarize_window(frame, mask)

    assert result["n_days"] == 5
    assert result["tmean_adjusted_mean_c"] == 10.0
    assert result["frost_days"] == 1.0
    assert result["gdd10_adjusted_c_days"] == 3.0
    assert result["precipitation_sum_mm"] == 5.0
    assert result["rain_days_ge1mm"] == 5.0
    assert result["solar_radiation_sum_mj_m2"] == 10.0
    assert result["vpd_raw_grid_mean_kpa"] > 0.0
    assert result["frost_degree_days_below0_c_days"] == 1.0
    assert result["heat_degree_days_above30_c_days"] == 0.0
    assert result["heat_degree_days_above35_c_days"] == 0.0
    assert result["cool_degree_days_below10_c_days"] == 3.0
    assert result["cool_days_tmean_lt10c"] == 2.0
    assert result["solar_radiation_mean_mj_m2_day"] == 2.0
    assert "vpd_degree_days_above1p5_kpa_days" in result
    assert "vpd_degree_days_above2_kpa_days" in result
    assert result["diurnal_temperature_range_mean_c"] == 21.0


def test_predicted_stage_window_excludes_upstream_day_and_observed_dates():
    frame = weather_frame()
    mask = predicted_stage_window_mask(
        frame,
        year=2000,
        upstream_doy=3,
        current_doy=7,
    )

    assert mask.sum() == 4
    assert not mask[:3].any()
    assert mask[3:7].all()
    assert not mask[7:].any()


def test_daylength_and_frozen_feature_sets_are_stage_specific():
    value = daylength_hours(pd.Series([45.0]), pd.Series([172.0])).iloc[0]
    manifest = feature_set_manifest()

    assert 15.0 < value < 16.0
    counts = manifest.groupby(["stage", "feature_set"]).size().to_dict()
    assert counts[("budburst", "selected")] == 6
    assert counts[("flowering", "selected")] == 8
    assert counts[("veraison", "selected")] == 11
    assert counts[("maturity_or_harvest", "selected")] == 9
    assert not manifest["feature"].isin(
        ["lat", "lon", "predicted_doy", "site_minus_grid_elevation_m"]
    ).any()
