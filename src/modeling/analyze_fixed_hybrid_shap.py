#!/usr/bin/env python
"""Compute and plot SHAP values for fixed hybrid residual learners."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from src.modeling.run_residual_ml_models import (
        REPO_ROOT,
        build_estimator,
        residual_to_doy,
        validate_inputs,
    )
except ModuleNotFoundError:
    from run_residual_ml_models import (  # type: ignore
        REPO_ROOT,
        build_estimator,
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
DEFAULT_OUTPUT_DIR = DEFAULT_FIXED_DIR / "interpretability/shap"
DEFAULT_IMPORTANCE_FIGURE = (
    REPO_ROOT / "fig/results_figure/fixed_hybrid_residual_shap_top10_importance.png"
)
DEFAULT_BEESWARM_FIGURE = (
    REPO_ROOT / "fig/results_figure/fixed_hybrid_residual_shap_top10_beeswarm.png"
)
DEFAULT_TABLE_DIR = REPO_ROOT / "results/paper_results"
STAGE_ORDER = ("budburst", "flowering", "veraison", "maturity_or_harvest")
STAGE_LABELS = {
    "budburst": "BBCH07",
    "flowering": "BBCH65",
    "veraison": "BBCH81",
    "maturity_or_harvest": "BBCH89",
}
ALGORITHM_LABELS = {
    "ridge": "Ridge",
    "gam": "GAM",
    "rf": "RF",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
}
STAGE_COLORS = {
    "budburst": "#0072B2",
    "flowering": "#009E73",
    "veraison": "#D55E00",
    "maturity_or_harvest": "#8E63B0",
}
FIG_WIDTH_IN = 7.0
IMPORTANCE_FIG_HEIGHT_IN = 6.7
BEESWARM_FIG_HEIGHT_IN = 8.20
BASE_FONT_SIZE = 9.2
TITLE_FONT_SIZE = 10.2
PANEL_LABEL_FONT_SIZE = 10.8
LABEL_FONT_SIZE = 8.0
LEGEND_FONT_SIZE = 8.2
POINT_SIZE = 8.0
BEESWARM_AXIS_FONT_SIZE = 11.0
BEESWARM_TICK_FONT_SIZE = 11.0
BEESWARM_TITLE_FONT_SIZE = 11.0
BEESWARM_PANEL_LABEL_FONT_SIZE = 11.0
BEESWARM_COLORBAR_FONT_SIZE = 11.0


def ensure_mpl_cache() -> None:
    cache_dir = Path(tempfile.gettempdir()) / "grape_growth_stage_mplconfig"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))


ensure_mpl_cache()


def parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--fixed-dir", type=Path, default=DEFAULT_FIXED_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--table-dir", type=Path, default=DEFAULT_TABLE_DIR)
    parser.add_argument("--importance-figure", type=Path, default=DEFAULT_IMPORTANCE_FIGURE)
    parser.add_argument("--beeswarm-figure", type=Path, default=DEFAULT_BEESWARM_FIGURE)
    parser.add_argument("--outer-folds", type=parse_int_list, default=[1, 2, 3, 4, 5])
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--max-beeswarm-records-per-stage", type=int, default=1400)
    parser.add_argument("--n-jobs", type=int, default=4)
    parser.add_argument("--random-state", type=int, default=20260805)
    parser.add_argument("--dpi", type=int, default=300)
    return parser.parse_args()


def configure_matplotlib() -> None:
    ensure_mpl_cache()
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.size": BASE_FONT_SIZE,
            "axes.labelsize": BASE_FONT_SIZE,
            "axes.titlesize": TITLE_FONT_SIZE,
            "xtick.labelsize": BASE_FONT_SIZE,
            "ytick.labelsize": LABEL_FONT_SIZE,
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
    config = json.loads(config_json)
    estimator = build_estimator(algorithm, config, n_jobs, random_state)
    estimator.fit(train[features], train["residual_days"].to_numpy(float))
    return estimator


def ridge_shap_values(estimator, train: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> np.ndarray:
    regressor = estimator.regressor_
    imputer = regressor.named_steps["imputer"]
    scaler = regressor.named_steps["scale"]
    ridge_model = regressor.named_steps["ridge"]
    train_scaled = scaler.transform(imputer.transform(train[features]))
    test_scaled = scaler.transform(imputer.transform(test[features]))
    background_scaled = np.nanmean(train_scaled, axis=0)
    coefficient = np.asarray(ridge_model.coef_, dtype=float).reshape(-1)
    target_scale = float(estimator.transformer_.scale_[0])
    return (test_scaled - background_scaled) * coefficient.reshape(1, -1) * target_scale


def tree_shap_values(estimator, test: pd.DataFrame, features: list[str]) -> np.ndarray:
    import shap

    imputer = estimator.named_steps["imputer"]
    model = estimator.named_steps["model"]
    test_imputed = imputer.transform(test[features])
    explainer = shap.TreeExplainer(model, feature_names=features)
    shap_values = explainer.shap_values(test_imputed, check_additivity=False)
    if isinstance(shap_values, list):
        shap_values = shap_values[0]
    return np.asarray(shap_values, dtype=float)


def estimator_shap_values(
    estimator,
    algorithm: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
) -> np.ndarray:
    if algorithm == "ridge":
        return ridge_shap_values(estimator, train, test, features)
    if algorithm in {"rf", "xgboost", "lightgbm"}:
        return tree_shap_values(estimator, test, features)
    raise ValueError(f"SHAP support is not implemented for fixed algorithm: {algorithm}")


def optional_column(frame: pd.DataFrame, column: str, length: int) -> np.ndarray:
    if column in frame.columns:
        return frame[column].to_numpy()
    return np.repeat(np.nan, length)


def long_shap_frame(
    stage: str,
    outer_fold: int,
    algorithm: str,
    test: pd.DataFrame,
    features: list[str],
    shap_values: np.ndarray,
    predicted_residual: np.ndarray,
) -> pd.DataFrame:
    row_count = len(test)
    feature_count = len(features)
    feature_values = test[features].to_numpy(float)
    hybrid_predicted_doy = residual_to_doy(test, predicted_residual)
    return pd.DataFrame(
        {
            "stage": np.repeat(stage, row_count * feature_count),
            "outer_fold": np.repeat(outer_fold, row_count * feature_count),
            "algorithm": np.repeat(algorithm, row_count * feature_count),
            "residual_row_id": np.repeat(test["residual_row_id"].to_numpy(), feature_count),
            "record_id": np.repeat(test["record_id"].to_numpy(), feature_count),
            "site_uid": np.repeat(optional_column(test, "site_uid", row_count), feature_count),
            "validation_block_1deg_id": np.repeat(
                optional_column(test, "validation_block_1deg_id", row_count), feature_count
            ),
            "observed_doy": np.repeat(test["observed_doy"].to_numpy(float), feature_count),
            "mechanistic_predicted_doy": np.repeat(
                test["mechanistic_predicted_doy"].to_numpy(float), feature_count
            ),
            "hybrid_predicted_doy": np.repeat(hybrid_predicted_doy, feature_count),
            "observed_residual_days": np.repeat(
                test["residual_days"].to_numpy(float), feature_count
            ),
            "predicted_residual_days": np.repeat(predicted_residual, feature_count),
            "feature": np.tile(np.asarray(features, dtype=object), row_count),
            "feature_order": np.tile(np.arange(1, feature_count + 1), row_count),
            "feature_value": feature_values.reshape(-1),
            "shap_value_days": shap_values.reshape(-1),
        }
    )


def compute_shap(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    features_by_stage = feature_sets(args.data_dir)
    outer_configs = load_outer_config(args.fixed_dir)
    shap_frames: list[pd.DataFrame] = []
    model_rows: list[dict[str, object]] = []

    for stage in STAGE_ORDER:
        features = features_by_stage[stage]
        table = pd.read_parquet(args.data_dir / "training_ready" / f"{stage}_residual_ml.parquet")
        for outer_fold in args.outer_folds:
            config_row = outer_configs.loc[
                outer_configs["stage"].eq(stage) & outer_configs["outer_fold"].eq(outer_fold)
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
            predicted_residual = np.asarray(estimator.predict(test[features]), dtype=float)
            shap_values = estimator_shap_values(estimator, algorithm, train, test, features)
            if shap_values.shape != (len(test), len(features)):
                raise ValueError(
                    f"{stage} fold {outer_fold}: SHAP shape {shap_values.shape} "
                    f"does not match {(len(test), len(features))}"
                )
            shap_frames.append(
                long_shap_frame(
                    stage,
                    outer_fold,
                    algorithm,
                    test,
                    features,
                    shap_values,
                    predicted_residual,
                )
            )
            model_rows.append(
                {
                    "stage": stage,
                    "outer_fold": outer_fold,
                    "algorithm": algorithm,
                    "selected_config_json": selected_config_json,
                    "n_train": int(len(train)),
                    "n_test": int(len(test)),
                    "n_features": int(len(features)),
                }
            )

    shap_long = pd.concat(shap_frames, ignore_index=True)
    summary = summarize_shap(shap_long)
    model_inventory = pd.DataFrame(model_rows)
    return shap_long, summary, model_inventory


def summarize_shap(shap_long: pd.DataFrame) -> pd.DataFrame:
    summary = (
        shap_long.groupby(["stage", "algorithm", "feature", "feature_order"], sort=False)
        .agg(
            n=("shap_value_days", "size"),
            mean_abs_shap_days=("shap_value_days", lambda values: float(np.mean(np.abs(values)))),
            median_abs_shap_days=(
                "shap_value_days",
                lambda values: float(np.median(np.abs(values))),
            ),
            mean_shap_days=("shap_value_days", "mean"),
            sd_shap_days=("shap_value_days", "std"),
            q05_shap_days=("shap_value_days", lambda values: float(np.quantile(values, 0.05))),
            q95_shap_days=("shap_value_days", lambda values: float(np.quantile(values, 0.95))),
        )
        .reset_index()
    )
    summary["rank"] = (
        summary.groupby("stage")["mean_abs_shap_days"]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    summary["stage_label"] = summary["stage"].map(STAGE_LABELS)
    summary["algorithm_label"] = summary["algorithm"].map(ALGORITHM_LABELS)
    summary["feature_label"] = summary["feature"].map(feature_label)
    summary["stage_order"] = summary["stage"].map(
        {stage: stage_index for stage_index, stage in enumerate(STAGE_ORDER)}
    )
    return summary.sort_values(["stage_order", "rank"]).reset_index(drop=True)


def feature_label(feature: str) -> str:
    labels = {
        "mechanistic_predicted_doy": "Process-predicted DOY",
        "dem_elevation_m": "Elevation",
        "dem_local_std_m": "Local elevation SD",
        "northness": "Northness",
        "lat": "Latitude",
        "lon": "Longitude",
        "country_france": "France indicator",
        "preseason_chill_days_tmean_0_10c": "Preseason chill days (0–10°C)",
        "preseason_frost_degree_days_below0_c_days": "Preseason frost intensity",
        "budburst_pre15d_gdd5_rate_c_day": "Pre-BBCH07 15 d GDD5 rate",
        "budburst_pre30d_gdd5_rate_c_day": "Pre-BBCH07 30 d GDD5 rate",
        "budburst_pre15d_frost_degree_days_below0_c_days": "Pre-BBCH07 15 d frost",
        "budburst_pre30d_frost_degree_days_below0_c_days": "Pre-BBCH07 30 d frost",
        "budburst_to_flowering_tmean_adjusted_sd_c": "BBCH07–65 Tmean SD",
        "budburst_to_flowering_diurnal_temperature_range_mean_c": "BBCH07–65 DTR",
        "budburst_to_flowering_cool_degree_days_below10_c_days": "BBCH07–65 cool intensity",
        "budburst_to_flowering_solar_radiation_mean_mj_m2_day": "BBCH07–65 mean radiation",
        "budburst_to_flowering_vpd_fao56_mean_kpa": "BBCH07–65 mean VPD",
        "budburst_to_flowering_et0_fao56_sum_mm": "BBCH07–65 ET0 sum",
        "budburst_to_flowering_positive_climatic_water_deficit_sum_mm": "BBCH07–65 CWD sum",
        "flowering_predicted_stage_length_days": "Predicted BBCH07–65 length",
        "budburst_to_flowering_gdd10_rate_c_day": "BBCH07–65 GDD10 rate",
        "flowering_pre15d_heat_degree_days_above30_c_days": "Pre-BBCH65 15 d heat",
        "flowering_pre15d_solar_radiation_mean_mj_m2_day": "Pre-BBCH65 15 d radiation",
        "flowering_to_veraison_tmean_adjusted_sd_c": "BBCH65–81 Tmean SD",
        "flowering_to_veraison_diurnal_temperature_range_mean_c": "BBCH65–81 DTR",
        "flowering_to_veraison_heat_degree_days_above30_c_days": "BBCH65–81 heat intensity",
        "flowering_to_veraison_precipitation_sum_mm": "BBCH65–81 precipitation",
        "preveraison_30d_heat_degree_days_above35_c_days": "Pre-BBCH81 30 d heat",
        "preveraison_30d_vpd_fao56_mean_kpa": "Pre-BBCH81 30 d VPD",
        "preveraison_30d_et0_fao56_sum_mm": "Pre-BBCH81 30 d ET0",
        "preveraison_30d_positive_climatic_water_deficit_sum_mm": "Pre-BBCH81 30 d CWD",
        "veraison_predicted_stage_length_days": "Predicted BBCH65–81 length",
        "flowering_to_veraison_gdd10_rate_c_day": "BBCH65–81 GDD10 rate",
        "veraison_to_harvest_tmean_adjusted_sd_c": "BBCH81–89 Tmean SD",
        "veraison_to_harvest_diurnal_temperature_range_mean_c": "BBCH81–89 DTR",
        "veraison_to_harvest_heat_degree_days_above30_c_days": "BBCH81–89 heat intensity",
        "veraison_to_harvest_precipitation_sum_mm": "BBCH81–89 precipitation",
        "veraison_to_harvest_solar_radiation_sum_mj_m2": "BBCH81–89 radiation sum",
        "veraison_to_harvest_vpd_fao56_mean_kpa": "BBCH81–89 mean VPD",
        "veraison_to_harvest_et0_fao56_sum_mm": "BBCH81–89 ET0 sum",
        "veraison_to_harvest_positive_climatic_water_deficit_sum_mm": "BBCH81–89 CWD sum",
    }
    return labels.get(feature, feature.replace("_", " "))


def wrapped_feature_label(feature: str, width: int = 25) -> str:
    return textwrap.fill(feature_label(feature), width=width)


def beeswarm_feature_label(feature: str) -> str:
    labels = {
        "mechanistic_predicted_doy": "Proc. DOY",
        "dem_elevation_m": "Elevation",
        "dem_local_std_m": "Elev. SD",
        "northness": "Northness",
        "lat": "Latitude",
        "lon": "Longitude",
        "country_france": "France",
        "preseason_chill_days_tmean_0_10c": "Preseason chill",
        "preseason_frost_degree_days_below0_c_days": "Preseason frost",
        "budburst_pre15d_gdd5_rate_c_day": "Pre-07 15d GDD5",
        "budburst_pre30d_gdd5_rate_c_day": "Pre-07 30d GDD5",
        "budburst_pre15d_frost_degree_days_below0_c_days": "Pre-07 15d frost",
        "budburst_pre30d_frost_degree_days_below0_c_days": "Pre-07 30d frost",
        "budburst_pre15d_solar_radiation_sum_mj_m2": "Pre-07 15d RAD",
        "budburst_to_flowering_tmean_adjusted_sd_c": "07–65 Tmean SD",
        "budburst_to_flowering_diurnal_temperature_range_mean_c": "07–65 DTR",
        "budburst_to_flowering_cool_degree_days_below10_c_days": "07–65 cool",
        "budburst_to_flowering_solar_radiation_mean_mj_m2_day": "07–65 RAD",
        "budburst_to_flowering_vpd_fao56_mean_kpa": "07–65 VPD",
        "budburst_to_flowering_et0_fao56_sum_mm": "07–65 ET0",
        "budburst_to_flowering_positive_climatic_water_deficit_sum_mm": "07–65 CWD",
        "flowering_predicted_stage_length_days": "Pred. 07–65 length",
        "budburst_to_flowering_gdd10_rate_c_day": "07–65 GDD10",
        "flowering_pre15d_heat_degree_days_above30_c_days": "Pre-65 15d heat",
        "flowering_pre15d_solar_radiation_mean_mj_m2_day": "Pre-65 15d RAD",
        "flowering_pre15d_vpd_fao56_mean_kpa": "Pre-65 15d VPD",
        "flowering_pre30d_diurnal_temperature_range_mean_c": "Pre-65 30d DTR",
        "flowering_to_veraison_tmean_adjusted_sd_c": "65–81 Tmean SD",
        "flowering_to_veraison_diurnal_temperature_range_mean_c": "65–81 DTR",
        "flowering_to_veraison_heat_degree_days_above30_c_days": "65–81 heat",
        "flowering_to_veraison_precipitation_sum_mm": "65–81 precip.",
        "flowering_to_veraison_gdd10_rate_c_day": "65–81 GDD10",
        "preveraison_30d_heat_degree_days_above35_c_days": "Pre-81 30d heat",
        "preveraison_30d_vpd_fao56_mean_kpa": "Pre-81 30d VPD",
        "preveraison_30d_et0_fao56_sum_mm": "Pre-81 30d ET0",
        "preveraison_30d_positive_climatic_water_deficit_sum_mm": "Pre-81 30d CWD",
        "veraison_pre15d_gdd10_rate_c_day": "Pre-81 15d GDD10",
        "veraison_predicted_stage_length_days": "Pred. 65–81 length",
        "veraison_to_harvest_tmean_adjusted_sd_c": "81–89 Tmean SD",
        "veraison_to_harvest_diurnal_temperature_range_mean_c": "81–89 DTR",
        "veraison_to_harvest_heat_degree_days_above30_c_days": "81–89 heat",
        "veraison_to_harvest_precipitation_sum_mm": "81–89 precip.",
        "veraison_to_harvest_solar_radiation_sum_mj_m2": "81–89 RAD",
        "veraison_to_harvest_vpd_fao56_mean_kpa": "81–89 VPD",
        "veraison_to_harvest_et0_fao56_sum_mm": "81–89 ET0",
        "veraison_to_harvest_positive_climatic_water_deficit_sum_mm": "81–89 CWD",
        "maturity_pre15d_gdd10_rate_c_day": "Pre-89 15d GDD10",
        "maturity_pre15d_heat_degree_days_above30_c_days": "Pre-89 15d heat",
    }
    return labels.get(feature, feature_label(feature))


def top_features(summary: pd.DataFrame, top_n: int) -> dict[str, list[str]]:
    return {
        stage: (
            summary.loc[summary["stage"].eq(stage)]
            .sort_values("rank")
            .head(top_n)["feature"]
            .tolist()
        )
        for stage in STAGE_ORDER
    }


def panel_title(stage: str, algorithm: str) -> str:
    return f"{STAGE_LABELS[stage]} {ALGORITHM_LABELS.get(algorithm, algorithm)}"


def panel_label(axis, label: str, font_size: float = PANEL_LABEL_FONT_SIZE) -> None:
    axis.text(
        -0.085,
        1.055,
        label,
        transform=axis.transAxes,
        ha="left",
        va="bottom",
        fontsize=font_size,
        clip_on=False,
    )


def plot_importance(summary: pd.DataFrame, top_n: int, output: Path, dpi: int) -> None:
    configure_matplotlib()
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(FIG_WIDTH_IN, IMPORTANCE_FIG_HEIGHT_IN))
    axes = axes.ravel()
    panel_labels = ("(a)", "(b)", "(c)", "(d)")
    for axis, stage, label in zip(axes, STAGE_ORDER, panel_labels):
        stage_summary = summary.loc[summary["stage"].eq(stage)].sort_values("rank").head(top_n)
        algorithm = str(stage_summary["algorithm"].iloc[0])
        plot_frame = stage_summary.iloc[::-1].copy()
        positions = np.arange(len(plot_frame))
        axis.barh(
            positions,
            plot_frame["mean_abs_shap_days"].to_numpy(float),
            color=STAGE_COLORS[stage],
            edgecolor="white",
            linewidth=0.6,
            alpha=0.88,
        )
        axis.set_yticks(positions)
        axis.set_yticklabels([wrapped_feature_label(feature, 27) for feature in plot_frame["feature"]])
        axis.set_title(panel_title(stage, algorithm), pad=4)
        axis.set_xlabel("mean(|SHAP|) (days)")
        axis.set_xlim(0, float(plot_frame["mean_abs_shap_days"].max()) * 1.06)
        axis.grid(axis="x", color="#dddddd", linewidth=0.55)
        axis.set_axisbelow(True)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        panel_label(axis, label, BEESWARM_PANEL_LABEL_FONT_SIZE)
    figure.subplots_adjust(left=0.245, right=0.985, bottom=0.075, top=0.925, wspace=0.50, hspace=0.44)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=dpi)
    plt.close(figure)


def sample_stage_records(
    stage_frame: pd.DataFrame,
    max_records: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    record_columns = ["stage", "outer_fold", "residual_row_id"]
    records = stage_frame[record_columns].drop_duplicates()
    if len(records) <= max_records:
        return stage_frame
    sampled_records = records.sample(n=max_records, random_state=int(rng.integers(1, 2**31 - 1)))
    return stage_frame.merge(sampled_records, on=record_columns, how="inner")


def feature_color_values(values: np.ndarray) -> np.ndarray:
    numeric = np.asarray(values, dtype=float)
    finite = np.isfinite(numeric)
    normalized = np.repeat(0.5, len(numeric)).astype(float)
    if not finite.any():
        return normalized
    lower, upper = np.nanquantile(numeric[finite], [0.05, 0.95])
    if np.isclose(lower, upper):
        normalized[finite] = 0.5
        return normalized
    clipped = np.clip(numeric[finite], lower, upper)
    normalized[finite] = (clipped - lower) / (upper - lower)
    return normalized


def plot_beeswarm(
    shap_long: pd.DataFrame,
    summary: pd.DataFrame,
    top_n: int,
    max_records: int,
    output: Path,
    random_state: int,
    dpi: int,
) -> None:
    configure_matplotlib()
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    feature_order = top_features(summary, top_n)
    rng = np.random.default_rng(random_state)
    figure, axes = plt.subplots(2, 2, figsize=(FIG_WIDTH_IN, BEESWARM_FIG_HEIGHT_IN))
    axes = axes.ravel()
    panel_labels = ("(a)", "(b)", "(c)", "(d)")
    colormap = plt.get_cmap("coolwarm")
    for axis, stage, label in zip(axes, STAGE_ORDER, panel_labels):
        features = feature_order[stage]
        stage_frame = shap_long.loc[
            shap_long["stage"].eq(stage) & shap_long["feature"].isin(features)
        ].copy()
        stage_frame = sample_stage_records(stage_frame, max_records, rng)
        algorithm = str(stage_frame["algorithm"].iloc[0])
        for feature_index, feature in enumerate(features):
            feature_frame = stage_frame.loc[stage_frame["feature"].eq(feature)]
            if feature_frame.empty:
                continue
            shap_values = feature_frame["shap_value_days"].to_numpy(float)
            feature_values = feature_frame["feature_value"].to_numpy(float)
            color_values = feature_color_values(feature_values)
            jitter = rng.normal(0.0, 0.085, len(feature_frame))
            axis.scatter(
                shap_values,
                np.repeat(feature_index, len(feature_frame)) + jitter,
                c=color_values,
                cmap=colormap,
                vmin=0,
                vmax=1,
                s=POINT_SIZE,
                alpha=0.58,
                linewidths=0,
                rasterized=True,
            )
        stage_shap = stage_frame["shap_value_days"].to_numpy(float)
        finite = np.isfinite(stage_shap)
        if finite.any():
            limit = float(np.nanquantile(np.abs(stage_shap[finite]), 0.995))
            limit = max(limit, 0.25)
            axis.set_xlim(-limit * 1.08, limit * 1.08)
        axis.axvline(0.0, color="#666666", linewidth=0.8)
        axis.set_yticks(np.arange(len(features)))
        axis.set_yticklabels([beeswarm_feature_label(feature) for feature in features])
        axis.invert_yaxis()
        axis.set_title(panel_title(stage, algorithm), pad=4)
        axis.set_xlabel("SHAP value (days)")
        axis.grid(axis="x", color="#dddddd", linewidth=0.55)
        axis.set_axisbelow(True)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.tick_params(axis="both", labelsize=BEESWARM_TICK_FONT_SIZE)
        axis.xaxis.label.set_size(BEESWARM_AXIS_FONT_SIZE)
        axis.yaxis.label.set_size(BEESWARM_AXIS_FONT_SIZE)
        axis.title.set_size(BEESWARM_TITLE_FONT_SIZE)
        panel_label(axis, label, BEESWARM_PANEL_LABEL_FONT_SIZE)

    color_axis = figure.add_axes([0.245, 0.052, 0.725, 0.018])
    scalar_map = mpl.cm.ScalarMappable(cmap=colormap, norm=mpl.colors.Normalize(vmin=0, vmax=1))
    scalar_map.set_array([])
    colorbar = figure.colorbar(scalar_map, cax=color_axis, orientation="horizontal")
    colorbar.set_ticks([0, 1])
    colorbar.set_ticklabels(["Low", "High"])
    colorbar.set_label("Feature value", labelpad=2)
    colorbar.ax.tick_params(labelsize=BEESWARM_COLORBAR_FONT_SIZE)
    colorbar.ax.xaxis.label.set_size(BEESWARM_COLORBAR_FONT_SIZE)
    color_axis.xaxis.set_label_position("top")
    figure.subplots_adjust(left=0.245, right=0.970, bottom=0.145, top=0.930, wspace=0.80, hspace=0.45)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=dpi)
    plt.close(figure)


def write_outputs(
    args: argparse.Namespace,
    shap_long: pd.DataFrame,
    summary: pd.DataFrame,
    model_inventory: pd.DataFrame,
) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.table_dir.mkdir(parents=True, exist_ok=True)
    shap_long.to_parquet(args.output_dir / "fixed_hybrid_residual_shap_values.parquet", index=False)
    summary.to_csv(args.output_dir / "fixed_hybrid_residual_shap_feature_importance.csv", index=False)
    model_inventory.to_csv(args.output_dir / "fixed_hybrid_residual_shap_model_inventory.csv", index=False)
    summary.to_csv(args.table_dir / "fixed_hybrid_residual_shap_feature_importance.csv", index=False)
    (
        summary.loc[summary["rank"].le(args.top_n)]
        .sort_values(["stage_order", "rank"])
        .to_csv(args.table_dir / "fixed_hybrid_residual_shap_top10_feature_importance.csv", index=False)
    )
    model_inventory.to_csv(args.table_dir / "fixed_hybrid_residual_shap_model_inventory.csv", index=False)


def print_terminal_summary(summary: pd.DataFrame, top_n: int) -> None:
    display = summary.loc[summary["rank"].le(top_n)].copy()
    display["mean_abs_shap_days"] = display["mean_abs_shap_days"].round(3)
    display["mean_shap_days"] = display["mean_shap_days"].round(3)
    display = display[
        [
            "stage_label",
            "algorithm_label",
            "rank",
            "feature",
            "mean_abs_shap_days",
            "mean_shap_days",
        ]
    ]
    print("\nFixed-hybrid residual learner SHAP top features")
    print(display.to_string(index=False))


def main() -> None:
    args = parse_args()
    shap_long, summary, model_inventory = compute_shap(args)
    write_outputs(args, shap_long, summary, model_inventory)
    plot_importance(summary, args.top_n, args.importance_figure, args.dpi)
    plot_beeswarm(
        shap_long,
        summary,
        args.top_n,
        args.max_beeswarm_records_per_stage,
        args.beeswarm_figure,
        args.random_state,
        args.dpi,
    )
    print_terminal_summary(summary, args.top_n)
    print(f"\nSHAP values: {args.output_dir / 'fixed_hybrid_residual_shap_values.parquet'}")
    print(f"Importance figure: {args.importance_figure}")
    print(f"Beeswarm figure: {args.beeswarm_figure}")


if __name__ == "__main__":
    main()
