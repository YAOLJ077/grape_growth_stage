#!/usr/bin/env python3
"""Render an audited snapshot of process-only median/cutoff calibration outputs.

Usage: python model_run/src/report_median_cutoff.py RUN_DIR [--output DIRECTORY]
The default output directory is RUN_DIR/report. No fitted files are modified.
"""
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
METHODS = ["existing", "median_cutoff"]
PARTITIONS = ["calibration", "test"]
VIEWS = ["raw", "scoring"]
PANELS = list(itertools.product(["RAW", "DEM"], PARTITIONS))
KEYS = ["model", "temperature", "method", "partition", "BBCH", "metric_view"]
COUNTS = ["n_observations", "n_sites", "n_scored"]
ERRORS = ["mae_days", "rmse_days", "bias_days"]
RATES = ["raw_attainment", "raw_site_attainment", "cutoff_attainment",
         "cutoff_site_attainment", "cutoff_assignment_fraction",
         "cutoff_assignment_site_fraction"]
COLUMNS = KEYS + COUNTS + ERRORS + RATES
FIT_KEYS = ["early_bias_target_met", "early_coverage_met", "median_threshold_status"]
GREY = "#e5e7e9"
MAIN_COLOUR_LIMITS = {"mae_days": (8., 20.), "bias_days": (-10., 10.)}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def collect(run: Path, units: list[str]):
    """Read only committed units, validating every declared artifact hash."""
    frames, fits, hashes = [], [], {}
    expected = set(itertools.product(METHODS, PARTITIONS, STAGES, VIEWS))
    for unit in units:
        model, temperature = unit.split("/")
        folder = run / unit
        marker_path = folder / "complete.json"
        marker_bytes = marker_path.read_bytes()
        marker = json.loads(marker_bytes)
        require(marker.get("verified") is True, f"Unverified unit: {unit}")
        artifacts = marker.get("artifacts", {})
        require({"metrics.csv", "fit.json"} <= set(artifacts),
                f"Missing required artifact hashes: {unit}")
        hashes[f"{unit}/complete.json"] = hashlib.sha256(marker_bytes).hexdigest()
        for name, expected_hash in artifacts.items():
            artifact = (folder / name).resolve()
            require(folder.resolve() in artifact.parents,
                    f"Artifact outside completed unit: {unit}/{name}")
            actual_hash = sha256(artifact)
            require(actual_hash == expected_hash, f"SHA-256 mismatch: {unit}/{name}")
            hashes[f"{unit}/{name}"] = actual_hash
        frame = pd.read_csv(folder / "metrics.csv", dtype={"BBCH": str})
        require(set(COLUMNS) <= set(frame), f"Incomplete metrics schema: {unit}")
        require(frame["model"].eq(model).all() and frame["temperature"].eq(temperature).all(),
                f"Unit identity mismatch: {unit}")
        require(not frame.duplicated(KEYS).any(), f"Duplicate metric rows: {unit}")
        actual = set(frame[["method", "partition", "BBCH", "metric_view"]].itertuples(index=False, name=None))
        require(actual == expected, f"Incomplete or unexpected metric combinations: {unit}")
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
        fit = json.loads((folder / "fit.json").read_text())
        require(set(FIT_KEYS) <= set(fit), f"Incomplete fit status: {unit}")
        require(all(isinstance(fit[k], bool) for k in FIT_KEYS[:2]), f"Invalid fit flags: {unit}")
        fits.append(dict(model=model, temperature=temperature,
                         **{k: fit[k] for k in FIT_KEYS}))
        frames.append(frame)
        # Detect changes between verification and parsing; incomplete writes cannot enter a snapshot.
        require(marker_path.read_bytes() == marker_bytes, f"Unit changed during snapshot: {unit}")
        for name in artifacts:
            require(sha256(folder / name) == hashes[f"{unit}/{name}"],
                    f"Artifact changed during snapshot: {unit}/{name}")
        print(f"Verified {unit}", flush=True)
    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    return data, pd.DataFrame(fits, columns=["model", "temperature"] + FIT_KEYS), hashes


def matrix(data, metric, method, view, temperature, partition):
    selected = data[(data.method == method) & (data.metric_view == view)
                    & (data.temperature == temperature) & (data.partition == partition)]
    return selected.pivot(index="model", columns="BBCH", values=metric).reindex(
        index=MODELS, columns=STAGES).to_numpy(dtype=float)


def colour_scale(data, metric, limits=None):
    if metric in RATES:
        maximum = 1.0
    else:
        values = pd.to_numeric(data[metric], errors="coerce").dropna().abs()
        maximum = max(1.0, float(np.ceil(values.max() / 5) * 5)) if len(values) else 1.0
    signed = metric == "bias_days"
    minimum = -maximum if signed else 0.
    if limits is not None:
        minimum, maximum = limits
    cmap = plt.get_cmap("PuOr_r" if signed else "YlOrBr").copy()
    cmap.set_bad(GREY)
    norm = TwoSlopeNorm(vcenter=0, vmin=minimum, vmax=maximum) if signed else Normalize(minimum, maximum)
    return cmap, norm


def heatmap(ax, values, cmap, norm, metric, temperature, completed, failed, requested, row_labels=True):
    image = ax.imshow(np.ma.masked_invalid(values), cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(4), STAGES)
    ax.set_yticks(range(10), MODELS if row_labels else [""] * 10)
    ax.xaxis.tick_top()
    ax.tick_params(length=0, labelsize=9)
    ax.set_xticks(np.arange(-.5, 4), minor=True)
    ax.set_yticks(np.arange(-.5, 10), minor=True)
    ax.grid(which="minor", color="white", linewidth=.7)
    ax.tick_params(which="minor", length=0)
    for (row, col), value in np.ndenumerate(values):
        if np.isfinite(value):
            label = f"{value:.0%}" if metric in RATES else (
                f"{value:+.1f}" if metric == "bias_days" else f"{value:.1f}")
            brightness = np.dot(cmap(norm(value))[:3], [.2126, .7152, .0722])
            colour = "white" if brightness < .48 else "#182630"
        else:
            unit = f"{MODELS[row]}/{temperature}"
            label = "n/a" if unit in completed else ("×" if unit in failed else ("—" if unit in requested else "·"))
            colour = "#686e74"
        ax.text(col, row, label, ha="center", va="center", fontsize=8, color=colour)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return image


def figure_notes(fig, notes, start=.16, step=.027):
    for number, note in enumerate(notes):
        fig.text(.105, start - number * step, note, fontsize=8.5)


def render(data, fits, output, units, failed, requested, expected, snapshot, smoke=False, requested_known=True):
    plt.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42,
                         "text.color": "#182630", "axes.titleweight": "bold"})
    common = [
        "BBCH 07 budburst · 65 flowering · 81 veraison · 89 maturity/harvest. Grey —: pending; ×: failed; ·: unrequested; n/a: unavailable.",
        "MAE and bias: within-site means, then equal site weights. Bias = predicted − observed date; negative is early.",
        "BBCH81/89 scoring can assign 4 November; an assigned date is not actual model attainment. Raw dates remain unchanged.",
        "Process models only; parameters shared across environmental zones. No confidence intervals. Source: metrics.csv."
    ]
    if not requested_known:
        common[0] = common[0].replace("—: pending", "—: pending or unrequested")
    scope = f"{len(units)}/{expected} requested configurations complete · calibration and held-out test sites · {snapshot}"
    if smoke:
        scope = "SMOKE RUN · reduced optimization budget · " + scope
    paths = []
    with PdfPages(output / "model_mae_bias.pdf") as main_pdf:
        for metric, title, stem in [("mae_days", "Mean absolute error (days)", "mae"),
                                    ("bias_days", "Signed bias (days)", "bias")]:
            cmap, norm = colour_scale(data, metric, MAIN_COLOUR_LIMITS[metric])
            fig, axes = plt.subplots(1, 4, figsize=(15.5, 7.8))
            fig.subplots_adjust(left=.105, right=.925, top=.76, bottom=.245, wspace=.30)
            for i, (temperature, partition) in enumerate(PANELS):
                values = matrix(data, metric, "median_cutoff", "scoring", temperature, partition)
                image = heatmap(axes[i], values, cmap, norm, metric, temperature, units, failed, requested, i == 0)
                axes[i].set_title(f"{temperature} temperature\n{partition.capitalize()} sites", fontsize=12, pad=25)
            fig.suptitle(title, x=.105, y=.965, ha="left", fontsize=21, fontweight="bold")
            fig.text(.105, .913, "Median thermal requirement and cutoff scoring", fontsize=13)
            fig.text(.105, .867, scope, fontsize=9)
            figure_notes(fig, common)
            shown = data.loc[data.method.eq("median_cutoff") & data.metric_view.eq("scoring"), metric].dropna()
            below, above = shown.lt(norm.vmin).any(), shown.gt(norm.vmax).any()
            extension = "both" if below and above else "min" if below else "max" if above else "neither"
            fig.colorbar(image, cax=fig.add_axes([.948, .30, .012, .38]), label="Days",
                         ticks=np.linspace(norm.vmin, norm.vmax, 5), extend=extension)
            for suffix in ["png", "pdf"]:
                path = output / f"{stem}.{suffix}"
                fig.savefig(path, dpi=200)
                paths.append(path)
            main_pdf.savefig(fig)
            plt.close(fig)
    paths.append(output / "model_mae_bias.pdf")

    attainment_metrics = [("raw_site_attainment", "Actual attainment by 31 December"),
                          ("cutoff_site_attainment", "Actual attainment by 4 November"),
                          ("cutoff_assignment_site_fraction", "Assigned cutoff dates")]
    fig, axes = plt.subplots(3, 4, figsize=(16, 17))
    fig.subplots_adjust(left=.11, right=.93, top=.86, bottom=.13, wspace=.30, hspace=.30)
    for row, (metric, title) in enumerate(attainment_metrics):
        cmap, norm = colour_scale(data, metric)
        for col, (temperature, partition) in enumerate(PANELS):
            values = matrix(data, metric, "median_cutoff", "scoring", temperature, partition)
            image = heatmap(axes[row, col], values, cmap, norm, metric, temperature, units, failed, requested, col == 0)
            axes[row, col].set_title(f"{temperature} · {partition.capitalize()}\n{title}", fontsize=10, pad=23)
    fig.suptitle("Actual attainment and cutoff assignment", x=.11, y=.975, ha="left", fontsize=21, fontweight="bold")
    fig.text(.11, .944, "Median thermal requirement and cutoff scoring · site-balanced fractions", fontsize=12)
    fig.text(.11, .918, scope, fontsize=9)
    figure_notes(fig, [common[0],
        "Fractions average each site's observation fraction with equal site weights; annotations round to whole percentages.",
        "Actual attainment by 4 November is shown for all stages; scoring-date assignment applies only to BBCH81/89.",
        "Actual attainment excludes assigned dates. Assignment and attainment have different meanings and are shown separately.",
        "A 100% scored fraction does not imply 100% actual attainment. No confidence intervals. Source: metrics.csv."], .09, .015)
    colorbar = fig.colorbar(image, cax=fig.add_axes([.945, .33, .012, .38]))
    colorbar.set_ticks([0, .25, .5, .75, 1], labels=["0%", "25%", "50%", "75%", "100%"])
    for suffix in ["png", "pdf"]:
        path = output / f"attainment.{suffix}"
        fig.savefig(path, dpi=180)
        paths.append(path)
    plt.close(fig)

    with PdfPages(output / "comparison.pdf") as comparison:
        for metric, title, stem in [("mae_days", "Mean absolute error (days)", "mae"),
                                    ("rmse_days", "Root mean square error (days)", "rmse"),
                                    ("bias_days", "Signed bias (days)", "bias")]:
            cmap, norm = colour_scale(data, metric)
            for view in ["scoring", "raw"]:
                fig, axes = plt.subplots(2, 4, figsize=(15.5, 12.5))
                fig.subplots_adjust(left=.105, right=.925, top=.84, bottom=.15, wspace=.30, hspace=.33)
                for row, (method, label) in enumerate(zip(METHODS, ["Existing thresholds", "Median / cutoff fit"])):
                    for col, (temperature, partition) in enumerate(PANELS):
                        values = matrix(data, metric, method, view, temperature, partition)
                        image = heatmap(axes[row, col], values, cmap, norm, metric, temperature, units, failed, requested, col == 0)
                        axes[row, col].set_title(f"{label}\n{temperature} · {partition.capitalize()}", fontsize=11, pad=24)
                fig.suptitle(f"{title} · {view} dates", x=.105, y=.975, ha="left", fontsize=21, fontweight="bold")
                fig.text(.105, .938, scope, fontsize=9)
                fig.text(.105, .906, "Common colour scales across both methods, date views, temperatures and partitions; fixed model order.", fontsize=9)
                notes = common[:1] + [
                    "Errors use finite dates in the selected view and equal site weights; RMSE = square root of the mean site MSE.",
                    "Raw errors exclude unattained predictions; scoring errors can include BBCH81/89 assigned dates. Denominators can differ.",
                    "Bias = predicted − observed; negative is early. No confidence intervals or matched-pair effect estimates."
                ]
                figure_notes(fig, notes, .105, .021)
                fig.colorbar(image, cax=fig.add_axes([.948, .30, .012, .43]), label="Days")
                path = output / f"{stem}_comparison_{view}.png"
                fig.savefig(path, dpi=180)
                paths.append(path)
                comparison.savefig(fig)
                plt.close(fig)
    paths.append(output / "comparison.pdf")
    return paths


def build_report(run: Path, output: Path | None = None) -> Path:
    """Write a verified report snapshot without changing run artifacts.

    Safe to call after a runner has published a completed unit and status.json.
    The output defaults to ``run / "report"`` and the resolved path is returned.
    """
    run = Path(run).resolve()
    output = (Path(output) if output is not None else run / "report").resolve()
    require(output != run and output not in run.parents, "Output cannot be the run directory or one of its ancestors")
    status_bytes = (run / "status.json").read_bytes()
    status = json.loads(status_bytes)
    smoke = status.get("smoke", False)
    require(isinstance(smoke, bool), "Invalid smoke status")
    run_note = ("SMOKE RUN: reduced optimization budget. These outputs are diagnostic and do not represent full-budget fits, even when all sites are included."
                if smoke else "The run is not marked as a reduced-budget smoke run.")
    units = status["completed"]
    valid = {f"{model}/{temperature}" for model, temperature in itertools.product(MODELS, ["RAW", "DEM"])}
    require(isinstance(units, list) and all(isinstance(unit, str) for unit in units), "Invalid completed-unit list")
    require(len(units) == len(set(units)) and set(units) <= valid, "Unknown or duplicate completed units")
    expected = status.get("expected")
    require(type(expected) is int and 1 <= expected <= 20
            and isinstance(status.get("complete"), bool), "Invalid status metadata")
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
    # Protect both existing and future model-unit folders from report writes.
    for unit in valid:
        folder = run / unit
        require(output != folder and folder not in output.parents and output not in folder.parents,
                "Output overlaps a fitted model unit")
    failed = status.get("failed", [])
    require(isinstance(failed, (list, dict)), "Invalid failed-unit list")
    failed = list(failed)
    require(all(isinstance(unit, str) for unit in failed) and set(failed) <= valid
            and set(failed) <= requested and len(failed) == len(set(failed))
            and not set(failed).intersection(units), "Invalid or overlapping failed units")
    require(len(units) + len(failed) <= expected, "Completed and failed counts exceed requested total")
    data, fits, hashes = collect(run, units)
    if run_bytes is not None:
        hashes["run.json"] = hashlib.sha256(run_bytes).hexdigest()
    snapshot = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    output.mkdir(parents=True, exist_ok=True)
    data.to_csv(output / "metrics.csv", index=False)
    fits.to_csv(output / "fit_status.csv", index=False)
    paths = [output / "metrics.csv", output / "fit_status.csv"]
    paths += render(data, fits, output, units, failed, requested, expected, snapshot, smoke=smoke,
                    requested_known=run_bytes is not None or expected == 20)
    unmet_bias = int((fits.early_bias_target_met == False).sum())  # noqa: E712
    unmet_coverage = int((fits.early_coverage_met == False).sum())  # noqa: E712
    readme = f'''# Median thermal requirement and cutoff scoring

Snapshot: {snapshot}. Completed model–temperature configurations: {len(units)}/{expected} requested configurations. Run status: {"complete" if status["complete"] else "partial"}.

{run_note}

`mae.png` / `mae.pdf` and `bias.png` / `bias.pdf` show the median/cutoff method's scoring metrics in RAW calibration, RAW test, DEM calibration and DEM test panels. `model_mae_bias.pdf` combines these two figures. `attainment.png` / `attainment.pdf` separately show raw actual attainment, actual attainment by the cutoff, and cutoff assignment. `comparison.pdf` contains six pages comparing existing thresholds with the median/cutoff method for MAE, RMSE and signed bias, using both scoring and raw dates. The six comparison PNGs are named `<metric>_comparison_<view>.png`.

The four equal target stages are BBCH07 (budburst), BBCH65 (flowering), BBCH81 (veraison), and BBCH89 (maturity/harvest). Maturity/harvest is an operational endpoint and need not represent physiological maturity. Ten process model structures have fixed row order; RAW and DEM are separate temperature-input levels. Residual machine learning is absent. Parameters are calibrated on calibration sites and shared across environmental zones; held-out test results do not establish calibration target feasibility.

The early-stage calibration targets are bias within ±1 day for BBCH07/65/81 and at least 99% raw attainment. The BBCH89 threshold uses median thermal requirements. Among {len(units)} completed fits, {unmet_bias} do not meet the saved early-bias target and {unmet_coverage} do not meet the saved early-coverage target. These flags are calibration diagnostics. `fit_status.csv` preserves `median_threshold_status` exactly; unsuccessful statuses are not reclassified as successful fits.

The fixed 4 November scoring cutoff applies to BBCH81/89. Scoring dates can be assigned to observations whose raw model prediction does not attain the stage by the cutoff. Such assignments are a scoring convention, not actual model attainment or a change to the raw process prediction. Scoring dates for BBCH07/65 remain unchanged. The raw attainment horizon is 31 December; actual attainment by 4 November is reported for all four stages. Actual attainment and assigned fractions are separate measures; complete scoring coverage is not evidence of complete attainment. Raw dates and fitted thresholds are unchanged by report generation.

MAE and bias average errors within sites and then give each site equal weight. RMSE is the square root of the equally weighted mean of site mean squared errors. Bias is predicted minus observed date; negative bias is early prediction. Error metrics use finite dates in the selected metric view. Site-balanced attainment averages within-site fractions; observation-weighted fractions and observation/site/scored counts remain available in `metrics.csv`. Different methods and date views can have different finite-date denominators; their differences are descriptive, not matched-pair effect estimates. No confidence intervals are available.

The main MAE figure uses a fixed 8–20-day colour scale and the main bias figure uses a fixed −10 to +10-day scale centred at zero. These limits are common across their four temperature/partition panels. Colourbar extensions identify values outside these limits if present; annotations retain the actual values. Comparison figures use separate, wider scales covering both methods and raw/scoring views, shared across temperatures and partitions. Rate panels use a common 0–100% scale. Annotation precision is one decimal day or one percentage point; `metrics.csv` retains source numeric precision. Grey cells with — indicate pending configurations, grey cells with × indicate configurations in the saved failed-unit list, and grey cells with · indicate unrequested configurations. None represents zero error. If a subset snapshot lacks `run.json`, requested identities are unavailable and — can include unrequested configurations. The complete 20-slot catalogue remains visible in fixed order. Grey cells with n/a indicate unavailable metrics in completed configurations. The figures retain pending rows even when no configuration has completed.

`metrics.csv` contains all verified source metric rows and `fit_status.csv` contains the three saved fit-status fields. `manifest.json` records the exact completed-unit list, initial status-file hash, every completed unit's artifact hashes, script hash, and generated output hashes. All declared artifacts, including prediction files when listed, are SHA-256 verified before plotting and rechecked after parsing. Report generation validates metric schema and basic numerical bounds; it does not independently recompute metrics from predictions. The completed-unit list is a fixed snapshot even if the calibration process subsequently advances.

Reproduction: `python model_run/src/report_median_cutoff.py RUN_DIR --output REPORT_DIR`. The default report directory is `RUN_DIR/report`.
'''
    (output / "README.md").write_text(readme, encoding="utf-8")
    paths.append(output / "README.md")
    manifest = dict(snapshot_utc=snapshot, run_dir=str(run), completed_units=units,
                    expected_units=expected, requested_units=sorted(requested) if run_bytes is not None or expected == 20 else None, partial=not status["complete"], failed_units=failed, smoke=smoke,
                    status_sha256=hashlib.sha256(status_bytes).hexdigest(),
                    source_sha256=hashes, script_sha256=sha256(Path(__file__)),
                    metric_rows=len(data), metric_recomputation=False,
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
