#!/usr/bin/env python3
"""Render verified process/TabM residual comparisons: RUN_DIR [--output DIRECTORY]."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import Normalize, TwoSlopeNorm
import numpy as np
import pandas as pd

MODELS = ["FL", "FB", "CL-FL-S", "CL-FL-P", "CB-FL-S", "CB-FL-P",
          "CL-FB-S", "CL-FB-P", "CB-FB-S", "CB-FB-P"]
STAGES = ["07", "65", "81", "89"]
METHODS = ["process", "tabm"]
PARTITIONS = ["calibration", "test"]
VIEWS = ["raw", "scoring"]
PANELS = list(itertools.product(["RAW", "DEM"], PARTITIONS))
KEYS = ["model", "temperature", "method", "partition", "BBCH", "metric_view"]
COUNTS = ["n_observations", "n_sites", "n_scored"]
ERRORS = ["mae_days", "rmse_days", "bias_days"]
RATES = ["raw_attainment", "raw_site_attainment", "cutoff_attainment",
         "cutoff_site_attainment", "cutoff_assignment_fraction", "cutoff_assignment_site_fraction"]
COLUMNS = KEYS + COUNTS + ERRORS + RATES
MAIN_COLOUR_LIMITS = {"mae_days": (8., 20.), "bias_days": (-10., 10.)}
GREY = "#e5e7e9"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def collect(run: Path, units: list[str]):
    """Verify every declared artifact and parse a fixed completed-unit snapshot."""
    frames, hashes = [], {}
    expected = set(itertools.product(METHODS, PARTITIONS, STAGES, VIEWS))
    for unit in units:
        model, temperature = unit.split("/")
        folder = run / unit
        marker_path = folder / "complete.json"
        marker_bytes = marker_path.read_bytes()
        marker = json.loads(marker_bytes)
        require(marker.get("verified") is True, f"Unverified unit: {unit}")
        artifacts = marker.get("artifacts", {})
        require(isinstance(artifacts, dict) and {"metrics.csv", "provenance.json"} <= set(artifacts),
                f"Missing required artifact hashes: {unit}")
        hashes[f"{unit}/complete.json"] = hashlib.sha256(marker_bytes).hexdigest()
        for name, expected_hash in artifacts.items():
            require(isinstance(name, str) and isinstance(expected_hash, str),
                    f"Invalid artifact declaration: {unit}")
            artifact = (folder / name).resolve()
            require(not Path(name).is_absolute() and folder.resolve() in artifact.parents,
                    f"Artifact outside completed unit: {unit}/{name}")
            actual_hash = sha256(artifact)
            require(actual_hash == expected_hash, f"SHA-256 mismatch: {unit}/{name}")
            hashes[f"{unit}/{name}"] = actual_hash
        require(isinstance(json.loads((folder / "provenance.json").read_text()), dict),
                f"Invalid provenance: {unit}")
        frame = pd.read_csv(folder / "metrics.csv", dtype={key: str for key in KEYS})
        require(list(frame.columns) == COLUMNS, f"Unexpected metrics schema: {unit}")
        require(frame["model"].eq(model).all() and frame["temperature"].eq(temperature).all(),
                f"Unit identity mismatch: {unit}")
        require(not frame.duplicated(KEYS).any(), f"Duplicate metric rows: {unit}")
        actual = set(frame[["method", "partition", "BBCH", "metric_view"]].itertuples(index=False, name=None))
        # OOF is optional and separate from apparent calibration performance.
        extra = actual - expected
        require(expected <= actual and all(m in METHODS and p == "oof" and s in STAGES and v in VIEWS
                                           for m, p, s, v in extra),
                f"Incomplete or unexpected metric combinations: {unit}")
        for method in {row[0] for row in extra}:
            require({row for row in extra if row[0] == method}
                    == set(itertools.product([method], ["oof"], STAGES, VIEWS)),
                    f"Incomplete OOF metric block: {unit}/{method}")
        for column in COUNTS + ERRORS + RATES:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
            require(not np.isinf(frame[column]).any(), f"Infinite metric: {unit}/{column}")
        for column in COUNTS:
            require(frame[column].notna().all() and frame[column].ge(0).all()
                    and frame[column].mod(1).eq(0).all(), f"Invalid counts: {unit}/{column}")
        require(frame.n_scored.le(frame.n_observations).all()
                and frame.n_sites.le(frame.n_observations).all(), f"Inconsistent counts: {unit}")
        for column in RATES:
            require(frame[column].dropna().between(0, 1).all(), f"Rate outside [0, 1]: {unit}/{column}")
        require(frame.mae_days.dropna().ge(0).all() and frame.rmse_days.dropna().ge(0).all(),
                f"Negative absolute error: {unit}")
        frames.append(frame)
        require(marker_path.read_bytes() == marker_bytes, f"Unit changed during snapshot: {unit}")
        for name in artifacts:
            require(sha256(folder / name) == hashes[f"{unit}/{name}"],
                    f"Artifact changed during snapshot: {unit}/{name}")
        print(f"Verified {unit}", flush=True)
    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    if len(data):
        order = {model: i for i, model in enumerate(MODELS)}
        data = data.assign(_model_order=data.model.map(order)).sort_values(
            ["_model_order", "temperature", "method", "partition", "BBCH", "metric_view"]
        ).drop(columns="_model_order").reset_index(drop=True)
    return data, hashes


def matrix(data, metric, method, temperature, partition):
    selected = data[(data.method == method) & (data.metric_view == "scoring")
                    & (data.temperature == temperature) & (data.partition == partition)]
    return selected.pivot(index="model", columns="BBCH", values=metric).reindex(
        index=MODELS, columns=STAGES).to_numpy(dtype=float)


def heatmap(ax, values, cmap, norm, metric, temperature, completed, failed, requested, labels):
    image = ax.imshow(np.ma.masked_invalid(values), cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(4), STAGES)
    ax.set_yticks(range(10), MODELS if labels else [""] * 10)
    ax.xaxis.tick_top()
    ax.tick_params(length=0, labelsize=10)
    ax.set_xticks(np.arange(-.5, 4), minor=True)
    ax.set_yticks(np.arange(-.5, 10), minor=True)
    ax.grid(which="minor", color="white", linewidth=.7)
    ax.tick_params(which="minor", length=0)
    for (row, col), value in np.ndenumerate(values):
        if np.isfinite(value):
            label = f"{value:+.1f}" if metric == "bias_days" else f"{value:.1f}"
            brightness = np.dot(cmap(norm(value))[:3], [.2126, .7152, .0722])
            colour = "white" if brightness < .48 else "#182630"
        else:
            unit = f"{MODELS[row]}/{temperature}"
            label = "n/a" if unit in completed else ("×" if unit in failed else ("—" if unit in requested else "·"))
            colour = "#686e74"
        ax.text(col, row, label, ha="center", va="center", fontsize=9, color=colour)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return image


def render(data, output, units, failed, requested, expected, snapshot, smoke, requested_known):
    plt.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42,
                         "text.color": "#182630", "axes.titleweight": "bold"})
    scope = f"{len(units)}/{expected} requested configurations complete · {snapshot}"
    if smoke:
        scope = "SMOKE RUN · reduced training/optimization budget · " + scope
    legend = "Grey —: pending; ×: failed; ·: unrequested; n/a: unavailable in a completed unit."
    if not requested_known:
        legend = legend.replace("—: pending", "—: pending or unrequested")
    notes = [
        "BBCH 07 budburst · 65 flowering · 81 veraison · 89 maturity/harvest. " + legend,
        "MAE and bias average within sites, then weight sites equally. Bias = predicted − observed; negative is early.",
        "TabM residual target = observed raw date − process-model raw date; features include weather through process-predicted dates.",
        "Final hybrid dates undergo chronological correction before BBCH81/89 scoring applies the 4 November cap.",
        "An unattained process prediction receives no ML residual; BBCH81/89 can still receive 4 November for scoring.",
        "Calibration panels show apparent training performance, not OOF estimates. Test sites are held out. No confidence intervals.",
    ]
    paths = []
    with PdfPages(output / "model_mae_bias.pdf") as pdf:
        for metric, title, stem in [("mae_days", "Mean absolute error (days)", "mae"),
                                    ("bias_days", "Signed bias (days)", "bias")]:
            minimum, maximum = MAIN_COLOUR_LIMITS[metric]
            cmap = plt.get_cmap("PuOr_r" if metric == "bias_days" else "YlOrBr").copy()
            cmap.set_bad(GREY)
            norm = (TwoSlopeNorm(vcenter=0, vmin=minimum, vmax=maximum)
                    if metric == "bias_days" else Normalize(minimum, maximum))
            fig, axes = plt.subplots(2, 4, figsize=(16.8, 13))
            fig.subplots_adjust(left=.105, right=.925, top=.84, bottom=.22, wspace=.30, hspace=.36)
            for row, (method, label) in enumerate(zip(METHODS, ["Process model", "Process model + TabM residual"])):
                for col, (temperature, partition) in enumerate(PANELS):
                    values = matrix(data, metric, method, temperature, partition)
                    image = heatmap(axes[row, col], values, cmap, norm, metric, temperature,
                                    units, failed, requested, col == 0)
                    axes[row, col].set_title(f"{label}\n{temperature} · {partition.capitalize()}", fontsize=11, pad=25)
            fig.suptitle(title, x=.105, y=.976, ha="left", fontsize=23, fontweight="bold")
            fig.text(.105, .941, "Median/cutoff process calibration with and without TabM residual correction · scoring dates", fontsize=12)
            fig.text(.105, .909, scope, fontsize=9)
            for number, note in enumerate(notes):
                fig.text(.105, .158 - number * .022, note, fontsize=8.5)
            shown = data.loc[data.method.isin(METHODS) & data.metric_view.eq("scoring")
                             & data.partition.isin(PARTITIONS), metric].dropna()
            below, above = shown.lt(minimum).any(), shown.gt(maximum).any()
            extension = "both" if below and above else "min" if below else "max" if above else "neither"
            fig.colorbar(image, cax=fig.add_axes([.947, .30, .012, .43]), label="Days",
                         ticks=np.linspace(minimum, maximum, 5), extend=extension)
            for suffix in ["png", "pdf"]:
                path = output / f"{stem}.{suffix}"
                fig.savefig(path, dpi=180)
                paths.append(path)
            pdf.savefig(fig)
            plt.close(fig)
    paths.append(output / "model_mae_bias.pdf")
    return paths


def build_report(run: Path, output: Path | None = None) -> Path:
    """Write a verified, read-only snapshot of completed process/TabM run units."""
    run = Path(run).resolve()
    output = (Path(output) if output is not None else run / "report").resolve()
    require(output != run and output not in run.parents, "Output cannot be the run directory or one of its ancestors")
    status_bytes = (run / "status.json").read_bytes()
    status = json.loads(status_bytes)
    smoke = status.get("smoke", False)
    require(isinstance(smoke, bool), "Invalid smoke status")
    units = status["completed"]
    valid = {f"{model}/{temperature}" for model, temperature in itertools.product(MODELS, ["RAW", "DEM"])}
    require(isinstance(units, list) and all(isinstance(unit, str) for unit in units), "Invalid completed-unit list")
    require(len(units) == len(set(units)) and set(units) <= valid, "Unknown or duplicate completed units")
    expected = status.get("expected")
    require(type(expected) is int and 1 <= expected <= 20 and isinstance(status.get("complete"), bool),
            "Invalid status metadata")
    requested = valid.copy()
    run_path = run / "run.json"
    run_bytes = run_path.read_bytes() if run_path.exists() else None
    if run_bytes is not None:
        config = json.loads(run_bytes)
        models, temperatures = config.get("models"), config.get("temperatures")
        require(isinstance(models, list) and isinstance(temperatures, list)
                and all(isinstance(value, str) for value in models + temperatures),
                "Invalid requested configuration catalogue")
        require(len(models) == len(set(models)) and len(temperatures) == len(set(temperatures)),
                "Duplicate requested configurations")
        requested = {f"{model}/{temperature}" for model, temperature in itertools.product(models, temperatures)}
        require(requested <= valid and len(requested) == expected, "Requested catalogue disagrees with status")
    require(set(units) <= requested, "Completed units were not requested")
    require(not status["complete"] or len(units) == expected, "Complete run is missing requested units")
    for unit in valid:
        folder = (run / unit).resolve()
        require(output != folder and folder not in output.parents and output not in folder.parents,
                "Output overlaps a fitted model unit")
    failed = status.get("failed", [])
    require(isinstance(failed, (list, dict)), "Invalid failed-unit list")
    failed = list(failed)
    require(all(isinstance(unit, str) for unit in failed) and set(failed) <= requested
            and len(failed) == len(set(failed)) and not set(failed).intersection(units),
            "Invalid or overlapping failed units")
    require(len(units) + len(failed) <= expected, "Completed and failed counts exceed requested total")
    data, hashes = collect(run, units)
    if run_bytes is not None:
        hashes["run.json"] = hashlib.sha256(run_bytes).hexdigest()
    snapshot = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    output.mkdir(parents=True, exist_ok=True)
    data.to_csv(output / "metrics.csv", index=False)
    paths = [output / "metrics.csv"]
    requested_known = run_bytes is not None or expected == 20
    paths += render(data, output, units, failed, requested, expected, snapshot, smoke, requested_known)
    run_note = ("SMOKE RUN: reduced training/optimization budget; these are diagnostic outputs, not full-budget results."
                if smoke else "The run is not marked as a reduced-budget smoke run.")
    readme = f'''# Process models with TabM residual correction

Snapshot: {snapshot}. Completed model–temperature configurations: {len(units)}/{expected}. Run status: {"complete" if status["complete"] else "partial"}.

{run_note}

`mae.png` / `mae.pdf` and `bias.png` / `bias.pdf` compare the median/cutoff-calibrated process model (top row) with its TabM residual hybrid (bottom row). Columns are RAW calibration, RAW test, DEM calibration and DEM test. Each panel contains ten process structures in fixed catalogue order and four equal target stages: BBCH07 budburst, BBCH65 flowering, BBCH81 veraison and BBCH89 maturity/harvest. The -S and -P suffixes identify sequential and parallel interactions. The second row represents each corresponding -ML model; RAW and DEM are separate temperature-input levels. `model_mae_bias.pdf` contains these two figure pages. Harvest can reflect management and need not represent physiological maturity.

The residual target is observed raw date minus process-model raw date. Residual learning uses the new median/cutoff calibration run. Nested out-of-fold prediction and model selection are confined to calibration sites; held-out test outcomes are excluded from fitting and tuning. Calibration panels contain apparent performance of the final fitted model on calibration observations, not OOF generalization estimates. Optional `partition=oof` rows remain separate in `metrics.csv` and are not plotted as apparent calibration performance.

Residual predictions are added to attained process dates. Final hybrid dates undergo chronological correction (`correct_dates`) before scoring applies the fixed 4 November cap to BBCH81/89. A process prediction that does not attain a stage receives no learned residual; BBCH81/89 can nevertheless be assigned 4 November for scoring. BBCH07/65 receive no November scoring assignment. Assigned dates are scoring conventions and do not establish process attainment. Raw hybrid dates remain distinct from scoring dates.

For `method=tabm`, the legacy metric fields `raw_attainment` and `raw_site_attainment` mean finite hybrid-date availability before November scoring assignment, not physiological or thermal attainment. Here “before assignment” refers to the processing order, not an earlier calendar date. `cutoff_attainment` and `cutoff_site_attainment` describe finite raw hybrid dates by the cutoff; these are also prediction-availability diagnostics. For `method=process`, the fields describe raw process attainment. Assignment fractions remain separate. Observation-weighted and site-balanced fractions are retained in the CSV; they are not shown as biological attainment improvements.

MAE and bias average errors within each site and then weight eligible sites equally. RMSE is the square root of the equally weighted mean of within-site mean squared errors. Bias equals predicted minus observed date; negative bias indicates early prediction. Error metrics use finite dates in their selected raw or scoring view. Site-balanced fractions first average observation indicators within sites, then weight sites equally. Observation counts, site counts and scored counts preserve denominators. Methods and date views can have different finite-date denominators; paired visual panels do not constitute matched-pair effect estimates. No confidence intervals are available.

The main MAE scale is fixed at 8–20 days. The bias scale is fixed at −10 to +10 days and centred at zero. Limits are shared across all eight panels of each figure. Colourbar extensions identify out-of-range values, including MAE below 8 days; cell annotations retain actual values to one decimal day. CSV metrics retain source precision. Grey — indicates pending units; × indicates failed units; · indicates unrequested units; n/a indicates unavailable metrics in completed units. Without `run.json`, a subset snapshot cannot distinguish pending from unrequested units. The full 20-unit catalogue remains visible even for empty or subset runs; grey cells never imply zero error.

Weather features through process-predicted dates use retrospective information. These evaluations describe retrospective phenology prediction and do not establish operational forecast performance. Predictive associations do not establish causal effects of terrain or temperature correction.

`metrics.csv` contains every verified source metric row (32 mandatory rows per completed unit, plus any complete optional OOF blocks). `manifest.json` records the initial status hash, completed and requested units, active status, smoke flag, source artifact hashes, script hash and generated output hashes. Every artifact declared in a completed unit is SHA-256 verified before parsing and rechecked afterwards; `metrics.csv` and `provenance.json` are required. Metric schema, complete method/partition/stage/view combinations and basic numerical bounds are validated. Metrics are read from source outputs and are not independently recomputed from predictions. The completed-unit list is a fixed snapshot even if training subsequently advances.

Reproduction: `python model_run/src/report_cutoff_ml.py RUN_DIR --output REPORT_DIR`. Default output: `RUN_DIR/report`.
'''
    (output / "README.md").write_text(readme, encoding="utf-8")
    paths.append(output / "README.md")
    manifest = dict(snapshot_utc=snapshot, run_dir=str(run), completed_units=units,
                    expected_units=expected, requested_units=sorted(requested) if requested_known else None,
                    complete=status["complete"], partial=not status["complete"], failed_units=failed,
                    active=status.get("active"), smoke=smoke,
                    status_sha256=hashlib.sha256(status_bytes).hexdigest(), source_sha256=hashes,
                    script_sha256=sha256(Path(__file__)), metric_rows=len(data), metric_recomputation=False,
                    main_colour_limits_days=MAIN_COLOUR_LIMITS,
                    output_sha256={path.name: sha256(path) for path in paths})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Exported audited report for {len(units)}/{expected} requested units to {output}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path, help="Default: RUN_DIR/report")
    args = parser.parse_args()
    build_report(args.run_dir, args.output)


if __name__ == "__main__":
    main()
