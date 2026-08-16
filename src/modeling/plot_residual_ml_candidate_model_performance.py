#!/usr/bin/env python
"""Plot residual-learning candidate model performance by stage."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/"
    "main_final_minrmse_four_stage"
)
DEFAULT_FIXED_SELECTION = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/"
    "main_final_fixed_stage_models_refit/"
    "fixed_stage_algorithm_selection.csv"
)
DEFAULT_OUTPUT = REPO_ROOT / "fig/results_figure/residual_ml_candidate_model_performance.png"
DEFAULT_TABLE_DIR = REPO_ROOT / "results/paper_results"
STAGE_ORDER = ("budburst", "flowering", "veraison", "maturity_or_harvest")
INSET_STAGE_ORDER = ("budburst", "flowering", "veraison")
STAGE_LABELS = {
    "budburst": "BBCH07",
    "flowering": "BBCH65",
    "veraison": "BBCH81",
    "maturity_or_harvest": "BBCH89",
}
ALGORITHM_ORDER = ("mechanistic", "ridge", "gam", "rf", "xgboost", "lightgbm")
ALGORITHM_LABELS = {
    "mechanistic": "Process",
    "ridge": "Ridge",
    "gam": "GAM",
    "rf": "RF",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
}
ALGORITHM_COLORS = {
    "mechanistic": "#8f8f8f",
    "ridge": "#0072B2",
    "gam": "#009E73",
    "rf": "#D55E00",
    "xgboost": "#8E63B0",
    "lightgbm": "#E69F00",
}
METRIC_LABELS = {"mae_days": "MAE (days)", "rmse_days": "RMSE (days)"}
GAIN_METRIC_LABELS = {
    "delta_mae_days": "ΔMAE (days; hybrid - process)",
    "delta_rmse_days": "ΔRMSE (days; hybrid - process)",
}
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 6.45
BASE_FONT_SIZE = 11
LEGEND_FONT_SIZE = 10.0
PANEL_LABEL_FONT_SIZE = 11.0
MAIN_OUTER_FOLD_POINT_SIZE = 8.5
PERFORMANCE_STAR_SIZE = 38
GAIN_STAR_SIZE = 38
PERFORMANCE_STAR_OFFSET = 1.05
GAIN_STAR_OFFSET = 0.24
INSET_GAIN_STAR_OFFSET = 0.18
INSET_FONT_SIZE = 7.8
INSET_POINT_SIZE = 5.2
INSET_STAR_SIZE = 26
STAR_VERTICAL_OFFSETS = {
    "mae_days": {
        "budburst": 0.70,
        "flowering": 0.65,
        "veraison": 0.85,
        "maturity_or_harvest": 0.75,
    },
    "rmse_days": {
        "budburst": 0.80,
        "flowering": 0.75,
        "veraison": 0.95,
        "maturity_or_harvest": 0.85,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE_DIR)
    parser.add_argument("--fixed-selection", type=Path, default=DEFAULT_FIXED_SELECTION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--gain-summary-output", type=Path, default=None)
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


def load_candidate_metrics(candidate_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    aggregate_path = candidate_dir / "aggregate_outer_metrics.csv"
    folds_path = candidate_dir / "outer_fold_metrics.csv"
    aggregate = pd.read_csv(aggregate_path)
    folds = pd.read_csv(folds_path)
    required = {"stage", "algorithm", "mae_days", "rmse_days", "bias_days"}
    missing_aggregate = required.difference(aggregate.columns)
    missing_folds = required.union({"outer_fold"}).difference(folds.columns)
    if missing_aggregate:
        raise ValueError(f"{aggregate_path} is missing columns: {sorted(missing_aggregate)}")
    if missing_folds:
        raise ValueError(f"{folds_path} is missing columns: {sorted(missing_folds)}")

    aggregate = aggregate.loc[
        aggregate["stage"].isin(STAGE_ORDER) & aggregate["algorithm"].isin(ALGORITHM_ORDER)
    ].copy()
    folds = folds.loc[
        folds["stage"].isin(STAGE_ORDER) & folds["algorithm"].isin(ALGORITHM_ORDER)
    ].copy()
    expected = {(stage, algorithm) for stage in STAGE_ORDER for algorithm in ALGORITHM_ORDER}
    actual = set(zip(aggregate["stage"], aggregate["algorithm"]))
    missing = sorted(expected.difference(actual))
    if missing:
        raise ValueError(f"Missing expected stage/algorithm aggregate rows: {missing}")

    fold_error = (
        folds.groupby(["stage", "algorithm"], sort=False)[["mae_days", "rmse_days"]]
        .agg(["mean", "std", "sem"])
        .reset_index()
    )
    fold_error.columns = [
        "_".join(part for part in column if part)
        for column in fold_error.columns.to_flat_index()
    ]
    fold_error = fold_error.rename(
        columns={
            "mae_days_mean": "fold_mean_mae_days",
            "mae_days_std": "fold_sd_mae_days",
            "mae_days_sem": "fold_se_mae_days",
            "rmse_days_mean": "fold_mean_rmse_days",
            "rmse_days_std": "fold_sd_rmse_days",
            "rmse_days_sem": "fold_se_rmse_days",
        }
    )
    aggregate = aggregate.merge(fold_error, on=["stage", "algorithm"], how="left")
    aggregate["algorithm_label"] = aggregate["algorithm"].map(ALGORITHM_LABELS)
    folds["algorithm_label"] = folds["algorithm"].map(ALGORITHM_LABELS)
    return aggregate, folds


def load_fixed_selection(path: Path) -> dict[str, str]:
    selection = pd.read_csv(path)
    required = {"stage", "fixed_residual_algorithm"}
    missing = required.difference(selection.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    return selection.set_index("stage")["fixed_residual_algorithm"].to_dict()


def bar_positions(stage_x: float) -> list[tuple[str, float]]:
    bar_width = 0.110
    gap = 0.015
    total_width = len(ALGORITHM_ORDER) * bar_width + (len(ALGORITHM_ORDER) - 1) * gap
    start = stage_x - total_width / 2 + bar_width / 2
    return [
        (algorithm, start + index * (bar_width + gap))
        for index, algorithm in enumerate(ALGORITHM_ORDER)
    ]


def gain_bar_positions(
    stage_x: float,
    bar_width: float = 0.118,
    gap: float = 0.017,
) -> list[tuple[str, float]]:
    algorithms = [algorithm for algorithm in ALGORITHM_ORDER if algorithm != "mechanistic"]
    total_width = len(algorithms) * bar_width + (len(algorithms) - 1) * gap
    start = stage_x - total_width / 2 + bar_width / 2
    return [
        (algorithm, start + index * (bar_width + gap))
        for index, algorithm in enumerate(algorithms)
    ]


def compute_gain_metrics(folds: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    process = folds.loc[folds["algorithm"].eq("mechanistic")].copy()
    process = process[
        [
            "stage",
            "outer_fold",
            "mae_days",
            "rmse_days",
        ]
    ].rename(
        columns={
            "mae_days": "process_mae_days",
            "rmse_days": "process_rmse_days",
        }
    )
    hybrid = folds.loc[~folds["algorithm"].eq("mechanistic")].copy()
    gain_folds = hybrid.merge(process, on=["stage", "outer_fold"], how="left")
    if gain_folds[["process_mae_days", "process_rmse_days"]].isna().any().any():
        raise ValueError("Missing process baseline rows for fold-wise hybrid gain calculation.")
    gain_folds["delta_mae_days"] = gain_folds["mae_days"] - gain_folds["process_mae_days"]
    gain_folds["delta_rmse_days"] = gain_folds["rmse_days"] - gain_folds["process_rmse_days"]

    rows: list[dict[str, object]] = []
    for (stage, algorithm), group in gain_folds.groupby(["stage", "algorithm"], sort=False):
        row: dict[str, object] = {
            "stage": stage,
            "algorithm": algorithm,
            "algorithm_label": ALGORITHM_LABELS[algorithm],
            "n_outer_folds": int(group["outer_fold"].nunique()),
        }
        for metric_name in ("delta_mae_days", "delta_rmse_days"):
            values = group[metric_name].to_numpy(dtype=float)
            row[metric_name] = float(values.mean())
            row[f"{metric_name}_sd"] = float(values.std(ddof=1))
            row[f"{metric_name}_se"] = float(values.std(ddof=1) / np.sqrt(len(values)))
            row[f"{metric_name}_min"] = float(values.min())
            row[f"{metric_name}_max"] = float(values.max())
        rows.append(row)
    return pd.DataFrame(rows), gain_folds


def y_limits(values: pd.Series, star_values: list[float] | None = None) -> tuple[float, float]:
    plotted = list(values.dropna().astype(float)) + [0.0]
    if star_values:
        plotted.extend(star_values)
    lower = min(plotted)
    upper = max(plotted)
    span = max(upper - lower, 1.0)
    margin = max(0.30, span * 0.12)
    lower = np.floor((lower - margin) * 2.0) / 2.0
    upper = np.ceil((upper + margin) * 2.0) / 2.0
    return float(lower), float(upper)


def style_axis(axis, ylabel: str, panel_label: str) -> None:
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


def draw_performance_panel(
    axis,
    aggregate: pd.DataFrame,
    folds: pd.DataFrame,
    fixed_selection: dict[str, str],
    metric_name: str,
    panel_label: str,
) -> None:
    stage_x = {stage: index for index, stage in enumerate(STAGE_ORDER)}
    se_column = "fold_se_mae_days" if metric_name == "mae_days" else "fold_se_rmse_days"
    star_y_values = []
    for stage in STAGE_ORDER:
        for algorithm, x in bar_positions(float(stage_x[stage])):
            row = aggregate.loc[
                aggregate["stage"].eq(stage)
                & aggregate["algorithm"].eq(algorithm)
            ].iloc[0]
            fold = folds.loc[
                folds["stage"].eq(stage)
                & folds["algorithm"].eq(algorithm)
            ].copy()
            jitter = np.linspace(-0.024, 0.024, len(fold))
            axis.bar(
                x,
                float(row[metric_name]),
                width=0.110,
                color=ALGORITHM_COLORS[algorithm],
                edgecolor="white",
                linewidth=0.55,
                alpha=0.88,
                zorder=2,
            )
            axis.errorbar(
                x,
                float(row[metric_name]),
                yerr=float(row[se_column]),
                fmt="none",
                ecolor="#333333",
                elinewidth=0.75,
                capsize=1.9,
                capthick=0.75,
                zorder=4,
            )
            axis.scatter(
                np.full(len(fold), x) + jitter,
                fold[metric_name],
                s=MAIN_OUTER_FOLD_POINT_SIZE,
                marker="o",
                facecolors="white",
                edgecolors="#4d4d4d",
                linewidths=0.28,
                alpha=0.62,
                zorder=5,
            )
            if fixed_selection.get(stage) == algorithm:
                star_y = (
                    max(
                        float(fold[metric_name].max()),
                        float(row[metric_name]) + float(row[se_column]),
                    )
                    + PERFORMANCE_STAR_OFFSET
                )
                star_y_values.append(star_y)
                axis.scatter(
                    [x],
                    [star_y],
                    marker="*",
                    s=PERFORMANCE_STAR_SIZE,
                    color="#111111",
                    linewidths=0.0,
                    zorder=6,
                )

    axis_top = max(float(aggregate[metric_name].max()), max(star_y_values, default=0.0))
    axis.set_ylim(0, float(np.ceil(axis_top / 5.0) * 5.0 + 3.0))
    style_axis(axis, METRIC_LABELS[metric_name], panel_label)


def draw_gain_panel(
    axis,
    gain_summary: pd.DataFrame,
    gain_folds: pd.DataFrame,
    fixed_selection: dict[str, str],
    metric_name: str,
    panel_label: str,
) -> None:
    stage_x = {stage: index for index, stage in enumerate(STAGE_ORDER)}
    star_y_values = draw_gain_content(
        axis,
        gain_summary,
        gain_folds,
        fixed_selection,
        metric_name,
        STAGE_ORDER,
        stage_x,
        bar_width=0.118,
        gap=0.017,
        point_size=MAIN_OUTER_FOLD_POINT_SIZE,
        star_size=GAIN_STAR_SIZE,
        star_offset=GAIN_STAR_OFFSET,
    )
    axis.axhline(0.0, color="#333333", linewidth=0.75, zorder=1)
    axis.set_ylim(*y_limits(gain_folds[metric_name], star_y_values))
    style_axis(axis, GAIN_METRIC_LABELS[metric_name], panel_label)
    add_gain_inset(axis, gain_summary, gain_folds, fixed_selection, metric_name)


def draw_gain_content(
    axis,
    gain_summary: pd.DataFrame,
    gain_folds: pd.DataFrame,
    fixed_selection: dict[str, str],
    metric_name: str,
    stages: tuple[str, ...],
    stage_x: dict[str, int],
    bar_width: float,
    gap: float,
    point_size: float,
    star_size: float,
    star_offset: float,
) -> list[float]:
    star_y_values: list[float] = []
    for stage in stages:
        for algorithm, x in gain_bar_positions(float(stage_x[stage]), bar_width=bar_width, gap=gap):
            row = gain_summary.loc[
                gain_summary["stage"].eq(stage)
                & gain_summary["algorithm"].eq(algorithm)
            ].iloc[0]
            fold = gain_folds.loc[
                gain_folds["stage"].eq(stage)
                & gain_folds["algorithm"].eq(algorithm)
            ].copy()
            axis.bar(
                x,
                float(row[metric_name]),
                width=bar_width,
                color=ALGORITHM_COLORS[algorithm],
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
                s=point_size,
                marker="o",
                facecolors="white",
                edgecolors="#4d4d4d",
                linewidths=0.28,
                alpha=0.65,
                zorder=5,
            )
            if fixed_selection.get(stage) == algorithm:
                star_y = (
                    min(
                        float(fold[metric_name].min()),
                        float(row[metric_name]) - float(row[f"{metric_name}_se"]),
                        0.0,
                    )
                    - star_offset
                )
                star_y_values.append(star_y)
                axis.scatter(
                    [x],
                    [star_y],
                    marker="*",
                    s=star_size,
                    color="#111111",
                    linewidths=0.0,
                    zorder=6,
                )
    return star_y_values


def add_gain_inset(
    axis,
    gain_summary: pd.DataFrame,
    gain_folds: pd.DataFrame,
    fixed_selection: dict[str, str],
    metric_name: str,
) -> None:
    inset = axis.inset_axes([0.115, 0.075, 0.600, 0.405])
    inset_stage_x = {stage: index for index, stage in enumerate(INSET_STAGE_ORDER)}
    star_y_values = draw_gain_content(
        inset,
        gain_summary,
        gain_folds,
        fixed_selection,
        metric_name,
        INSET_STAGE_ORDER,
        inset_stage_x,
        bar_width=0.105,
        gap=0.013,
        point_size=INSET_POINT_SIZE,
        star_size=INSET_STAR_SIZE,
        star_offset=INSET_GAIN_STAR_OFFSET,
    )
    zoom_folds = gain_folds.loc[gain_folds["stage"].isin(INSET_STAGE_ORDER)]
    inset.axhline(0.0, color="#333333", linewidth=0.60, zorder=1)
    inset.set_ylim(*y_limits(zoom_folds[metric_name], star_y_values))
    inset.set_xlim(-0.50, len(INSET_STAGE_ORDER) - 0.50)
    inset.set_xticks(
        [inset_stage_x[stage] for stage in INSET_STAGE_ORDER],
        [STAGE_LABELS[stage] for stage in INSET_STAGE_ORDER],
    )
    inset.tick_params(axis="both", labelsize=INSET_FONT_SIZE, length=2.0, width=0.55, pad=1.0)
    inset.grid(axis="y", color="#d4d4d4", linewidth=0.30, alpha=0.65, zorder=0)
    inset.set_facecolor("white")
    for spine in inset.spines.values():
        spine.set_visible(True)
        spine.set_color("#777777")
        spine.set_linewidth(0.60)
    inset.text(
        0.03,
        0.93,
        "BBCH07–81",
        transform=inset.transAxes,
        ha="left",
        va="top",
        fontsize=INSET_FONT_SIZE,
    )


def plot(
    aggregate: pd.DataFrame,
    folds: pd.DataFrame,
    gain_summary: pd.DataFrame,
    gain_folds: pd.DataFrame,
    fixed_selection: dict[str, str],
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
            "top": 0.815,
            "wspace": 0.18,
            "hspace": 0.34,
        },
    )
    draw_performance_panel(axes[0, 0], aggregate, folds, fixed_selection, "mae_days", "(a)")
    draw_performance_panel(axes[0, 1], aggregate, folds, fixed_selection, "rmse_days", "(b)")
    draw_gain_panel(
        axes[1, 0],
        gain_summary,
        gain_folds,
        fixed_selection,
        "delta_mae_days",
        "(c)",
    )
    draw_gain_panel(
        axes[1, 1],
        gain_summary,
        gain_folds,
        fixed_selection,
        "delta_rmse_days",
        "(d)",
    )

    handles = [
        Patch(
            facecolor=ALGORITHM_COLORS[algorithm],
            edgecolor="white",
            linewidth=0.55,
            label=ALGORITHM_LABELS[algorithm],
        )
        for algorithm in ALGORITHM_ORDER
    ]
    handles.extend(
        [
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="none",
                markersize=5.2,
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
                markersize=6.0,
                label="Selected model",
            ),
        ]
    )
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.085, 0.822, 0.900, 0.082),
        bbox_transform=fig.transFigure,
        ncol=8,
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
    aggregate, folds = load_candidate_metrics(args.candidate_dir)
    gain_summary, gain_folds = compute_gain_metrics(folds)
    fixed_selection = load_fixed_selection(args.fixed_selection)
    plot(aggregate, folds, gain_summary, gain_folds, fixed_selection, args.output, args.dpi)

    summary_output = args.summary_output
    if summary_output is None:
        summary_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_summary.csv"
    gain_summary_output = args.gain_summary_output
    if gain_summary_output is None:
        gain_summary_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_gain_summary.csv"
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    gain_summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary = aggregate.copy()
    summary["selected_fixed_model"] = summary.apply(
        lambda row: fixed_selection.get(row["stage"]) == row["algorithm"],
        axis=1,
    )
    gain_summary = gain_summary.copy()
    gain_summary["selected_fixed_model"] = gain_summary.apply(
        lambda row: fixed_selection.get(row["stage"]) == row["algorithm"],
        axis=1,
    )
    summary.to_csv(summary_output, index=False)
    gain_summary.to_csv(gain_summary_output, index=False)

    print("Residual ML candidate model performance figure")
    print(f"Candidate directory: {args.candidate_dir.relative_to(REPO_ROOT)}")
    print(f"Fixed selection: {args.fixed_selection.relative_to(REPO_ROOT)}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(f"Summary: {summary_output.relative_to(REPO_ROOT)}")
    print(f"Gain summary: {gain_summary_output.relative_to(REPO_ROOT)}")
    print(
        summary.pivot_table(
            index=["stage", "algorithm_label"],
            columns="selected_fixed_model",
            values=["mae_days", "rmse_days"],
            aggfunc="first",
        )
        .round(3)
        .to_string()
    )
    print("\nSelected fixed hybrid gain (hybrid - process; negative means improvement):")
    print(
        gain_summary.loc[gain_summary["selected_fixed_model"]][
            ["stage", "algorithm_label", "delta_mae_days", "delta_rmse_days"]
        ]
        .round(3)
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
