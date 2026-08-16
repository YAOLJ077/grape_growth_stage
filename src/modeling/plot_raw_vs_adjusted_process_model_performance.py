#!/usr/bin/env python
"""Plot process-model candidate performance by stage and temperature branch."""

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
DEFAULT_OUTPUT = REPO_ROOT / "fig/results_figure/raw_vs_adjusted_process_model_performance.png"
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
BRANCH_LABELS = {"raw": "Raw temperature", "adjusted": "Adjusted temperature"}
BRANCH_ORDER = ("raw", "adjusted")
METRIC_COLUMNS = {"mae_days": "mean_penalized_mae_days", "rmse_days": "mean_penalized_rmse_days"}
METRIC_LABELS = {"mae_days": "MAE (days)", "rmse_days": "RMSE (days)"}
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
            "hatch.linewidth": 0.45,
            "savefig.dpi": 300,
        }
    )


def expected_model_ids() -> set[str]:
    return {model_id for model_ids in MODEL_ORDER.values() for model_id in model_ids}


def load_selection_metrics(path: Path) -> pd.DataFrame:
    required = {
        "outer_fold",
        "stage",
        "temperature_branch",
        "model_id",
        "mean_penalized_mae_days",
        "mean_penalized_rmse_days",
        "n_inner_oof_events",
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
    data["model_style"] = data["model_id"].map(MODEL_STYLE_LABELS)
    data["selected_model"] = data.apply(
        lambda row: row["model_id"] == SELECTED_MODEL_IDS[row["stage"]],
        axis=1,
    )

    expected = {
        (stage, model_id, branch)
        for stage, model_ids in MODEL_ORDER.items()
        for model_id in model_ids
        for branch in BRANCH_ORDER
    }
    actual = set(zip(data["stage"], data["model_id"], data["temperature_branch"]))
    missing_combinations = sorted(expected.difference(actual))
    if missing_combinations:
        raise ValueError(f"Missing expected stage/model/branch combinations: {missing_combinations}")
    return data


def metric_summary(folds: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    group_columns = ["stage", "model_id", "model_style", "selected_model", "temperature_branch"]
    for keys, group in folds.groupby(group_columns, sort=False):
        row = dict(zip(group_columns, keys))
        row["n_outer_rounds"] = int(group["outer_fold"].nunique())
        row["mean_inner_oof_events"] = float(group["n_inner_oof_events"].mean())
        for metric_name, source_column in METRIC_COLUMNS.items():
            values = group[source_column].to_numpy(dtype=float)
            row[metric_name] = float(values.mean())
            row[f"{metric_name}_sd"] = float(values.std(ddof=1))
            row[f"{metric_name}_se"] = float(values.std(ddof=1) / np.sqrt(len(values)))
        rows.append(row)
    return pd.DataFrame(rows)


def bar_positions(stage: str, stage_x: float) -> list[tuple[str, str, float]]:
    bar_width = 0.120
    gap = 0.013
    bars = [(model_id, branch) for model_id in MODEL_ORDER[stage] for branch in BRANCH_ORDER]
    total_width = len(bars) * bar_width + (len(bars) - 1) * gap
    start = stage_x - total_width / 2 + bar_width / 2
    return [
        (model_id, branch, start + index * (bar_width + gap))
        for index, (model_id, branch) in enumerate(bars)
    ]


def draw_bar(
    axis,
    x: float,
    value: float,
    error: float,
    model_style: str,
    branch: str,
    selected: bool,
) -> None:
    color = MODEL_COLORS[model_style]
    if branch == "raw":
        facecolor = "white"
        edgecolor = color
        hatch = "////"
        alpha = 1.0
    else:
        facecolor = color
        edgecolor = "white"
        hatch = None
        alpha = 0.92

    axis.bar(
        x,
        value,
        width=0.120,
        color=facecolor,
        edgecolor=edgecolor,
        linewidth=0.65,
        hatch=hatch,
        alpha=alpha,
        zorder=2,
    )
    axis.errorbar(
        x,
        value,
        yerr=error,
        fmt="none",
        ecolor="#333333",
        elinewidth=0.75,
        capsize=1.8,
        capthick=0.75,
        zorder=4,
    )
    if selected:
        axis.scatter(
            [x],
            [value + error + 0.75],
            marker="*",
            s=22,
            color="#111111",
            linewidths=0.0,
            zorder=5,
        )


def plot(summary: pd.DataFrame, output: Path, dpi: int) -> None:
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
        for stage in STAGE_ORDER:
            for model_id, branch, x in bar_positions(stage, float(stage_x[stage])):
                row = summary.loc[
                    summary["stage"].eq(stage)
                    & summary["model_id"].eq(model_id)
                    & summary["temperature_branch"].eq(branch)
                ].iloc[0]
                draw_bar(
                    axis,
                    x,
                    float(row[metric_name]),
                    float(row[f"{metric_name}_se"]),
                    str(row["model_style"]),
                    branch,
                    bool(row["selected_model"]),
                )

        axis.set_ylabel(METRIC_LABELS[metric_name])
        axis.set_xticks(
            [stage_x[stage] for stage in STAGE_ORDER],
            [STAGE_LABELS[stage] for stage in STAGE_ORDER],
        )
        axis.set_xlim(-0.55, len(STAGE_ORDER) - 0.45)
        axis.set_ylim(0, float(np.ceil(summary[metric_name].max() / 5.0) * 5.0 + 3.0))
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

    model_handles = [
        Patch(
            facecolor=MODEL_COLORS[label],
            edgecolor="white",
            linewidth=0.5,
            label=label,
        )
        for label in MODEL_LEGEND_ORDER
    ]
    branch_handles = [
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
            linewidth=0.5,
            label=BRANCH_LABELS["adjusted"],
        ),
        Line2D(
            [0],
            [0],
            marker="*",
            linestyle="none",
            color="#111111",
            markersize=5.5,
            label="Selected model",
        ),
    ]
    fig.legend(
        handles=model_handles + branch_handles,
        loc="upper left",
        bbox_to_anchor=(0.085, 0.795, 0.900, 0.060),
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
    folds = load_selection_metrics(args.selection_metrics)
    summary = metric_summary(folds)
    plot(summary, args.output, args.dpi)

    summary_output = args.summary_output
    if summary_output is None:
        summary_output = DEFAULT_TABLE_DIR / f"{args.output.stem}_summary.csv"
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_output, index=False)

    print("Process-model candidate performance figure")
    print(f"Selection metrics: {args.selection_metrics.relative_to(REPO_ROOT)}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(f"Summary: {summary_output.relative_to(REPO_ROOT)}")
    print(
        summary.pivot_table(
            index=["stage", "model_style"],
            columns="temperature_branch",
            values=["mae_days", "rmse_days"],
            aggfunc="first",
        )
        .round(3)
        .to_string()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
