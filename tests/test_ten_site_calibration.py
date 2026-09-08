"""Pilot split leakage, weather eligibility and paired error regressions."""
import importlib
import json

import numpy as np
import pandas as pd
import pytest


def api():
    try:
        return importlib.import_module("model_run.src.calibrate_ten_sites")
    except ModuleNotFoundError:
        pytest.fail("The ten-site calibration runner is missing")


def inputs(tmp_path):
    inventory, observations, weather = [], [], []
    directory = tmp_path / "weather"
    directory.mkdir()
    for i in range(14):
        site = f"FR:tempo:{i:03}"
        inventory.append(dict(site_uid=f"France|france_tempo|{i:03}", site_name=f"vine{i}",
                              lat=44+i/10, lon=4., first_year=2000, last_year=2000,
                              era5_grid_id=f"grid{i}"))
        # No site has all four stages: eligibility must be collective.
        stages = [("07", "2000-03-01"), ("65", "2000-05-01")] if i % 2 else [
            ("81", "2000-07-01"), ("89", "2000-09-01")]
        for stage, date in stages:
            observations.append(dict(site=site, variety="", country="FR", lat=44+i/10,
                                     lon=4., Date=date, BBCH=stage))
        pd.DataFrame(dict(Date=pd.date_range("1999-01-01", "2000-12-31"), Tmean=15.)).to_csv(
            directory / f"vine{i}.csv", index=False)
    inv, obs = tmp_path / "inventory.csv", tmp_path / "observations.csv"
    pd.DataFrame(inventory).to_csv(inv, index=False)
    pd.DataFrame(observations).to_csv(obs, index=False)
    return inv, obs, directory


def test_reproducible_six_four_split_keeps_missing_stage_sites_and_groups(tmp_path):
    mod = api()
    inv, obs, weather = inputs(tmp_path)
    frame = pd.read_csv(inv)
    frame.loc[1, "era5_grid_id"] = frame.loc[0, "era5_grid_id"]
    frame.loc[2, ["lat", "lon"]] = frame.loc[0, ["lat", "lon"]]
    frame.to_csv(inv, index=False)
    source = pd.read_csv(obs, dtype=str, keep_default_na=False)
    source.loc[source.site.eq("FR:tempo:002"), "lat"] = "44.0"
    source.to_csv(obs, index=False)
    cohort = mod.prepare_cohort(inv, obs, weather, seed=123)
    split = cohort["sites"]
    assert split.groupby("partition").size().to_dict() == {"calibration": 6, "test": 4}
    assert split.group_id.nunique() == 10
    assert split.site.nunique() == 10
    assert split.stages.str.split("|").map(len).eq(2).all()
    for partition in ("calibration", "test"):
        ids = split.loc[split.partition.eq(partition), "site"]
        assert set(cohort["observations"].loc[lambda x: x.site.isin(ids), "BBCH"]) == {"07", "65", "81", "89"}
    second = mod.prepare_cohort(inv, obs, weather, seed=123)
    pd.testing.assert_frame_equal(split, second["sites"])


def test_incomplete_weather_and_coordinate_mismatch_are_audited(tmp_path):
    mod = api()
    inv, obs, directory = inputs(tmp_path)
    weather = pd.read_csv(directory / "vine0.csv")
    weather[weather.Date.ne("1999-09-01")].to_csv(directory / "vine0.csv", index=False)
    observations = pd.read_csv(obs)
    observations.loc[observations.site.eq("FR:tempo:001"), "lat"] = np.nan
    observations.to_csv(obs, index=False)
    cohort = mod.prepare_cohort(inv, obs, directory, seed=123)
    assert not set(cohort["sites"].site) & {"FR:tempo:000", "FR:tempo:001"}
    rejected = cohort["eligibility"].set_index("site")
    assert "Incomplete daily weather" in rejected.loc["FR:tempo:000", "reason"]
    assert "coordinates" in rejected.loc["FR:tempo:001", "reason"]


def test_paired_summary_does_not_reward_missing_predictions():
    mod = api()
    comparison = pd.DataFrame(dict(model="FL", partition="test", BBCH="07",
        observation_id=[0, 1, 2, 0, 1, 2], site=["a", "a", "b"]*2,
        parameter_source=["default"]*3+["calibrated"]*3,
        delta_days=[10., 20., 100., 5., 5., np.nan]))
    row = mod.summarize_improvement(comparison).iloc[0]
    assert row.n_observations == 3 and row.n_paired == 2
    assert row.default_attainment_rate == 1 and row.calibrated_attainment_rate == pytest.approx(2/3)
    assert row.paired_default_mae == 15 and row.paired_calibrated_mae == 5
    assert row.mae_improvement_days == 10
    assert row.n_sites_paired == 1


def test_real_fit_uses_six_sites_and_saved_comparisons_keep_test_independent(tmp_path):
    mod = api()
    inv, obs, directory = inputs(tmp_path)
    from model.calibration import FitSettings
    from model.parameters import default_parameters
    defaults = default_parameters("FL")
    bounds = {key: (value, value) for key, value in defaults.items()}
    bounds["start_doy"] = (1, 10)
    settings = FitSettings(bounds=bounds, seeds=(1,), maxiter=0, popsize=1, temperature_column="Tmean")
    cohort = mod.prepare_cohort(inv, obs, directory, seed=123)
    result = mod.run_model("FL", cohort, settings, tmp_path / "fit")
    saved = json.loads((tmp_path / "fit/FL/fit.json").read_text())
    assert saved["diagnostics"]["n_sites"] == 6
    assert saved["diagnostics"]["n_observations"] == 12
    assert json.loads((tmp_path / "fit/FL/default_parameters.json").read_text()) == defaults
    assert result["comparison"].groupby(["partition", "parameter_source"]).size().to_dict() == {
        ("calibration", "calibrated"): 12, ("calibration", "default"): 12,
        ("test", "calibrated"): 8, ("test", "default"): 8}
    changed = {**cohort, "observations": cohort["observations"].copy()}
    test_ids = cohort["sites"].loc[lambda x: x.partition.eq("test"), "site"]
    changed["observations"].loc[lambda x: x.site.isin(test_ids), "Date"] += pd.Timedelta(days=5)
    result2 = mod.run_model("FL", changed, settings, tmp_path / "fit2")
    saved2 = json.loads((tmp_path / "fit2/FL/fit.json").read_text())
    assert saved2["calibration_hash"] == saved["calibration_hash"]
    assert saved2["weather_hash"] == saved["weather_hash"]
    assert saved2["parameters"] == saved["parameters"]
    pd.testing.assert_frame_equal(result["predictions"], result2["predictions"])
    with pytest.raises(FileExistsError):
        mod.run_model("FL", cohort, settings, tmp_path / "fit")


def test_frozen_cohort_round_trip_and_tamper_detection(tmp_path):
    mod = api()
    cohort = mod.prepare_cohort(*inputs(tmp_path), seed=123)
    mod.save_cohort(cohort, tmp_path / "snapshot")
    loaded = mod.load_cohort(tmp_path / "snapshot")
    pd.testing.assert_frame_equal(cohort["observations"].reset_index(drop=True), loaded["observations"])
    assert loaded["sites"].partition.tolist().count("test") == 4
    assert loaded["observations"].variety.eq("").all()
    path = tmp_path / "snapshot/weather.csv"
    weather = pd.read_csv(path)
    weather.loc[0, "Tmean"] += 1
    weather.to_csv(path, index=False)
    with pytest.raises(ValueError, match="checksum"):
        mod.load_cohort(tmp_path / "snapshot")


def test_overall_summary_requires_all_four_stages_and_uses_equal_stage_weights():
    mod = api()
    stage = pd.DataFrame(dict(model="FL", partition="test", BBCH=["07", "65", "81", "89"],
        n_observations=[1, 2, 3, 10], n_paired=[1, 2, 3, 10], n_sites_paired=[1, 1, 2, 3],
        default_attainment_rate=1., calibrated_attainment_rate=1.,
        paired_default_mae=[10., 20., 30., 40.], paired_calibrated_mae=[5., 10., 15., 20.],
        paired_default_rmse=[10., 20., 30., 40.], paired_calibrated_rmse=[5., 10., 15., 20.],
        paired_default_bias=[10., 20., 30., 40.], paired_calibrated_bias=[5., 10., 15., 20.]))
    row = mod.overall_summary(stage).iloc[0]
    assert row.mean_stage_default_mae == 25
    assert row.mean_stage_calibrated_mae == 12.5
    assert row.mae_improvement_percent == 50
    stage.loc[3, "paired_calibrated_mae"] = np.nan
    assert np.isnan(mod.overall_summary(stage).iloc[0].mean_stage_calibrated_mae)


@pytest.mark.parametrize("column,value", [("delta_days", 99), ("predicted_date", "2000-12-31"),
                                         ("status", "unmet_forcing"), ("absolute_error_days", 99)])
def test_saved_run_verification_detects_altered_prediction(tmp_path, column, value):
    mod = api()
    from model.calibration import FitSettings
    from model.parameters import default_parameters
    cohort = mod.prepare_cohort(*inputs(tmp_path), seed=123)
    out = tmp_path / "result"
    mod.save_cohort(cohort, out)
    bounds = {key: (value, value) for key, value in default_parameters("FL").items()}
    settings = FitSettings(bounds=bounds, maxiter=0, seeds=(1,), popsize=1, temperature_column="Tmean")
    mod.run_model("FL", cohort, settings, out)
    checks = mod.verify_run(out, names=["FL"])
    assert checks["calibration_sites"] == 6 and checks["test_sites"] == 4
    assert checks["verified_models"] == ["FL"]
    path = out / "FL/comparison.csv"
    comparison = pd.read_csv(path, dtype={"BBCH": str})
    comparison.loc[0, column] = value
    comparison.to_csv(path, index=False)
    with pytest.raises(AssertionError):
        mod.verify_run(out, names=["FL"])


def test_verification_checks_weather_hash_and_combined_summary(tmp_path, monkeypatch):
    mod = api()
    from model.calibration import FitSettings
    from model.parameters import default_parameters
    from model.artifacts import write_csv
    cohort = mod.prepare_cohort(*inputs(tmp_path), seed=123)
    out = tmp_path / "result"
    mod.save_cohort(cohort, out)
    bounds = {key: (value, value) for key, value in default_parameters("FL").items()}
    result = mod.run_model("FL", cohort, FitSettings(bounds=bounds, maxiter=0, seeds=(1,),
                                                    popsize=1, temperature_column="Tmean"), out)
    for key in ("comparison", "predictions", "metrics", "improvement"):
        write_csv(result[key], out / f"{key}.csv")
    write_csv(mod.overall_summary(result["improvement"]), out / "summary.csv")
    # Restrict the catalogue, not simulation or metrics, to keep this audit regression small.
    monkeypatch.setattr(mod, "list_models", lambda: ("FL",))
    mod.verify_run(out)
    original = (out / "FL/fit.json").read_text()
    changed = json.loads(original)
    changed["weather_hash"] = "0" * 64
    (out / "FL/fit.json").write_text(json.dumps(changed))
    with pytest.raises(AssertionError):
        mod.verify_run(out)
    (out / "FL/fit.json").write_text(original)
    summary = pd.read_csv(out / "summary.csv")
    summary.loc[0, "mean_stage_calibrated_mae"] += 1
    summary.to_csv(out / "summary.csv", index=False)
    with pytest.raises(AssertionError):
        mod.verify_run(out)
