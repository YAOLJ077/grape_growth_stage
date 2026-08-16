import pandas as pd

from src.weather_processing.prepare_model_ready_weather import finalize_qc, standardize_units, update_stats


def weather_frame():
    return pd.DataFrame({
        "weather_id": ["A", "A"], "country": ["France", "France"], "source": ["tempo", "tempo"],
        "site_id": ["1", "1"], "year": [2020, 2020], "weather_start_date": ["2020-01-01"] * 2,
        "weather_end_date": ["2020-01-02"] * 2, "first_event_date": ["2020-01-01"] * 2,
        "last_event_date": ["2020-01-02"] * 2, "weather_date": ["2020-01-01", "2020-01-02"],
        "temperature_2m": [273.15, 274.15], "temperature_2m_min": [272.15, 273.15],
        "temperature_2m_max": [274.15, 275.15], "dewpoint_temperature_2m": [271.15, 272.15],
        "total_precipitation_sum": [0.001, 0.0], "surface_pressure": [100000.0, 99000.0],
        "surface_solar_radiation_downwards_sum": [1_000_000.0, 2_000_000.0],
        "u_component_of_wind_10m": [3.0, 0.0], "v_component_of_wind_10m": [4.0, 2.0],
        "weather_fill_method": ["original_point_sample", "original_point_sample"],
    })


def test_weather_unit_standardization():
    result = standardize_units(weather_frame())
    assert result.loc[0, "temperature_2m_c"] == 0.0
    assert result.loc[0, "total_precipitation_mm"] == 1.0
    assert result.loc[0, "surface_pressure_kpa"] == 100.0
    assert result.loc[0, "surface_solar_radiation_downwards_mj_m2"] == 1.0
    assert result.loc[0, "wind_speed_10m_m_s"] == 5.0
    assert "temperature_2m" not in result.columns


def test_complete_weather_period_passes_qc():
    stats = {}
    update_stats(stats, weather_frame())
    result = finalize_qc(stats)
    assert bool(result.loc[0, "weather_period_complete"])
    assert bool(result.loc[0, "weather_complete_for_observed_events"])
    assert bool(result.loc[0, "daily_physical_qc_pass"])


def test_tiny_negative_precipitation_is_clamped_and_audited_as_roundoff():
    frame = weather_frame()
    frame.loc[0, "total_precipitation_sum"] = -5e-8
    normalized = standardize_units(frame)
    assert normalized.loc[0, "total_precipitation_mm"] == 0.0
    stats = {}
    update_stats(stats, frame)
    result = finalize_qc(stats)
    assert result.loc[0, "n_tiny_negative_precipitation_clipped"] == 1
    assert result.loc[0, "n_material_negative_precipitation"] == 0
    assert bool(result.loc[0, "daily_physical_qc_pass"])
