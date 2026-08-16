#!/usr/bin/env python
"""Plot paired raw-vs-adjusted process-model performance differences."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTION_METRICS = (
    REPO_ROOT
    / "data/phenology/derived/modeling/france_germany_four_stage/"
    "baseline_mechanistic_doyrange21_postflower/stage_model_selection_metrics.csv"
)
DEFAULT_OUTPUT = REPO_ROOT / "fig/results_figure/raw_vs_adjusted_process_model_difference.png"
DEFAULT_TABLE_DIR = REPO_ROOT / "results/paper_results"
STAGE_ORDER = ("budburst", "flowering", "veraison", "maturity_or_harvest")
STAGE_LABELS = {
    "budburst": "BBCH07",
    "flowering": "BBCH65",
    "veraison": "BBCH81",
    "maturity_or_harvest": "BBCH89",
}
MODEL_ORDER = {
    "budburst": (
        "budburst__calibrated_brin_aug1",
        "budburst__calibrated_gdd5",
    ),
    "flowering": (
        "flowering__calibrated_gfv",
        "flowering__calibrated_gdd10",
    ),
    "veraison": (
        "veraison__calibrated_gfv",
        "veraison__predicted_flowering_post_gdd10",
        "veraison__calibrated_gdd10",
    ),
    "maturity_or_harvest": (
        "maturity_or_harvest__predicted_veraison_post_gdd10",
        "maturity_or_harvest__calibrated_seasonal_gdd10",
    ),
}
MODEL_STYLE_LABELS = {
    "budburst__calibrated_brin_aug1": "BRIN",
    "budburst__calibrated_gdd5": "GDD5",
    "flowering__calibrated_gfv": "GFV",
    "flowering__calibrated_gdd10": "GDD10",
    "veraison__calibrated_gfv": "GFV",
    "veraison__predicted_flowering_post_gdd10": "Stage-to-stage GDD10",
    "veraison__calibrated_gdd10": "GDD10",
    "maturity_or_harvest__predicted_veraison_post_gdd10": "Stage-to-stage GDD10",
    "maturity_or_harvest__calibrated_seasonal_gdd10": "GDD10",
}
SELECTED_MODEL_IDS = {
    "budburst": "budburst__calibrated_brin_aug1",
    "flowering": "flowering__calibrated_gfv",
    "veraison": "veraison__calibrated_gfv",
    "maturity_or_harvest": "maturity_or_harvest__predicted_veraison_post_gdd10",
}
MODEL_COLORS = {
    "BRIN": "#0072B2",
    "GDD5": "#56B4E9",
    "GFV": "#009E73",
    "GDD10": "#8E63B0",
    "Stage-to-stage GDD10": "#E69F00",
}
MODEL_LEGEND_ORDER = ("BRIN", "GDD5", "GFV", "GDD10", "Stage-to-stage GDD10")
BRANCH_MAP = {"raw": "raw", "adjusted_6p5": "adjusted"}
SOURCE_METRICS = {
    "delta_mae_days": "mean_penalized_mae_days",
    "delta_rmse_days": "mean_penalized_rmse_days",
}
METRIC_LABELS = {
    "delta_mae_days": "ΔMAE (days; adjusted - raw)",
    "delta_rmse_days": "ΔRMSE (days; adjusted - raw)",
}
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 3.45
BASE_FONT_SIZE = 10
LEGEND_FONT_SIZE = 7.8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-metrics", type=Path, default=DEFAULT_SELECTION_METRICS)
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


def expected_model_ids() -> set[str]:
    return {model_id for model_ids in MODEL_ORDER.values() for model_id in model_ids}


def load_fold_differences(path: Path) -> pd.DataFrame:
    required = {
        "outer_fold",
        "stage",
        "temperature_branch",
        "model_id",
        "mean_penalized_mae_days",
        "mean_penalized_rmse_days",
    }
    data = pd.read_csv(path)
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")

    data = data.loc[
        data["stage"].isin(STAGE_ORDER)
        & data["temperature_branch"].isin(BRANCH_MAP)
        & data["model_id"].isin(expected_model_ids())
    ].copy()
    data["temperature_branch"] = data["temperature_branch"].map(BRANCH_MAP)

    expected = {
        (fold, stage, model_id, branch)
        for fold in sorted(data["outer_fold"].unique())
        for stage, model_ids in MODEL_ORDER.items()
        for model_id in model_ids
        for branch in ("raw", "adjusted")
    }
    actual = set(zip(data["outer_fold"], data["stage"], data["model_id"], data["temperature_branch"]))
    missing_combinations = sorted(expected.difference(actual))
    if missing_combinations:
        raise ValueError(f"Missing expected paired combinations: {missing_combinations}")

    wide = data.pivot_table(
        index=["outer_fold", "stage", "model_id"],
        columns="temperature_branch",
        values=list(SOURCE_METRICS.values()),
        aggfunc="first",
    )
    wide.columns = [f"{metric}_{branch}" for metric, branch in wide.columns.to_flat_index()]
    wide = wide.reset_index()

    for delta_metric, source_metric in SOURCE_METRICS.items():
        wide[delta_metric] = wide[f"{source_metric}_adjusted"] - wide[f"{source_metric}_raw"]

    wide["model_style"] = wide["model_id"].map(MODEL_STYLE_LABELS)
    wide["selected_model"] = wide.apply(
        lambda row: row["model_id"] == SELECTED_MODEL_IDS[row["stage"]],
        axis=1,
    )
    return wide


def difference_summary(fold_differences: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    group_columns = ["stage", "model_id", "model_style", "selected_model"]
    for keys, group in fold_differences.groupby(group_columns, sort=False):
        row = dict(zip(group_columns, keys))
        row["n_outer_rounds"] = int(group["outer_fold"].nunique())
        for metric_name in SOURCE_METRICS:
            values = group[metric_name].to_numpy(dtype=float)
            row[metric_name] = float(values.mean())
            row[f"{metric_name}_sd"] = float(values.std(ddof=1))
            row[f"{metric_name}_se"] = float(values.std(ddof=1) / np.sqrt(len(values)))
            row[f"{metric_name}_min"] = float(values.min())
            row[f"{metric_name}_max"] = float(values.max())
        rows.append(row)
    return pd.DataFrame(rows)


def bar_positions(stage: str, stage_x: float) -> list[tuple[str, float]]:
    bar_width = 0.155
    gap = 0.020
    bars = list(MODEL_ORDER[stage])
    total_width = len(bars) * bar_width + (len(bars) - 1) * gap
    start = stage_x - total_width / 2 + bar_width / 2
    return [
        (model_id, start + index * (bar_width + gap))
        for index, model_id in enumerate(bars)
    ]


def y_limits(values: pd.Series, star_values: list[float]) -> tuple[float, float]:
    all_values = list(values.dropna().astype(float)) + star_values + [0.0]
    lower = min(all_values)
    upper = max(all_values)
    span = max(upper - lower, 1.0)
    margin = max(0.25, span * 0.10)
    lower = np.floor((lower - margin) * 2.0) / 2.0
    upper = np.ceil((upper + margin) * 2.0) / 2.0
    return float(lower), float(upper)


def plot(
    summary: pd.DataFrame,
    fold_differences: pd.DataFrame,
    output: Path,
    dpi: int,
) -> None:
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
            "top": 0.735,
            "wspace": 0.18,
        },
    )
    stage_x = {stage: index for index, stage in enumerate(STAGE_ORDER)}

    for axis, metric_name, panel_label in zip(
        axes,
        ("delta_mae_days", "delta_rmse_days"),
        ("(a)", "(b)"),
    ):
        star_y_values = []
        for stage in STAGE_ORDER:
            for model_id, x in bar_positions(stage, float(stage_x[stage])):
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

        axis.axhline(0.0, color="#333333", linewidth=0.75, zorder=1)
        axis.set_ylabel(METRIC_LABELS[metric_name])
        axis.set_xticks(
            [stage_x[stage] for stage in STAGE_ORDER],
            [STAGE_LABELS[stage] for stage in STAGE_ORDER],
        )
        axis.set_xlim(-0.55, len(STAGE_ORDER) - 0.45)
        axis.set_ylim(*y_limits(fold_differences[metric_name], star_y_values))
        axis.grid(axis="y", color="#bdbdbd", linewidth=0.35, alpha=0.55, zorder=0)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.tick_params(length=3.0, width=0.7)
        axis.text(
            0.02,
            0.94,
            panel_label,
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=BASE_FONT_SIZE,
        )

    handles = [
        Patch(
            facecolor=MODEL_COLORS[label],
            edgecolor="white",
            linewidth=0.55,
            label=label,
        )
        for label in MODEL_LEGEND_ORDER
    ]
    handles.extend(
        [
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
                label="Selected model",
            ),
        ]
    )
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.085, 0.795, 0.900, 0.060),
        bbox_transform=fig.transFigure,
        ncol=7,
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
    fold_differences = load_fold_differences(args.selection_metrics)
    summary = difference_summary(fold_differences)
    plot(summary, fold_differences, args.output, args.dpi)

    summary_output = args.summary_output
    if summary_output is None:
        summary_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_summary.csv"
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_output, index=False)

    print("Raw-vs-adjusted process-model paired difference figure")
    print(f"Selection metrics: {args.selection_metrics.relative_to(REPO_ROOT)}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(f"Summary: {summary_output.relative_to(REPO_ROOT)}")
    print(
        summary.pivot_table(
            index=["stage", "model_style"],
            columns="selected_model",
            values=["delta_mae_days", "delta_rmse_days"],
            aggfunc="first",
        )
        .round(3)
        .to_string()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
