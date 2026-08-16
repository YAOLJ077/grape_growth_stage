#!/usr/bin/env python
"""Plot raw-vs-adjusted temperature differences for the fixed hybrid system."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from . import plot_raw_vs_adjusted_process_and_hybrid_difference as combined_diff
except ImportError:
    import plot_raw_vs_adjusted_process_and_hybrid_difference as combined_diff


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADJUSTED_HYBRID_PREDICTIONS = combined_diff.DEFAULT_ADJUSTED_HYBRID_PREDICTIONS
DEFAULT_RAW_HYBRID_PREDICTIONS = combined_diff.DEFAULT_RAW_HYBRID_PREDICTIONS
DEFAULT_OUTPUT = REPO_ROOT / "fig/results_figure/raw_vs_adjusted_hybrid_temperature_difference.png"
DEFAULT_TABLE_DIR = REPO_ROOT / "results/paper_results"
STAGE_ORDER = combined_diff.STAGE_ORDER
STAGE_LABELS = combined_diff.STAGE_LABELS
METRIC_LABELS = {
    "delta_mae_days": "ΔMAE (days; adjusted - raw)",
    "delta_rmse_days": "ΔRMSE (days; adjusted - raw)",
}
HYBRID_COLOR = "#666666"
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 3.45
BASE_FONT_SIZE = 11
LEGEND_FONT_SIZE = 9.5
PANEL_LABEL_FONT_SIZE = 11.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
    parser.add_argument("--fold-output", type=Path, default=None)
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


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    return float(np.average(values.to_numpy(dtype=float), weights=weights.to_numpy(dtype=float)))


def weighted_rmse_from_fold_rmse(values: pd.Series, weights: pd.Series) -> float:
    return float(
        np.sqrt(
            np.average(
                np.square(values.to_numpy(dtype=float)),
                weights=weights.to_numpy(dtype=float),
            )
        )
    )


def summarize_hybrid_temperature_difference(fold_differences: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    group_columns = ["stage", "adjusted_algorithm", "raw_algorithm"]
    for keys, group in fold_differences.groupby(group_columns, sort=False):
        row = dict(zip(group_columns, keys))
        weights = group["n_common_events"]
        row["stage_label"] = STAGE_LABELS[row["stage"]]
        row["n_outer_folds"] = int(group["outer_fold"].nunique())
        row["n_common_events"] = int(weights.sum())
        row["adjusted_mae_days"] = weighted_mean(group["adjusted_mae_days"], weights)
        row["raw_mae_days"] = weighted_mean(group["raw_mae_days"], weights)
        row["adjusted_rmse_days"] = weighted_rmse_from_fold_rmse(
            group["adjusted_rmse_days"], weights
        )
        row["raw_rmse_days"] = weighted_rmse_from_fold_rmse(group["raw_rmse_days"], weights)
        row["event_weighted_delta_mae_days"] = row["adjusted_mae_days"] - row["raw_mae_days"]
        row["event_weighted_delta_rmse_days"] = (
            row["adjusted_rmse_days"] - row["raw_rmse_days"]
        )
        for metric_name in ("delta_mae_days", "delta_rmse_days"):
            values = group[metric_name].to_numpy(dtype=float)
            row[f"fold_mean_{metric_name}"] = float(values.mean())
            row[f"fold_sd_{metric_name}"] = float(values.std(ddof=1))
            row[f"fold_se_{metric_name}"] = float(values.std(ddof=1) / np.sqrt(len(values)))
            row[f"fold_min_{metric_name}"] = float(values.min())
            row[f"fold_max_{metric_name}"] = float(values.max())
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary["stage"] = pd.Categorical(summary["stage"], categories=STAGE_ORDER, ordered=True)
    return summary.sort_values("stage").reset_index(drop=True)


def y_limits(values: pd.Series) -> tuple[float, float]:
    plotted = list(values.dropna().astype(float)) + [0.0]
    lower = min(plotted)
    upper = max(plotted)
    span = max(upper - lower, 1.0)
    margin = max(0.25, span * 0.14)
    lower = np.floor((lower - margin) * 2.0) / 2.0
    upper = np.ceil((upper + margin) * 2.0) / 2.0
    return float(lower), float(upper)


def draw_panel(
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
        value = float(row[f"fold_mean_{metric_name}"])
        se = float(row[f"fold_se_{metric_name}"])
        axis.bar(
            x,
            value,
            width=0.36,
            color=HYBRID_COLOR,
            edgecolor="white",
            linewidth=0.55,
            alpha=0.90,
            zorder=2,
        )
        axis.errorbar(
            x,
            value,
            yerr=se,
            fmt="none",
            ecolor="#333333",
            elinewidth=0.75,
            capsize=1.9,
            capthick=0.75,
            zorder=4,
        )
        jitter = np.linspace(-0.055, 0.055, len(fold))
        axis.scatter(
            np.full(len(fold), x) + jitter,
            fold[metric_name],
            s=8.0,
            marker="o",
            facecolors="white",
            edgecolors="#4d4d4d",
            linewidths=0.32,
            alpha=0.68,
            zorder=5,
        )

    axis.axhline(0.0, color="#333333", linewidth=0.75, zorder=1)
    axis.set_ylabel(METRIC_LABELS[metric_name])
    axis.set_xticks(
        [stage_x[stage] for stage in STAGE_ORDER],
        [STAGE_LABELS[stage] for stage in STAGE_ORDER],
    )
    axis.set_xlim(-0.55, len(STAGE_ORDER) - 0.45)
    axis.set_ylim(*y_limits(fold_differences[metric_name]))
    axis.grid(axis="y", color="#bdbdbd", linewidth=0.35, alpha=0.55, zorder=0)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.tick_params(length=3.0, width=0.7)
    axis.text(
        0.02,
        0.97,
        panel_label,
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=PANEL_LABEL_FONT_SIZE,
    )


def plot(summary: pd.DataFrame, fold_differences: pd.DataFrame, output: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(FIG_WIDTH_IN, FIG_HEIGHT_IN),
        sharex=True,
        gridspec_kw={
            "left": 0.085,
            "right": 0.985,
            "bottom": 0.14,
            "top": 0.755,
            "wspace": 0.20,
        },
    )
    draw_panel(axes[0], summary, fold_differences, "delta_mae_days", "(a)")
    draw_panel(axes[1], summary, fold_differences, "delta_rmse_days", "(b)")

    handles = [
        Patch(
            facecolor=HYBRID_COLOR,
            edgecolor="white",
            linewidth=0.55,
            label="Fixed hybrid",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markersize=4.0,
            markerfacecolor="white",
            markeredgecolor="#4d4d4d",
            color="#4d4d4d",
            label="Outer folds",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.085, 0.825, 0.900, 0.070),
        bbox_transform=fig.transFigure,
        ncol=2,
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


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    fold_differences = combined_diff.load_hybrid_fold_differences(
        args.adjusted_hybrid_predictions,
        args.raw_hybrid_predictions,
    )
    summary = summarize_hybrid_temperature_difference(fold_differences)
    plot(summary, fold_differences, args.output, args.dpi)

    summary_output = args.summary_output
    if summary_output is None:
        summary_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_summary.csv"
    fold_output = args.fold_output
    if fold_output is None:
        fold_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_outer_folds.csv"
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    fold_output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_output, index=False)
    fold_differences.to_csv(fold_output, index=False)

    print("Fixed hybrid raw-vs-adjusted temperature difference figure")
    print(f"Adjusted hybrid predictions: {args.adjusted_hybrid_predictions.relative_to(REPO_ROOT)}")
    print(f"Raw hybrid predictions: {args.raw_hybrid_predictions.relative_to(REPO_ROOT)}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(f"Summary: {summary_output.relative_to(REPO_ROOT)}")
    print(f"Outer folds: {fold_output.relative_to(REPO_ROOT)}")
    print(
        summary[
            [
                "stage",
                "adjusted_algorithm",
                "raw_algorithm",
                "n_common_events",
                "adjusted_mae_days",
                "raw_mae_days",
                "event_weighted_delta_mae_days",
                "adjusted_rmse_days",
                "raw_rmse_days",
                "event_weighted_delta_rmse_days",
            ]
        ]
        .round(3)
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
