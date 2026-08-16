import pandas as pd
import pytest

from src.weather_processing.add_evaporative_demand_features import (
    fao56_penman_monteith_et0,
    saturation_vapor_pressure_kpa,
    wind_speed_at_2m,
)


def weather_frame():
    return pd.DataFrame({
        "weather_id": ["France|tempo|1|2020"],
        "weather_date": ["2020-07-01"],
        "weather_doy": [183],
        "lat": [45.0],
        "dem_elevation_m": [120.0],
        "temperature_2m_c_adjusted_main_6p5c_km": [22.0],
        "temperature_2m_min_c_adjusted_main_6p5c_km": [16.0],
        "temperature_2m_max_c_adjusted_main_6p5c_km": [29.0],
        "dewpoint_temperature_2m_c": [13.0],
        "surface_pressure_kpa": [99.0],
        "surface_solar_radiation_downwards_mj_m2": [24.0],
        "wind_speed_10m_m_s": [3.0],
        "total_precipitation_mm": [1.5],
    })


def test_saturation_vapor_pressure_reference_value():
    assert saturation_vapor_pressure_kpa(pd.Series([20.0]))[0] == pytest.approx(2.338, abs=0.001)


def test_wind_speed_converts_10m_to_2m():
    assert wind_speed_at_2m(pd.Series([3.0]))[0] == pytest.approx(2.244, abs=0.001)


def test_fao56_et0_and_vpd_columns_are_added():
    result = fao56_penman_monteith_et0(weather_frame())

    assert result.loc[0, "et0_fao56_penman_monteith_mm_day"] > 3.0
    assert result.loc[0, "vpd_mean_kpa"] > 0.0
    assert result.loc[0, "vpd_fao56_kpa"] > 0.0
    assert result.loc[0, "climatic_water_deficit_fao56_mm_day"] == pytest.approx(
        result.loc[0, "et0_fao56_penman_monteith_mm_day"] - 1.5
    )
