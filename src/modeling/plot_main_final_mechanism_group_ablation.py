#!/usr/bin/env python
"""Plot main_final mechanism-group ablation results."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRIBUTION_TABLE = (
    REPO_ROOT
    / "results/paper_results/main_final_mechanism_group_ablation_contribution_summary.csv"
)
DEFAULT_OUTPUT = REPO_ROOT / "fig/results_figure/main_final_mechanism_group_ablation.png"
DEFAULT_PLOT_DATA = (
    REPO_ROOT / "results/paper_results/main_final_mechanism_group_ablation_plot_data.csv"
)
STAGE_ORDER = ("budburst", "flowering", "veraison", "maturity_or_harvest")
STAGE_LABELS = {
    "budburst": "BBCH07",
    "flowering": "BBCH65",
    "veraison": "BBCH81",
    "maturity_or_harvest": "BBCH89",
}
GROUP_ORDER = (
    "process_state",
    "process_timing",
    "temperature_structure",
    "water_drought",
    "radiation_light",
    "terrain_spatial",
)
GROUP_LABELS = {
    "process_state": "Process state",
    "process_timing": "Process timing",
    "temperature_structure": "Thermal structure",
    "water_drought": "Water/drought",
    "radiation_light": "Radiation",
    "terrain_spatial": "Terrain/spatial",
}
GROUP_COLORS = {
    "process_state": "#4C78A8",
    "process_timing": "#72B7B2",
    "temperature_structure": "#D55E00",
    "water_drought": "#009E73",
    "radiation_light": "#E69F00",
    "terrain_spatial": "#8E63B0",
}
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 4.55
BASE_FONT_SIZE = 11.0
LEGEND_FONT_SIZE = 10.0
PANEL_LABEL_FONT_SIZE = 11.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contribution-table",
        type=Path,
        default=DEFAULT_CONTRIBUTION_TABLE,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--plot-data", type=Path, default=DEFAULT_PLOT_DATA)
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


def load_plot_data(path: Path) -> pd.DataFrame:
    required = {
        "stage",
        "mechanism_group",
        "n_group_features",
        "addon_rmse_gain_vs_anchor_days",
        "leaveout_rmse_cost_vs_all_days",
        "addon_mae_gain_vs_anchor_days",
        "leaveout_mae_cost_vs_all_days",
    }
    data = pd.read_csv(path)
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    data = data.loc[
        data["stage"].isin(STAGE_ORDER)
        & data["mechanism_group"].isin(GROUP_ORDER)
        & data["n_group_features"].gt(0)
    ].copy()
    data["stage_label"] = data["stage"].map(STAGE_LABELS)
    data["group_label"] = data["mechanism_group"].map(GROUP_LABELS)
    data["stage_order"] = data["stage"].map({stage: index for index, stage in enumerate(STAGE_ORDER)})
    data["group_order"] = data["mechanism_group"].map(
        {group: index for index, group in enumerate(GROUP_ORDER)}
    )
    data = data.sort_values(["stage_order", "group_order"]).reset_index(drop=True)
    return data


def x_limits(data: pd.DataFrame) -> tuple[float, float]:
    values = pd.concat(
        [
            data["leaveout_rmse_cost_vs_all_days"],
            data["addon_rmse_gain_vs_anchor_days"],
            pd.Series([0.0]),
        ],
        ignore_index=True,
    ).astype(float)
    lower = min(-0.08, float(values.min()) - 0.08)
    upper = max(0.25, float(values.max()) + 0.12)
    lower = np.floor(lower * 10.0) / 10.0
    upper = np.ceil(upper * 10.0) / 10.0
    return lower, upper


def draw_panel(axis, stage_data: pd.DataFrame, stage: str, panel_label: str, xlim: tuple[float, float]) -> None:
    y_positions = np.arange(len(GROUP_ORDER))
    axis.axvline(0, color="#4d4d4d", linewidth=0.9, zorder=1)
    axis.grid(axis="x", color="#d9d9d9", linewidth=0.65, alpha=0.8, zorder=0)
    axis.set_xlim(*xlim)
    axis.set_ylim(-0.55, len(GROUP_ORDER) - 0.45)
    axis.invert_yaxis()
    axis.set_yticks(y_positions)
    axis.set_yticklabels([GROUP_LABELS[group] for group in GROUP_ORDER])
    axis.set_title(STAGE_LABELS[stage], pad=5)
    axis.text(
        0.015,
        0.955,
        panel_label,
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=PANEL_LABEL_FONT_SIZE,
    )

    by_group = stage_data.set_index("mechanism_group")
    for y_position, group in enumerate(GROUP_ORDER):
        if group not in by_group.index:
            continue
        row = by_group.loc[group]
        leaveout = float(row["leaveout_rmse_cost_vs_all_days"])
        addon = float(row["addon_rmse_gain_vs_anchor_days"])
        color = GROUP_COLORS[group]
        axis.barh(
            y_position,
            leaveout,
            height=0.52,
            color=color,
            edgecolor="#333333",
            linewidth=0.35,
            alpha=0.88,
            zorder=2,
        )
        axis.scatter(
            addon,
            y_position,
            marker="o",
            s=34,
            facecolor="white",
            edgecolor="#1f1f1f",
            linewidth=0.85,
            zorder=4,
        )
    for spine in ("top", "right"):
        axis.spines[spine].set_visible(False)
    axis.spines["left"].set_color("#333333")
    axis.spines["bottom"].set_color("#333333")


def plot(data: pd.DataFrame, output: Path, dpi: int) -> None:
    configure_matplotlib()
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    xlim = x_limits(data)
    fig, axes = plt.subplots(
        2,
        2,
        figsize=(FIG_WIDTH_IN, FIG_HEIGHT_IN),
        sharex=True,
        sharey=True,
    )
    panel_labels = ("(a)", "(b)", "(c)", "(d)")
    for axis, stage, panel_label in zip(axes.ravel(), STAGE_ORDER, panel_labels):
        draw_panel(axis, data.loc[data["stage"].eq(stage)], stage, panel_label, xlim)

    for axis in axes[:, 1]:
        axis.tick_params(axis="y", labelleft=False)
    for axis in axes[0, :]:
        axis.tick_params(axis="x", labelbottom=False)
    for axis in axes[1, :]:
        axis.set_xlabel("ΔRMSE (days)")

    handles = [
        Patch(facecolor="#808080", edgecolor="#333333", alpha=0.88, label="Leave-out cost"),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor="white",
            markeredgecolor="#1f1f1f",
            markersize=5.5,
            label="Add-on gain",
        ),
    ]
    legend = fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.205, 0.995),
        ncol=2,
        frameon=True,
        fancybox=False,
        edgecolor="#9f9f9f",
        columnspacing=1.2,
        handlelength=1.4,
        handletextpad=0.45,
    )
    legend.get_frame().set_linewidth(0.8)
    legend.get_frame().set_facecolor("white")
    fig.subplots_adjust(left=0.205, right=0.970, top=0.865, bottom=0.125, wspace=0.12, hspace=0.24)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=dpi)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    data = load_plot_data(args.contribution_table)
    args.plot_data.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.plot_data, index=False)
    plot(data, args.output, args.dpi)
    print("main_final mechanism-group ablation figure")
    print(f"Contribution table: {args.contribution_table.relative_to(REPO_ROOT)}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(f"Plot data: {args.plot_data.relative_to(REPO_ROOT)}")
    print(
        data[
            [
                "stage_label",
                "group_label",
                "n_group_features",
                "leaveout_rmse_cost_vs_all_days",
                "addon_rmse_gain_vs_anchor_days",
            ]
        ]
        .round(3)
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
