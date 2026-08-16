#!/usr/bin/env python
"""Plot fixed process-model versus fixed hybrid-model performance."""

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
DEFAULT_OUTPUT = REPO_ROOT / "fig/results_figure/fixed_process_vs_hybrid_performance.png"
DEFAULT_TABLE_DIR = REPO_ROOT / "results/paper_results"
STAGE_ORDER = ("budburst", "flowering", "veraison", "maturity_or_harvest")
STAGE_LABELS = {
    "budburst": "BBCH07",
    "flowering": "BBCH65",
    "veraison": "BBCH81",
    "maturity_or_harvest": "BBCH89",
}
MODEL_ORDER = ("process", "hybrid")
MODEL_LABELS = {
    "process": "Process model",
    "hybrid": "Hybrid model",
}
MODEL_COLORS = {
    "process": "#8f8f8f",
    "hybrid": "#D55E00",
}
METRIC_LABELS = {"mae_days": "MAE (days)", "rmse_days": "RMSE (days)"}
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 3.45
BASE_FONT_SIZE = 10
LEGEND_FONT_SIZE = 8.2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
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


def prediction_metrics(observed: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - observed
    absolute_error = np.abs(error)
    return {
        "mae_days": float(np.mean(absolute_error)),
        "rmse_days": float(np.sqrt(np.mean(error**2))),
        "bias_days": float(np.mean(error)),
        "within_5d_pct": float(np.mean(absolute_error <= 5.0) * 100.0),
        "within_7d_pct": float(np.mean(absolute_error <= 7.0) * 100.0),
    }


def load_predictions(path: Path) -> pd.DataFrame:
    required = {
        "stage",
        "outer_fold",
        "observed_doy",
        "mechanistic_predicted_doy",
        "hybrid_predicted_doy",
    }
    data = pd.read_parquet(path)
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    data = data.loc[data["stage"].isin(STAGE_ORDER)].copy()
    if data.empty:
        raise ValueError(f"No usable prediction rows found in {path}")
    return data


def metrics_table(predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    fold_rows: list[dict[str, object]] = []
    prediction_columns = {
        "process": "mechanistic_predicted_doy",
        "hybrid": "hybrid_predicted_doy",
    }
    for (stage, model_type), column in (
        ((stage, model_type), prediction_columns[model_type])
        for stage in STAGE_ORDER
        for model_type in MODEL_ORDER
    ):
        group = predictions.loc[predictions["stage"].eq(stage)]
        metrics = prediction_metrics(
            group["observed_doy"].to_numpy(dtype=float),
            group[column].to_numpy(dtype=float),
        )
        rows.append(
            {
                "stage": stage,
                "model_type": model_type,
                "n": int(len(group)),
                **metrics,
            }
        )
        for outer_fold, fold in group.groupby("outer_fold", sort=True):
            fold_metrics = prediction_metrics(
                fold["observed_doy"].to_numpy(dtype=float),
                fold[column].to_numpy(dtype=float),
            )
            fold_rows.append(
                {
                    "stage": stage,
                    "model_type": model_type,
                    "outer_fold": int(outer_fold),
                    "n": int(len(fold)),
                    **fold_metrics,
                }
            )

    aggregate = pd.DataFrame(rows)
    folds = pd.DataFrame(fold_rows)
    fold_error = (
        folds.groupby(["stage", "model_type"], sort=False)[["mae_days", "rmse_days"]]
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
    aggregate = aggregate.merge(fold_error, on=["stage", "model_type"], how="left")

    process = aggregate.loc[aggregate["model_type"].eq("process")].set_index("stage")
    hybrid = aggregate.loc[aggregate["model_type"].eq("hybrid")].set_index("stage")
    for metric in ("mae_days", "rmse_days"):
        gain = process[metric] - hybrid[metric]
        aggregate[f"{metric.replace('_days', '')}_gain_vs_process_days"] = aggregate["stage"].map(gain)
    return aggregate, folds


def bar_positions(stage_x: float) -> list[tuple[str, float]]:
    bar_width = 0.250
    gap = 0.045
    total_width = len(MODEL_ORDER) * bar_width + (len(MODEL_ORDER) - 1) * gap
    start = stage_x - total_width / 2 + bar_width / 2
    return [
        (model_type, start + index * (bar_width + gap))
        for index, model_type in enumerate(MODEL_ORDER)
    ]


def plot(aggregate: pd.DataFrame, folds: pd.DataFrame, output: Path, dpi: int) -> None:
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

    for axis, metric_name, panel_label in zip(axes, ("mae_days", "rmse_days"), ("(a)", "(b)")):
        se_column = "fold_se_mae_days" if metric_name == "mae_days" else "fold_se_rmse_days"
        for stage in STAGE_ORDER:
            for model_type, x in bar_positions(float(stage_x[stage])):
                row = aggregate.loc[
                    aggregate["stage"].eq(stage)
                    & aggregate["model_type"].eq(model_type)
                ].iloc[0]
                fold = folds.loc[
                    folds["stage"].eq(stage)
                    & folds["model_type"].eq(model_type)
                ].copy()
                jitter = np.linspace(-0.035, 0.035, len(fold))
                axis.bar(
                    x,
                    float(row[metric_name]),
                    width=0.250,
                    color=MODEL_COLORS[model_type],
                    edgecolor="white",
                    linewidth=0.65,
                    alpha=0.88,
                    zorder=2,
                )
                axis.errorbar(
                    x,
                    float(row[metric_name]),
                    yerr=float(row[se_column]),
                    fmt="none",
                    ecolor="#333333",
                    elinewidth=0.85,
                    capsize=2.4,
                    capthick=0.85,
                    zorder=4,
                )
                axis.scatter(
                    np.full(len(fold), x) + jitter,
                    fold[metric_name],
                    s=11,
                    marker="o",
                    facecolors="white",
                    edgecolors="#4d4d4d",
                    linewidths=0.35,
                    alpha=0.70,
                    zorder=5,
                )

        axis.set_ylabel(METRIC_LABELS[metric_name])
        axis.set_xticks(
            [stage_x[stage] for stage in STAGE_ORDER],
            [STAGE_LABELS[stage] for stage in STAGE_ORDER],
        )
        axis.set_xlim(-0.55, len(STAGE_ORDER) - 0.45)
        axis.set_ylim(0, float(np.ceil(aggregate[metric_name].max() / 5.0) * 5.0 + 3.0))
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
            facecolor=MODEL_COLORS[model_type],
            edgecolor="white",
            linewidth=0.65,
            label=MODEL_LABELS[model_type],
        )
        for model_type in MODEL_ORDER
    ]
    handles.append(
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
        )
    )
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.085, 0.795, 0.900, 0.060),
        bbox_transform=fig.transFigure,
        ncol=3,
        mode="expand",
        frameon=True,
        fancybox=False,
        facecolor="white",
        edgecolor="#bdbdbd",
        framealpha=1.0,
        handlelength=1.0,
        handletextpad=0.30,
        columnspacing=0.50,
        fontsize=LEGEND_FONT_SIZE,
        borderaxespad=0.0,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=dpi, facecolor="white")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    predictions = load_predictions(args.predictions)
    aggregate, folds = metrics_table(predictions)
    plot(aggregate, folds, args.output, args.dpi)

    summary_output = args.summary_output
    if summary_output is None:
        summary_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_summary.csv"
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    aggregate.to_csv(summary_output, index=False)

    print("Fixed process versus hybrid performance figure")
    print(f"Predictions: {args.predictions.relative_to(REPO_ROOT)}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(f"Summary: {summary_output.relative_to(REPO_ROOT)}")
    print(
        aggregate.pivot_table(
            index="stage",
            columns="model_type",
            values=["n", "mae_days", "rmse_days", "bias_days"],
            aggfunc="first",
        )
        .round(3)
        .to_string()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
