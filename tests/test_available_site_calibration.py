"""Interim all-available cohort: no site/grid leakage or response refitting."""
import importlib
import json

import pandas as pd
import pytest

from test_ten_site_calibration import inputs


def api():
    try:
        return importlib.import_module("model_run.src.calibrate_available_sites")
    except ModuleNotFoundError:
        pytest.fail("The all-available-sites runner is missing")


def test_all_available_sites_retained_with_groups_and_reproducible_split(tmp_path):
    mod = api()
    inv, obs, weather = inputs(tmp_path)
    frame = pd.read_csv(inv)
    frame.loc[1, "era5_grid_id"] = frame.loc[0, "era5_grid_id"]
    frame.to_csv(inv, index=False)
    cohort = mod.prepare_available(inv, obs, weather, seed=123)
    sites = cohort["sites"]
    assert len(sites) == 14
    assert sites.groupby("group_id").partition.nunique().eq(1).all()
    assert set(cohort["observations"].site) == set(sites.site)
    assert len(cohort["observations"]) == 28
    assert sites.stages.str.split("|").map(len).eq(2).all()
    assert 2 <= sites.partition.eq("test").sum() <= 4
    pd.testing.assert_frame_equal(sites, mod.prepare_available(inv, obs, weather, seed=123)["sites"])
    assert cohort["metadata"]["temperature_zone_stratified"] is False


def test_missing_weather_and_out_of_inventory_observations_are_audited(tmp_path):
    mod = api()
    inv, obs, directory = inputs(tmp_path)
    (directory / "vine0.csv").unlink()
    data = pd.read_csv(obs, dtype=str, keep_default_na=False)
    extra = data.iloc[[0]].assign(site="ES:pep725:1:1", country="ES")
    pd.concat([data, extra], ignore_index=True).to_csv(obs, index=False)
    cohort = mod.prepare_available(inv, obs, directory, seed=123)
    assert len(cohort["sites"]) == 13
    assert cohort["metadata"]["canonical_sites_outside_inventory"] == 1
    assert "unavailable" in cohort["eligibility"].set_index("site").loc["FR:tempo:000", "reason"]


def test_interim_fit_keeps_responses_fixed_and_test_outcomes_out_of_fit(tmp_path):
    mod = api()
    from model.structure_comparison import fixed_parameters, threshold_only_settings
    from model_run.src.calibrate_ten_sites import save_cohort, run_model, verify_run
    cohort = mod.prepare_available(*inputs(tmp_path), seed=123)
    settings = threshold_only_settings("FL", seeds=(1,), maxiter=1, popsize=2, temperature_column="Tmean")
    baseline = mod.baseline_parameters("FL")
    assert baseline["start_doy"] == 1
    assert all(baseline[f"forcing_base_{stage}"] == 0 for stage in ("07", "65", "81", "89"))
    out = tmp_path / "run"
    save_cohort(cohort, out)
    result = run_model("FL", cohort, settings, out, baseline_parameters=baseline)
    fit = json.loads((out / "FL/fit.json").read_text())
    assert fit["diagnostics"]["n_sites"] == cohort["sites"].partition.eq("calibration").sum()
    assert all(fit["parameters"][k] == v for k, v in fixed_parameters("FL").items())
    verify_run(out, names=["FL"], expected_site_counts=None)
    altered = {**cohort, "observations": cohort["observations"].copy()}
    ids = cohort["sites"].loc[lambda x: x.partition.eq("test"), "site"]
    altered["observations"].loc[lambda x: x.site.isin(ids), "Date"] += pd.Timedelta(days=8)
    second = run_model("FL", altered, settings, tmp_path / "second", baseline_parameters=baseline)
    fitted2 = json.loads((tmp_path / "second/FL/fit.json").read_text())
    assert fitted2["calibration_hash"] == fit["calibration_hash"]
    assert fitted2["parameters"] == fit["parameters"]
    pd.testing.assert_frame_equal(result["predictions"], second["predictions"])
    with pytest.raises(FileExistsError):
        save_cohort(cohort, out)
