#!/usr/bin/env python
"""Quantify phenology shifts induced by terrain temperature adjustment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_BASELINE_DIR = (
    REPO_ROOT / "data/phenology/derived/modeling/france_germany_four_stage/baseline_mechanistic"
)
DEFAULT_REFERENCE_SAMPLE_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_machine_learning_doyrange21_postflower_water_spatial_ablation_pruned"
)
DEFAULT_ADJUSTED_FIXED_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/"
    "doyrange21_postflower_water_spatial_ablation_pruned_fixed_stage_models_refit"
)
DEFAULT_RAW_FIXED_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/"
    "raw_temperature_doyrange21_postflower_water_spatial_ablation_pruned_fixed_stage_models_refit"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "results/france_germany_four_stage/terrain_temperature_shift_quantification"
)
DEFAULT_REPORT_PATH = REPO_ROOT / "results/report/terrain_temperature_phenology_shift_quantification.md"

HARVEST_CHAIN_MODEL_ID = "maturity_or_harvest__predicted_veraison_post_gdd10"
TEMPERATURE_BRANCHES = ("raw", "adjusted_6p5")
STAGES = ("budburst", "flowering", "veraison", "maturity_or_harvest")
STAGE_LABELS = {
    "budburst": "BBCH07 萌芽",
    "flowering": "BBCH65 开花",
    "veraison": "BBCH81 转色",
    "maturity_or_harvest": "BBCH89 成熟/采收",
}
PROCESS_MODEL_IDS = {
    "budburst": "budburst__calibrated_brin_aug1",
    "flowering": "flowering__calibrated_gfv",
    "veraison": "veraison__calibrated_gfv",
    "maturity_or_harvest": HARVEST_CHAIN_MODEL_ID,
}
META_COLUMNS = [
    "stage",
    "outer_fold",
    "record_id",
    "weather_id",
    "site_uid",
    "country",
    "source",
    "site_id",
    "year",
    "lat",
    "lon",
    "dem_elevation_m",
    "era5_grid_elevation_m",
    "site_minus_grid_elevation_m",
    "abs_site_grid_elevation_difference_m",
    "dem_local_std_m",
    "northness",
    "observed_doy",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    parser.add_argument("--reference-sample-dir", type=Path, default=DEFAULT_REFERENCE_SAMPLE_DIR)
    parser.add_argument("--adjusted-fixed-dir", type=Path, default=DEFAULT_ADJUSTED_FIXED_DIR)
    parser.add_argument("--raw-fixed-dir", type=Path, default=DEFAULT_RAW_FIXED_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--lapse-rate-c-per-km",
        type=float,
        default=6.5,
        help="Main terrain lapse-rate correction; adjusted = raw - lapse_rate * dz_km.",
    )
    return parser.parse_args()


def reference_sample(reference_sample_dir: Path) -> pd.DataFrame:
    path = reference_sample_dir / "residual_spatial_test.parquet"
    frame = pd.read_parquet(path, columns=META_COLUMNS).drop_duplicates(
        ["stage", "outer_fold", "record_id"]
    )
    return frame


def outer_process_predictions(baseline_dir: Path) -> pd.DataFrame:
    baseline = pd.read_parquet(baseline_dir / "nested_cv_predictions.parquet")
    baseline = baseline.loc[
        baseline["split"].eq("outer_test")
        & baseline["analysis_set"].eq("independent_stage")
        & baseline["selection_eligible"].astype(bool)
        & baseline["temperature_branch"].isin(TEMPERATURE_BRANCHES)
    ].copy()
    process_frames = []
    for stage in ("budburst", "flowering", "veraison"):
        process_frames.append(
            baseline.loc[
                baseline["stage"].eq(stage)
                & baseline["model_id"].eq(PROCESS_MODEL_IDS[stage]),
                [
                    "stage",
                    "outer_fold",
                    "temperature_branch",
                    "model_id",
                    "record_id",
                    "observed_doy",
                    "predicted_doy",
                    "threshold_reached",
                ],
            ]
        )
    harvest = pd.read_parquet(
        baseline_dir
        / "bbch89_independent"
        / "predicted_veraison_to_bbch89_outer_predictions.parquet"
    ).copy()
    harvest["stage"] = "maturity_or_harvest"
    harvest["model_id"] = HARVEST_CHAIN_MODEL_ID
    harvest = harvest.loc[
        harvest["temperature_branch"].isin(TEMPERATURE_BRANCHES),
        [
            "stage",
            "outer_fold",
            "temperature_branch",
            "model_id",
            "record_id",
            "observed_doy",
            "predicted_doy",
            "threshold_reached",
        ],
    ]
    process_frames.append(harvest)
    return pd.concat(process_frames, ignore_index=True)


def process_shift_table(args: argparse.Namespace) -> pd.DataFrame:
    meta = reference_sample(args.reference_sample_dir)
    process = outer_process_predictions(args.baseline_dir)
    process = process.merge(
        meta[["stage", "outer_fold", "record_id"]],
        on=["stage", "outer_fold", "record_id"],
        how="inner",
        validate="many_to_one",
    )
    wide = process.pivot_table(
        index=["stage", "outer_fold", "record_id"],
        columns="temperature_branch",
        values="predicted_doy",
        aggfunc="first",
    ).reset_index()
    wide = wide.rename(
        columns={
            "raw": "raw_process_predicted_doy",
            "adjusted_6p5": "adjusted_process_predicted_doy",
        }
    )
    observed = (
        process.groupby(["stage", "outer_fold", "record_id"], as_index=False)["observed_doy"]
        .first()
        .rename(columns={"observed_doy": "observed_doy_from_process"})
    )
    wide = wide.merge(observed, on=["stage", "outer_fold", "record_id"], how="left")
    wide = wide.merge(meta, on=["stage", "outer_fold", "record_id"], how="left")
    valid = wide["raw_process_predicted_doy"].notna() & wide[
        "adjusted_process_predicted_doy"
    ].notna()
    wide = wide.loc[valid].copy()
    wide["temperature_adjustment_c"] = (
        -args.lapse_rate_c_per_km
        * wide["site_minus_grid_elevation_m"].astype(float)
        / 1000.0
    )
    wide["abs_temperature_adjustment_c"] = wide["temperature_adjustment_c"].abs()
    wide["process_shift_adjusted_minus_raw_days"] = (
        wide["adjusted_process_predicted_doy"].astype(float)
        - wide["raw_process_predicted_doy"].astype(float)
    )
    wide["abs_process_shift_days"] = wide[
        "process_shift_adjusted_minus_raw_days"
    ].abs()
    wide["process_shift_days_per_abs_100m"] = np.where(
        wide["abs_site_grid_elevation_difference_m"].astype(float).ge(10.0),
        wide["abs_process_shift_days"]
        / (wide["abs_site_grid_elevation_difference_m"].astype(float) / 100.0),
        np.nan,
    )
    direction_mask = wide["abs_temperature_adjustment_c"].gt(0.01) & wide[
        "abs_process_shift_days"
    ].gt(0.0)
    wide["thermal_direction_consistent"] = np.where(
        direction_mask,
        np.sign(wide["process_shift_adjusted_minus_raw_days"])
        == -np.sign(wide["temperature_adjustment_c"]),
        np.nan,
    )
    wide["stage_label"] = wide["stage"].map(STAGE_LABELS)
    return wide


def branch_predictions(path: Path, branch: str) -> pd.DataFrame:
    predictions = pd.read_parquet(path / "fixed_stage_outer_predictions.parquet").copy()
    return predictions.rename(
        columns={
            "algorithm": f"{branch}_algorithm",
            "observed_doy": f"{branch}_observed_doy",
            "mechanistic_predicted_doy": f"{branch}_process_predicted_doy",
            "predicted_residual_days": f"{branch}_predicted_residual_days",
            "hybrid_predicted_doy": f"{branch}_hybrid_predicted_doy",
        }
    )[
        [
            "stage",
            "outer_fold",
            "record_id",
            "site_uid",
            f"{branch}_algorithm",
            f"{branch}_observed_doy",
            f"{branch}_process_predicted_doy",
            f"{branch}_predicted_residual_days",
            f"{branch}_hybrid_predicted_doy",
        ]
    ]


def hybrid_shift_table(args: argparse.Namespace, process_table: pd.DataFrame) -> pd.DataFrame:
    adjusted = branch_predictions(args.adjusted_fixed_dir, "adjusted")
    raw = branch_predictions(args.raw_fixed_dir, "raw")
    merged = adjusted.merge(
        raw,
        on=["stage", "outer_fold", "record_id", "site_uid"],
        how="inner",
        validate="one_to_one",
    )
    merged = merged.merge(
        process_table[
            [
                "stage",
                "outer_fold",
                "record_id",
                "country",
                "year",
                "site_minus_grid_elevation_m",
                "abs_site_grid_elevation_difference_m",
                "temperature_adjustment_c",
                "abs_temperature_adjustment_c",
            ]
        ],
        on=["stage", "outer_fold", "record_id"],
        how="inner",
        validate="one_to_one",
    )
    merged["hybrid_shift_adjusted_minus_raw_days"] = (
        merged["adjusted_hybrid_predicted_doy"].astype(float)
        - merged["raw_hybrid_predicted_doy"].astype(float)
    )
    merged["process_shift_from_fixed_outputs_adjusted_minus_raw_days"] = (
        merged["adjusted_process_predicted_doy"].astype(float)
        - merged["raw_process_predicted_doy"].astype(float)
    )
    merged["abs_hybrid_shift_days"] = merged[
        "hybrid_shift_adjusted_minus_raw_days"
    ].abs()
    merged["stage_label"] = merged["stage"].map(STAGE_LABELS)
    return merged


def q(series: pd.Series, probability: float) -> float:
    return float(series.dropna().quantile(probability)) if series.notna().any() else np.nan


def stage_distribution_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stage, group in frame.groupby("stage", sort=False):
        direction = group["thermal_direction_consistent"].dropna().astype(bool)
        rows.append(
            {
                "stage": stage,
                "stage_label": STAGE_LABELS[stage],
                "n": int(len(group)),
                "site_minus_grid_elevation_mean_m": float(
                    group["site_minus_grid_elevation_m"].mean()
                ),
                "site_minus_grid_elevation_median_m": float(
                    group["site_minus_grid_elevation_m"].median()
                ),
                "site_minus_grid_elevation_p05_m": q(
                    group["site_minus_grid_elevation_m"], 0.05
                ),
                "site_minus_grid_elevation_p95_m": q(
                    group["site_minus_grid_elevation_m"], 0.95
                ),
                "temperature_adjustment_mean_c": float(
                    group["temperature_adjustment_c"].mean()
                ),
                "temperature_adjustment_median_c": float(
                    group["temperature_adjustment_c"].median()
                ),
                "temperature_adjustment_p05_c": q(group["temperature_adjustment_c"], 0.05),
                "temperature_adjustment_p95_c": q(group["temperature_adjustment_c"], 0.95),
                "abs_temperature_adjustment_median_c": float(
                    group["abs_temperature_adjustment_c"].median()
                ),
                "process_shift_mean_days": float(
                    group["process_shift_adjusted_minus_raw_days"].mean()
                ),
                "process_shift_median_days": float(
                    group["process_shift_adjusted_minus_raw_days"].median()
                ),
                "process_shift_p05_days": q(
                    group["process_shift_adjusted_minus_raw_days"], 0.05
                ),
                "process_shift_p95_days": q(
                    group["process_shift_adjusted_minus_raw_days"], 0.95
                ),
                "abs_process_shift_mean_days": float(group["abs_process_shift_days"].mean()),
                "abs_process_shift_median_days": float(
                    group["abs_process_shift_days"].median()
                ),
                "nonzero_process_shift_pct": float(
                    group["abs_process_shift_days"].gt(0.0).mean() * 100.0
                ),
                "thermal_direction_consistent_pct": float(
                    direction.mean() * 100.0 if len(direction) else np.nan
                ),
                "thermal_direction_consistency_n": int(len(direction)),
                "median_event_abs_shift_days_per_abs_100m": float(
                    group["process_shift_days_per_abs_100m"].median()
                ),
            }
        )
    order = {stage: index for index, stage in enumerate(STAGES)}
    result = pd.DataFrame(rows)
    result["stage_order"] = result["stage"].map(order)
    return result.sort_values("stage_order").drop(columns="stage_order")


def ols_relationship(x: pd.Series, y: pd.Series) -> dict[str, float]:
    valid = x.notna() & y.notna() & np.isfinite(x) & np.isfinite(y)
    x_values = x.loc[valid].to_numpy(float)
    y_values = y.loc[valid].to_numpy(float)
    if len(x_values) < 3 or np.isclose(np.nanstd(x_values), 0.0):
        return {
            "n": int(len(x_values)),
            "intercept_days": np.nan,
            "slope": np.nan,
            "pearson_r": np.nan,
            "r2": np.nan,
        }
    design = np.column_stack([np.ones(len(x_values)), x_values])
    intercept, slope = np.linalg.lstsq(design, y_values, rcond=None)[0]
    r = float(np.corrcoef(x_values, y_values)[0, 1])
    return {
        "n": int(len(x_values)),
        "intercept_days": float(intercept),
        "slope": float(slope),
        "pearson_r": r,
        "r2": float(r * r),
    }


def relationship_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stage, group in frame.groupby("stage", sort=False):
        dz_relation = ols_relationship(
            group["site_minus_grid_elevation_m"].astype(float) / 100.0,
            group["process_shift_adjusted_minus_raw_days"].astype(float),
        )
        temp_relation = ols_relationship(
            group["temperature_adjustment_c"].astype(float),
            group["process_shift_adjusted_minus_raw_days"].astype(float),
        )
        abs_relation = ols_relationship(
            group["abs_site_grid_elevation_difference_m"].astype(float) / 100.0,
            group["abs_process_shift_days"].astype(float),
        )
        rows.append(
            {
                "stage": stage,
                "stage_label": STAGE_LABELS[stage],
                "n": dz_relation["n"],
                "process_shift_days_per_100m_site_minus_grid": dz_relation["slope"],
                "process_shift_intercept_days": dz_relation["intercept_days"],
                "process_shift_vs_dz_pearson_r": dz_relation["pearson_r"],
                "process_shift_vs_dz_r2": dz_relation["r2"],
                "process_shift_days_per_1c_adjustment": temp_relation["slope"],
                "process_shift_vs_temp_adjustment_r2": temp_relation["r2"],
                "abs_process_shift_days_per_abs_100m": abs_relation["slope"],
                "abs_shift_vs_abs_dz_r2": abs_relation["r2"],
            }
        )
    order = {stage: index for index, stage in enumerate(STAGES)}
    result = pd.DataFrame(rows)
    result["stage_order"] = result["stage"].map(order)
    return result.sort_values("stage_order").drop(columns="stage_order")


def country_stage_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (stage, country), group in frame.groupby(["stage", "country"], sort=False):
        rows.append(
            {
                "stage": stage,
                "stage_label": STAGE_LABELS[stage],
                "country": country,
                "n": int(len(group)),
                "temperature_adjustment_median_c": float(
                    group["temperature_adjustment_c"].median()
                ),
                "process_shift_mean_days": float(
                    group["process_shift_adjusted_minus_raw_days"].mean()
                ),
                "process_shift_median_days": float(
                    group["process_shift_adjusted_minus_raw_days"].median()
                ),
                "abs_process_shift_median_days": float(
                    group["abs_process_shift_days"].median()
                ),
            }
        )
    order = {stage: index for index, stage in enumerate(STAGES)}
    result = pd.DataFrame(rows)
    result["stage_order"] = result["stage"].map(order)
    return result.sort_values(["stage_order", "country"]).drop(columns="stage_order")


def elevation_bin_summary(frame: pd.DataFrame) -> pd.DataFrame:
    bins = [-np.inf, 25.0, 50.0, 100.0, 200.0, np.inf]
    labels = ["<25 m", "25-50 m", "50-100 m", "100-200 m", ">=200 m"]
    binned = frame.copy()
    binned["abs_elevation_mismatch_bin"] = pd.cut(
        binned["abs_site_grid_elevation_difference_m"],
        bins=bins,
        labels=labels,
        right=False,
    )
    rows = []
    for (stage, mismatch_bin), group in binned.groupby(
        ["stage", "abs_elevation_mismatch_bin"], observed=True, sort=False
    ):
        rows.append(
            {
                "stage": stage,
                "stage_label": STAGE_LABELS[stage],
                "abs_elevation_mismatch_bin": str(mismatch_bin),
                "n": int(len(group)),
                "abs_temperature_adjustment_median_c": float(
                    group["abs_temperature_adjustment_c"].median()
                ),
                "abs_process_shift_mean_days": float(group["abs_process_shift_days"].mean()),
                "abs_process_shift_median_days": float(
                    group["abs_process_shift_days"].median()
                ),
                "process_shift_p05_days": q(
                    group["process_shift_adjusted_minus_raw_days"], 0.05
                ),
                "process_shift_p95_days": q(
                    group["process_shift_adjusted_minus_raw_days"], 0.95
                ),
            }
        )
    order = {stage: index for index, stage in enumerate(STAGES)}
    result = pd.DataFrame(rows)
    result["stage_order"] = result["stage"].map(order)
    return result.sort_values(["stage_order", "abs_elevation_mismatch_bin"]).drop(
        columns="stage_order"
    )


def hybrid_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stage, group in frame.groupby("stage", sort=False):
        rows.append(
            {
                "stage": stage,
                "stage_label": STAGE_LABELS[stage],
                "n": int(len(group)),
                "adjusted_algorithm": str(group["adjusted_algorithm"].iloc[0]),
                "raw_algorithm": str(group["raw_algorithm"].iloc[0]),
                "fixed_process_shift_mean_days": float(
                    group["process_shift_from_fixed_outputs_adjusted_minus_raw_days"].mean()
                ),
                "fixed_process_shift_median_days": float(
                    group["process_shift_from_fixed_outputs_adjusted_minus_raw_days"].median()
                ),
                "hybrid_shift_mean_days": float(
                    group["hybrid_shift_adjusted_minus_raw_days"].mean()
                ),
                "hybrid_shift_median_days": float(
                    group["hybrid_shift_adjusted_minus_raw_days"].median()
                ),
                "abs_hybrid_shift_mean_days": float(group["abs_hybrid_shift_days"].mean()),
                "abs_hybrid_shift_median_days": float(
                    group["abs_hybrid_shift_days"].median()
                ),
            }
        )
    order = {stage: index for index, stage in enumerate(STAGES)}
    result = pd.DataFrame(rows)
    result["stage_order"] = result["stage"].map(order)
    return result.sort_values("stage_order").drop(columns="stage_order")


def table_markdown(frame: pd.DataFrame, columns: list[str], rename: dict[str, str]) -> str:
    return frame[columns].rename(columns=rename).round(3).to_markdown(index=False)


def write_report(
    args: argparse.Namespace,
    stage_summary: pd.DataFrame,
    relationship: pd.DataFrame,
    bin_summary: pd.DataFrame,
    hybrid_stage_summary: pd.DataFrame,
    country_summary: pd.DataFrame,
) -> None:
    stage_md = table_markdown(
        stage_summary,
        [
            "stage_label",
            "n",
            "temperature_adjustment_median_c",
            "temperature_adjustment_p05_c",
            "temperature_adjustment_p95_c",
            "process_shift_mean_days",
            "process_shift_median_days",
            "process_shift_p05_days",
            "process_shift_p95_days",
            "abs_process_shift_median_days",
            "thermal_direction_consistent_pct",
        ],
        {
            "stage_label": "阶段",
            "n": "n",
            "temperature_adjustment_median_c": "温度校正中位数(°C)",
            "temperature_adjustment_p05_c": "温度校正P05",
            "temperature_adjustment_p95_c": "温度校正P95",
            "process_shift_mean_days": "过程位移均值(d)",
            "process_shift_median_days": "过程位移中位数(d)",
            "process_shift_p05_days": "过程位移P05",
            "process_shift_p95_days": "过程位移P95",
            "abs_process_shift_median_days": "绝对过程位移中位数(d)",
            "thermal_direction_consistent_pct": "热方向一致(%)",
        },
    )
    relationship_md = table_markdown(
        relationship,
        [
            "stage_label",
            "n",
            "process_shift_days_per_100m_site_minus_grid",
            "process_shift_vs_dz_r2",
            "process_shift_days_per_1c_adjustment",
            "process_shift_vs_temp_adjustment_r2",
            "abs_process_shift_days_per_abs_100m",
            "abs_shift_vs_abs_dz_r2",
        ],
        {
            "stage_label": "阶段",
            "n": "n",
            "process位移/100m(d)": "process位移/100m(d)",
            "process_shift_days_per_100m_site_minus_grid": "过程位移/100m(d)",
            "process_shift_vs_dz_r2": "位移~高差R²",
            "process_shift_days_per_1c_adjustment": "过程位移/1°C校正(d)",
            "process_shift_vs_temp_adjustment_r2": "位移~温度校正R²",
            "abs_process_shift_days_per_abs_100m": "绝对位移/绝对100m(d)",
            "abs_shift_vs_abs_dz_r2": "绝对位移~绝对高差R²",
        },
    )
    bin_md = table_markdown(
        bin_summary,
        [
            "stage_label",
            "abs_elevation_mismatch_bin",
            "n",
            "abs_temperature_adjustment_median_c",
            "abs_process_shift_mean_days",
            "abs_process_shift_median_days",
            "process_shift_p05_days",
            "process_shift_p95_days",
        ],
        {
            "stage_label": "阶段",
            "abs_elevation_mismatch_bin": "站点-格点绝对高差",
            "n": "n",
            "abs_temperature_adjustment_median_c": "绝对温度校正中位数(°C)",
            "abs_process_shift_mean_days": "绝对过程位移均值(d)",
            "abs_process_shift_median_days": "绝对过程位移中位数(d)",
            "process_shift_p05_days": "过程位移P05",
            "process_shift_p95_days": "过程位移P95",
        },
    )
    hybrid_md = table_markdown(
        hybrid_stage_summary,
        [
            "stage_label",
            "n",
            "adjusted_algorithm",
            "raw_algorithm",
            "fixed_process_shift_mean_days",
            "hybrid_shift_mean_days",
            "hybrid_shift_median_days",
            "abs_hybrid_shift_median_days",
        ],
        {
            "stage_label": "阶段",
            "n": "n",
            "adjusted_algorithm": "adjusted算法",
            "raw_algorithm": "raw算法",
            "fixed_process_shift_mean_days": "固定输出过程位移均值(d)",
            "hybrid_shift_mean_days": "混合位移均值(d)",
            "hybrid_shift_median_days": "混合位移中位数(d)",
            "abs_hybrid_shift_median_days": "绝对混合位移中位数(d)",
        },
    )
    country_md = table_markdown(
        country_summary,
        [
            "stage_label",
            "country",
            "n",
            "temperature_adjustment_median_c",
            "process_shift_mean_days",
            "process_shift_median_days",
            "abs_process_shift_median_days",
        ],
        {
            "stage_label": "阶段",
            "country": "国家",
            "n": "n",
            "temperature_adjustment_median_c": "温度校正中位数(°C)",
            "process_shift_mean_days": "过程位移均值(d)",
            "process_shift_median_days": "过程位移中位数(d)",
            "abs_process_shift_median_days": "绝对过程位移中位数(d)",
        },
    )
    lines = [
        "# Terrain-temperature adjustment and phenology-shift quantification",
        "",
        "主量化指标使用纯过程模型 raw vs adjusted_6p5 分支：`process_shift = adjusted_process_predicted_doy - raw_process_predicted_doy`。正值表示地形温度校正后预测日期更晚。`temperature_adjustment_c = -6.5 °C km-1 × (site elevation - ERA5 grid elevation)`。",
        "",
        "重要边界：第 1–3 表是分支级量化，raw 与 adjusted_6p5 分支各自使用训练区校准得到的阈值，因此结果包含温度输入校正和分支阈值重校准的合成影响。它可以作为预测分支层面的量化证据，但不能单独解释为固定阈值下的纯物理反事实效应。",
        "",
        "## 1. 阶段尺度温度校正与过程预测位移",
        "",
        stage_md,
        "",
        "## 2. 高差-位移连续关系",
        "",
        relationship_md,
        "",
        "## 3. 站点-格点高差分箱",
        "",
        bin_md,
        "",
        "## 4. 固定混合模型分支位移辅助表",
        "",
        "该表使用当前 fixed hybrid outputs。萌芽阶段当前 adjusted 主分析曾存在温度分支未完全一致的问题，因此主量化仍以第 1–3 表的纯过程分支为准。",
        "",
        hybrid_md,
        "",
        "## 5. 国家分组补充",
        "",
        country_md,
        "",
        "## 6. 输出文件",
        "",
        f"- Event-level process shifts: `{args.output_dir / 'event_level_process_temperature_adjustment_shift.parquet'}`",
        f"- Stage summary: `{args.output_dir / 'stage_process_shift_summary.csv'}`",
        f"- Relationship summary: `{args.output_dir / 'stage_elevation_relationship_summary.csv'}`",
        f"- Bin summary: `{args.output_dir / 'elevation_mismatch_bin_summary.csv'}`",
        f"- Hybrid branch summary: `{args.output_dir / 'hybrid_branch_shift_summary.csv'}`",
    ]
    args.output_dir.joinpath("REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    process = process_shift_table(args)
    hybrid = hybrid_shift_table(args, process)
    stage_summary = stage_distribution_summary(process)
    relationship = relationship_summary(process)
    country = country_stage_summary(process)
    bins = elevation_bin_summary(process)
    hybrid_stage = hybrid_summary(hybrid)

    process.to_parquet(
        args.output_dir / "event_level_process_temperature_adjustment_shift.parquet",
        index=False,
    )
    process.to_csv(
        args.output_dir / "event_level_process_temperature_adjustment_shift.csv",
        index=False,
    )
    hybrid.to_parquet(
        args.output_dir / "event_level_hybrid_temperature_branch_shift.parquet",
        index=False,
    )
    stage_summary.to_csv(args.output_dir / "stage_process_shift_summary.csv", index=False)
    relationship.to_csv(args.output_dir / "stage_elevation_relationship_summary.csv", index=False)
    country.to_csv(args.output_dir / "country_stage_process_shift_summary.csv", index=False)
    bins.to_csv(args.output_dir / "elevation_mismatch_bin_summary.csv", index=False)
    hybrid_stage.to_csv(args.output_dir / "hybrid_branch_shift_summary.csv", index=False)
    audit = {
        "scope": "terrain temperature adjustment and phenology shift quantification",
        "baseline_dir": str(args.baseline_dir),
        "reference_sample_dir": str(args.reference_sample_dir),
        "adjusted_fixed_dir": str(args.adjusted_fixed_dir),
        "raw_fixed_dir": str(args.raw_fixed_dir),
        "lapse_rate_c_per_km": args.lapse_rate_c_per_km,
        "process_shift_definition": "adjusted_process_predicted_doy - raw_process_predicted_doy",
        "temperature_adjustment_definition": "-lapse_rate_c_per_km * site_minus_grid_elevation_m / 1000",
        "calibration_caveat": (
            "Raw and adjusted process branches use branch-specific thresholds calibrated "
            "inside training folds; process shifts are branch-level prediction shifts, not "
            "same-threshold physical counterfactuals."
        ),
        "process_rows": int(len(process)),
        "hybrid_rows": int(len(hybrid)),
        "output_dir": str(args.output_dir),
        "report_path": str(args.report_path),
    }
    (args.output_dir / "run_summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(args, stage_summary, relationship, bins, hybrid_stage, country)
    print("\nTerrain-temperature phenology-shift quantification completed")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print("\nStage process-shift summary")
    print(stage_summary.round(3).to_string(index=False))
    print("\nElevation relationship summary")
    print(relationship.round(3).to_string(index=False))
    print("\nHybrid branch-shift summary")
    print(hybrid_stage.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
