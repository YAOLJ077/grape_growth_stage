"""Plot calibrated test MAE by stage and model, or its across-model distribution."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from model.registry import list_models
from model.specification import STAGES

SOURCE = ROOT / "model_run/results/ten_site_calibration_20260907/metrics.csv"
OUT = ROOT / "fig/model_evaluation"


def prepare_plot(metrics):
    """Require the same complete test-event coverage for every model and stage."""
    selected = metrics.loc[metrics.partition.eq("test") & metrics.parameter_source.eq("calibrated")
                           & metrics.temperature_input.eq("RAW")].copy()
    selected["BBCH"] = selected.BBCH.astype(str).str.zfill(2)
    if set(selected.model) != set(list_models()):
        raise ValueError("Require calibrated RAW test metrics for all ten models")
    numeric = ["site_balanced_mae", "n_observations", "n_attained"]
    selected[numeric] = selected[numeric].apply(pd.to_numeric, errors="raise")
    if (not np.isfinite(selected[numeric].to_numpy()).all()
            or selected.site_balanced_mae.lt(0).any()
            or selected.n_observations.le(0).any()
            or not selected.n_observations.eq(selected.n_attained).all()):
        raise ValueError("Require nonnegative finite MAE and complete test-event attainment")
    rows, coverage = [], None
    for name in list_models():
        part = selected.loc[selected.model.eq(name)].sort_values("BBCH")
        if len(part) != 4 or set(part.BBCH) != set(STAGES):
            raise ValueError("Require exactly one metric row per model and stage")
        counts = part.n_observations.tolist()
        if coverage is not None and counts != coverage:
            raise ValueError("Models must use identical stage observation counts")
        coverage = counts
        rows.append(dict(model=name, mae_days=float(part.site_balanced_mae.mean()),
                         n_observations=int(part.n_observations.sum()), n_stages=4,
                         partition="test", parameter_source="calibrated", temperature_input="RAW"))
    values = pd.DataFrame(rows)
    width = 0.5
    lower = np.floor(values.mae_days.min()/width)*width
    upper = max(lower+width, np.ceil(values.mae_days.max()/width)*width)
    edges = np.linspace(lower, upper, int(round((upper-lower)/width))+1)
    counts, _ = np.histogram(values.mae_days, bins=edges)
    bins = pd.DataFrame(dict(left=edges[:-1], right=edges[1:], count=counts))
    assert int(counts.sum()) == len(values)
    return values, bins


def prepare_stage_plot(metrics):
    """Preserve the forty stage/model metrics rather than averaging over stages."""
    prepare_plot(metrics)  # Reuse the existing coverage and metric validation.
    selected = metrics.loc[metrics.partition.eq("test") & metrics.parameter_source.eq("calibrated")
                           & metrics.temperature_input.eq("RAW")].copy()
    selected["BBCH"] = selected.BBCH.astype(str).str.zfill(2)
    selected["site_balanced_mae"] = pd.to_numeric(selected.site_balanced_mae)
    names = list(list_models())
    selected = selected.set_index(["BBCH", "model"]).loc[
        [(stage, name) for stage in STAGES for name in names]].reset_index()
    upper = max(5., float(np.ceil(selected.site_balanced_mae.max()/5)*5))
    spec = dict(model_order=names, stage_order=list(STAGES), y_min=0, y_max=upper, y_tick_step=5,
                y_axis="Calibrated test MAE (days)", x_axis="Model", visible_title=False,
                panels=[dict(BBCH=stage, values=selected.loc[selected.BBCH.eq(stage),
                             "site_balanced_mae"].tolist()) for stage in STAGES])
    return selected, spec


def run_stage(source=SOURCE, output=OUT):
    source, output = Path(source), Path(output)
    targets = [output / f"mae_by_stage_model.{suffix}" for suffix in ("pdf", "png", "csv", "json")]
    if any(path.exists() for path in targets):
        raise FileExistsError("Stage/model outputs exist; choose a new --output directory")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    values, spec = prepare_stage_plot(pd.read_csv(source, dtype={"BBCH": str}))
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise ValueError("Metrics changed during reading")
    spec.update(source=str(source.resolve()), source_sha256=source_hash,
                metric="Stage-specific site_balanced_mae; all calibrated RAW test observations",
                layout="2 by 2; identical model order and y-axis scale",
                palette={"fill": "#326C9C", "ink": "#27333D"},
                caution="Small France-only pilot; stage sample sizes differ; all fits reached generation limit")
    output.mkdir(parents=True, exist_ok=True)
    values.to_csv(targets[2], index=False)
    targets[3].write_text(json.dumps(spec, indent=2, allow_nan=False)+"\n")
    subprocess.run(["swift", "-module-cache-path", "/tmp/grape-workflow-swift-cache",
                    str(Path(__file__).with_name("draw_stage_mae.swift")), str(targets[3]), str(output)], check=True)
    return spec


def run(source=SOURCE, output=OUT):
    source, output = Path(source), Path(output)
    if output.exists():
        raise FileExistsError(f"Output exists; choose a new --output: {output}")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    values, bins = prepare_plot(pd.read_csv(source, dtype={"BBCH": str}))
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise ValueError("Metrics changed during reading")
    output.mkdir(parents=True, exist_ok=False)
    values.to_csv(output / "model_mae.csv", index=False)
    bins.to_csv(output / "histogram_bins.csv", index=False)
    quality = dict(source=str(source.resolve()), source_sha256=source_hash,
                   metric="Equal-stage mean of site_balanced_mae from all calibrated RAW test observations",
                   n_models=len(values), n_test_observations_per_model=int(values.n_observations.iloc[0]),
                   bin_width_days=0.5, bins=bins.to_dict("records"),
                   bin_convention="Left closed, right open; final bin includes its right edge",
                   x_axis="Calibrated test MAE (days)", y_axis="Number of models",
                   visible_title=False, palette={"fill": "#326C9C", "ink": "#27333D"},
                   caution="Ten dependent model evaluations at four French test sites; budget-limited, nonconverged fits, not a population error distribution")
    payload = output / "plot_quality.json"
    payload.write_text(json.dumps(quality, indent=2, allow_nan=False)+"\n")
    subprocess.run(["swift", "-module-cache-path", "/tmp/grape-workflow-swift-cache",
                    str(Path(__file__).with_name("draw_mae_histogram.swift")),
                    str(payload), str(output)], check=True)
    return quality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--by-stage", action="store_true", help="Four stage panels with one bar per model")
    args = parser.parse_args()
    if args.by_stage:
        run_stage(args.metrics, args.output)
        print(f"Saved stage-by-model MAE figure to {args.output}")
        return
    result = run(args.metrics, args.output)
    print(f"Saved histogram of {result['n_models']} calibrated models to {args.output}")


if __name__ == "__main__":
    main()
