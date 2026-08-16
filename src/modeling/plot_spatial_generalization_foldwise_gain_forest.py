#!/usr/bin/env python
"""Plot fixed-hybrid spatial gains as a two-scale forest plot."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from plot_spatial_generalization_foldwise_gain import (
    DEFAULT_PREDICTIONS,
    FOLD_COLORS,
    REPO_ROOT,
    STAGE_LABELS,
    STAGE_ORDER,
    configure_matplotlib,
    load_fold_metrics,
    summarize_fold_metrics,
)


DEFAULT_OUTPUT = REPO_ROOT / "fig/results_figure/spatial_generalization_foldwise_gain_forest.png"
DEFAULT_TABLE_DIR = REPO_ROOT / "results/paper_results"
METRIC_ORDER = ("delta_mae_days", "delta_rmse_days")
METRIC_LABELS = {
    "delta_mae_days": "ΔMAE (days; hybrid - process)",
    "delta_rmse_days": "ΔRMSE (days; hybrid - process)",
}
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 4.25
BASE_FONT_SIZE = 11
LEGEND_FONT_SIZE = 10
FOLD_POINT_SIZE = 20
MEAN_MARKER_SIZE = 4.0
BREAK_THRESHOLD = -5.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fold-output", type=Path, default=None)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--dpi", type=int, default=300)
    return parser.parse_args()


def stage_y_positions() -> dict[str, float]:
    return {stage: float(len(STAGE_ORDER) - index - 1) for index, stage in enumerate(STAGE_ORDER)}


def collect_plotted_values(fold_metrics: pd.DataFrame, summary: pd.DataFrame) -> np.ndarray:
    values: list[float] = []
    for metric_name in METRIC_ORDER:
        values.extend(fold_metrics[metric_name].dropna().astype(float).tolist())
        for _, row in summary.iterrows():
            mean_value = float(row[f"fold_mean_{metric_name}"])
            se_value = float(row[f"fold_se_{metric_name}"])
            values.extend([mean_value - se_value, mean_value + se_value])
    return np.asarray(values, dtype=float)


def rounded_limits(values: np.ndarray, pad: float) -> tuple[float, float]:
    lower = np.floor((float(values.min()) - pad) * 2.0) / 2.0
    upper = np.ceil((float(values.max()) + pad) * 2.0) / 2.0
    return lower, upper


def split_x_limits(fold_metrics: pd.DataFrame, summary: pd.DataFrame) -> tuple[tuple[float, float], tuple[float, float]]:
    values = collect_plotted_values(fold_metrics, summary)
    large_gain = values[values < BREAK_THRESHOLD]
    near_zero = values[values >= BREAK_THRESHOLD]
    if len(large_gain) == 0:
        large_gain = np.asarray([-22.0, -17.0])
    if len(near_zero) == 0:
        near_zero = np.asarray([-2.0, 0.0])
    large_xlim = rounded_limits(large_gain, pad=0.55)
    near_xlim = rounded_limits(np.append(near_zero, 0.0), pad=0.20)
    near_xlim = (near_xlim[0], max(0.35, near_xlim[1]))
    return large_xlim, near_xlim


def draw_break_marks(left_axis, right_axis) -> None:
    kwargs = {"color": "#333333", "clip_on": False, "linewidth": 0.75}
    d = 0.012
    left_axis.plot((1 - d, 1 + d), (-d, +d), transform=left_axis.transAxes, **kwargs)
    left_axis.plot((1 - d, 1 + d), (1 - d, 1 + d), transform=left_axis.transAxes, **kwargs)
    right_axis.plot((-d, +d), (-d, +d), transform=right_axis.transAxes, **kwargs)
    right_axis.plot((-d, +d), (1 - d, 1 + d), transform=right_axis.transAxes, **kwargs)


def value_in_axis(value: float, xlim: tuple[float, float]) -> bool:
    return xlim[0] <= value <= xlim[1]


def draw_metric_segment(
    axis,
    fold_metrics: pd.DataFrame,
    summary: pd.DataFrame,
    metric_name: str,
    xlim: tuple[float, float],
) -> None:
    y_lookup = stage_y_positions()
    jitter_lookup = {1: -0.16, 2: -0.08, 3: 0.00, 4: 0.08, 5: 0.16}

    for stage in STAGE_ORDER:
        stage_rows = fold_metrics.loc[fold_metrics["stage"].eq(stage)].copy()
        for _, row in stage_rows.iterrows():
            value = float(row[metric_name])
            if not value_in_axis(value, xlim):
                continue
            outer_fold = int(row["outer_fold"])
            axis.scatter(
                [value],
                [y_lookup[stage] + jitter_lookup.get(outer_fold, 0.0)],
                s=FOLD_POINT_SIZE,
                marker="o",
                facecolors=FOLD_COLORS.get(outer_fold, "#4d4d4d"),
                edgecolors="white",
                linewidths=0.45,
                alpha=0.92,
                zorder=4,
            )

        summary_row = summary.loc[summary["stage"].eq(stage)].iloc[0]
        mean_value = float(summary_row[f"fold_mean_{metric_name}"])
        se_value = float(summary_row[f"fold_se_{metric_name}"])
        if value_in_axis(mean_value, xlim):
            axis.errorbar(
                [mean_value],
                [y_lookup[stage]],
                xerr=[se_value],
                fmt="D",
                markersize=MEAN_MARKER_SIZE,
                markerfacecolor="#111111",
                markeredgecolor="#111111",
                ecolor="#111111",
                elinewidth=0.75,
                capsize=2.4,
                capthick=0.75,
                zorder=6,
            )


def style_metric_axes(left_axis, right_axis, metric_name: str, panel_label: str, large_xlim, near_xlim) -> None:
    y_lookup = stage_y_positions()
    y_ticks = [y_lookup[stage] for stage in STAGE_ORDER]
    y_labels = [STAGE_LABELS[stage] for stage in STAGE_ORDER]

    for axis, xlim in ((left_axis, large_xlim), (right_axis, near_xlim)):
        axis.set_xlim(*xlim)
        axis.set_ylim(-0.55, len(STAGE_ORDER) - 0.45)
        axis.set_yticks(y_ticks, y_labels)
        axis.grid(axis="y", color="#bdbdbd", linewidth=0.35, alpha=0.55, zorder=0)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.tick_params(length=3.0, width=0.7, labelsize=BASE_FONT_SIZE)

    right_axis.axvline(0.0, color="#333333", linewidth=0.75, zorder=1)
    left_axis.spines["right"].set_visible(False)
    right_axis.spines["left"].set_visible(False)
    right_axis.tick_params(axis="y", left=False, labelleft=False)
    draw_break_marks(left_axis, right_axis)

    left_axis.text(
        0.03,
        0.96,
        panel_label,
        transform=left_axis.transAxes,
        ha="left",
        va="top",
        fontsize=BASE_FONT_SIZE,
    )


def plot(fold_metrics: pd.DataFrame, summary: pd.DataFrame, output: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    large_xlim, near_xlim = split_x_limits(fold_metrics, summary)
    fig = plt.figure(figsize=(FIG_WIDTH_IN, FIG_HEIGHT_IN))
    grid = fig.add_gridspec(
        2,
        2,
        left=0.120,
        right=0.985,
        bottom=0.130,
        top=0.760,
        width_ratios=(1.05, 2.55),
        hspace=0.56,
        wspace=0.055,
    )

    axes = []
    for row_index, metric_name in enumerate(METRIC_ORDER):
        left_axis = fig.add_subplot(grid[row_index, 0])
        right_axis = fig.add_subplot(grid[row_index, 1], sharey=left_axis)
        draw_metric_segment(left_axis, fold_metrics, summary, metric_name, large_xlim)
        draw_metric_segment(right_axis, fold_metrics, summary, metric_name, near_xlim)
        style_metric_axes(
            left_axis,
            right_axis,
            metric_name,
            "(a)" if row_index == 0 else "(b)",
            large_xlim,
            near_xlim,
        )
        axes.append((left_axis, right_axis))

    for (left_axis, right_axis), metric_name in zip(axes, METRIC_ORDER):
        left_box = left_axis.get_position()
        right_box = right_axis.get_position()
        fig.text(
            (left_box.x0 + right_box.x1) / 2.0,
            left_box.y0 - 0.065,
            METRIC_LABELS[metric_name],
            ha="center",
            va="top",
            fontsize=BASE_FONT_SIZE,
        )

    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markersize=4.2,
            markerfacecolor=FOLD_COLORS[outer_fold],
            markeredgecolor="white",
            color=FOLD_COLORS[outer_fold],
            label=f"Fold {outer_fold}",
        )
        for outer_fold in sorted(FOLD_COLORS)
    ]
    handles.append(
        Line2D(
            [0],
            [0],
            marker="D",
            linestyle="none",
            markersize=4.0,
            markerfacecolor="#111111",
            markeredgecolor="#111111",
            color="#111111",
            label="Mean ± SE",
        )
    )
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.120, 0.820, 0.865, 0.065),
        bbox_transform=fig.transFigure,
        ncol=6,
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
    fold_metrics = load_fold_metrics(args.predictions)
    summary = summarize_fold_metrics(fold_metrics)
    plot(fold_metrics, summary, args.output, args.dpi)

    fold_output = args.fold_output
    if fold_output is None:
        fold_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_fold_metrics.csv"
    summary_output = args.summary_output
    if summary_output is None:
        summary_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_summary.csv"
    fold_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    fold_metrics.to_csv(fold_output, index=False)
    summary.to_csv(summary_output, index=False)

    print("Spatial generalization forest plot")
    print(f"Predictions: {args.predictions.relative_to(REPO_ROOT)}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(f"Fold metrics: {fold_output.relative_to(REPO_ROOT)}")
    print(f"Summary: {summary_output.relative_to(REPO_ROOT)}")
    print(
        summary[
            [
                "stage",
                "fold_mean_delta_mae_days",
                "fold_se_delta_mae_days",
                "fold_mean_delta_rmse_days",
                "fold_se_delta_rmse_days",
            ]
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
