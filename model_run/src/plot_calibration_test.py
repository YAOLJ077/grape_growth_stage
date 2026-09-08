"""Paired calibration/test MAE panels from explicitly selected completed models."""
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
from model_run.src.calibrate_ten_sites import verify_run


def prepare_plot(metrics, names):
    names = list(names)
    if not names or len(set(names)) != len(names) or not set(names).issubset(list_models()):
        raise ValueError("Select unique catalogue model names")
    frame = metrics.loc[metrics.model.isin(names) & metrics.parameter_source.eq("calibrated")
                        & metrics.temperature_input.eq("RAW")].copy()
    frame["BBCH"] = frame.BBCH.astype(str).str.zfill(2)
    keys = ["BBCH", "model", "partition"]
    expected = [(stage, name, partition) for stage in STAGES for name in names
                for partition in ("calibration", "test")]
    if frame.duplicated(keys).any() or set(map(tuple, frame[keys].to_numpy())) != set(expected):
        raise ValueError("Require exactly four stages and both partitions for every selected model")
    numeric = ["site_balanced_mae", "n_observations", "n_sites", "n_attained", "n_unattained", "attainment_rate"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    if (not np.isfinite(frame[numeric]).all().all() or frame[numeric].lt(0).any().any()
            or frame.n_attained.eq(0).any() or frame.n_sites.eq(0).any()
            or not (frame.n_attained + frame.n_unattained).eq(frame.n_observations).all()
            or not np.allclose(frame.attainment_rate, frame.n_attained / frame.n_observations)):
        raise ValueError("Invalid MAE, event counts or attainment")
    if frame.groupby(["BBCH", "partition"])[["n_observations", "n_sites"]].nunique().gt(1).any().any():
        raise ValueError("Selected models must share observation and site counts within each stage/partition")
    frame = frame.set_index(keys).loc[expected].reset_index()
    panels = []
    for stage in STAGES:
        panel = {"BBCH": stage}
        for partition in ("calibration", "test"):
            part = frame.loc[frame.BBCH.eq(stage) & frame.partition.eq(partition)]
            panel[partition] = part.site_balanced_mae.tolist()
            panel[partition + "_missing"] = part.n_unattained.astype(int).tolist()
            panel[partition + "_n"] = int(part.n_observations.iloc[0])
        panels.append(panel)
    upper = max(5., float(np.ceil((frame.site_balanced_mae.max() + 2) / 5) * 5))
    return frame, dict(model_order=names, panels=panels, y_min=0, y_max=upper, y_tick_step=5,
                       omitted_models=[name for name in list_models() if name not in names],
                       visible_title=False, legend_pt=15, footprint_pt=[720, 655])


def run(directory, output, names):
    directory, output = Path(directory), Path(output)
    stem = "calibration_test_mae"
    targets = [output / f"{stem}.{ext}" for ext in ("pdf", "png", "csv", "json")]
    if any(path.exists() for path in targets):
        raise FileExistsError("Figure outputs already exist; choose a new directory")
    paths = [directory / "cohort.json", directory / "settings.json"]
    for name in names:
        paths.extend(directory / name / filename for filename in
                     ("fit.json", "metrics.csv", "predictions.csv", "comparison.csv", "improvement.csv"))
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    hashes = {str(p.resolve()): digest(p) for p in paths}
    checks = verify_run(directory, names=names, expected_site_counts=None)
    metrics = pd.concat([pd.read_csv(directory / name / "metrics.csv", dtype={"BBCH": str})
                         for name in names], ignore_index=True)
    values, spec = prepare_plot(metrics, names)
    if any(digest(Path(path)) != sha for path, sha in hashes.items()):
        raise ValueError("Selected model results changed during figure preparation")
    sites = pd.read_csv(directory / "sites.csv")
    observations = pd.read_csv(directory / "observations.csv", usecols=["Date", "country"])
    spec.update(source_run=str(directory.resolve()), source_sha256=hashes, verification=checks,
        snapshot="Explicit selected-model snapshot; omitted models are not zero-error results",
        countries=sorted(observations.country.unique().tolist()),
        date_min=observations.Date.min(), date_max=observations.Date.max(),
        partition_sites=sites.groupby("partition").size().to_dict(),
        metric="Stage-specific site-balanced MAE in days, among attained observations",
        chart_contract=dict(question="How do calibration and test MAE differ by model and stage?",
            takeaway="Partial model comparison; calibration and test use distinct sites; attainment remains explicit",
            family="bar", variant="2x2 grouped bars", n_metrics=len(values),
            renderer="Swift CoreGraphics/PDFKit", palette_policy="hard two-root cap",
            colors=["#326C9C", "#B46B28"], non_color="solid calibration versus open test bars",
            uncertainty="Not shown; bars are point estimates"))
    renderer = Path(__file__).with_name("draw_calibration_test.swift")
    spec["plot_source_sha256"] = {str(p.relative_to(ROOT)): digest(p) for p in (Path(__file__).resolve(), renderer)}
    output.mkdir(parents=True, exist_ok=True)
    values.to_csv(targets[2], index=False)
    spec["data_sha256"] = digest(targets[2])
    targets[3].write_text(json.dumps(spec, indent=2, allow_nan=False) + "\n")
    subprocess.run(["swift", "-module-cache-path", "/tmp/grape-workflow-swift-cache",
                    str(renderer), str(targets[3]), str(output)], check=True)
    return spec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", nargs="+", required=True, choices=list_models())
    args = parser.parse_args()
    run(args.run, args.output, args.models)
