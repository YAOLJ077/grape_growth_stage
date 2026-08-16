#!/usr/bin/env python
"""Compute and plot mechanism-group permutation importance for fixed hybrid models."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from src.modeling.run_residual_ml_models import (
        REPO_ROOT,
        build_estimator,
        prediction_metrics,
        residual_to_doy,
        validate_inputs,
    )
except ModuleNotFoundError:
    from run_residual_ml_models import (  # type: ignore
        REPO_ROOT,
        build_estimator,
        prediction_metrics,
        residual_to_doy,
        validate_inputs,
    )


DEFAULT_DATA_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_machine_learning_main_final"
)
DEFAULT_FIXED_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/"
    "main_final_fixed_stage_models_refit"
)
DEFAULT_OUTPUT_DIR = DEFAULT_FIXED_DIR / "interpretability"
DEFAULT_FIGURE = REPO_ROOT / "fig/results_figure/fixed_hybrid_mechanism_group_permutation_importance.png"
STAGE_ORDER = ("budburst", "flowering", "veraison", "maturity_or_harvest")
STAGE_LABELS = {
    "budburst": "BBCH07",
    "flowering": "BBCH65",
    "veraison": "BBCH81",
    "maturity_or_harvest": "BBCH89",
}
GROUP_ORDER = (
    "timing_context",
    "thermal_stress",
    "water_atmospheric_demand",
    "radiation",
    "topography",
    "geography_country",
)
GROUP_LABELS = {
    "timing_context": "Timing context",
    "thermal_stress": "Thermal stress",
    "water_atmospheric_demand": "Water demand",
    "radiation": "Radiation",
    "topography": "Topography",
    "geography_country": "Geography / country",
}
GROUP_COLORS = {
    "timing_context": "#0072B2",
    "thermal_stress": "#D55E00",
    "water_atmospheric_demand": "#009E73",
    "radiation": "#E69F00",
    "topography": "#8E63B0",
    "geography_country": "#CC79A7",
}
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 5.35
BASE_FONT_SIZE = 10
LEGEND_FONT_SIZE = 7.8


def parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--fixed-dir", type=Path, default=DEFAULT_FIXED_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--outer-folds", type=parse_int_list, default=[1, 2, 3, 4, 5])
    parser.add_argument("--n-repeats", type=int, default=20)
    parser.add_argument("--n-jobs", type=int, default=4)
    parser.add_argument("--random-state", type=int, default=20260805)
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


def feature_sets(data_dir: Path) -> dict[str, list[str]]:
    manifest = pd.read_csv(data_dir / "residual_ml_feature_sets.csv")
    return {
        stage: (
            manifest.loc[manifest["stage"].eq(stage)]
            .sort_values("feature_order")["feature"]
            .tolist()
        )
        for stage in STAGE_ORDER
    }


def assign_feature_group(feature: str) -> str:
    if feature == "mechanistic_predicted_doy" or feature.endswith("_predicted_stage_length_days"):
        return "timing_context"
    if feature in {"dem_elevation_m", "dem_local_std_m", "northness"}:
        return "topography"
    if feature in {"lat", "lon", "country_france"}:
        return "geography_country"
    if "solar_radiation" in feature:
        return "radiation"
    if (
        "precipitation" in feature
        or "vpd" in feature
        or "et0" in feature
        or "water_deficit" in feature
    ):
        return "water_atmospheric_demand"
    if (
        "gdd" in feature
        or "tmean" in feature
        or "diurnal_temperature_range" in feature
        or "chill" in feature
        or "frost" in feature
        or "cool" in feature
        or "heat_degree_days" in feature
    ):
        return "thermal_stress"
    raise ValueError(f"Feature has no mechanism group assignment: {feature}")


def mechanism_groups(features: list[str]) -> dict[str, list[str]]:
    groups = {group: [] for group in GROUP_ORDER}
    for feature in features:
        groups[assign_feature_group(feature)].append(feature)
    return {group: members for group, members in groups.items() if members}


def load_outer_config(fixed_dir: Path) -> pd.DataFrame:
    metrics = pd.read_csv(fixed_dir / "fixed_stage_outer_fold_metrics.csv")
    required = {"stage", "outer_fold", "algorithm", "selected_config_json"}
    missing = required.difference(metrics.columns)
    if missing:
        raise ValueError(f"fixed_stage_outer_fold_metrics.csv missing columns: {sorted(missing)}")
    return metrics


def fit_fixed_estimator(
    train: pd.DataFrame,
    features: list[str],
    algorithm: str,
    config_json: str,
    n_jobs: int,
    random_state: int,
):
    if algorithm == "mechanistic":
        return None
    config = json.loads(config_json)
    estimator = build_estimator(algorithm, config, n_jobs, random_state)
    estimator.fit(train[features], train["residual_days"].to_numpy(float))
    return estimator


def predict_residual(estimator, frame: pd.DataFrame, features: list[str], algorithm: str) -> np.ndarray:
    if algorithm == "mechanistic":
        return np.zeros(len(frame), dtype=float)
    return np.asarray(estimator.predict(frame[features]), dtype=float)


def permute_group(
    frame: pd.DataFrame,
    group_features: list[str],
    rng: np.random.Generator,
) -> pd.DataFrame:
    permuted = frame.copy()
    permutation = rng.permutation(len(frame))
    permuted.loc[:, group_features] = frame[group_features].iloc[permutation].to_numpy()
    return permuted


def calculate_importance(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    features_by_stage = feature_sets(args.data_dir)
    outer_configs = load_outer_config(args.fixed_dir)
    repeat_rows: list[dict[str, object]] = []
    group_rows: list[dict[str, object]] = []
    baseline_rows: list[dict[str, object]] = []

    for stage in STAGE_ORDER:
        features = features_by_stage[stage]
        groups = mechanism_groups(features)
        table = pd.read_parquet(args.data_dir / "training_ready" / f"{stage}_residual_ml.parquet")
        for outer_fold in args.outer_folds:
            config_row = outer_configs.loc[
                outer_configs["stage"].eq(stage)
                & outer_configs["outer_fold"].eq(outer_fold)
            ].iloc[0]
            algorithm = str(config_row["algorithm"])
            selected_config_json = str(config_row["selected_config_json"])
            train, test = validate_inputs(table, features, stage, outer_fold)
            estimator = fit_fixed_estimator(
                train,
                features,
                algorithm,
                selected_config_json,
                args.n_jobs,
                args.random_state + outer_fold * 10000,
            )
            baseline_residual = predict_residual(estimator, test, features, algorithm)
            baseline_doy = residual_to_doy(test, baseline_residual)
            baseline_metric = prediction_metrics(
                test["observed_doy"].to_numpy(float),
                baseline_doy,
            )
            baseline_rows.append(
                {
                    "stage": stage,
                    "outer_fold": outer_fold,
                    "algorithm": algorithm,
                    "selected_config_json": selected_config_json,
                    **baseline_metric,
                }
            )

            for group_id, group_features in groups.items():
                for repeat in range(1, args.n_repeats + 1):
                    rng = np.random.default_rng(
                        args.random_state
                        + outer_fold * 100000
                        + repeat * 1000
                        + GROUP_ORDER.index(group_id) * 100
                        + STAGE_ORDER.index(stage)
                    )
                    permuted = permute_group(test, group_features, rng)
                    permuted_residual = predict_residual(estimator, permuted, features, algorithm)
                    permuted_doy = residual_to_doy(test, permuted_residual)
                    permuted_metric = prediction_metrics(
                        test["observed_doy"].to_numpy(float),
                        permuted_doy,
                    )
                    repeat_rows.append(
                        {
                            "stage": stage,
                            "outer_fold": outer_fold,
                            "algorithm": algorithm,
                            "group_id": group_id,
                            "group_label": GROUP_LABELS[group_id],
                            "n_group_features": len(group_features),
                            "group_features": ";".join(group_features),
                            "repeat": repeat,
                            "baseline_mae_days": baseline_metric["mae_days"],
                            "baseline_rmse_days": baseline_metric["rmse_days"],
                            "permuted_mae_days": permuted_metric["mae_days"],
                            "permuted_rmse_days": permuted_metric["rmse_days"],
                            "mae_increase_days": permuted_metric["mae_days"]
                            - baseline_metric["mae_days"],
                            "rmse_increase_days": permuted_metric["rmse_days"]
                            - baseline_metric["rmse_days"],
                        }
                    )

    repeat_importance = pd.DataFrame(repeat_rows)
    by_fold = (
        repeat_importance.groupby(
            [
                "stage",
                "outer_fold",
                "algorithm",
                "group_id",
                "group_label",
                "n_group_features",
                "group_features",
            ],
            sort=False,
        )[["mae_increase_days", "rmse_increase_days"]]
        .agg(["mean", "std"])
        .reset_index()
    )
    by_fold.columns = [
        "_".join(part for part in column if part)
        for column in by_fold.columns.to_flat_index()
    ]
    by_fold = by_fold.rename(
        columns={
            "mae_increase_days_mean": "fold_mean_mae_increase_days",
            "mae_increase_days_std": "repeat_sd_mae_increase_days",
            "rmse_increase_days_mean": "fold_mean_rmse_increase_days",
            "rmse_increase_days_std": "repeat_sd_rmse_increase_days",
        }
    )

    summary_rows = []
    for keys, group in by_fold.groupby(
        ["stage", "algorithm", "group_id", "group_label", "n_group_features", "group_features"],
        sort=False,
    ):
        stage, algorithm, group_id, group_label, n_group_features, group_features = keys
        row: dict[str, object] = {
            "stage": stage,
            "algorithm": algorithm,
            "group_id": group_id,
            "group_label": group_label,
            "n_group_features": int(n_group_features),
            "group_features": group_features,
            "n_outer_folds": int(group["outer_fold"].nunique()),
            "n_positive_mae_folds": int((group["fold_mean_mae_increase_days"] > 0).sum()),
            "n_positive_rmse_folds": int((group["fold_mean_rmse_increase_days"] > 0).sum()),
        }
        for metric in ("mae", "rmse"):
            values = group[f"fold_mean_{metric}_increase_days"].to_numpy(dtype=float)
            row[f"mean_{metric}_increase_days"] = float(values.mean())
            row[f"sd_{metric}_increase_days"] = float(values.std(ddof=1))
            row[f"se_{metric}_increase_days"] = float(values.std(ddof=1) / np.sqrt(len(values)))
            row[f"min_{metric}_increase_days"] = float(values.min())
            row[f"max_{metric}_increase_days"] = float(values.max())
        summary_rows.append(row)
    summary = pd.DataFrame(summary_rows)
    baseline = pd.DataFrame(baseline_rows)
    return repeat_importance, by_fold, summary, baseline


def plot_importance(summary: pd.DataFrame, by_fold: pd.DataFrame, figure: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(FIG_WIDTH_IN, FIG_HEIGHT_IN),
        sharex=True,
        gridspec_kw={
            "left": 0.205,
            "right": 0.985,
            "bottom": 0.095,
            "top": 0.805,
            "wspace": 0.18,
            "hspace": 0.38,
        },
    )
    axes_flat = axes.ravel()
    y_positions = np.arange(len(GROUP_ORDER))

    max_value = max(float(summary["mean_rmse_increase_days"].max()), 0.0)
    x_upper = float(np.ceil((max_value + summary["se_rmse_increase_days"].max() + 0.10) * 2.0) / 2.0)
    x_upper = max(x_upper, 0.5)

    for axis, stage, panel_label in zip(axes_flat, STAGE_ORDER, ("(a)", "(b)", "(c)", "(d)")):
        stage_summary = summary.loc[summary["stage"].eq(stage)].copy()
        stage_summary["group_order"] = stage_summary["group_id"].map(
            {group: index for index, group in enumerate(GROUP_ORDER)}
        )
        stage_summary = stage_summary.sort_values("group_order")
        for _, row in stage_summary.iterrows():
            group_id = str(row["group_id"])
            y = GROUP_ORDER.index(group_id)
            axis.barh(
                y,
                float(row["mean_rmse_increase_days"]),
                xerr=float(row["se_rmse_increase_days"]),
                height=0.58,
                color=GROUP_COLORS[group_id],
                edgecolor="white",
                linewidth=0.55,
                alpha=0.90,
                error_kw={
                    "elinewidth": 0.75,
                    "ecolor": "#333333",
                    "capsize": 2.0,
                    "capthick": 0.75,
                },
                zorder=2,
            )
            fold_values = by_fold.loc[
                by_fold["stage"].eq(stage)
                & by_fold["group_id"].eq(group_id),
                ["outer_fold", "fold_mean_rmse_increase_days"],
            ].copy()
            jitter = np.linspace(-0.19, 0.19, len(fold_values))
            axis.scatter(
                fold_values["fold_mean_rmse_increase_days"],
                np.full(len(fold_values), y) + jitter,
                s=8.0,
                marker="o",
                facecolors="white",
                edgecolors="#4d4d4d",
                linewidths=0.30,
                alpha=0.65,
                zorder=4,
            )

        axis.axvline(0.0, color="#333333", linewidth=0.75, zorder=1)
        axis.set_title(STAGE_LABELS[stage], pad=2.0)
        axis.set_yticks(y_positions, [GROUP_LABELS[group] for group in GROUP_ORDER])
        if axis not in axes[:, 0]:
            axis.set_yticklabels([])
        axis.invert_yaxis()
        axis.set_xlim(-0.05, x_upper)
        axis.grid(axis="x", color="#bdbdbd", linewidth=0.35, alpha=0.55, zorder=0)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.tick_params(length=3.0, width=0.7)
        axis.text(
            0.01,
            1.02,
            panel_label,
            transform=axis.transAxes,
            ha="left",
            va="bottom",
            fontsize=BASE_FONT_SIZE,
        )

    for axis in axes[1, :]:
        axis.set_xlabel("ΔRMSE after group permutation (days)")

    handles = [
        Patch(
            facecolor=GROUP_COLORS[group],
            edgecolor="white",
            linewidth=0.55,
            label=GROUP_LABELS[group],
        )
        for group in GROUP_ORDER
    ]
    handles.append(
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markersize=3.8,
            markerfacecolor="white",
            markeredgecolor="#4d4d4d",
            color="#4d4d4d",
            label="Outer folds",
        )
    )
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.085, 0.840, 0.900, 0.120),
        bbox_transform=fig.transFigure,
        ncol=4,
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

    figure.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure, dpi=dpi, facecolor="white")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    repeat_importance, by_fold, summary, baseline = calculate_importance(args)

    repeat_path = args.output_dir / "mechanism_group_permutation_importance_by_repeat.csv"
    fold_path = args.output_dir / "mechanism_group_permutation_importance_by_fold.csv"
    summary_path = args.output_dir / "mechanism_group_permutation_importance_summary.csv"
    baseline_path = args.output_dir / "mechanism_group_permutation_importance_baseline_metrics.csv"
    group_map_path = args.output_dir / "mechanism_group_feature_mapping.csv"

    repeat_importance.to_csv(repeat_path, index=False)
    by_fold.to_csv(fold_path, index=False)
    summary.to_csv(summary_path, index=False)
    baseline.to_csv(baseline_path, index=False)
    (
        summary[["stage", "group_id", "group_label", "n_group_features", "group_features"]]
        .drop_duplicates()
        .sort_values(["stage", "group_id"])
        .to_csv(group_map_path, index=False)
    )
    plot_importance(summary, by_fold, args.figure, args.dpi)

    print("Fixed hybrid mechanism-group permutation importance completed")
    print(f"Data directory: {args.data_dir.relative_to(REPO_ROOT)}")
    print(f"Fixed directory: {args.fixed_dir.relative_to(REPO_ROOT)}")
    print(f"Output directory: {args.output_dir.relative_to(REPO_ROOT)}")
    print(f"Figure: {args.figure.relative_to(REPO_ROOT)}")
    print(f"Summary: {summary_path.relative_to(REPO_ROOT)}")
    print(
        summary.sort_values(["stage", "mean_rmse_increase_days"], ascending=[True, False])[
            [
                "stage",
                "algorithm",
                "group_label",
                "n_group_features",
                "mean_rmse_increase_days",
                "se_rmse_increase_days",
                "n_positive_rmse_folds",
            ]
        ]
        .round(3)
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
