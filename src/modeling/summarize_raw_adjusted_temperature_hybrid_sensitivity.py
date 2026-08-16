#!/usr/bin/env python
"""Summarize raw-vs-adjusted temperature residual-hybrid sensitivity results."""

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

try:
    from src.modeling.run_residual_ml_models import prediction_metrics
except ModuleNotFoundError:
    from run_residual_ml_models import prediction_metrics  # type: ignore


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
DEFAULT_RAW_DATA_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_machine_learning_raw_temperature_doyrange21_postflower_water_spatial_ablation_pruned"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/temperature_branch_sensitivity/raw_vs_adjusted_hybrid"
)
DEFAULT_REPORT_PATH = REPO_ROOT / "results/report/raw_vs_adjusted_temperature_hybrid_sensitivity.md"
STAGES = ("budburst", "flowering", "veraison", "maturity_or_harvest")
STAGE_LABELS = {
    "budburst": "BBCH07 萌芽",
    "flowering": "BBCH65 开花",
    "veraison": "BBCH81 转色",
    "maturity_or_harvest": "BBCH89 成熟/采收",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adjusted-fixed-dir", type=Path, default=DEFAULT_ADJUSTED_FIXED_DIR)
    parser.add_argument("--raw-fixed-dir", type=Path, default=DEFAULT_RAW_FIXED_DIR)
    parser.add_argument("--raw-data-dir", type=Path, default=DEFAULT_RAW_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args()


def branch_predictions(path: Path, branch: str) -> pd.DataFrame:
    predictions = pd.read_parquet(path / "fixed_stage_outer_predictions.parquet").copy()
    predictions = predictions.rename(
        columns={
            "mechanistic_predicted_doy": f"{branch}_process_predicted_doy",
            "hybrid_predicted_doy": f"{branch}_hybrid_predicted_doy",
            "predicted_residual_days": f"{branch}_predicted_residual_days",
            "algorithm": f"{branch}_algorithm",
            "observed_doy": f"{branch}_observed_doy",
        }
    )
    keep = [
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
    return predictions[keep]


def metrics_for(group: pd.DataFrame, observed_column: str, predicted_column: str) -> dict[str, float]:
    return prediction_metrics(
        group[observed_column].to_numpy(float),
        group[predicted_column].to_numpy(float),
    )


def common_sample_metrics(adjusted_dir: Path, raw_dir: Path) -> pd.DataFrame:
    adjusted = branch_predictions(adjusted_dir, "adjusted")
    raw = branch_predictions(raw_dir, "raw")
    common = adjusted.merge(
        raw,
        on=["stage", "outer_fold", "record_id", "site_uid"],
        how="inner",
        validate="one_to_one",
    )
    if not np.allclose(common["adjusted_observed_doy"], common["raw_observed_doy"]):
        raise ValueError("Adjusted and raw common-sample observations do not match")
    rows = []
    for stage, group in common.groupby("stage", sort=False):
        adjusted_process = metrics_for(group, "adjusted_observed_doy", "adjusted_process_predicted_doy")
        raw_process = metrics_for(group, "adjusted_observed_doy", "raw_process_predicted_doy")
        adjusted_hybrid = metrics_for(group, "adjusted_observed_doy", "adjusted_hybrid_predicted_doy")
        raw_hybrid = metrics_for(group, "adjusted_observed_doy", "raw_hybrid_predicted_doy")
        rows.append(
            {
                "stage": stage,
                "stage_label": STAGE_LABELS[stage],
                "n_common": int(len(group)),
                "adjusted_algorithm": str(group["adjusted_algorithm"].iloc[0]),
                "raw_algorithm": str(group["raw_algorithm"].iloc[0]),
                "adjusted_process_mae_days": adjusted_process["mae_days"],
                "raw_process_mae_days": raw_process["mae_days"],
                "process_adjusted_gain_mae_days": raw_process["mae_days"] - adjusted_process["mae_days"],
                "adjusted_process_rmse_days": adjusted_process["rmse_days"],
                "raw_process_rmse_days": raw_process["rmse_days"],
                "process_adjusted_gain_rmse_days": raw_process["rmse_days"] - adjusted_process["rmse_days"],
                "adjusted_hybrid_mae_days": adjusted_hybrid["mae_days"],
                "raw_hybrid_mae_days": raw_hybrid["mae_days"],
                "hybrid_adjusted_gain_mae_days": raw_hybrid["mae_days"] - adjusted_hybrid["mae_days"],
                "adjusted_hybrid_rmse_days": adjusted_hybrid["rmse_days"],
                "raw_hybrid_rmse_days": raw_hybrid["rmse_days"],
                "hybrid_adjusted_gain_rmse_days": raw_hybrid["rmse_days"] - adjusted_hybrid["rmse_days"],
                "adjusted_hybrid_within_7d_pct": adjusted_hybrid["within_7d_pct"],
                "raw_hybrid_within_7d_pct": raw_hybrid["within_7d_pct"],
                "hybrid_adjusted_gain_within_7d_pct": (
                    adjusted_hybrid["within_7d_pct"] - raw_hybrid["within_7d_pct"]
                ),
            }
        )
    order = {stage: index for index, stage in enumerate(STAGES)}
    result = pd.DataFrame(rows)
    result["stage_order"] = result["stage"].map(order)
    return result.sort_values("stage_order").drop(columns="stage_order").reset_index(drop=True)


def native_branch_table(adjusted_dir: Path, raw_dir: Path) -> pd.DataFrame:
    rows = []
    for branch, directory in (("adjusted", adjusted_dir), ("raw", raw_dir)):
        fixed = pd.read_csv(directory / "fixed_stage_aggregate_metrics.csv")
        process = pd.read_csv(directory / "process_baseline_metrics.csv")
        selection = pd.read_csv(directory / "fixed_stage_algorithm_selection.csv")
        merged = fixed.merge(
            process[["stage", "mae_days", "rmse_days", "bias_days", "within_7d_pct"]].rename(
                columns={
                    "mae_days": "process_mae_days",
                    "rmse_days": "process_rmse_days",
                    "bias_days": "process_bias_days",
                    "within_7d_pct": "process_within_7d_pct",
                }
            ),
            on="stage",
            how="left",
        ).merge(
            selection[["stage", "process_model", "fixed_residual_algorithm"]],
            on="stage",
            how="left",
        )
        for _, row in merged.iterrows():
            rows.append(
                {
                    "temperature_branch": branch,
                    "stage": row["stage"],
                    "stage_label": STAGE_LABELS[row["stage"]],
                    "process_model": row["process_model"],
                    "fixed_residual_algorithm": row["fixed_residual_algorithm"],
                    "n": int(row["n"]),
                    "n_features": int(row["n_features"]),
                    "process_mae_days": float(row["process_mae_days"]),
                    "hybrid_mae_days": float(row["mae_days"]),
                    "mae_gain_days": float(row["process_mae_days"] - row["mae_days"]),
                    "process_rmse_days": float(row["process_rmse_days"]),
                    "hybrid_rmse_days": float(row["rmse_days"]),
                    "rmse_gain_days": float(row["process_rmse_days"] - row["rmse_days"]),
                    "hybrid_bias_days": float(row["bias_days"]),
                    "hybrid_within_7d_pct": float(row["within_7d_pct"]),
                }
            )
    order = {stage: index for index, stage in enumerate(STAGES)}
    result = pd.DataFrame(rows)
    result["stage_order"] = result["stage"].map(order)
    return (
        result.sort_values(["stage_order", "temperature_branch"])
        .drop(columns="stage_order")
        .reset_index(drop=True)
    )


def raw_sample_audit(raw_data_dir: Path) -> pd.DataFrame:
    summary_path = raw_data_dir / "run_summary.json"
    if not summary_path.exists():
        return pd.DataFrame()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return pd.DataFrame(summary.get("reference_sample_filter_by_stage", []))


def write_report(
    report_path: Path,
    output_dir: Path,
    common: pd.DataFrame,
    native: pd.DataFrame,
    sample_audit: pd.DataFrame,
) -> None:
    common_display = common[
        [
            "stage_label",
            "n_common",
            "adjusted_algorithm",
            "raw_algorithm",
            "adjusted_process_mae_days",
            "raw_process_mae_days",
            "process_adjusted_gain_mae_days",
            "adjusted_hybrid_mae_days",
            "raw_hybrid_mae_days",
            "hybrid_adjusted_gain_mae_days",
            "adjusted_process_rmse_days",
            "raw_process_rmse_days",
            "process_adjusted_gain_rmse_days",
            "adjusted_hybrid_rmse_days",
            "raw_hybrid_rmse_days",
            "hybrid_adjusted_gain_rmse_days",
        ]
    ].rename(
        columns={
            "stage_label": "阶段",
            "n_common": "共同n",
            "adjusted_algorithm": "adjusted算法",
            "raw_algorithm": "raw算法",
            "adjusted_process_mae_days": "adjusted过程MAE",
            "raw_process_mae_days": "raw过程MAE",
            "process_adjusted_gain_mae_days": "过程MAE调整增益",
            "adjusted_hybrid_mae_days": "adjusted混合MAE",
            "raw_hybrid_mae_days": "raw混合MAE",
            "hybrid_adjusted_gain_mae_days": "混合MAE调整增益",
            "adjusted_process_rmse_days": "adjusted过程RMSE",
            "raw_process_rmse_days": "raw过程RMSE",
            "process_adjusted_gain_rmse_days": "过程RMSE调整增益",
            "adjusted_hybrid_rmse_days": "adjusted混合RMSE",
            "raw_hybrid_rmse_days": "raw混合RMSE",
            "hybrid_adjusted_gain_rmse_days": "混合RMSE调整增益",
        }
    )
    native_display = native[
        [
            "temperature_branch",
            "stage_label",
            "process_model",
            "fixed_residual_algorithm",
            "n",
            "n_features",
            "process_mae_days",
            "hybrid_mae_days",
            "mae_gain_days",
            "process_rmse_days",
            "hybrid_rmse_days",
            "rmse_gain_days",
            "hybrid_bias_days",
            "hybrid_within_7d_pct",
        ]
    ].rename(
        columns={
            "temperature_branch": "温度分支",
            "stage_label": "阶段",
            "process_model": "过程模型",
            "fixed_residual_algorithm": "固定残差算法",
            "n": "n",
            "n_features": "特征数",
            "process_mae_days": "过程MAE",
            "hybrid_mae_days": "混合MAE",
            "mae_gain_days": "MAE增益",
            "process_rmse_days": "过程RMSE",
            "hybrid_rmse_days": "混合RMSE",
            "rmse_gain_days": "RMSE增益",
            "hybrid_bias_days": "混合Bias",
            "hybrid_within_7d_pct": "混合≤7d(%)",
        }
    )
    lines = [
        "# Raw vs adjusted temperature residual-hybrid sensitivity",
        "",
        "严格比较表使用 raw 与 adjusted 两个固定混合模型都能给出预测的共同空间测试样本。正的“调整增益”表示 adjusted 温度分支误差更低。",
        "",
        "## 1. 共同样本 raw-vs-adjusted 对比",
        "",
        common_display.round(3).to_markdown(index=False),
        "",
        "## 2. 各温度分支原生固定混合表现",
        "",
        native_display.round(3).to_markdown(index=False),
        "",
        "## 3. 样本边界审计",
        "",
    ]
    if sample_audit.empty:
        lines.append("未记录 reference sample filter。")
    else:
        lines.append(sample_audit.to_markdown(index=False))
    lines.extend(
        [
            "",
            "## 4. 规则说明",
            "",
            "- 两个分支使用相同空间折、相同阶段过程模型结构、相同残差定义、相同特征 profile、相同 RMSE 主导固定算法规则。",
            "- raw 分支过程模型使用 raw temperature branch；raw 特征窗口内温度、VPD、ET0 均由 raw Tmean/Tmin/Tmax 计算。",
            "- raw 分支特征列名保留主分析 schema 中的 adjusted/gdd 命名，只是数值改为 raw，以保证建模脚本完全可复用。",
            "- BBCH81 样本边界以当前主分析 residual dataset 为 reference，避免 raw 分支重新纳入主分析已排除的极端噪声记录。",
            "",
            f"Output directory: `{output_dir}`",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    common = common_sample_metrics(args.adjusted_fixed_dir, args.raw_fixed_dir)
    native = native_branch_table(args.adjusted_fixed_dir, args.raw_fixed_dir)
    sample_audit = raw_sample_audit(args.raw_data_dir)
    common.to_csv(args.output_dir / "common_sample_raw_vs_adjusted_metrics.csv", index=False)
    native.to_csv(args.output_dir / "native_branch_fixed_hybrid_metrics.csv", index=False)
    if not sample_audit.empty:
        sample_audit.to_csv(args.output_dir / "raw_reference_sample_filter_audit.csv", index=False)
    write_report(args.report_path, args.output_dir, common, native, sample_audit)
    print("\nRaw-vs-adjusted temperature sensitivity completed")
    print(f"Report: {args.report_path}")
    print("\nCommon-sample raw-vs-adjusted metrics")
    print(common.round(3).to_string(index=False))
    print("\nNative branch fixed-hybrid metrics")
    print(native.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
