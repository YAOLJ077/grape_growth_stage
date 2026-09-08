"""The one-site example compares actual observations without fitting to them."""
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from model.artifacts import save_fit
from model.calibration import FitSettings, fit
from model.registry import list_models
from test_model_calibration import fixture


def api():
    try:
        return importlib.import_module("model_run.src.run_first_site")
    except ModuleNotFoundError:
        pytest.fail("The first-site comparison script is missing")


def inputs(tmp_path):
    inventory = tmp_path / "inventory.csv"
    pd.DataFrame([dict(site_uid="France|france_tempo|001", site_name="Test vineyard",
                       lat=44., lon=4., first_year=2000, last_year=2000)]).to_csv(inventory, index=False)
    observations = tmp_path / "observations.csv"
    pd.DataFrame({"site": ["FR:tempo:001"] * 3 + ["FR:tempo:other"],
                  "variety": ["A", "B", "", ""], "country": "FR", "lat": 44., "lon": 4.,
                  "Date": ["2000-03-01", "2000-03-02", "2000-05-01", "2000-06-01"],
                  "BBCH": ["07", "07", "65", "07"]}).to_csv(observations, index=False)
    directory = tmp_path / "weather"
    directory.mkdir()
    pd.DataFrame({"Date": pd.date_range("1999-01-01", "2000-12-31"), "Tmean": 10.}).to_csv(
        directory / "Test vineyard.csv", index=False)
    return inventory, observations, directory


def test_demo_uses_first_inventory_site_keeps_repeats_and_signed_deltas(tmp_path):
    mod = api()
    inventory, obs, weather = inputs(tmp_path)
    out = tmp_path / "result"
    result = mod.run(inventory, obs, weather, out)
    comparison = result["comparison"]
    # Default FL: 300 degree-days / (10-5) = 60 days per stage, Jan1 inclusive.
    assert comparison.predicted_date.dt.strftime("%Y-%m-%d").tolist() == ["2000-02-29", "2000-02-29", "2000-04-29"]
    assert comparison.delta_days.tolist() == [-1, -2, -2]
    assert comparison.variety.tolist() == ["A", "B", ""]
    assert comparison.site.unique().tolist() == ["FR:tempo:001"]
    assert len(result["predictions"]) == 4
    assert result["metadata"]["parameter_source"] == "illustrative_uncalibrated"
    assert pd.read_csv(out / "comparison.csv").delta_days.tolist() == [-1, -2, -2]
    assert set(json.loads((out / "run.json").read_text())["input_sha256"]) == {"inventory", "observations", "weather"}
    before = (out / "comparison.csv").read_bytes()
    with pytest.raises(FileExistsError):
        mod.run(inventory, obs, weather, out)
    assert (out / "comparison.csv").read_bytes() == before


def test_no_observations_or_incomplete_weather_fails_without_outputs(tmp_path):
    mod = api()
    inventory, obs, weather = inputs(tmp_path)
    raw = pd.read_csv(weather / "Test vineyard.csv")
    raw = raw[raw.Date.ne("2000-06-01")]
    raw.to_csv(weather / "Test vineyard.csv", index=False)
    with pytest.raises(ValueError, match="weather"):
        mod.run(inventory, obs, weather, tmp_path / "result")
    assert not (tmp_path / "result").exists()
    observed = pd.read_csv(obs)
    observed["site"] = "unrelated"
    observed.to_csv(obs, index=False)
    with pytest.raises(ValueError, match="observations"):
        mod.run(inventory, obs, weather, tmp_path / "result")


def test_saved_fit_is_reused_without_fitting_to_comparison_observations(tmp_path):
    mod = api()
    inventory, obs, weather = inputs(tmp_path)
    w, calibration_obs, _, bounds = fixture()
    fitted = fit("FL", calibration_obs, w, FitSettings(bounds=bounds, seeds=(7,), maxiter=5, popsize=5))
    artifact = tmp_path / "fit.json"
    save_fit(fitted, artifact)
    result = mod.run(inventory, obs, weather, tmp_path / "result", fit_path=artifact)
    assert result["predictions"].predicted_doy.tolist() == [2, 4, 6, 8]
    assert result["metadata"]["parameters"] == fitted.parameters
    assert result["metadata"]["parameter_source"] == "saved_fit"
    with pytest.raises(ValueError, match="model"):
        mod.run(inventory, obs, weather, tmp_path / "other", model_name="FB", fit_path=artifact)


def test_dem_fit_cannot_be_run_with_raw_temperature(tmp_path):
    mod = api()
    inventory, obs, weather = inputs(tmp_path)
    w, calibration_obs, _, bounds = fixture()
    fitted = fit("FL", calibration_obs, w, FitSettings(bounds=bounds, seeds=(7,), maxiter=5, popsize=5, temperature_input="DEM"))
    artifact = tmp_path / "fit.json"
    save_fit(fitted, artifact)
    with pytest.raises(ValueError, match="RAW|raw|DEM"):
        mod.run(inventory, obs, weather, tmp_path / "result", fit_path=artifact)


def test_script_runs_from_another_directory_and_prints_comparison(tmp_path):
    api()
    inventory, obs, weather = inputs(tmp_path)
    script = Path(__file__).resolve().parents[1] / "model_run/src/run_first_site.py"
    result = subprocess.run([sys.executable, str(script), "--inventory", str(inventory),
                             "--observations", str(obs), "--weather-dir", str(weather),
                             "--output", str(tmp_path / "result")], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "uncalibrated" in result.stdout
    assert "delta_days" in result.stdout
    assert "Test vineyard" in result.stdout


@pytest.mark.parametrize("column", ["lat", "lon"])
def test_missing_observation_coordinates_cannot_pass_site_matching(tmp_path, column):
    mod = api()
    inventory, obs, weather = inputs(tmp_path)
    frame = pd.read_csv(obs, dtype=str, keep_default_na=False)
    frame.loc[0, column] = ""
    frame.to_csv(obs, index=False)
    with pytest.raises(ValueError, match="coordinates"):
        mod.run(inventory, obs, weather, tmp_path / "result")
    assert not (tmp_path / "result").exists()


def test_all_models_share_one_comparison_with_explicit_model_column(tmp_path):
    mod = api()
    inventory, obs, weather = inputs(tmp_path)
    out = tmp_path / "all_models"
    result = mod.run(inventory, obs, weather, out, model_name="all")
    comparison = result["comparison"]
    assert comparison.columns[0] == "model"
    assert comparison.model.unique().tolist() == list(list_models())
    assert comparison.groupby("model").size().eq(3).all()
    assert len(result["predictions"]) == 40
    assert result["predictions"].model.eq(result["predictions"].model_name).all()
    assert result["metrics"].model.nunique() == 10
    assert comparison.loc[comparison.model.eq("FL"), "delta_days"].tolist() == [-1, -2, -2]
    assert all(info["parameter_source"] == "illustrative_uncalibrated" for info in result["metadata"]["models"].values())
    assert set(result["metadata"]["models"]) == set(list_models())
    saved = pd.read_csv(out / "comparison.csv")
    assert saved.model.nunique() == 10 and len(saved) == 30
    assert not any(path.is_dir() for path in out.iterdir())


def test_all_model_cli_prints_model_names_and_writes_one_table(tmp_path):
    api()
    inventory, obs, weather = inputs(tmp_path)
    script = Path(__file__).resolve().parents[1] / "model_run/src/run_first_site.py"
    out = tmp_path / "result"
    result = subprocess.run([sys.executable, str(script), "--model", "all", "--inventory", str(inventory),
                             "--observations", str(obs), "--weather-dir", str(weather),
                             "--output", str(out)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "CL-FL-S" in result.stdout and "CB-FB-P" in result.stdout
    assert pd.read_csv(out / "comparison.csv").model.nunique() == 10


def test_single_saved_fit_cannot_be_applied_to_all_model_structures(tmp_path):
    mod = api()
    inventory, obs, weather = inputs(tmp_path)
    with pytest.raises(ValueError, match="saved fit|--fit"):
        mod.run(inventory, obs, weather, tmp_path / "result", model_name="all", fit_path=tmp_path / "one_fit.json")
    assert not (tmp_path / "result").exists()
