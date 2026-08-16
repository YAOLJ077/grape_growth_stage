#!/usr/bin/env python
"""Plot process-model performance and terrain-temperature gain in one figure."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np

try:
    from . import plot_raw_vs_adjusted_process_model_difference as difference
    from . import plot_raw_vs_adjusted_process_model_performance as performance
except ImportError:
    import plot_raw_vs_adjusted_process_model_difference as difference
    import plot_raw_vs_adjusted_process_model_performance as performance


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTION_METRICS = performance.DEFAULT_SELECTION_METRICS
DEFAULT_OUTPUT = REPO_ROOT / "fig/results_figure/raw_vs_adjusted_process_model_combined.png"
DEFAULT_TABLE_DIR = REPO_ROOT / "results/paper_results"
STAGE_ORDER = performance.STAGE_ORDER
STAGE_LABELS = performance.STAGE_LABELS
MODEL_ORDER = performance.MODEL_ORDER
MODEL_COLORS = performance.MODEL_COLORS
MODEL_LEGEND_ORDER = performance.MODEL_LEGEND_ORDER
BRANCH_LABELS = performance.BRANCH_LABELS
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 6.45
BASE_FONT_SIZE = 11
LEGEND_FONT_SIZE = 10
PANEL_LABEL_FONT_SIZE = 11.0
STAR_COLOR = "#111111"
STAR_SIZE = 55
OUTER_FOLD_POINT_SIZE = 15
PERFORMANCE_STAR_OFFSET = 1.35
DIFFERENCE_STAR_OFFSET = 0.40


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-metrics", type=Path, default=DEFAULT_SELECTION_METRICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--performance-summary-output", type=Path, default=None)
    parser.add_argument("--difference-summary-output", type=Path, default=None)
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
            "hatch.linewidth": 0.45,
            "savefig.dpi": 300,
        }
    )


def style_stage_axis(axis, ylabel: str, panel_label: str) -> None:
    stage_x = {stage: index for index, stage in enumerate(STAGE_ORDER)}
    axis.set_ylabel(ylabel)
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
        0.97,
        panel_label,
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=PANEL_LABEL_FONT_SIZE,
    )


def draw_performance_panel(axis, summary, metric_name: str, panel_label: str) -> None:
    stage_x = {stage: index for index, stage in enumerate(STAGE_ORDER)}
    for stage in STAGE_ORDER:
        for model_id, branch, x in performance.bar_positions(stage, float(stage_x[stage])):
            row = summary.loc[
                summary["stage"].eq(stage)
                & summary["model_id"].eq(model_id)
                & summary["temperature_branch"].eq(branch)
            ].iloc[0]
            performance.draw_bar(
                axis,
                x,
                float(row[metric_name]),
                float(row[f"{metric_name}_se"]),
                str(row["model_style"]),
                branch,
                False,
            )
            if bool(row["selected_model"]):
                axis.scatter(
                    [x],
                    [
                        float(row[metric_name])
                        + float(row[f"{metric_name}_se"])
                        + PERFORMANCE_STAR_OFFSET
                    ],
                    marker="*",
                    s=STAR_SIZE,
                    color=STAR_COLOR,
                    linewidths=0.0,
                    zorder=7,
                )

    axis.set_ylim(0, float(np.ceil(summary[metric_name].max() / 5.0) * 5.0 + 3.0))
    style_stage_axis(axis, performance.METRIC_LABELS[metric_name], panel_label)


def draw_difference_panel(
    axis,
    summary,
    fold_differences,
    metric_name: str,
    panel_label: str,
) -> None:
    stage_x = {stage: index for index, stage in enumerate(STAGE_ORDER)}
    star_y_values: list[float] = []
    for stage in STAGE_ORDER:
        for model_id, x in difference.bar_positions(stage, float(stage_x[stage])):
            row = summary.loc[
                summary["stage"].eq(stage) & summary["model_id"].eq(model_id)
            ].iloc[0]
            fold = fold_differences.loc[
                fold_differences["stage"].eq(stage)
                & fold_differences["model_id"].eq(model_id)
            ].copy()
            color = MODEL_COLORS[str(row["model_style"])]
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
                s=OUTER_FOLD_POINT_SIZE,
                marker="o",
                facecolors="white",
                edgecolors="#4d4d4d",
                linewidths=0.45,
                alpha=0.78,
                zorder=5,
            )
            if bool(row["selected_model"]):
                star_y = (
                    min(
                        float(fold[metric_name].min()),
                        float(row[metric_name]) - float(row[f"{metric_name}_se"]),
                        0.0,
                    )
                    - DIFFERENCE_STAR_OFFSET
                )
                star_y_values.append(star_y)
                axis.scatter(
                    [x],
                    [star_y],
                    marker="*",
                    s=STAR_SIZE,
                    color=STAR_COLOR,
                    linewidths=0.0,
                    zorder=7,
                )

    axis.axhline(0.0, color="#333333", linewidth=0.75, zorder=1)
    axis.set_ylim(*difference.y_limits(fold_differences[metric_name], star_y_values))
    style_stage_axis(axis, difference.METRIC_LABELS[metric_name], panel_label)


def add_legend(fig, axes) -> None:
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    model_handles = [
        Patch(
            facecolor=MODEL_COLORS[label],
            edgecolor="white",
            linewidth=0.55,
            label=label,
        )
        for label in MODEL_LEGEND_ORDER
    ]
    handles = model_handles + [
        Patch(
            facecolor="white",
            edgecolor="#666666",
            hatch="////",
            linewidth=0.65,
            label=BRANCH_LABELS["raw"],
        ),
        Patch(
            facecolor="#999999",
            edgecolor="white",
            linewidth=0.55,
            label=BRANCH_LABELS["adjusted"],
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markersize=6.0,
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
            color=STAR_COLOR,
            markersize=6.0,
            label="Selected model",
        ),
    ]
    fig.canvas.draw()
    legend_left = axes[0, 0].get_position().x0
    legend_right = axes[0, 1].get_position().x1
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(legend_left, 0.838, legend_right - legend_left, 0.112),
        bbox_transform=fig.transFigure,
        ncol=5,
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


def plot(
    performance_summary,
    difference_summary,
    fold_differences,
    output: Path,
    dpi: int,
) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(FIG_WIDTH_IN, FIG_HEIGHT_IN),
        sharex=False,
        gridspec_kw={
            "left": 0.085,
            "right": 0.985,
            "bottom": 0.085,
            "top": 0.835,
            "wspace": 0.18,
            "hspace": 0.34,
        },
    )

    draw_performance_panel(axes[0, 0], performance_summary, "mae_days", "(a)")
    draw_performance_panel(axes[0, 1], performance_summary, "rmse_days", "(b)")
    draw_difference_panel(
        axes[1, 0],
        difference_summary,
        fold_differences,
        "delta_mae_days",
        "(c)",
    )
    draw_difference_panel(
        axes[1, 1],
        difference_summary,
        fold_differences,
        "delta_rmse_days",
        "(d)",
    )
    add_legend(fig, axes)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=dpi, facecolor="white")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    folds = performance.load_selection_metrics(args.selection_metrics)
    performance_summary = performance.metric_summary(folds)
    fold_differences = difference.load_fold_differences(args.selection_metrics)
    difference_summary = difference.difference_summary(fold_differences)
    plot(performance_summary, difference_summary, fold_differences, args.output, args.dpi)

    performance_summary_output = args.performance_summary_output
    if performance_summary_output is None:
        performance_summary_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_performance_summary.csv"
    difference_summary_output = args.difference_summary_output
    if difference_summary_output is None:
        difference_summary_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_temperature_gain_summary.csv"

    performance_summary_output.parent.mkdir(parents=True, exist_ok=True)
    difference_summary_output.parent.mkdir(parents=True, exist_ok=True)
    performance_summary.to_csv(performance_summary_output, index=False)
    difference_summary.to_csv(difference_summary_output, index=False)

    print("Combined process-model performance and temperature-gain figure")
    print(f"Selection metrics: {args.selection_metrics.relative_to(REPO_ROOT)}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(f"Performance summary: {performance_summary_output.relative_to(REPO_ROOT)}")
    print(f"Temperature-gain summary: {difference_summary_output.relative_to(REPO_ROOT)}")
    print("\nSelected adjusted process-model performance:")
    selected_performance = performance_summary.loc[
        performance_summary["selected_model"]
        & performance_summary["temperature_branch"].eq("adjusted"),
        ["stage", "model_style", "mae_days", "rmse_days"],
    ].copy()
    print(selected_performance.round(3).to_string(index=False))
    print("\nSelected model temperature gain (adjusted - raw; negative means improvement):")
    selected_difference = difference_summary.loc[
        difference_summary["selected_model"],
        ["stage", "model_style", "delta_mae_days", "delta_rmse_days"],
    ].copy()
    print(selected_difference.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
