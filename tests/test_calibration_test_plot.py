"""Calibration/test figure preserves both partitions and incomplete attainment."""
import importlib

import pandas as pd
import pytest


def api():
    try:
        return importlib.import_module("model_run.src.plot_calibration_test")
    except ModuleNotFoundError:
        pytest.fail("Calibration/test plotting module missing")


def metrics():
    return pd.DataFrame([dict(model=name, BBCH=stage, partition=partition,
        parameter_source="calibrated", temperature_input="RAW",
        site_balanced_mae=value, n_observations=10, n_sites=5, n_attained=10,
        n_unattained=0, attainment_rate=1.)
        for name in ["FL", "FB"] for stage in ["07", "65", "81", "89"]
        for partition, value in [("calibration", 5.), ("test", 8.)]])


def test_keeps_both_partitions_and_flags_unattained_events():
    mod = api()
    data = metrics()
    ix = data.index[(data.model == "FB") & (data.partition == "test") & (data.BBCH == "89")][0]
    data.loc[ix, ["n_attained", "n_unattained", "attainment_rate"]] = [9, 1, .9]
    values, spec = mod.prepare_plot(data, ["FL", "FB"])
    assert len(values) == 16
    assert spec["panels"][0]["calibration"] == [5., 5.]
    assert spec["panels"][0]["test"] == [8., 8.]
    assert spec["panels"][3]["test_missing"] == [0, 1]
    assert spec["y_min"] == 0 and spec["y_max"] > 8
    assert spec["omitted_models"] == ["CL-FL-S", "CL-FL-P", "CB-FL-S", "CB-FL-P", "CL-FB-S", "CL-FB-P", "CB-FB-S", "CB-FB-P"]


@pytest.mark.parametrize("issue", ["duplicate", "missing", "different_counts", "negative", "bad_attainment"])
def test_rejects_misleading_inputs(issue):
    mod = api()
    data = metrics()
    if issue == "duplicate":
        data = pd.concat([data, data.iloc[[0]]])
    elif issue == "missing":
        data = data.iloc[1:]
    elif issue == "different_counts":
        data.loc[0, ["n_observations", "n_attained"]] = [11, 11]
    elif issue == "negative":
        data.loc[0, "site_balanced_mae"] = -1
    else:
        data.loc[0, "attainment_rate"] = .5
    with pytest.raises(ValueError):
        mod.prepare_plot(data, ["FL", "FB"])
