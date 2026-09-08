"""Fixed response profiles and figures preserve published values and native units."""
import importlib
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from model import fit
from model.registry import list_models


def api(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        pytest.fail(f"Required fixed-response module is missing: {name}")


@pytest.mark.parametrize("name", list_models())
def test_profile_leaves_only_stage_and_chilling_thresholds_free(name):
    mod = api("model.structure_comparison")
    settings = mod.threshold_only_settings(name)
    free = {key for key, (lo, hi) in settings.bounds.items() if lo != hi}
    expected = {f"forcing_requirement_{s}" for s in ("07", "65", "81", "89")}
    if name not in {"FL", "FB"}:
        expected.add("chilling_requirement")
    assert free == expected
    assert all(lo > 0 for key, (lo, hi) in settings.bounds.items() if key in free)


@pytest.mark.parametrize("name", ["FL", "CB-FB-P"])
def test_real_fit_cannot_change_shared_response_temperatures(name):
    mod = api("model.structure_comparison")
    settings = mod.threshold_only_settings(name, seeds=(7,), maxiter=1, popsize=5)
    bounds = {k: ((1., 5.) if "requirement" in k else v) for k, v in settings.bounds.items()}
    dates = pd.date_range("1999-09-01", "2000-12-31")
    weather = pd.DataFrame({"site": "A", "Date": dates, "tmean_c": 5.})
    obs = pd.DataFrame({"site": "A", "Date": pd.to_datetime(["2000-04-01", "2000-06-01", "2000-08-01", "2000-09-01"]),
                        "BBCH": ["07", "65", "81", "89"]})
    fitted = fit(name, obs, weather, replace(settings, bounds=bounds))
    for key, value in mod.fixed_parameters(name).items():
        assert fitted.parameters[key] == value
    assert set(fitted.diagnostics["fixed_by_equal_bounds"]) == {
        k for k, (lo, hi) in bounds.items() if lo == hi}


def test_curve_samples_preserve_units_boundaries_peaks_and_chilling_shapes():
    mod = api("model_run.src.plot_temperature_responses")
    data = mod.curve_data()
    assert set(data.response) == {"FL", "FB", "CL", "CB"}
    assert not data.duplicated(["response", "temperature_c"]).any()
    assert np.isfinite(data.rate).all() and data.rate.ge(0).all()
    def at(response, t):
        return data.loc[data.response.eq(response) & np.isclose(data.temperature_c, t), "rate"].item()
    assert at("FL", 25.4) == pytest.approx(25.4)
    assert at("FL", 40) == pytest.approx(40)  # No artificial high-T cap.
    assert at("FB", 25.4) == pytest.approx(1)
    assert at("FB", 0) == at("FB", 35) == 0
    for response in ["CL", "CB"]:
        assert at(response, -1.7) == at(response, 13.2) == 0
        assert at(response, 1.7) == pytest.approx(1)
    assert at("CL", 5) != pytest.approx(at("CB", 5))
    assert data.loc[data.response.eq("FL"), "rate_unit"].unique().tolist() == ["degree_C_day_per_day"]
    assert data.source_doi.str.len().gt(0).all()


def test_figure_exports_reproducible_data_and_refuses_overwrite(tmp_path):
    mod = api("model_run.src.plot_temperature_responses")
    out = tmp_path / "figure"
    spec = mod.run(out)
    assert spec["panels"] == [["FL", "FB"], ["CL", "CB"]]
    for item in spec["series"]:
        if item["response"] == "FL":
            assert np.asarray(item["display_rate"]) == pytest.approx(np.asarray(item["rate"]) / 25.4)
        else:
            assert item["display_rate"] == pytest.approx(item["rate"])
    pdf = (out / "temperature_responses.pdf").read_bytes()
    assert pdf.startswith(b"%PDF")
    assert (out / "temperature_responses.png").read_bytes().startswith(b"\x89PNG")
    assert len(pd.read_csv(out / "temperature_responses.csv")) >= 1604
    with pytest.raises(FileExistsError):
        mod.run(out)
    assert (out / "temperature_responses.pdf").read_bytes() == pdf


def test_forcing_display_normalization_preserves_native_model_rates():
    data = api("model_run.src.plot_temperature_responses").curve_data()
    assert "display_rate" in data, "Common forcing display scale is missing"
    for response in ["FL", "FB"]:
        row = data.loc[data.response.eq(response) & np.isclose(data.temperature_c, 25.4)].iloc[0]
        assert row.display_rate == pytest.approx(1)
    linear = data.loc[data.response.eq("FL")]
    assert linear.display_rate.to_numpy() == pytest.approx(linear.rate.to_numpy() / 25.4)
    high = linear.loc[np.isclose(linear.temperature_c, 40)].iloc[0]
    assert high.rate == pytest.approx(40)
    assert high.display_rate == pytest.approx(40 / 25.4)  # Do not cap the relative curve at 1.
    chilling = data.loc[data.process.eq("chilling")]
    assert chilling.display_rate.tolist() == chilling.rate.tolist()
