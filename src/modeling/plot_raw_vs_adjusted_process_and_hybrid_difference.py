#!/usr/bin/env python
"""Plot raw-vs-adjusted differences for process and final hybrid systems."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from . import plot_raw_vs_adjusted_process_model_difference as process_diff
except ImportError:
    import plot_raw_vs_adjusted_process_model_difference as process_diff


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTION_METRICS = process_diff.DEFAULT_SELECTION_METRICS
DEFAULT_ADJUSTED_HYBRID_PREDICTIONS = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/"
    "doyrange21_postflower_water_spatial_ablation_pruned_fixed_stage_models_refit/"
    "fixed_stage_outer_predictions.parquet"
)
DEFAULT_RAW_HYBRID_PREDICTIONS = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/"
    "raw_temperature_doyrange21_postflower_water_spatial_ablation_pruned_fixed_stage_models_refit/"
    "fixed_stage_outer_predictions.parquet"
)
DEFAULT_OUTPUT = REPO_ROOT / "fig/results_figure/raw_vs_adjusted_process_and_hybrid_difference.png"
DEFAULT_TABLE_DIR = REPO_ROOT / "results/paper_results"
STAGE_ORDER = process_diff.STAGE_ORDER
STAGE_LABELS = process_diff.STAGE_LABELS
METRIC_LABELS = {
    "delta_mae_days": {
        "process": "Process ΔMAE (days)",
        "hybrid": "Hybrid ΔMAE (days)",
    },
    "delta_rmse_days": {
        "process": "Process ΔRMSE (days)",
        "hybrid": "Hybrid ΔRMSE (days)",
    },
}
HYBRID_COLOR = "#666666"
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 5.35
BASE_FONT_SIZE = 10
LEGEND_FONT_SIZE = 7.8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-metrics", type=Path, default=DEFAULT_SELECTION_METRICS)
    parser.add_argument(
        "--adjusted-hybrid-predictions",
        type=Path,
        default=DEFAULT_ADJUSTED_HYBRID_PREDICTIONS,
    )
    parser.add_argument(
        "--raw-hybrid-predictions",
        type=Path,
        default=DEFAULT_RAW_HYBRID_PREDICTIONS,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--dpi", type=int, default=300)
    return parser.parse_args()


def configure_matplotlib() -> None:
    cache_dir = Path(tempfile.gettempdir()) / "grape_growth_stage_mplconfig"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.size": BASE_FONT_SIZE,
            "axes.labelsize": BASE_FONT_SIZE,
            "axes.titlesize": BASE_FONT_SIZE,
            "xtick.labelsize": BASE_FONT_SIZE,
            "ytick.labelsize": BASE_FONT_SIZE,
            "legend.fontsize": LEGEND_FONT_SIZE,
            "axes.linewidth": 0.75,
            "axes.unicode_minus": False,
            "savefig.dpi": 300,
        }
    )


def load_hybrid_fold_differences(
    adjusted_predictions_path: Path,
    raw_predictions_path: Path,
) -> pd.DataFrame:
    required = {
        "stage",
        "outer_fold",
        "algorithm",
        "record_id",
        "observed_doy",
        "hybrid_predicted_doy",
    }
    adjusted = pd.read_parquet(adjusted_predictions_path)
    raw = pd.read_parquet(raw_predictions_path)
    for path, data in (
        (adjusted_predictions_path, adjusted),
        (raw_predictions_path, raw),
    ):
        missing = required.difference(data.columns)
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")

    adjusted = adjusted.loc[adjusted["stage"].isin(STAGE_ORDER)].copy()
    raw = raw.loc[raw["stage"].isin(STAGE_ORDER)].copy()
    keys = ["stage", "outer_fold", "record_id"]
    for path, data in (
        (adjusted_predictions_path, adjusted),
        (raw_predictions_path, raw),
    ):
        duplicated = data.duplicated(keys).sum()
        if duplicated:
            raise ValueError(f"{path} has duplicated prediction keys: {duplicated}")

    paired = adjusted.merge(raw, on=keys, suffixes=("_adjusted", "_raw"))
    if paired.empty:
        raise ValueError("No paired adjusted/raw hybrid predictions were found.")
    if not np.allclose(paired["observed_doy_adjusted"], paired["observed_doy_raw"]):
        raise ValueError("Paired adjusted/raw hybrid predictions have different observed DOY values.")

    rows: list[dict[str, object]] = []
    for (stage, outer_fold), group in paired.groupby(["stage", "outer_fold"], sort=False):
        observed = group["observed_doy_adjusted"].to_numpy(dtype=float)
        adjusted_error = group["hybrid_predicted_doy_adjusted"].to_numpy(dtype=float) - observed
        raw_error = group["hybrid_predicted_doy_raw"].to_numpy(dtype=float) - observed
        adjusted_algorithm = "|".join(sorted(group["algorithm_adjusted"].unique()))
        raw_algorithm = "|".join(sorted(group["algorithm_raw"].unique()))
        rows.append(
            {
                "stage": stage,
                "outer_fold": outer_fold,
                "model_id": "final_hybrid_system",
                "model_style": "Final hybrid",
                "selected_model": True,
                "adjusted_algorithm": adjusted_algorithm,
                "raw_algorithm": raw_algorithm,
                "n_common_events": int(len(group)),
                "adjusted_mae_days": float(np.mean(np.abs(adjusted_error))),
                "raw_mae_days": float(np.mean(np.abs(raw_error))),
                "adjusted_rmse_days": float(np.sqrt(np.mean(adjusted_error**2))),
                "raw_rmse_days": float(np.sqrt(np.mean(raw_error**2))),
            }
        )
    differences = pd.DataFrame(rows)
    differences["delta_mae_days"] = (
        differences["adjusted_mae_days"] - differences["raw_mae_days"]
    )
    differences["delta_rmse_days"] = (
        differences["adjusted_rmse_days"] - differences["raw_rmse_days"]
    )
    return differences


def summarize_hybrid_differences(fold_differences: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    group_columns = [
        "stage",
        "model_id",
        "model_style",
        "selected_model",
        "adjusted_algorithm",
        "raw_algorithm",
    ]
    for keys, group in fold_differences.groupby(group_columns, sort=False):
        row = dict(zip(group_columns, keys))
        row["n_outer_rounds"] = int(group["outer_fold"].nunique())
        row["n_common_events"] = int(group["n_common_events"].sum())
        for metric_name in ("delta_mae_days", "delta_rmse_days"):
            values = group[metric_name].to_numpy(dtype=float)
            row[metric_name] = float(values.mean())
            row[f"{metric_name}_sd"] = float(values.std(ddof=1))
            row[f"{metric_name}_se"] = float(values.std(ddof=1) / np.sqrt(len(values)))
            row[f"{metric_name}_min"] = float(values.min())
            row[f"{metric_name}_max"] = float(values.max())
        rows.append(row)
    return pd.DataFrame(rows)


def y_limits(values: pd.Series, star_values: list[float] | None = None) -> tuple[float, float]:
    plotted = list(values.dropna().astype(float))
    if star_values:
        plotted.extend(star_values)
    plotted.append(0.0)
    lower = min(plotted)
    upper = max(plotted)
    span = max(upper - lower, 1.0)
    margin = max(0.25, span * 0.11)
    lower = np.floor((lower - margin) * 2.0) / 2.0
    upper = np.ceil((upper + margin) * 2.0) / 2.0
    return float(lower), float(upper)


def style_axis(axis, metric_name: str, component: str, panel_label: str) -> None:
    stage_x = {stage: index for index, stage in enumerate(STAGE_ORDER)}
    axis.axhline(0.0, color="#333333", linewidth=0.75, zorder=1)
    axis.set_ylabel(METRIC_LABELS[metric_name][component])
    axis.set_xticks(
        [stage_x[stage] for stage in STAGE_ORDER],
        [STAGE_LABELS[stage] for stage in STAGE_ORDER],
    )
    axis.set_xlim(-0.55, len(STAGE_ORDER) - 0.45)
    axis.grid(axis="y", color="#bdbdbd", linewidth=0.35, alpha=0.55, zorder=0)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.tick_params(length=3.0, width=0.7)
    axis.text(
        0.02,
        0.93,
        panel_label,
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=BASE_FONT_SIZE,
    )


def draw_process_panel(
    axis,
    summary: pd.DataFrame,
    fold_differences: pd.DataFrame,
    metric_name: str,
    panel_label: str,
) -> None:
    stage_x = {stage: index for index, stage in enumerate(STAGE_ORDER)}
    star_y_values = []
    for stage in STAGE_ORDER:
        for model_id, x in process_diff.bar_positions(stage, float(stage_x[stage])):
            row = summary.loc[
                summary["stage"].eq(stage) & summary["model_id"].eq(model_id)
            ].iloc[0]
            fold = fold_differences.loc[
                fold_differences["stage"].eq(stage)
                & fold_differences["model_id"].eq(model_id)
            ].copy()
            color = process_diff.MODEL_COLORS[str(row["model_style"])]
            axis.bar(
                x,
                float(row[metric_name]),
                width=0.155,
                color=color,
                edgecolor="white",
                linewidth=0.55,
                alpha=0.90,
                zorder=2,
            )
            axis.errorbar(
                x,
                float(row[metric_name]),
                yerr=float(row[f"{metric_name}_se"]),
                fmt="none",
                ecolor="#333333",
                elinewidth=0.75,
                capsize=1.9,
                capthick=0.75,
                zorder=4,
            )
            jitter = np.linspace(-0.030, 0.030, len(fold))
            axis.scatter(
                np.full(len(fold), x) + jitter,
                fold[metric_name],
                s=7.0,
                marker="o",
                facecolors="white",
                edgecolors="#4d4d4d",
                linewidths=0.28,
                alpha=0.65,
                zorder=5,
            )
            if bool(row["selected_model"]):
                star_y = (
                    max(
                        float(fold[metric_name].max()),
                        float(row[metric_name]) + float(row[f"{metric_name}_se"]),
                    )
                    + 0.18
                )
                star_y_values.append(star_y)
                axis.scatter(
                    [x],
                    [star_y],
                    marker="*",
                    s=20,
                    color="#111111",
                    linewidths=0.0,
                    zorder=6,
                )

    style_axis(axis, metric_name, "process", panel_label)
    axis.set_ylim(*y_limits(fold_differences[metric_name], star_y_values))


def draw_hybrid_panel(
    axis,
    summary: pd.DataFrame,
    fold_differences: pd.DataFrame,
    metric_name: str,
    panel_label: str,
) -> None:
    stage_x = {stage: index for index, stage in enumerate(STAGE_ORDER)}
    for stage in STAGE_ORDER:
        x = float(stage_x[stage])
        row = summary.loc[summary["stage"].eq(stage)].iloc[0]
        fold = fold_differences.loc[fold_differences["stage"].eq(stage)].copy()
        axis.bar(
            x,
            float(row[metric_name]),
            width=0.34,
            color=HYBRID_COLOR,
            edgecolor="white",
            linewidth=0.55,
            alpha=0.90,
            zorder=2,
        )
        axis.errorbar(
            x,
            float(row[metric_name]),
            yerr=float(row[f"{metric_name}_se"]),
            fmt="none",
            ecolor="#333333",
            elinewidth=0.75,
            capsize=1.9,
            capthick=0.75,
            zorder=4,
        )
        jitter = np.linspace(-0.045, 0.045, len(fold))
        axis.scatter(
            np.full(len(fold), x) + jitter,
            fold[metric_name],
            s=7.0,
            marker="o",
            facecolors="white",
            edgecolors="#4d4d4d",
            linewidths=0.28,
            alpha=0.65,
            zorder=5,
        )

    style_axis(axis, metric_name, "hybrid", panel_label)
    axis.set_ylim(*y_limits(fold_differences[metric_name]))


def plot(
    process_summary: pd.DataFrame,
    process_folds: pd.DataFrame,
    hybrid_summary: pd.DataFrame,
    hybrid_folds: pd.DataFrame,
    output: Path,
    dpi: int,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(FIG_WIDTH_IN, FIG_HEIGHT_IN),
        sharex=False,
        gridspec_kw={
            "left": 0.085,
            "right": 0.985,
            "bottom": 0.085,
            "top": 0.780,
            "wspace": 0.22,
            "hspace": 0.40,
        },
    )

    draw_process_panel(axes[0, 0], process_summary, process_folds, "delta_mae_days", "(a)")
    draw_process_panel(axes[0, 1], process_summary, process_folds, "delta_rmse_days", "(b)")
    draw_hybrid_panel(axes[1, 0], hybrid_summary, hybrid_folds, "delta_mae_days", "(c)")
    draw_hybrid_panel(axes[1, 1], hybrid_summary, hybrid_folds, "delta_rmse_days", "(d)")

    handles = [
        Patch(
            facecolor=process_diff.MODEL_COLORS[label],
            edgecolor="white",
            linewidth=0.55,
            label=label,
        )
        for label in process_diff.MODEL_LEGEND_ORDER
    ]
    handles.extend(
        [
            Patch(
                facecolor=HYBRID_COLOR,
                edgecolor="white",
                linewidth=0.55,
                label="Final hybrid",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="none",
                markersize=3.6,
                markerfacecolor="white",
                markeredgecolor="#4d4d4d",
                color="#4d4d4d",
                label="Outer folds",
            ),
            Line2D(
                [0],
                [0],
                marker="*",
                linestyle="none",
                color="#111111",
                markersize=5.2,
                label="Selected process model",
            ),
        ]
    )
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.085, 0.835, 0.900, 0.125),
        bbox_transform=fig.transFigure,
        ncol=4,
        mode="expand",
        frameon=True,
        fancybox=False,
        facecolor="white",
        edgecolor="#bdbdbd",
        framealpha=1.0,
        handlelength=1.0,
        handletextpad=0.25,
        columnspacing=0.35,
        fontsize=LEGEND_FONT_SIZE,
        borderaxespad=0.0,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=dpi, facecolor="white")
    plt.close(fig)


def combined_summary(process_summary: pd.DataFrame, hybrid_summary: pd.DataFrame) -> pd.DataFrame:
    process = process_summary.copy()
    process["component"] = "process"
    process["adjusted_algorithm"] = ""
    process["raw_algorithm"] = ""
    process["n_common_events"] = np.nan
    hybrid = hybrid_summary.copy()
    hybrid["component"] = "hybrid"
    shared_columns = [
        "component",
        "stage",
        "model_id",
        "model_style",
        "selected_model",
        "adjusted_algorithm",
        "raw_algorithm",
        "n_outer_rounds",
        "n_common_events",
        "delta_mae_days",
        "delta_mae_days_sd",
        "delta_mae_days_se",
        "delta_mae_days_min",
        "delta_mae_days_max",
        "delta_rmse_days",
        "delta_rmse_days_sd",
        "delta_rmse_days_se",
        "delta_rmse_days_min",
        "delta_rmse_days_max",
    ]
    return pd.concat(
        [process.reindex(columns=shared_columns), hybrid.reindex(columns=shared_columns)],
        ignore_index=True,
    )


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    process_folds = process_diff.load_fold_differences(args.selection_metrics)
    process_summary = process_diff.difference_summary(process_folds)
    hybrid_folds = load_hybrid_fold_differences(
        args.adjusted_hybrid_predictions,
        args.raw_hybrid_predictions,
    )
    hybrid_summary = summarize_hybrid_differences(hybrid_folds)
    plot(process_summary, process_folds, hybrid_summary, hybrid_folds, args.output, args.dpi)

    summary_output = args.summary_output
    if summary_output is None:
        summary_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_summary.csv"
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary = combined_summary(process_summary, hybrid_summary)
    summary.to_csv(summary_output, index=False)

    print("Raw-vs-adjusted process and hybrid paired difference figure")
    print(f"Process selection metrics: {args.selection_metrics.relative_to(REPO_ROOT)}")
    print(f"Adjusted hybrid predictions: {args.adjusted_hybrid_predictions.relative_to(REPO_ROOT)}")
    print(f"Raw hybrid predictions: {args.raw_hybrid_predictions.relative_to(REPO_ROOT)}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(f"Summary: {summary_output.relative_to(REPO_ROOT)}")
    print("\nHybrid final-system difference (adjusted - raw; paired common events):")
    print(
        hybrid_summary[
            [
                "stage",
                "adjusted_algorithm",
                "raw_algorithm",
                "n_common_events",
                "delta_mae_days",
                "delta_rmse_days",
            ]
        ]
        .round(3)
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
