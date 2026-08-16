#!/usr/bin/env python
"""Plot observed versus selected process-model predicted DOY by stage."""

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
DEFAULT_SELECTION = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/"
    "main_final_fixed_stage_models_refit/"
    "fixed_stage_algorithm_selection.csv"
)
DEFAULT_OUTPUT = REPO_ROOT / "fig/results_figure/selected_process_model_observed_predicted.png"
DEFAULT_TABLE_DIR = REPO_ROOT / "results/paper_results"
STAGE_ORDER = ("budburst", "flowering", "veraison", "maturity_or_harvest")
STAGE_LABELS = {
    "budburst": "BBCH07",
    "flowering": "BBCH65",
    "veraison": "BBCH81",
    "maturity_or_harvest": "BBCH89",
}
PROCESS_MODEL_SHORT_LABELS = {
    "BRIN-Aug1": "BRIN",
    "adjusted GFV": "GFV",
    "predicted-veraison GDD10": "PV-GDD10",
    "raw BRIN-Aug1": "raw BRIN",
    "raw GFV": "raw GFV",
    "raw predicted-veraison GDD10": "raw PV-GDD10",
}
FOLD_COLORS = {
    1: "#009E73",
    2: "#D55E00",
    3: "#8E63B0",
    4: "#CC79A7",
    5: "#7CAE00",
}
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 6.05
BASE_FONT_SIZE = 11
LEGEND_FONT_SIZE = 10
TITLE_FONT_SIZE = 11
PANEL_LABEL_FONT_SIZE = 10.8
STATS_FONT_SIZE = 9.5
ONE_TO_ONE_LINEWIDTH = 1.0
PANEL_FACE_COLOR = "#f2f2f2"
SPINE_COLOR = "#5f5f5f"
TITLE_FACE_COLOR = "#6e6e6e"
TITLE_EDGE_COLOR = "#4a4a4a"
TITLE_STRIP_HEIGHT = 0.1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
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
    absolute = np.abs(error)
    return {
        "n": int(len(observed)),
        "mae_days": float(np.mean(absolute)),
        "rmse_days": float(np.sqrt(np.mean(np.square(error)))),
        "bias_days": float(np.mean(error)),
        "r2": float(np.corrcoef(observed, predicted)[0, 1] ** 2)
        if len(observed) > 1 and np.std(predicted) > 0 and np.std(observed) > 0
        else np.nan,
    }


def load_inputs(predictions_path: Path, selection_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    predictions = pd.read_parquet(predictions_path)
    required_predictions = {
        "stage",
        "outer_fold",
        "observed_doy",
        "mechanistic_predicted_doy",
    }
    missing_predictions = required_predictions.difference(predictions.columns)
    if missing_predictions:
        raise ValueError(f"{predictions_path} missing columns: {sorted(missing_predictions)}")
    predictions = predictions.loc[predictions["stage"].isin(STAGE_ORDER)].copy()

    selection = pd.read_csv(selection_path)
    required_selection = {"stage", "process_model"}
    missing_selection = required_selection.difference(selection.columns)
    if missing_selection:
        raise ValueError(f"{selection_path} missing columns: {sorted(missing_selection)}")
    selection = selection.loc[selection["stage"].isin(STAGE_ORDER)].copy()
    return predictions, selection


def summarize(predictions: pd.DataFrame, selection: pd.DataFrame) -> pd.DataFrame:
    process_model_by_stage = selection.set_index("stage")["process_model"].to_dict()
    rows: list[dict[str, object]] = []
    for stage in STAGE_ORDER:
        group = predictions.loc[predictions["stage"].eq(stage)]
        metrics = prediction_metrics(
            group["observed_doy"].to_numpy(dtype=float),
            group["mechanistic_predicted_doy"].to_numpy(dtype=float),
        )
        fold_metrics = []
        for outer_fold, fold_group in group.groupby("outer_fold", sort=True):
            fold_metric = prediction_metrics(
                fold_group["observed_doy"].to_numpy(dtype=float),
                fold_group["mechanistic_predicted_doy"].to_numpy(dtype=float),
            )
            fold_metrics.append(
                {
                    "outer_fold": int(outer_fold),
                    "fold_mae_days": fold_metric["mae_days"],
                    "fold_rmse_days": fold_metric["rmse_days"],
                }
            )
        fold_table = pd.DataFrame(fold_metrics)
        rows.append(
            {
                "stage": stage,
                "stage_label": STAGE_LABELS[stage],
                "process_model": process_model_by_stage[stage],
                "process_model_short": PROCESS_MODEL_SHORT_LABELS.get(
                    process_model_by_stage[stage],
                    process_model_by_stage[stage],
                ),
                **metrics,
                "sd_outer_fold_mae_days": float(fold_table["fold_mae_days"].std(ddof=1)),
                "worst_outer_fold_mae_days": float(fold_table["fold_mae_days"].max()),
                "sd_outer_fold_rmse_days": float(fold_table["fold_rmse_days"].std(ddof=1)),
                "worst_outer_fold_rmse_days": float(fold_table["fold_rmse_days"].max()),
            }
        )
    return pd.DataFrame(rows)


def stage_axis_limits(stage_data: pd.DataFrame) -> tuple[float, float]:
    values = pd.concat(
        [
            stage_data["observed_doy"],
            stage_data["mechanistic_predicted_doy"],
        ],
        ignore_index=True,
    ).to_numpy(dtype=float)
    lower = float(np.floor((values.min() - 4.0) / 5.0) * 5.0)
    upper = float(np.ceil((values.max() + 4.0) / 5.0) * 5.0)
    return lower, upper


def plot(
    predictions: pd.DataFrame,
    summary: pd.DataFrame,
    output: Path,
    dpi: int,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(FIG_WIDTH_IN, FIG_HEIGHT_IN),
        gridspec_kw={
            "left": 0.075,
            "right": 0.975,
            "bottom": 0.075,
            "top": 0.835,
            "wspace": 0.045,
            "hspace": 0.300,
        },
    )
    axes_flat = axes.ravel()
    for axis, stage, panel_label in zip(axes_flat, STAGE_ORDER, ("(a)", "(b)", "(c)", "(d)")):
        stage_data = predictions.loc[predictions["stage"].eq(stage)].copy()
        stage_summary = summary.loc[summary["stage"].eq(stage)].iloc[0]
        for outer_fold, fold_data in stage_data.groupby("outer_fold", sort=True):
            axis.scatter(
                fold_data["observed_doy"],
                fold_data["mechanistic_predicted_doy"],
                s=6.0,
                marker="o",
                facecolors=FOLD_COLORS.get(int(outer_fold), "#4d4d4d"),
                edgecolors="none",
                alpha=0.42,
                rasterized=True,
                zorder=3,
            )
        lower, upper = stage_axis_limits(stage_data)
        axis.plot(
            [lower, upper],
            [lower, upper],
            linestyle=(0, (4, 4)),
            color="#111111",
            linewidth=ONE_TO_ONE_LINEWIDTH,
            zorder=2,
        )
        axis.set_xlim(lower, upper)
        axis.set_ylim(lower, upper)
        axis.set_aspect("equal", adjustable="box")
        axis.set_facecolor(PANEL_FACE_COLOR)
        axis.set_axisbelow(True)
        axis.add_patch(
            Rectangle(
                (0.0, 1.0),
                1.0,
                TITLE_STRIP_HEIGHT,
                transform=axis.transAxes,
                clip_on=False,
                facecolor=TITLE_FACE_COLOR,
                edgecolor=TITLE_EDGE_COLOR,
                linewidth=0.65,
                zorder=5,
            )
        )
        axis.text(
            0.5,
            1.0 + TITLE_STRIP_HEIGHT * 0.49,
            f"{STAGE_LABELS[stage]} {stage_summary['process_model_short']}",
            transform=axis.transAxes,
            ha="center",
            va="center",
            fontsize=TITLE_FONT_SIZE,
            color="white",
            zorder=6,
        )
        axis.grid(color="#ffffff", linewidth=0.40, alpha=0.95, zorder=0)
        for spine in axis.spines.values():
            spine.set_visible(True)
            spine.set_color(SPINE_COLOR)
            spine.set_linewidth(0.75)
        axis.tick_params(length=3.0, width=0.7, labelsize=BASE_FONT_SIZE)
        axis.text(
            0.03,
            0.95,
            panel_label,
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=PANEL_LABEL_FONT_SIZE,
        )
        axis.text(
            0.04,
            0.84,
            (
                f"n = {int(stage_summary['n'])}\n"
                f"MAE = {stage_summary['mae_days']:.1f} d\n"
                f"RMSE = {stage_summary['rmse_days']:.1f} d\n"
                f"Bias = {stage_summary['bias_days']:.1f} d"
            ),
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=STATS_FONT_SIZE,
            linespacing=1.15,
        )

    for axis in axes[:, 0]:
        axis.set_ylabel("Predicted DOY")
    for axis in axes[1, :]:
        axis.set_xlabel("Observed DOY")

    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markersize=4.6,
            markerfacecolor=FOLD_COLORS[outer_fold],
            markeredgecolor="none",
            color=FOLD_COLORS[outer_fold],
            label=f"Fold {outer_fold}",
        )
        for outer_fold in sorted(FOLD_COLORS)
    ]
    handles.append(
        Line2D(
            [0],
            [0],
            linestyle=(0, (3, 3)),
            color="#111111",
            linewidth=ONE_TO_ONE_LINEWIDTH,
            label="1:1 line",
        )
    )
    fig.canvas.draw()
    legend_left = axes[0, 0].get_position().x0
    legend_right = axes[0, 1].get_position().x1
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(legend_left, 0.875, legend_right - legend_left, 0.070),
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
    predictions, selection = load_inputs(args.predictions, args.selection)
    summary = summarize(predictions, selection)
    plot(predictions, summary, args.output, args.dpi)

    summary_output = args.summary_output
    if summary_output is None:
        summary_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_summary.csv"
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_output, index=False)

    print("Selected process model observed-predicted figure")
    print(f"Predictions: {args.predictions.relative_to(REPO_ROOT)}")
    print(f"Selection: {args.selection.relative_to(REPO_ROOT)}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(f"Summary: {summary_output.relative_to(REPO_ROOT)}")
    print(
        summary[
            [
                "stage",
                "process_model_short",
                "n",
                "mae_days",
                "rmse_days",
                "bias_days",
                "worst_outer_fold_rmse_days",
            ]
        ]
        .round(3)
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
