"""MAE histogram uses all calibrated test events and equal stage weights."""
import importlib

import numpy as np
import pandas as pd
import pytest

from model.registry import list_models


def api():
    try:
        return importlib.import_module("model_run.src.plot_mae_histogram")
    except ModuleNotFoundError:
        pytest.fail("MAE histogram script is missing")


def metrics():
    rows = []
    for i, name in enumerate(list_models()):
        for stage, count, error in zip(["07", "65", "81", "89"], [3, 4, 10, 5], [1, 3, 5, 7]):
            rows.append(dict(model=name, BBCH=stage, n_observations=count, n_attained=count,
                             temperature_input="RAW", partition="test", parameter_source="calibrated",
                             site_balanced_mae=float(error+i), mae=999.))
    return pd.DataFrame(rows)


def test_histogram_uses_equal_stage_weight_and_only_calibrated_test_metrics():
    mod = api()
    frame = metrics()
    distractor = frame.assign(partition="calibration", site_balanced_mae=100.)
    defaults = frame.assign(parameter_source="default", site_balanced_mae=200.)
    values, bins = mod.prepare_plot(pd.concat([frame, distractor, defaults]))
    assert values.mae_days.tolist() == list(np.arange(4., 14.))
    assert values.n_observations.eq(22).all()
    assert bins["count"].sum() == 10
    assert bins.iloc[0].left <= 4 and bins.iloc[-1].right >= 13


@pytest.mark.parametrize("problem", ["missing_stage", "duplicate_stage", "unattained", "negative", "nan"])
def test_incomplete_or_invalid_model_metrics_cannot_silently_change_histogram(problem):
    mod = api()
    frame = metrics()
    if problem == "missing_stage":
        frame = frame.iloc[1:]
    elif problem == "duplicate_stage":
        frame = pd.concat([frame, frame.iloc[:1]])
    elif problem == "unattained":
        frame.loc[0, "n_attained"] = 2
    else:
        frame.loc[0, "site_balanced_mae"] = -1 if problem == "negative" else np.nan
    with pytest.raises(ValueError):
        mod.prepare_plot(frame)


def test_render_exports_pdf_png_counts_and_provenance(tmp_path):
    mod = api()
    source = tmp_path / "metrics.csv"
    metrics().to_csv(source, index=False)
    out = tmp_path / "figure"
    result = mod.run(source, out)
    assert (out / "mae_histogram.pdf").read_bytes().startswith(b"%PDF")
    assert (out / "mae_histogram.png").read_bytes().startswith(b"\x89PNG")
    assert pd.read_csv(out / "histogram_bins.csv")["count"].sum() == 10
    assert result["n_models"] == 10 and result["n_test_observations_per_model"] == 22
    before = (out / "mae_histogram.pdf").read_bytes()
    with pytest.raises(FileExistsError):
        mod.run(source, out)
    assert (out / "mae_histogram.pdf").read_bytes() == before


def test_stage_plot_retains_individual_stage_values_and_common_scale():
    mod = api()
    assert hasattr(mod, "prepare_stage_plot"), "Stage-by-model plotting is missing"
    frame = metrics().sample(frac=1, random_state=7)
    values, spec = mod.prepare_stage_plot(frame)
    assert len(values) == 40
    assert values.loc[values.BBCH.eq("07"), "site_balanced_mae"].tolist() == list(np.arange(1., 11.))
    assert values.loc[values.BBCH.eq("89"), "site_balanced_mae"].tolist() == list(np.arange(7., 17.))
    assert spec["model_order"] == list(list_models())
    assert spec["stage_order"] == ["07", "65", "81", "89"]
    assert spec["y_min"] == 0 and spec["y_max"] >= 16
    assert spec["visible_title"] is False


def test_stage_export_preserves_existing_histogram_and_rejects_overwrite(tmp_path):
    mod = api()
    assert hasattr(mod, "run_stage"), "Stage-by-model export is missing"
    source = tmp_path / "metrics.csv"
    metrics().to_csv(source, index=False)
    out = tmp_path / "figure"
    out.mkdir()
    old = out / "mae_histogram.pdf"
    old.write_bytes(b"existing histogram")
    mod.run_stage(source, out)
    assert (out / "mae_by_stage_model.pdf").read_bytes().startswith(b"%PDF")
    assert (out / "mae_by_stage_model.png").read_bytes().startswith(b"\x89PNG")
    assert len(pd.read_csv(out / "mae_by_stage_model.csv")) == 40
    assert old.read_bytes() == b"existing histogram"
    with pytest.raises(FileExistsError):
        mod.run_stage(source, out)
