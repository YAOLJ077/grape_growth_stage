"""The fixed-response accelerator must preserve the public numerical contract."""
import importlib

import numpy as np
import pandas as pd
import pytest

from model.parameters import default_parameters
from model.registry import list_models
from model.simulation import predict
from model.structure_comparison import fixed_parameters, threshold_only_settings


def accelerated():
    return importlib.import_module("model.fast_thresholds")


def weather(site="A", season=2000, *, profile="mixed"):
    dates = pd.date_range(f"{season - 1}-09-01", f"{season}-12-31")
    day = np.arange(len(dates), dtype=float)
    if profile == "mixed":
        values = 8.0 + 11.0 * np.sin(day / 19.0) + 2.0 * np.cos(day / 7.0)
    elif profile == "cold":
        values = np.full(len(dates), -15.0)
    else:
        values = np.full(len(dates), 10.0)
    return pd.DataFrame({"site": site, "Date": dates, "Tmean": values, "corrected": values + 0.5})


def fixed_thresholds(name, forcing=12.5, chilling=3.0):
    parameters = default_parameters(name)
    parameters.update(fixed_parameters(name))
    for stage, value in zip(("07", "65", "81", "89"), (forcing, forcing + 1, forcing + 2, forcing + 3)):
        parameters[f"forcing_requirement_{stage}"] = value
    if "chilling_requirement" in parameters:
        parameters["chilling_requirement"] = chilling
    return parameters


@pytest.mark.parametrize("name", list_models())
@pytest.mark.parametrize("profile", ["mixed", "constant"])
def test_predict_matches_reference_for_fixed_response_models(name, profile):
    params = fixed_thresholds(name)
    w = weather(profile=profile)
    expected = predict(name, params, w.rename(columns={"Tmean": "tmean_c"}), [("A", 2000)])
    actual = accelerated().predict_with_starts(name, params, w, [("A", 2000)], temperature_column="Tmean")
    pd.testing.assert_series_equal(actual.predicted_date, expected.predicted_date, check_names=False)
    assert actual.status.tolist() == expected.status.tolist()


@pytest.mark.parametrize("name", list_models())
def test_threshold_equality_matches_reference_on_leap_year_and_prior_season(name):
    params = fixed_thresholds(name, forcing=10.0, chilling=3.0)
    w = weather(season=2000, profile="constant")
    expected = predict(name, params, w.rename(columns={"Tmean": "tmean_c"}), [("A", 2000)])
    actual = accelerated().predict_with_starts(name, params, w, [("A", 2000)], temperature_column="Tmean")
    pd.testing.assert_series_equal(actual.predicted_date, expected.predicted_date, check_names=False)


@pytest.mark.parametrize("name", list_models())
def test_deterministic_random_thresholds_match_reference(name):
    rng = np.random.default_rng(20260909)
    w = weather(profile="mixed")
    for _ in range(6):
        params = fixed_thresholds(name, forcing=float(rng.uniform(.001, 55)),
                                  chilling=float(rng.uniform(.001, 50)))
        for stage in ("07", "65", "81", "89"):
            params[f"forcing_requirement_{stage}"] = float(rng.uniform(.001, 65))
        expected = predict(name, params, w.rename(columns={"Tmean": "tmean_c"}), [("A", 2000)])
        actual = accelerated().predict_with_starts(name, params, w, [("A", 2000)], temperature_column="Tmean")
        pd.testing.assert_series_equal(actual.predicted_date, expected.predicted_date, check_names=False)
        assert actual.status.tolist() == expected.status.tolist()


@pytest.mark.parametrize("name", ["CL-FL-S", "CB-FB-S"])
def test_unmet_chilling_and_unmet_forcing_match_reference(name):
    params = fixed_thresholds(name, forcing=1e6, chilling=1e6)
    w = weather(profile="cold")
    expected = predict(name, params, w.rename(columns={"Tmean": "tmean_c"}), [("A", 2000)])
    actual = accelerated().predict_with_starts(name, params, w, [("A", 2000)], temperature_column="Tmean")
    pd.testing.assert_series_equal(actual.predicted_date, expected.predicted_date, check_names=False)
    assert actual.status.tolist() == expected.status.tolist()


@pytest.mark.parametrize("name, first_start", [("FL", "2000-01-01"), ("CL-FL-P", "1999-09-01"),
                                                  ("CL-FL-S", "1999-09-02")])
def test_phase_start_dates_follow_model_accumulation(name, first_start):
    params = fixed_thresholds(name, forcing=10.0, chilling=1.0)
    input_weather = weather(profile="constant")
    if name == "CL-FL-S":
        input_weather["Tmean"] = 1.7  # One triangular chilling unit on the first day.
    result = accelerated().predict_with_starts(name, params, input_weather, [("A", 2000)],
                                                temperature_column="Tmean")
    assert result.phase_start_date.iloc[0] == pd.Timestamp(first_start)
    assert result.phase_start_date.iloc[1] == result.predicted_date.iloc[0] + pd.Timedelta(days=1)


def test_fit_uses_compiled_backend_preserves_reference_objective_and_hashes():
    name = "FL"
    params = fixed_thresholds(name, forcing=10.0)
    w = weather(profile="constant")
    reference = predict(name, params, w.rename(columns={"Tmean": "tmean_c"}), [("A", 2000)])
    observations = pd.concat([reference.assign(site="A"), reference.assign(site="B")], ignore_index=True)
    observations = observations[["site", "BBCH", "predicted_date"]].rename(columns={"predicted_date": "Date"})
    weather_two = pd.concat([w, w.assign(site="B")], ignore_index=True)
    settings = threshold_only_settings(name, seeds=(13,), maxiter=1, popsize=5, temperature_column="Tmean",
                                       temperature_input="DEM")
    fast = accelerated().fit(name, observations, weather_two, settings)
    reference_fit = importlib.import_module("model.calibration").fit(name, observations, weather_two, settings)
    assert fast.objective_value == pytest.approx(reference_fit.objective_value, abs=1e-10)
    assert fast.calibration_hash == reference_fit.calibration_hash
    assert fast.weather_hash == reference_fit.weather_hash
    assert fast.temperature_input == "DEM"
    assert fast.diagnostics["engine"] == "numba"
    assert fast.diagnostics["compiled_backend"] is True


def test_fit_rejects_non_threshold_only_settings():
    with pytest.raises(ValueError, match="threshold_only_settings|fixed-response"):
        accelerated().fit("FL", pd.DataFrame(), pd.DataFrame())


def test_vectorized_errors_mask_missing_positions_and_preserve_repeated_rows():
    m = accelerated()
    assert hasattr(m, '_gather_errors'), 'Vectorized residual gather is not implemented'
    result = m._gather_errors(np.array([[0, 1, -1, 2], [1, 0, 2, -1]]),
        np.array([[100, 101, 102], [200, 201, 202]]), np.array([0, 1, 0, 0, 1]),
        np.array([0, 0, 2, 0, 2]), np.array([98, 204, 99, 98, -163]))
    np.testing.assert_array_equal(result.view(np.uint64),
                                  np.array([2., -3., np.nan, 2., 365.]).view(np.uint64))
    result = m._gather_errors(np.full((2, 4), -1), np.empty((2, 0), dtype=np.int64),
                             np.array([0, 1]), np.array([0, 3]), np.array([1, 2]))
    assert np.isnan(result).all()


@pytest.mark.parametrize('name', list_models())
def test_vectorized_gather_preserves_complete_seeded_fit(name, monkeypatch):
    m = accelerated()
    assert hasattr(m, '_gather_errors'), 'Vectorized residual gather is not implemented'
    w = weather(profile='mixed')
    # Tiny synthetic thresholds can attain chilling models in the preceding
    # calendar year. Calibration seasons are defined by observation year, so
    # use explicit observations in the season covered by this weather fixture.
    obs = pd.DataFrame({'site': ['A'] * 4, 'BBCH': ['07', '65', '81', '89'],
                        'Date': pd.to_datetime(['2000-04-15', '2000-06-15',
                                                '2000-08-15', '2000-09-15'])})
    settings = threshold_only_settings(name, seeds=(13,), maxiter=15, popsize=5,
                                       temperature_column='Tmean', temperature_input='RAW')
    candidate = m.fit(name, obs, w, settings)

    def scalar_gather(positions, date_numbers, season_indices, stage_indices, observed_dates):
        values = np.full(len(season_indices), np.nan, dtype=float)
        for index, (season, stage) in enumerate(zip(season_indices, stage_indices)):
            position = positions[season, stage]
            if position >= 0:
                values[index] = float(date_numbers[season, position] - observed_dates[index])
        return values

    monkeypatch.setattr(m, '_gather_errors', scalar_gather)
    original = m.fit(name, obs, w, settings)
    assert candidate.to_dict() == original.to_dict()
