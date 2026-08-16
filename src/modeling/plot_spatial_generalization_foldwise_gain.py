#!/usr/bin/env python
"""Plot fold-wise hybrid gains under held-out spatial validation."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREDICTIONS = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/"
    "main_final_fixed_stage_models_refit/"
    "fixed_stage_outer_predictions.parquet"
)
DEFAULT_OUTPUT = REPO_ROOT / "fig/results_figure/spatial_generalization_foldwise_gain.png"
DEFAULT_TABLE_DIR = REPO_ROOT / "results/paper_results"
STAGE_ORDER = ("budburst", "flowering", "veraison", "maturity_or_harvest")
INSET_STAGE_ORDER = ("budburst", "flowering", "veraison")
STAGE_LABELS = {
    "budburst": "BBCH07",
    "flowering": "BBCH65",
    "veraison": "BBCH81",
    "maturity_or_harvest": "BBCH89",
}
FOLD_COLORS = {
    1: "#009E73",
    2: "#D55E00",
    3: "#8E63B0",
    4: "#CC79A7",
    5: "#7CAE00",
}
METRIC_LABELS = {
    "delta_mae_days": "ΔMAE (days; hybrid - process)",
    "delta_rmse_days": "ΔRMSE (days; hybrid - process)",
}
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 3.45
BASE_FONT_SIZE = 11
LEGEND_FONT_SIZE = 10
INSET_FONT_SIZE = 7.8
INSET_Y_LIMITS = (-2.0, 0.5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fold-output", type=Path, default=None)
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


def load_fold_metrics(path: Path) -> pd.DataFrame:
    required = {
        "stage",
        "outer_fold",
        "algorithm",
        "record_id",
        "observed_doy",
        "mechanistic_predicted_doy",
        "hybrid_predicted_doy",
    }
    predictions = pd.read_parquet(path)
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    predictions = predictions.loc[predictions["stage"].isin(STAGE_ORDER)].copy()
    if predictions.duplicated(["stage", "outer_fold", "record_id"]).any():
        raise ValueError("Prediction file has duplicated stage/outer_fold/record_id rows.")

    rows: list[dict[str, object]] = []
    for (stage, outer_fold), group in predictions.groupby(["stage", "outer_fold"], sort=False):
        observed = group["observed_doy"].to_numpy(dtype=float)
        process_error = group["mechanistic_predicted_doy"].to_numpy(dtype=float) - observed
        hybrid_error = group["hybrid_predicted_doy"].to_numpy(dtype=float) - observed
        algorithm = "|".join(sorted(group["algorithm"].unique()))
        rows.append(
            {
                "stage": stage,
                "outer_fold": int(outer_fold),
                "algorithm": algorithm,
                "n": int(len(group)),
                "process_mae_days": float(np.mean(np.abs(process_error))),
                "hybrid_mae_days": float(np.mean(np.abs(hybrid_error))),
                "process_rmse_days": float(np.sqrt(np.mean(process_error**2))),
                "hybrid_rmse_days": float(np.sqrt(np.mean(hybrid_error**2))),
                "process_bias_days": float(np.mean(process_error)),
                "hybrid_bias_days": float(np.mean(hybrid_error)),
            }
        )
    metrics = pd.DataFrame(rows)
    metrics["delta_mae_days"] = metrics["hybrid_mae_days"] - metrics["process_mae_days"]
    metrics["delta_rmse_days"] = metrics["hybrid_rmse_days"] - metrics["process_rmse_days"]
    metrics["improved_mae"] = metrics["delta_mae_days"] < 0
    metrics["improved_rmse"] = metrics["delta_rmse_days"] < 0
    return metrics


def summarize_fold_metrics(fold_metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for stage, group in fold_metrics.groupby("stage", sort=False):
        row: dict[str, object] = {
            "stage": stage,
            "algorithm": "|".join(sorted(group["algorithm"].unique())),
            "n_outer_folds": int(group["outer_fold"].nunique()),
            "n_events": int(group["n"].sum()),
            "n_improved_mae_folds": int(group["improved_mae"].sum()),
            "n_improved_rmse_folds": int(group["improved_rmse"].sum()),
            "worst_process_rmse_days": float(group["process_rmse_days"].max()),
            "worst_hybrid_rmse_days": float(group["hybrid_rmse_days"].max()),
        }
        for metric_name in (
            "process_mae_days",
            "hybrid_mae_days",
            "process_rmse_days",
            "hybrid_rmse_days",
            "delta_mae_days",
            "delta_rmse_days",
        ):
            values = group[metric_name].to_numpy(dtype=float)
            row[f"fold_mean_{metric_name}"] = float(values.mean())
            row[f"fold_sd_{metric_name}"] = float(values.std(ddof=1))
            row[f"fold_se_{metric_name}"] = float(values.std(ddof=1) / np.sqrt(len(values)))
            row[f"fold_min_{metric_name}"] = float(values.min())
            row[f"fold_max_{metric_name}"] = float(values.max())
        rows.append(row)
    return pd.DataFrame(rows)


def y_limits(values: pd.Series) -> tuple[float, float]:
    plotted = list(values.dropna().astype(float)) + [0.0]
    lower = min(plotted)
    upper = max(plotted)
    span = max(upper - lower, 1.0)
    margin = max(0.35, span * 0.12)
    lower = np.floor((lower - margin) * 2.0) / 2.0
    upper = np.ceil((upper + margin) * 2.0) / 2.0
    return float(lower), float(upper)


def scatter_fold_points(
    axis,
    fold_metrics: pd.DataFrame,
    summary: pd.DataFrame,
    metric_name: str,
    stage_order: tuple[str, ...],
    point_size: float,
    mean_marker_size: float,
    jitter_scale: float,
) -> None:
    stage_x = {stage: index for index, stage in enumerate(stage_order)}
    jitter_lookup = {
        1: -0.16 * jitter_scale,
        2: -0.08 * jitter_scale,
        3: 0.00,
        4: 0.08 * jitter_scale,
        5: 0.16 * jitter_scale,
    }

    for stage in stage_order:
        stage_fold_metrics = fold_metrics.loc[fold_metrics["stage"].eq(stage)].copy()
        for _, row in stage_fold_metrics.iterrows():
            outer_fold = int(row["outer_fold"])
            axis.scatter(
                [stage_x[stage] + jitter_lookup.get(outer_fold, 0.0)],
                [float(row[metric_name])],
                s=point_size,
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
        axis.errorbar(
            [stage_x[stage]],
            [mean_value],
            yerr=[se_value],
            fmt="D",
            markersize=mean_marker_size,
            markerfacecolor="#111111",
            markeredgecolor="#111111",
            ecolor="#111111",
            elinewidth=0.75,
            capsize=2.4,
            capthick=0.75,
            zorder=6,
        )


def draw_inset(axis, fold_metrics: pd.DataFrame, summary: pd.DataFrame, metric_name: str) -> None:
    inset = axis.inset_axes([0.08, 0.12, 0.45, 0.40])
    inset.set_zorder(8)
    inset_metrics = fold_metrics.loc[fold_metrics["stage"].isin(INSET_STAGE_ORDER)].copy()
    scatter_fold_points(
        inset,
        inset_metrics,
        summary,
        metric_name,
        INSET_STAGE_ORDER,
        point_size=7.5,
        mean_marker_size=2.2,
        jitter_scale=0.70,
    )
    inset.axhline(0.0, color="#333333", linewidth=0.55, zorder=1)
    inset.set_xlim(-0.42, len(INSET_STAGE_ORDER) - 0.58)
    inset.set_ylim(*INSET_Y_LIMITS)
    inset.set_xticks(
        range(len(INSET_STAGE_ORDER)),
        [STAGE_LABELS[stage].replace("BBCH", "") for stage in INSET_STAGE_ORDER],
    )
    inset.set_yticks([-2.0, -1.0, 0.0])
    inset.grid(axis="y", color="#bdbdbd", linewidth=0.25, alpha=0.50, zorder=0)
    inset.tick_params(length=2.0, width=0.5, labelsize=INSET_FONT_SIZE, pad=1.0)
    for spine in inset.spines.values():
        spine.set_linewidth(0.55)
        spine.set_color("#666666")
    inset.set_facecolor("white")
    inset.patch.set_alpha(1.0)


def draw_panel(axis, fold_metrics: pd.DataFrame, summary: pd.DataFrame, metric_name: str) -> None:
    stage_x = {stage: index for index, stage in enumerate(STAGE_ORDER)}
    scatter_fold_points(
        axis,
        fold_metrics,
        summary,
        metric_name,
        STAGE_ORDER,
        point_size=19,
        mean_marker_size=3.8,
        jitter_scale=1.00,
    )
    axis.axhline(0.0, color="#333333", linewidth=0.75, zorder=1)
    axis.set_ylabel(METRIC_LABELS[metric_name])
    axis.set_xticks(
        [stage_x[stage] for stage in STAGE_ORDER],
        [STAGE_LABELS[stage] for stage in STAGE_ORDER],
    )
    axis.set_xlim(-0.45, len(STAGE_ORDER) - 0.55)
    axis.set_ylim(*y_limits(fold_metrics[metric_name]))
    axis.grid(axis="y", color="#bdbdbd", linewidth=0.35, alpha=0.55, zorder=0)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.tick_params(length=3.0, width=0.7)
    draw_inset(axis, fold_metrics, summary, metric_name)


def plot(fold_metrics: pd.DataFrame, summary: pd.DataFrame, output: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

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
    for axis, metric_name, panel_label in zip(
        axes,
        ("delta_mae_days", "delta_rmse_days"),
        ("(a)", "(b)"),
    ):
        draw_panel(axis, fold_metrics, summary, metric_name)
        axis.text(
            0.02,
            0.50,
            panel_label,
            transform=axis.get_yaxis_transform(),
            ha="left",
            va="bottom",
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
        bbox_to_anchor=(0.085, 0.795, 0.900, 0.060),
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

    print("Spatial generalization fold-wise hybrid gain figure")
    print(f"Predictions: {args.predictions.relative_to(REPO_ROOT)}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(f"Fold metrics: {fold_output.relative_to(REPO_ROOT)}")
    print(f"Summary: {summary_output.relative_to(REPO_ROOT)}")
    print(
        summary[
            [
                "stage",
                "algorithm",
                "n_improved_mae_folds",
                "n_improved_rmse_folds",
                "fold_mean_delta_mae_days",
                "fold_mean_delta_rmse_days",
                "worst_process_rmse_days",
                "worst_hybrid_rmse_days",
            ]
        ]
        .round(3)
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
