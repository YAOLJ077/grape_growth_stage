#!/usr/bin/env python
"""Evaluate fixed stage-level residual hybrid models with inner-RMSE tuning."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

try:
    from src.modeling.build_residual_ml_dataset import REPO_ROOT
    from src.modeling.run_residual_ml_models import (
        COMPLEXITY_ORDER,
        SELECTION_CANDIDATES,
        aggregate_outer_metrics,
        config_id,
        evaluate_config_inner,
        fit_full_and_predict,
        fold_summary,
        parameter_candidates,
        prediction_metrics,
        residual_to_doy,
        validate_inputs,
    )
except ModuleNotFoundError:
    from build_residual_ml_dataset import REPO_ROOT  # type: ignore
    from run_residual_ml_models import (  # type: ignore
        COMPLEXITY_ORDER,
        SELECTION_CANDIDATES,
        aggregate_outer_metrics,
        config_id,
        evaluate_config_inner,
        fit_full_and_predict,
        fold_summary,
        parameter_candidates,
        prediction_metrics,
        residual_to_doy,
        validate_inputs,
    )


DEFAULT_DATA_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_machine_learning_main_final"
)
DEFAULT_SELECTION_SOURCE_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_modeling/main_final_minrmse_four_stage"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_modeling/main_final_fixed_stage_models_refit"
)
DEFAULT_REPORT_PATH = REPO_ROOT / "results/report/main_final_fixed_stage_hybrid_results.md"
STAGES = ("budburst", "flowering", "veraison", "maturity_or_harvest")
PROCESS_MODEL_LABELS = {
    "budburst": "BRIN-Aug1",
    "flowering": "adjusted GFV",
    "veraison": "adjusted GFV",
    "maturity_or_harvest": "predicted-veraison GDD10",
}
RAW_PROCESS_MODEL_LABELS = {
    "budburst": "raw BRIN-Aug1",
    "flowering": "raw GFV",
    "veraison": "raw GFV",
    "maturity_or_harvest": "raw predicted-veraison GDD10",
}
STAGE_LABELS = {
    "budburst": "BBCH07 萌芽",
    "flowering": "BBCH65 开花",
    "veraison": "BBCH81 转色",
    "maturity_or_harvest": "BBCH89 成熟/采收",
}


def parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--selection-source-dir", type=Path, default=DEFAULT_SELECTION_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--stage-algorithm-rule",
        choices=["min_rmse", "one_se_min_complexity"],
        default="min_rmse",
        help=(
            "Rule for fixing one residual algorithm per stage. "
            "min_rmse uses the lowest stage-level mean inner RMSE; "
            "one_se_min_complexity keeps the previous one-SE complexity rule."
        ),
    )
    parser.add_argument("--outer-folds", type=parse_int_list, default=[1, 2, 3, 4, 5])
    parser.add_argument("--search-level", choices=["smoke", "formal"], default="formal")
    parser.add_argument("--n-jobs", type=int, default=4)
    parser.add_argument("--random-state", type=int, default=20260805)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def summarize_inner_search_for_algorithm_selection(selection_source_dir: Path) -> pd.DataFrame:
    search = pd.read_csv(selection_source_dir / "inner_parameter_search_metrics.csv")
    inner_best = pd.read_csv(selection_source_dir / "inner_best_algorithm_summary.csv")
    rows = []
    for _, row in inner_best.loc[inner_best["algorithm"].eq("mechanistic")].iterrows():
        rows.append(
            {
                "stage": row["stage"],
                "outer_fold": int(row["outer_fold"]),
                "algorithm": "mechanistic",
                "config_id": "mechanistic",
                "config_json": "{}",
                "mean_mae_days": float(row["mean_mae_days"]),
                "mean_rmse_days": float(row["mean_rmse_days"]),
                "mean_abs_bias_days": abs(float(row["pooled_bias_days"])),
            }
        )
    for keys, group in search.groupby(
        ["stage", "outer_fold", "algorithm", "config_id", "config_json"],
        sort=False,
    ):
        stage, outer_fold, algorithm, config_identifier, config_json = keys
        rows.append(
            {
                "stage": stage,
                "outer_fold": int(outer_fold),
                "algorithm": algorithm,
                "config_id": config_identifier,
                "config_json": config_json,
                "mean_mae_days": float(group["mae_days"].mean()),
                "mean_rmse_days": float(group["rmse_days"].mean()),
                "mean_abs_bias_days": float(group["bias_days"].abs().mean()),
            }
        )
    candidates = pd.DataFrame(rows)
    return (
        candidates.sort_values(
            [
                "stage",
                "outer_fold",
                "algorithm",
                "mean_rmse_days",
                "mean_mae_days",
                "mean_abs_bias_days",
            ]
        )
        .groupby(["stage", "outer_fold", "algorithm"], sort=False)
        .head(1)
        .reset_index(drop=True)
    )


def stage_level_algorithm_summary(best_per_outer: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (stage, algorithm), group in best_per_outer.groupby(["stage", "algorithm"], sort=False):
        n_outer = int(group["outer_fold"].nunique())
        rows.append(
            {
                "stage": stage,
                "algorithm": algorithm,
                "n_outer_folds": n_outer,
                "mean_inner_mae_days": float(group["mean_mae_days"].mean()),
                "mean_inner_rmse_days": float(group["mean_rmse_days"].mean()),
                "sd_inner_rmse_days": float(group["mean_rmse_days"].std(ddof=1)),
                "se_inner_rmse_days": float(group["mean_rmse_days"].std(ddof=1) / math.sqrt(n_outer)),
                "mean_abs_inner_bias_days": float(group["mean_abs_bias_days"].mean()),
                "complexity_rank": int(COMPLEXITY_ORDER[algorithm]),
            }
        )
    return pd.DataFrame(rows)


def process_model_labels_for_data(data_dir: Path) -> dict[str, str]:
    summary_path = data_dir / "run_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("process_temperature_branch") == "raw":
            return RAW_PROCESS_MODEL_LABELS
    return PROCESS_MODEL_LABELS


def select_fixed_stage_algorithms(
    summary: pd.DataFrame,
    process_labels: dict[str, str] | None = None,
    stage_algorithm_rule: str = "min_rmse",
) -> pd.DataFrame:
    if process_labels is None:
        process_labels = PROCESS_MODEL_LABELS
    rows = []
    for stage, group in summary.groupby("stage", sort=False):
        group = group.loc[group["algorithm"].isin(SELECTION_CANDIDATES)].copy()
        best = group.sort_values(
            [
                "mean_inner_rmse_days",
                "mean_inner_mae_days",
                "mean_abs_inner_bias_days",
                "complexity_rank",
            ]
        ).iloc[0]
        cutoff = float(best["mean_inner_rmse_days"] + best["se_inner_rmse_days"])
        if stage_algorithm_rule == "min_rmse":
            selected = best
            used_one_se_cutoff = False
        elif stage_algorithm_rule == "one_se_min_complexity":
            eligible = group.loc[group["mean_inner_rmse_days"].le(cutoff)].copy()
            selected = eligible.sort_values(
                [
                    "complexity_rank",
                    "mean_inner_rmse_days",
                    "mean_inner_mae_days",
                    "mean_abs_inner_bias_days",
                ]
            ).iloc[0]
            used_one_se_cutoff = True
        else:
            raise ValueError(f"Unknown stage algorithm rule: {stage_algorithm_rule}")
        rows.append(
            {
                "stage": stage,
                "process_model": process_labels[stage],
                "stage_algorithm_rule": stage_algorithm_rule,
                "best_inner_rmse_algorithm": best["algorithm"],
                "best_mean_inner_rmse_days": float(best["mean_inner_rmse_days"]),
                "best_se_inner_rmse_days": float(best["se_inner_rmse_days"]),
                "one_se_cutoff_rmse_days": cutoff if used_one_se_cutoff else np.nan,
                "used_one_se_cutoff": used_one_se_cutoff,
                "fixed_residual_algorithm": selected["algorithm"],
                "fixed_mean_inner_rmse_days": float(selected["mean_inner_rmse_days"]),
                "fixed_mean_inner_mae_days": float(selected["mean_inner_mae_days"]),
                "fixed_mean_abs_inner_bias_days": float(selected["mean_abs_inner_bias_days"]),
                "fixed_complexity_rank": int(selected["complexity_rank"]),
            }
        )
    order = {stage: index for index, stage in enumerate(STAGES)}
    result = pd.DataFrame(rows)
    result["stage_order"] = result["stage"].map(order)
    return result.sort_values("stage_order").drop(columns="stage_order").reset_index(drop=True)


def feature_sets(data_dir: Path) -> dict[str, list[str]]:
    manifest = pd.read_csv(data_dir / "residual_ml_feature_sets.csv")
    return {
        stage: (
            manifest.loc[manifest["stage"].eq(stage)]
            .sort_values("feature_order")["feature"]
            .tolist()
        )
        for stage in STAGES
    }


def select_config_by_inner_rmse(
    train: pd.DataFrame,
    features: list[str],
    algorithm: str,
    configs: list[dict[str, object]],
    n_jobs: int,
    random_state: int,
) -> tuple[dict[str, object], str, pd.DataFrame]:
    rows = []
    for index, config in enumerate(configs):
        identifier = config_id(algorithm, index)
        _, metrics = evaluate_config_inner(train, features, algorithm, config, n_jobs, random_state)
        summary = fold_summary(metrics)
        rows.append(
            {
                "algorithm": algorithm,
                "config_id": identifier,
                "config_json": json.dumps(config, sort_keys=True),
                **summary,
            }
        )
    table = pd.DataFrame(rows)
    selected = table.sort_values(
        [
            "mean_rmse_days",
            "mean_mae_days",
            "pooled_bias_days",
            "config_id",
        ]
    ).iloc[0]
    return json.loads(str(selected["config_json"])), str(selected["config_id"]), table


def evaluate_fixed_models(args: argparse.Namespace, fixed_selection: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    features_by_stage = feature_sets(args.data_dir)
    candidates = parameter_candidates(args.search_level)
    prediction_tables = []
    outer_rows = []
    config_rows = []
    tasks = [(stage, fold) for stage in STAGES for fold in args.outer_folds]
    fixed_algorithm_by_stage = fixed_selection.set_index("stage")["fixed_residual_algorithm"].to_dict()
    for stage, outer_fold in tqdm(tasks, desc="Fixed stage hybrid evaluation", unit="task"):
        algorithm = fixed_algorithm_by_stage[stage]
        features = features_by_stage[stage]
        table = pd.read_parquet(args.data_dir / "training_ready" / f"{stage}_residual_ml.parquet")
        train, test = validate_inputs(table, features, stage, outer_fold)
        if algorithm == "mechanistic":
            selected_config = None
            selected_config_id = "mechanistic"
            config_table = pd.DataFrame()
        else:
            selected_config, selected_config_id, config_table = select_config_by_inner_rmse(
                train,
                features,
                algorithm,
                candidates[algorithm],
                args.n_jobs,
                args.random_state + outer_fold * 100,
            )
            config_table.insert(0, "outer_fold", outer_fold)
            config_table.insert(0, "stage", stage)
            config_rows.extend(config_table.to_dict("records"))
        predicted_residual = fit_full_and_predict(
            train,
            test,
            features,
            algorithm,
            selected_config,
            args.n_jobs,
            args.random_state + outer_fold * 10000,
        )
        predicted_doy = residual_to_doy(test, predicted_residual)
        metric = prediction_metrics(test["observed_doy"].to_numpy(float), predicted_doy)
        outer_rows.append(
            {
                "stage": stage,
                "outer_fold": outer_fold,
                "algorithm": algorithm,
                "selected_config_id": selected_config_id,
                "selected_config_json": json.dumps(selected_config or {}, sort_keys=True),
                "n_features": len(features),
                **metric,
            }
        )
        prediction_tables.append(
            pd.DataFrame(
                {
                    "stage": stage,
                    "outer_fold": outer_fold,
                    "algorithm": algorithm,
                    "record_id": test["record_id"].to_numpy(),
                    "site_uid": test["site_uid"].to_numpy(),
                    "observed_doy": test["observed_doy"].to_numpy(float),
                    "mechanistic_predicted_doy": test["mechanistic_predicted_doy"].to_numpy(float),
                    "predicted_residual_days": predicted_residual,
                    "hybrid_predicted_doy": predicted_doy,
                }
            )
        )
    predictions = pd.concat(prediction_tables, ignore_index=True)
    outer_metrics = pd.DataFrame(outer_rows)
    config_metrics = pd.DataFrame(config_rows)
    return predictions, outer_metrics, config_metrics


def process_metrics(selection_source_dir: Path) -> pd.DataFrame:
    aggregate = pd.read_csv(selection_source_dir / "aggregate_outer_metrics.csv")
    return aggregate.loc[aggregate["algorithm"].eq("mechanistic")].copy()


def write_report(
    report_path: Path,
    output_dir: Path,
    fixed_selection: pd.DataFrame,
    fixed_metrics: pd.DataFrame,
    process: pd.DataFrame,
    elapsed_seconds: float,
    stage_algorithm_rule: str,
) -> None:
    comparison = fixed_metrics.merge(
        process[
            [
                "stage",
                "mae_days",
                "rmse_days",
                "bias_days",
                "within_7d_pct",
            ]
        ].rename(
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
        fixed_selection[["stage", "process_model"]],
        on="stage",
        how="left",
    )
    comparison["mae_gain_days"] = comparison["process_mae_days"] - comparison["mae_days"]
    comparison["rmse_gain_days"] = comparison["process_rmse_days"] - comparison["rmse_days"]
    comparison["stage_label"] = comparison["stage"].map(STAGE_LABELS)
    comparison["stage_order"] = comparison["stage"].map({stage: index for index, stage in enumerate(STAGES)})
    comparison = comparison.sort_values("stage_order")
    display = comparison[
        [
            "stage_label",
            "process_model",
            "algorithm",
            "n_features",
            "n",
            "process_mae_days",
            "mae_days",
            "mae_gain_days",
            "process_rmse_days",
            "rmse_days",
            "rmse_gain_days",
            "bias_days",
            "within_7d_pct",
        ]
    ].rename(
        columns={
            "stage_label": "阶段",
            "process_model": "过程模型",
            "algorithm": "固定残差算法",
            "n_features": "特征数",
            "n": "n",
            "process_mae_days": "过程MAE",
            "mae_days": "固定混合MAE",
            "mae_gain_days": "MAE增益(d)",
            "process_rmse_days": "过程RMSE",
            "rmse_days": "固定混合RMSE",
            "rmse_gain_days": "RMSE增益(d)",
            "bias_days": "固定混合Bias",
            "within_7d_pct": "固定混合≤7d(%)",
        }
    )
    selection_display = fixed_selection.copy()
    selection_display["阶段"] = selection_display["stage"].map(STAGE_LABELS)
    if stage_algorithm_rule == "min_rmse":
        selection_display = selection_display[
            [
                "阶段",
                "process_model",
                "best_inner_rmse_algorithm",
                "best_mean_inner_rmse_days",
                "fixed_residual_algorithm",
                "fixed_mean_inner_rmse_days",
                "fixed_mean_inner_mae_days",
                "fixed_mean_abs_inner_bias_days",
            ]
        ].rename(
            columns={
                "process_model": "过程模型",
                "best_inner_rmse_algorithm": "内层RMSE最优算法",
                "best_mean_inner_rmse_days": "最优内层RMSE",
                "fixed_residual_algorithm": "固定残差算法",
                "fixed_mean_inner_rmse_days": "固定算法内层RMSE",
                "fixed_mean_inner_mae_days": "固定算法内层MAE",
                "fixed_mean_abs_inner_bias_days": "固定算法内层AbsBias",
            }
        )
        rule_lines = [
            "- 对每个阶段，先用既有全算法内层搜索结果为各算法选择内层平均RMSE最低的候选配置。",
            "- 在阶段层面，对各算法跨五个外层训练区的最佳内层RMSE取平均，并选择平均内层RMSE最低的算法。",
            "- MAE、绝对偏差和模型复杂度只在RMSE数值并列或近似并列时作为次级判据；不使用统计放宽阈值。",
            "- 固定算法确定后，每个外层训练区仅在该固定算法内部按内层RMSE重新选择超参数，再评价外层空间测试区。",
        ]
    else:
        selection_display = selection_display[
            [
                "阶段",
                "process_model",
                "best_inner_rmse_algorithm",
                "best_mean_inner_rmse_days",
                "best_se_inner_rmse_days",
                "one_se_cutoff_rmse_days",
                "fixed_residual_algorithm",
                "fixed_mean_inner_rmse_days",
                "fixed_mean_inner_mae_days",
            ]
        ].rename(
            columns={
                "process_model": "过程模型",
                "best_inner_rmse_algorithm": "内层RMSE最优算法",
                "best_mean_inner_rmse_days": "最优内层RMSE",
                "best_se_inner_rmse_days": "最优RMSE_SE",
                "one_se_cutoff_rmse_days": "one-SE阈值",
                "fixed_residual_algorithm": "固定残差算法",
                "fixed_mean_inner_rmse_days": "固定算法内层RMSE",
                "fixed_mean_inner_mae_days": "固定算法内层MAE",
            }
        )
        rule_lines = [
            "- 对每个阶段，先用既有全算法内层搜索结果为各算法选择内层平均RMSE最低的候选配置。",
            "- 计算阶段级平均内层RMSE，并以最优算法的 `mean RMSE + SE` 作为one-SE阈值。",
            "- 在one-SE范围内选择复杂度最低的算法，复杂度顺序为 `mechanistic < ridge < gam < rf < xgboost < lightgbm`。",
            "- 固定算法确定后，每个外层训练区仅在该固定算法内部按内层RMSE重新选择超参数，再评价外层空间测试区。",
        ]
    lines = [
        "# 固定阶段混合模型最终主结果",
        "",
        "该结果使用阶段级固定算法，而不是逐外层折动态选择算法。固定算法由训练区内层空间CV确定；外层空间测试只用于最终评价。",
        "",
        "残差定义：`residual_days = observed_doy - mechanistic_predicted_doy`；正残差表示过程模型预测偏早。",
        "",
        "## 1. 最终固定组合表现",
        "",
        display.round(3).to_markdown(index=False),
        "",
        "## 2. 固定算法选择证据",
        "",
        selection_display.round(3).to_markdown(index=False),
        "",
        "## 3. 固定规则",
        "",
        *rule_lines,
        "",
        f"Output directory: `{output_dir}`",
        f"Elapsed minutes: {elapsed_seconds / 60.0:.2f}",
    ]
    output_dir.joinpath("REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    if args.output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"Output exists: {args.output_dir}; use --overwrite")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()

    best_per_outer = summarize_inner_search_for_algorithm_selection(args.selection_source_dir)
    stage_summary = stage_level_algorithm_summary(best_per_outer)
    fixed_selection = select_fixed_stage_algorithms(
        stage_summary,
        process_model_labels_for_data(args.data_dir),
        args.stage_algorithm_rule,
    )
    predictions, outer_metrics, config_metrics = evaluate_fixed_models(args, fixed_selection)
    fixed_metrics = aggregate_outer_metrics(predictions)
    n_features = outer_metrics.groupby(["stage", "algorithm"])["n_features"].first().reset_index()
    fixed_metrics = fixed_metrics.merge(n_features, on=["stage", "algorithm"], how="left")
    process = process_metrics(args.selection_source_dir)
    elapsed = time.perf_counter() - start
    if args.stage_algorithm_rule == "min_rmse":
        selection_rule_description = (
            "stage-level minimum mean inner spatial-CV RMSE for algorithm fixation; "
            "inner spatial-CV RMSE for hyperparameter tuning within fixed algorithm"
        )
    else:
        selection_rule_description = (
            "stage-level inner spatial-CV one-SE on RMSE for algorithm fixation; "
            "inner spatial-CV RMSE for hyperparameter tuning within fixed algorithm"
        )

    best_per_outer.to_csv(args.output_dir / "algorithm_best_config_by_outer_fold.csv", index=False)
    stage_summary.to_csv(args.output_dir / "stage_level_inner_algorithm_summary.csv", index=False)
    fixed_selection_output = fixed_selection.copy()
    if args.stage_algorithm_rule == "min_rmse":
        fixed_selection_output = fixed_selection_output.drop(
            columns=["one_se_cutoff_rmse_days", "used_one_se_cutoff"]
        )
    fixed_selection_output.to_csv(args.output_dir / "fixed_stage_algorithm_selection.csv", index=False)
    if not config_metrics.empty:
        config_metrics.to_csv(args.output_dir / "fixed_algorithm_inner_config_metrics.csv", index=False)
    outer_metrics.to_csv(args.output_dir / "fixed_stage_outer_fold_metrics.csv", index=False)
    predictions.to_parquet(args.output_dir / "fixed_stage_outer_predictions.parquet", index=False)
    fixed_metrics.to_csv(args.output_dir / "fixed_stage_aggregate_metrics.csv", index=False)
    process.to_csv(args.output_dir / "process_baseline_metrics.csv", index=False)
    audit = {
        "scope": "fixed stage-level hybrid model evaluation with inner-RMSE hyperparameter tuning",
        "data_dir": str(args.data_dir),
        "selection_source_dir": str(args.selection_source_dir),
        "residual_definition": "observed_doy - mechanistic_predicted_doy",
        "fixed_algorithms": fixed_selection.set_index("stage")[
            "fixed_residual_algorithm"
        ].to_dict(),
        "selection_rule": args.stage_algorithm_rule,
        "selection_rule_description": selection_rule_description,
        "complexity_order": COMPLEXITY_ORDER,
        "test_targets_used_for_algorithm_or_hyperparameter_selection": False,
        "n_jobs": args.n_jobs,
        "random_state": args.random_state,
        "elapsed_seconds": elapsed,
        "output_dir": str(args.output_dir),
        "report_path": str(args.report_path),
    }
    (args.output_dir / "run_summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(
        args.report_path,
        args.output_dir,
        fixed_selection,
        fixed_metrics,
        process,
        elapsed,
        args.stage_algorithm_rule,
    )

    print("\nFixed stage hybrid evaluation completed")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print("\nFixed stage aggregate metrics")
    print(fixed_metrics.round(3).to_string(index=False))
    print("\nFixed stage algorithm selection")
    print(fixed_selection.round(3).to_string(index=False))
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
