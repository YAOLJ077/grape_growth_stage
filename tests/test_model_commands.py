"""Saved fits and real subprocess commands must preserve predictions and failures."""
import importlib
import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from model.calibration import FitSettings, fit
from model.simulation import predict
from test_model_calibration import fixture


def api(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        pytest.fail(f"Required interface missing: {name}")


def fitted():
    weather, obs, _, bounds = fixture()
    return fit("FL", obs, weather, FitSettings(bounds=bounds, seeds=(1,), maxiter=5, popsize=5)), weather, obs


def test_fit_round_trip_reproduces_dates_and_refuses_overwrite(tmp_path):
    io = api("model.artifacts")
    result, weather, _ = fitted()
    path = tmp_path / "fit.json"
    io.save_fit(result, path)
    restored = io.load_fit(path)
    assert restored.parameters == result.parameters
    assert restored.bounds == result.bounds
    pd.testing.assert_frame_equal(predict("FL", result.parameters, weather, [("A", 2000)]),
                                  predict("FL", restored.parameters, weather, [("A", 2000)]))
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        io.save_fit(result, path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("defect", ["version", "parameters", "label", "model", "nan"])
def test_corrupt_fit_cannot_silently_change_model_identity(tmp_path, defect):
    io = api("model.artifacts")
    result, _, _ = fitted()
    path = tmp_path / "fit.json"
    io.save_fit(result, path)
    payload = json.loads(path.read_text())
    if defect == "version":
        payload["definition_version"] = "999.0.0"
    elif defect == "parameters":
        payload["parameters"]["forcing_requirement_07"] = -1
    elif defect == "label":
        payload["temperature_input"] = "unknown"
    elif defect == "model":
        payload["model_name"] = "FL-ML"
    else:
        payload["objective_value"] = float("nan")
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        io.load_fit(path)


def test_metrics_include_missing_events_and_are_site_balanced():
    metrics = api("model.metrics")
    obs = pd.DataFrame({"site": ["A", "A", "B", "C"], "Date": ["2000-01-01"] * 4, "BBCH": ["07"] * 4})
    predicted = pd.DataFrame({"site": ["A", "B", "C"], "season": [2000] * 3, "BBCH": ["07"] * 3,
                              "predicted_date": pd.to_datetime(["2000-01-01", "2000-01-11", None]),
                              "status": ["attained", "attained", "unmet_forcing"],
                              "model_name": "FL", "temperature_input": "RAW"})
    row = metrics.evaluate(obs, predicted).iloc[0]
    assert row.n_observations == 4 and row.n_attained == 3 and row.n_unattained == 1
    assert row.mae == pytest.approx(10 / 3)
    assert row.site_balanced_mae == 5
    assert row.site_balanced_rmse == pytest.approx(np.sqrt(50))
    assert row.site_balanced_bias == 5
    with pytest.raises(ValueError):
        metrics.evaluate(obs, predicted.iloc[:2])


def test_metrics_reject_duplicate_prediction_keys_and_report_all_missing():
    metrics = api("model.metrics")
    result, weather, obs = fitted()
    predicted = predict("FL", result.parameters, weather, [("A", 2000)])
    with pytest.raises(ValueError):
        metrics.evaluate(obs, pd.concat([predicted, predicted.iloc[:1]]))
    predicted["predicted_date"] = pd.NaT
    predicted["status"] = "unmet_forcing"
    summary = metrics.evaluate(obs, predicted)
    assert summary.n_attained.eq(0).all() and summary.mae.isna().all()


def test_metrics_accept_pandas_string_status_dtype():
    result, weather, obs = fitted()
    predicted = predict("FL", result.parameters, weather, [("A", 2000)])
    expected = api("model.metrics").evaluate(obs, predicted)
    predicted["status"] = predicted.status.astype("string")
    pd.testing.assert_frame_equal(api("model.metrics").evaluate(obs, predicted), expected)


@pytest.mark.parametrize("value", ["2000-01-01 23:59:59", 946771200000000000])
def test_metrics_reject_non_calendar_prediction_dates(value):
    result, weather, obs = fitted()
    predicted = predict("FL", result.parameters, weather, [("A", 2000)])
    predicted["predicted_date"] = value
    with pytest.raises(ValueError):
        api("model.metrics").evaluate(obs, predicted)


@pytest.mark.parametrize("mixed", [False, True])
def test_metrics_reject_numeric_dates_inside_object_columns(mixed):
    result, weather, obs = fitted()
    predicted = predict("FL", result.parameters, weather, [("A", 2000)])
    values = [946771200000000000] * 4
    if mixed:
        values[1:] = ["2000-01-04", "2000-01-06", "2000-01-08"]
    predicted["predicted_date"] = pd.Series(values, dtype=object)
    with pytest.raises(ValueError):
        api("model.metrics").evaluate(obs, predicted)


def command(*args):
    return subprocess.run([sys.executable, "-m", "model", *map(str, args)], capture_output=True, text=True)


def test_cli_lists_ten_models_and_rejects_ml_name():
    result = command("list")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == 10
    assert "CB-FB-P" in result.stdout
    invalid = command("fit", "--model", "FL-ML")
    assert invalid.returncode != 0


def test_cli_fit_predict_evaluate_round_trip_with_canonical_observations(tmp_path):
    weather, obs, _, bounds = fixture()
    paths = {name: tmp_path / name for name in ["observations.csv", "weather.csv", "settings.json", "fit.json",
                                                "seasons.csv", "predictions.csv", "metrics.csv"]}
    obs.to_csv(paths["observations.csv"], index=False)
    weather.to_csv(paths["weather.csv"], index=False)
    pd.DataFrame({"site": ["A"], "season": [2000]}).to_csv(paths["seasons.csv"], index=False)
    paths["settings.json"].write_text(json.dumps({"bounds": bounds, "seeds": [7], "maxiter": 5, "popsize": 5}))
    result = command("fit", "--model", "FL", "--calibration-observations", paths["observations.csv"],
                     "--weather", paths["weather.csv"], "--settings", paths["settings.json"], "--output", paths["fit.json"])
    assert result.returncode == 0, result.stderr
    assert paths["fit.json"].is_file()
    result = command("predict", "--fit", paths["fit.json"], "--weather", paths["weather.csv"],
                     "--seasons", paths["seasons.csv"], "--output", paths["predictions.csv"])
    assert result.returncode == 0, result.stderr
    predictions = pd.read_csv(paths["predictions.csv"], dtype={"BBCH": str})
    assert predictions.BBCH.tolist() == ["07", "65", "81", "89"]
    assert predictions.predicted_doy.tolist() == [2, 4, 6, 8]
    result = command("evaluate", "--observations", paths["observations.csv"],
                     "--predictions", paths["predictions.csv"], "--output", paths["metrics.csv"])
    assert result.returncode == 0, result.stderr
    assert pd.read_csv(paths["metrics.csv"]).mae.eq(0).all()


def test_cli_missing_weather_reports_actionable_error_without_output(tmp_path):
    weather, obs, _, _ = fixture()
    observation_path = tmp_path / "obs.csv"
    obs.to_csv(observation_path, index=False)
    output = tmp_path / "fit.json"
    result = command("fit", "--model", "FL", "--calibration-observations", observation_path,
                     "--weather", tmp_path / "absent.csv", "--output", output)
    assert result.returncode != 0
    assert "absent.csv" in result.stderr
    assert not output.exists()
