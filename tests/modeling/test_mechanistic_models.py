import pandas as pd

from src.modeling.mechanistic_models import (
    TEMPERATURE_BRANCH_COLUMNS,
    brin_daily_chill_action,
    brin_daily_gdh,
    brin_hourly_temperature,
    build_forcing_profiles,
    calibrate_forcing_threshold,
    daily_gdd,
    default_model_specifications,
    predict_from_profiles,
    predict_thermal_model,
)
from src.modeling.run_mechanistic_baselines import calibrate_threshold_fast


def weather_frame():
    rows = []
    for weather_id in ("site-a|2000", "site-b|2000"):
        for doy in range(1, 11):
            rows.append(
                {
                    "weather_id": weather_id,
                    "year": 2000,
                    "weather_year": 2000,
                    "weather_doy": doy,
                    "temperature_2m_c": 10.0,
                    "temperature_2m_min_c": 5.0,
                    "temperature_2m_max_c": 15.0,
                    "temperature_2m_c_adjusted_main_6p5c_km": 11.0,
                    "temperature_2m_min_c_adjusted_main_6p5c_km": 6.0,
                    "temperature_2m_max_c_adjusted_main_6p5c_km": 16.0,
                }
            )
    return pd.DataFrame(rows)


def test_daily_gdd_and_threshold_crossing():
    assert daily_gdd(pd.Series([2.0, 5.0, 8.0]), 5.0).tolist() == [0.0, 0.0, 3.0]
    profiles = build_forcing_profiles(weather_frame(), "temperature_2m_c", 1, 0.0)
    predicted = predict_from_profiles(profiles, 50.0)
    assert predicted["predicted_doy"].eq(5.0).all()
    assert predicted["threshold_reached"].all()


def test_calibrated_threshold_uses_explicit_training_observations():
    specification = next(
        spec
        for spec in default_model_specifications()
        if spec.model_id == "budburst__calibrated_gdd5"
    )
    profiles = build_forcing_profiles(
        weather_frame(), "temperature_2m_c", specification.start_doy, specification.base_temperature_c
    )
    observations = pd.DataFrame(
        {"weather_id": ["site-a|2000", "site-b|2000"], "event_doy": [5, 6]}
    )
    fit = calibrate_forcing_threshold(
        profiles, observations, specification, objective="rmse", n_candidates=101
    )

    assert 25.0 <= fit.forcing_threshold_c_days <= 30.0
    assert fit.objective_value_days <= 1.0


def test_gfv_definition_and_temperature_branch_pairing():
    registry = default_model_specifications()
    gfv = [spec for spec in registry if spec.family == "gfv_spring_warming"]
    assert {spec.stage for spec in gfv} == {"flowering", "veraison"}
    assert all(spec.start_doy == 60 and spec.base_temperature_c == 0.0 for spec in gfv)
    assert set(TEMPERATURE_BRANCH_COLUMNS) == {"raw", "adjusted_6p5"}


def test_brin_uses_published_hourly_and_temperature_response_structure():
    hourly = brin_hourly_temperature(5.0, 17.0, 7.0)
    assert len(hourly) == 24
    assert hourly[11] == 17.0
    assert hourly[-1] == 7.0
    chill = brin_daily_chill_action([5.0], [17.0], q10=2.17)
    assert chill[0] > 0.0
    forcing = brin_daily_gdh([5.0, 7.0], [17.0, 19.0])
    assert forcing.shape == (2,)
    assert (forcing > 0.0).all()


def test_brin_aug1_is_a_selection_eligible_budburst_candidate():
    brin = [
        spec for spec in default_model_specifications()
        if spec.family == "brin_bidabe_richardson"
    ]
    assert len(brin) == 1
    assert brin[0].model_id == "budburst__calibrated_brin_aug1"
    assert brin[0].selection_eligible
    assert brin[0].base_temperature_c == 5.0


def test_fixed_reference_refuses_prediction_before_threshold_freeze():
    fixed = next(spec for spec in default_model_specifications() if spec.model_id == "budburst__fixed_gdd5_external_median")
    prediction = predict_thermal_model(weather_frame(), fixed, "raw")
    assert not prediction["threshold_reached"].any()


def test_only_supported_external_thresholds_are_frozen():
    fixed = [spec for spec in default_model_specifications() if spec.threshold_mode == "fixed_external"]
    assert {spec.model_id for spec in fixed} == {
        "budburst__fixed_gdd5_external_median",
        "flowering__fixed_gfv_external_median",
        "veraison__fixed_gfv_external_median",
    }
    assert all(spec.forcing_threshold_c_days is not None for spec in fixed)


def test_fast_calibration_penalizes_unreached_threshold_without_prioritizing_coverage():
    profiles = {
        "warm": (pd.Series(range(1, 11)).to_numpy(), pd.Series(range(1, 11), dtype=float).to_numpy()),
        "cold": (pd.Series(range(1, 11)).to_numpy(), pd.Series([0.2 * day for day in range(1, 11)]).to_numpy()),
    }
    observations = pd.DataFrame(
        {"weather_id": ["warm", "cold"], "event_doy": [5, 10]}
    )
    fit = calibrate_threshold_fast(profiles, observations, n_candidates=31)

    assert fit["forcing_threshold_c_days"] > 2.0
    assert fit["training_coverage"] == 0.5
