import pandas as pd
import pytest

from src.weather_processing.adjust_france_germany_temperature_elevation import (
    MAIN_RATE_LABEL,
    add_adjusted_temperatures,
    adjusted_column,
    adjustment_column,
    temperature_order_bad,
)


def topography_frame():
    return pd.DataFrame({
        "site_uid": ["France|tempo|1", "France|tempo|2"],
        "dem_elevation_m": [300.0, 100.0],
        "era5_grid_id": ["grid1", "grid2"],
        "era5_grid_elevation_m": [100.0, 200.0],
        "site_minus_grid_elevation_m": [200.0, -100.0],
        "abs_site_grid_elevation_difference_m": [200.0, 100.0],
        "coordinate_instability_flag": [False, False],
    })


def weather_frame(fill_method="original_point_sample"):
    return pd.DataFrame({
        "weather_id": ["France|tempo|1|2020"],
        "site_uid": ["France|tempo|1"],
        "weather_fill_method": [fill_method],
        "temperature_2m_c": [10.0],
        "temperature_2m_min_c": [5.0],
        "temperature_2m_max_c": [15.0],
    })


def test_main_adjustment_uses_correct_sign_and_value():
    result = add_adjusted_temperatures(weather_frame(), topography_frame())
    assert bool(result.loc[0, "temperature_elevation_adjustment_eligible"])
    assert result.loc[0, adjustment_column(MAIN_RATE_LABEL)] == pytest.approx(-1.3)
    assert result.loc[0, adjusted_column("temperature_2m_c", MAIN_RATE_LABEL)] == pytest.approx(8.7)
    assert not bool(temperature_order_bad(result, MAIN_RATE_LABEL).iloc[0])


def test_lower_site_is_warmed_and_sensitivity_columns_are_created():
    weather = weather_frame()
    weather["weather_id"] = "France|tempo|2|2020"
    weather["site_uid"] = "France|tempo|2"
    result = add_adjusted_temperatures(weather, topography_frame())
    assert result.loc[0, adjustment_column(MAIN_RATE_LABEL)] == pytest.approx(0.65)
    assert result.loc[0, adjustment_column("sensitivity_4p5c_km")] == pytest.approx(0.45)
    assert result.loc[0, adjustment_column("sensitivity_6p0c_km")] == pytest.approx(0.6)


def test_weather_without_a_unique_point_sample_is_rejected():
    with pytest.raises(ValueError, match="unique ERA5-Land point sample"):
        add_adjusted_temperatures(weather_frame("era5_land_buffer_mean"), topography_frame())
