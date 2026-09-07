"""Calibration contracts: real optimizations, balanced losses, no held-out input."""
import importlib

import numpy as np
import pandas as pd
import pytest

from model.parameters import default_bounds, default_parameters
from model.registry import list_models
from model.simulation import predict


def calibration():
    try:
        return importlib.import_module("model.calibration")
    except ModuleNotFoundError:
        pytest.fail("The shared calibration module is not implemented")


def fixture(name="FL"):
    dates = pd.date_range("1999-09-01", "2000-12-31")
    # 0 deg C prior to Jan 1 prevents prior-year budburst in the synthetic target.
    temperatures = np.where(dates.year < 2000, 0., 10.)
    w = pd.DataFrame({"site": "A", "Date": dates, "tmean_c": temperatures})
    p = default_parameters(name)
    for stage in ("07", "65", "81", "89"):
        p[f"forcing_requirement_{stage}"] = 10. if "forcing_base_07" in p else 2.
        key = f"forcing_base_{stage}" if "forcing_base_07" in p else f"forcing_optimum_{stage}"
        p[key] = 5. if "forcing_base_07" in p else 10.
    if "chilling_requirement" in p:
        p.update(chilling_minimum=-5., chilling_optimum=0., chilling_maximum=10., chilling_requirement=3.)
    rows = [{"site": "A", "variety": "", "country": "DE", "lat": 50., "lon": 8.,
             "Date": f"2000-01-{day:02}", "BBCH": stage}
            for stage, day in zip(("07", "65", "81", "89"), (2, 4, 6, 8))]
    # Fit four independently variable requirements; keep response parameters fixed
    # through equal bounds so the optimizer smoke test has a known exact solution.
    bounds = {key: (p[key], p[key]) for key in default_bounds(name)}
    for stage in ("07", "65", "81", "89"):
        value = p[f"forcing_requirement_{stage}"]
        bounds[f"forcing_requirement_{stage}"] = (value * .8, value * 1.2)
    return w, pd.DataFrame(rows), p, bounds


@pytest.mark.parametrize("name", list_models())
def test_real_calibration_for_all_ten_models_reaches_known_dates(name):
    mod = calibration()
    w, obs, parameters, bounds = fixture(name)
    fitted = mod.fit(name, obs, w, mod.FitSettings(bounds=bounds, seeds=(7,), maxiter=30, popsize=5))
    assert fitted.objective_value == pytest.approx(0)
    result = predict(name, fitted.parameters, w, [("A", 2000)])
    assert result.predicted_doy.tolist() == [2, 4, 6, 8]
    assert fitted.diagnostics["n_observations"] == 4
    assert fitted.temperature_input == "RAW"
    assert fitted.definition_version


@pytest.mark.parametrize("name", ["FL", "FB", "CL-FL-S", "CB-FB-P"])
def test_joint_optimization_with_all_parameters_free_and_overlapping_chilling_bounds(name):
    mod = calibration()
    w, obs, p, _ = fixture(name)
    bounds = {}
    for key in default_bounds(name):
        if key == "start_doy":
            bounds[key] = (0, 2)
        elif key.startswith("chilling_") and key != "chilling_requirement":
            # Overlapping ranges force the optimizer's ordering constraints to act.
            bounds[key] = {"chilling_minimum": (-6, 1), "chilling_optimum": (-1, 6),
                           "chilling_maximum": (5, 11)}[key]
        else:
            bounds[key] = (p[key] * .9, p[key] * 1.1)
    result = mod.fit(name, obs, w, mod.FitSettings(bounds=bounds, seeds=(7,), maxiter=10, popsize=5))
    assert np.isfinite(result.objective_value)
    assert result.objective_value < 10
    assert not result.diagnostics["fixed_by_equal_bounds"]
    if "start_doy" in result.parameters:
        assert result.parameters["start_doy"] == int(result.parameters["start_doy"])
    if "chilling_minimum" in result.parameters:
        assert result.parameters["chilling_optimum"] - result.parameters["chilling_minimum"] >= .1 - 1e-12
        assert result.parameters["chilling_maximum"] - result.parameters["chilling_optimum"] >= .1 - 1e-12


def test_balanced_loss_has_equal_stage_and_site_weight_and_missing_penalty():
    mod = calibration()
    obs = pd.DataFrame({"site": ["A", "A", "B", "A", "A", "A"],
                        "BBCH": ["07", "07", "07", "65", "81", "89"]})
    # Stage07 site MSE=(0+0)/2 and 100: RMSE=sqrt(50); others zero.
    assert mod.balanced_loss(obs, np.array([0, 0, 10, 0, 0, 0.])) == pytest.approx(np.sqrt(50) / 4)
    # A missing date contributes 1000^2, it is not dropped.
    assert mod.balanced_loss(obs, np.array([0, 0, np.nan, 0, 0, 0.])) == pytest.approx(np.sqrt(500000) / 4)


def test_rounded_cardinal_gap_is_feasible_for_both_prediction_and_calibration():
    mod = calibration()
    w, _, p, _ = fixture("CL-FL-S")
    w["tmean_c"] = np.where(w.Date.dt.year < 2000, .3, 10.)
    p.update(chilling_minimum=.2, chilling_optimum=.3, chilling_maximum=10.)
    predicted = predict("CL-FL-S", p, w, [("A", 2000)])
    obs = predicted[["site", "BBCH", "predicted_date"]].rename(columns={"predicted_date": "Date"})
    bounds = {key: (p[key], p[key]) for key in default_bounds("CL-FL-S")}
    result = mod.fit("CL-FL-S", obs, w, mod.FitSettings(bounds=bounds, seeds=(1,), maxiter=1, popsize=5))
    assert result.objective_value == 0


def test_single_stage_sites_are_retained_and_repeated_dates_not_aggregated():
    mod = calibration()
    w, obs, _, bounds = fixture()
    obs["site"] = ["A", "B", "C", "D"]
    obs = pd.concat([obs, obs.iloc[:1]], ignore_index=True)
    w = pd.concat([w.assign(site=site) for site in ("A", "B", "C", "D")], ignore_index=True)
    fit = mod.fit("FL", obs, w, mod.FitSettings(bounds=bounds, seeds=(7,), maxiter=5, popsize=5))
    assert fit.diagnostics["n_observations"] == 5
    assert fit.diagnostics["n_sites"] == 4
    assert fit.objective_value == 0


def test_seed_reproducibility_and_held_out_weather_independence():
    mod = calibration()
    w, obs, _, bounds = fixture()
    settings = mod.FitSettings(bounds=bounds, seeds=(11, 12), maxiter=3, popsize=5)
    first = mod.fit("FL", obs, w, settings)
    # An unrelated held-out site is excluded from prepared data and its hash.
    extra = w.assign(site="TEST", tmean_c=99.)
    second = mod.fit("FL", obs.copy(), pd.concat([w, extra]), settings)
    assert first.parameters == second.parameters
    assert first.calibration_hash == second.calibration_hash
    assert first.weather_hash == second.weather_hash
    assert first.diagnostics["restarts"] == second.diagnostics["restarts"]


def test_calibration_requires_each_stage_somewhere_not_at_every_site():
    mod = calibration()
    w, obs, _, bounds = fixture()
    with pytest.raises(ValueError, match="stage"):
        mod.fit("FL", obs.iloc[:3], w, mod.FitSettings(bounds=bounds))


def test_completely_unattained_stage_cannot_be_a_successful_fit():
    mod = calibration()
    w, obs, _, bounds = fixture()
    w["tmean_c"] = -20
    with pytest.raises(ValueError, match="finite|attain"):
        mod.fit("FL", obs, w, mod.FitSettings(bounds=bounds, seeds=(1,), maxiter=1, popsize=5))


def test_nonconverged_run_is_saved_as_nonconverged():
    mod = calibration()
    w, obs, _, bounds = fixture()
    fitted = mod.fit("FL", obs, w, mod.FitSettings(bounds=bounds, seeds=(7,), maxiter=0, popsize=5))
    assert not fitted.optimizer_converged
    assert fitted.diagnostics["restarts"][0]["nfev"] > 0


def test_default_seed_sequence_and_search_bounds_are_recorded():
    mod = calibration()
    w, obs, parameters, bounds = fixture()
    bounds = {key: (parameters[key], parameters[key]) for key in bounds}
    result = mod.fit("FL", obs, w, mod.FitSettings(bounds=bounds, maxiter=1, popsize=5))
    assert [r["seed"] for r in result.diagnostics["restarts"]] == [20260907, 20260908, 20260909]
    assert result.bounds["start_doy"] == (1., 1.)
    assert result.diagnostics["fixed_by_equal_bounds"]


@pytest.mark.parametrize("defect", ["unknown", "negative", "integer", "cardinals", "seeds"])
def test_invalid_calibration_settings_fail_before_optimization(defect):
    mod = calibration()
    w, obs, _, bounds = fixture("CL-FB-S" if defect == "cardinals" else "FL")
    kwargs = dict(bounds=bounds, seeds=(1,), maxiter=1)
    if defect == "unknown":
        bounds["unused"] = (0, 1)
    elif defect == "negative":
        bounds["forcing_requirement_07"] = (-1, 2)
    elif defect == "integer":
        bounds["start_doy"] = (1.1, 1.2)
    elif defect == "cardinals":
        bounds["chilling_optimum"] = (-10, -10)
    else:
        kwargs["seeds"] = ()
    with pytest.raises(ValueError):
        mod.fit("CL-FB-S" if defect == "cardinals" else "FL", obs, w, mod.FitSettings(**kwargs))
