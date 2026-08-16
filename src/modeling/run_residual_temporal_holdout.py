#!/usr/bin/env python
"""Supplementary temporal holdout for fixed residual hybrid models."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

for variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ[variable] = "1"

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

try:
    from src.modeling.build_residual_ml_dataset import REPO_ROOT
    from src.modeling.run_fixed_stage_hybrid_models import (
        PROCESS_MODEL_LABELS,
        STAGE_LABELS,
        STAGES,
        feature_sets,
    )
    from src.modeling.run_residual_ml_models import (
        build_estimator,
        config_id,
        parameter_candidates,
        prediction_metrics,
        residual_to_doy,
    )
except ModuleNotFoundError:
    from build_residual_ml_dataset import REPO_ROOT  # type: ignore
    from run_fixed_stage_hybrid_models import (  # type: ignore
        PROCESS_MODEL_LABELS,
        STAGE_LABELS,
        STAGES,
        feature_sets,
    )
    from run_residual_ml_models import (  # type: ignore
        build_estimator,
        config_id,
        parameter_candidates,
        prediction_metrics,
        residual_to_doy,
    )


DEFAULT_DATA_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_machine_learning_doyrange21_postflower_water_spatial_ablation_pruned"
)
DEFAULT_FIXED_SELECTION = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_modeling/doyrange21_postflower_water_spatial_ablation_pruned_fixed_stage_models_refit/"
    "fixed_stage_algorithm_selection.csv"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_temporal_holdout/doyrange21_postflower_water_spatial_ablation_pruned_fixed_stage_cutoff2015"
)
DEFAULT_REPORT_PATH = REPO_ROOT / "results/report/temporal_holdout_fixed_hybrid_summary.md"
FALLBACK_FIXED_ALGORITHMS = {
    "budburst": "ridge",
    "flowering": "rf",
    "veraison": "ridge",
    "maturity_or_harvest": "rf",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--fixed-selection", type=Path, default=DEFAULT_FIXED_SELECTION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--cutoff-year", type=int, default=2015)
    parser.add_argument("--search-level", choices=["smoke", "formal"], default="formal")
    parser.add_argument("--n-jobs", type=int, choices=(1, 2, 3, 4), default=4)
    parser.add_argument("--random-state", type=int, default=20260805)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def fixed_algorithms(path: Path) -> dict[str, str]:
    if not path.exists():
        return FALLBACK_FIXED_ALGORITHMS.copy()
    selection = pd.read_csv(path)
    required = {"stage", "fixed_residual_algorithm"}
    missing = required.difference(selection.columns)
    if missing:
        raise ValueError(f"Fixed selection file is missing columns: {sorted(missing)}")
    result = selection.set_index("stage")["fixed_residual_algorithm"].to_dict()
    for stage, algorithm in FALLBACK_FIXED_ALGORITHMS.items():
        result.setdefault(stage, algorithm)
    return result


def inner_spatial_folds(train: pd.DataFrame) -> list[int]:
    folds = sorted(pd.to_numeric(train["event_assigned_outer_fold"]).dropna().astype(int).unique())
    if len(folds) < 2:
        raise ValueError("Temporal training set has fewer than two spatial tuning folds")
    return folds


def summarize_inner_metrics(metrics: pd.DataFrame) -> dict[str, float]:
    return {
        "mean_mae_days": float(metrics["mae_days"].mean()),
        "mean_rmse_days": float(metrics["rmse_days"].mean()),
        "pooled_bias_days": float(np.average(metrics["bias_days"], weights=metrics["n"])),
        "mean_abs_bias_days": float(metrics["bias_days"].abs().mean()),
        "sd_spatial_fold_mae_days": float(metrics["mae_days"].std(ddof=1)),
        "worst_spatial_fold_mae_days": float(metrics["mae_days"].max()),
    }


def evaluate_config_inner_spatial(
    train: pd.DataFrame,
    features: list[str],
    algorithm: str,
    config: dict[str, object],
    n_jobs: int,
    random_state: int,
) -> pd.DataFrame:
    rows = []
    for fold in inner_spatial_folds(train):
        fit = train.loc[train["event_assigned_outer_fold"].ne(fold)].copy()
        validation = train.loc[train["event_assigned_outer_fold"].eq(fold)].copy()
        estimator = build_estimator(algorithm, config, n_jobs, random_state + fold)
        estimator.fit(fit[features], fit["residual_days"].to_numpy(float))
        predicted_residual = np.asarray(estimator.predict(validation[features]), dtype=float)
        predicted_doy = residual_to_doy(validation, predicted_residual)
        metric = prediction_metrics(validation["observed_doy"].to_numpy(float), predicted_doy)
        rows.append({"inner_spatial_fold": fold, **metric})
    return pd.DataFrame(rows)


def select_temporal_config(
    train: pd.DataFrame,
    features: list[str],
    algorithm: str,
    configs: list[dict[str, object]],
    n_jobs: int,
    random_state: int,
) -> tuple[dict[str, object], str, pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    fold_rows = []
    for index, config in enumerate(configs):
        identifier = config_id(algorithm, index)
        fold_metrics = evaluate_config_inner_spatial(
            train,
            features,
            algorithm,
            config,
            n_jobs,
            random_state + index * 100,
        )
        for row in fold_metrics.to_dict("records"):
            fold_rows.append(
                {
                    "algorithm": algorithm,
                    "config_id": identifier,
                    "config_json": json.dumps(config, sort_keys=True),
                    **row,
                }
            )
        summary_rows.append(
            {
                "algorithm": algorithm,
                "config_id": identifier,
                "config_json": json.dumps(config, sort_keys=True),
                **summarize_inner_metrics(fold_metrics),
            }
        )
    summary = pd.DataFrame(summary_rows)
    selected = summary.sort_values(
        [
            "mean_rmse_days",
            "mean_mae_days",
            "mean_abs_bias_days",
            "config_id",
        ]
    ).iloc[0]
    return (
        json.loads(str(selected["config_json"])),
        str(selected["config_id"]),
        summary,
        pd.DataFrame(fold_rows),
    )


def fit_predict_fixed_algorithm(
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
    algorithm: str,
    selected_config: dict[str, object] | None,
    n_jobs: int,
    random_state: int,
) -> np.ndarray:
    if algorithm == "mechanistic":
        return np.zeros(len(test), dtype=float)
    if selected_config is None:
        raise ValueError(f"Missing selected config for {algorithm}")
    estimator = build_estimator(algorithm, selected_config, n_jobs, random_state)
    estimator.fit(train[features], train["residual_days"].to_numpy(float))
    return np.asarray(estimator.predict(test[features]), dtype=float)


def metric_record(observed: np.ndarray, predicted: np.ndarray, prefix: str) -> dict[str, float]:
    metric = prediction_metrics(observed, predicted)
    return {f"{prefix}_{key}": value for key, value in metric.items()}


def country_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (stage, country), group in predictions.groupby(["stage", "country"], sort=False):
        observed = group["observed_doy"].to_numpy(float)
        process_predicted = group["mechanistic_predicted_doy"].to_numpy(float)
        hybrid_predicted = group["hybrid_predicted_doy"].to_numpy(float)
        process_metric = metric_record(observed, process_predicted, "process")
        hybrid_metric = metric_record(observed, hybrid_predicted, "hybrid")
        rows.append(
            {
                "stage": stage,
                "country": country,
                "n": int(len(group)),
                "year_min": int(group["year"].min()),
                "year_max": int(group["year"].max()),
                **process_metric,
                **hybrid_metric,
                "mae_gain_days": process_metric["process_mae_days"] - hybrid_metric["hybrid_mae_days"],
                "rmse_gain_days": process_metric["process_rmse_days"] - hybrid_metric["hybrid_rmse_days"],
            }
        )
    result = pd.DataFrame(rows)
    result["stage_order"] = result["stage"].map({stage: index for index, stage in enumerate(STAGES)})
    return result.sort_values(["stage_order", "country"]).drop(columns="stage_order")


def write_report(
    report_path: Path,
    output_dir: Path,
    aggregate: pd.DataFrame,
    by_country: pd.DataFrame,
    config_selection: pd.DataFrame,
    cutoff_year: int,
    elapsed_seconds: float,
) -> None:
    display = aggregate.copy()
    display["阶段"] = display["stage"].map(STAGE_LABELS)
    display = display[
        [
            "阶段",
            "process_model",
            "algorithm",
            "n_features",
            "train_n",
            "test_n",
            "train_year_range",
            "test_year_range",
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
            "process_model": "过程模型",
            "algorithm": "固定残差算法",
            "n_features": "特征数",
            "train_n": "训练n",
            "test_n": "测试n",
            "train_year_range": "训练年份",
            "test_year_range": "测试年份",
            "process_mae_days": "过程MAE",
            "hybrid_mae_days": "混合MAE",
            "mae_gain_days": "MAE增益(d)",
            "process_rmse_days": "过程RMSE",
            "hybrid_rmse_days": "混合RMSE",
            "rmse_gain_days": "RMSE增益(d)",
            "hybrid_bias_days": "混合Bias",
            "hybrid_within_7d_pct": "混合≤7d(%)",
        }
    )
    selected = config_selection.copy()
    selected["阶段"] = selected["stage"].map(STAGE_LABELS)
    selected = selected[
        [
            "阶段",
            "algorithm",
            "selected_config_id",
            "mean_inner_rmse_days",
            "mean_inner_mae_days",
            "worst_spatial_fold_mae_days",
        ]
    ].rename(
        columns={
            "algorithm": "固定残差算法",
            "selected_config_id": "选中参数",
            "mean_inner_rmse_days": "训练期内层RMSE",
            "mean_inner_mae_days": "训练期内层MAE",
            "worst_spatial_fold_mae_days": "训练期最差空间折MAE",
        }
    )
    country_display = by_country.copy()
    country_display["阶段"] = country_display["stage"].map(STAGE_LABELS)
    country_display = country_display[
        [
            "阶段",
            "country",
            "n",
            "year_min",
            "year_max",
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
            "country": "国家",
            "year_min": "起始年",
            "year_max": "结束年",
            "process_mae_days": "过程MAE",
            "hybrid_mae_days": "混合MAE",
            "mae_gain_days": "MAE增益(d)",
            "process_rmse_days": "过程RMSE",
            "hybrid_rmse_days": "混合RMSE",
            "rmse_gain_days": "RMSE增益(d)",
            "hybrid_bias_days": "混合Bias",
            "hybrid_within_7d_pct": "混合≤7d(%)",
        }
    )
    lines = [
        "# 固定混合模型时间留出补充分析",
        "",
        f"时间切分：训练年份 `<= {cutoff_year}`；测试年份 `>= {cutoff_year + 1}`。",
        "",
        "该分析固定使用当前主分析确定的阶段组合，只在训练年份内部按空间折选择固定算法的超参数；测试年份不参与调参。",
        "",
        "边界：本分析基于已经生成的空间折外过程模型预测表，评估残差学习器对近期年份的迁移能力；它不是重新按时间切分校准过程模型的严格全流程时间外推验证。",
        "",
        "## 1. 时间留出表现",
        "",
        display.round(3).to_markdown(index=False),
        "",
        "## 2. 国家层面诊断",
        "",
        country_display.round(3).to_markdown(index=False),
        "",
        "## 3. 训练期超参数选择",
        "",
        selected.round(3).to_markdown(index=False),
        "",
        "## 4. 输出",
        "",
        f"- 结果目录：`{output_dir}`",
        f"- 本报告：`{report_path}`",
        f"- 运行时间：{elapsed_seconds / 60.0:.2f} min",
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

    features_by_stage = feature_sets(args.data_dir)
    fixed_by_stage = fixed_algorithms(args.fixed_selection)
    candidates = parameter_candidates(args.search_level)
    table = pd.read_parquet(args.data_dir / "residual_spatial_test.parquet")
    table = table.loc[table["residual_ml_eligible"].astype(bool)].copy()
    if table.duplicated(["record_id", "stage"]).any():
        raise ValueError("Temporal holdout input has duplicate record-stage rows")

    aggregate_rows = []
    config_selection_rows = []
    inner_summary_rows = []
    inner_fold_rows = []
    prediction_tables = []
    start = time.perf_counter()

    for stage in tqdm(STAGES, desc="Temporal holdout", unit="stage"):
        features = features_by_stage[stage]
        missing = set(features).difference(table.columns)
        if missing:
            raise ValueError(f"{stage}: missing features: {sorted(missing)}")
        stage_table = table.loc[table["stage"].eq(stage)].copy()
        train = stage_table.loc[stage_table["year"].le(args.cutoff_year)].copy()
        test = stage_table.loc[stage_table["year"].gt(args.cutoff_year)].copy()
        if train.empty or test.empty:
            raise ValueError(f"{stage}: empty temporal train or test split")

        algorithm = fixed_by_stage[stage]
        if algorithm == "mechanistic":
            selected_config = None
            selected_config_id = "mechanistic"
            selected_summary = {
                "mean_inner_rmse_days": np.nan,
                "mean_inner_mae_days": np.nan,
                "worst_spatial_fold_mae_days": np.nan,
            }
        else:
            selected_config, selected_config_id, config_summary, fold_metrics = select_temporal_config(
                train,
                features,
                algorithm,
                candidates[algorithm],
                args.n_jobs,
                args.random_state + len(config_selection_rows) * 1000,
            )
            config_summary.insert(0, "stage", stage)
            fold_metrics.insert(0, "stage", stage)
            inner_summary_rows.extend(config_summary.to_dict("records"))
            inner_fold_rows.extend(fold_metrics.to_dict("records"))
            selected_summary = (
                config_summary.loc[config_summary["config_id"].eq(selected_config_id)]
                .iloc[0]
                .to_dict()
            )

        predicted_residual = fit_predict_fixed_algorithm(
            train,
            test,
            features,
            algorithm,
            selected_config,
            args.n_jobs,
            args.random_state + 10000,
        )
        hybrid_predicted_doy = residual_to_doy(test, predicted_residual)
        observed = test["observed_doy"].to_numpy(float)
        process_predicted = test["mechanistic_predicted_doy"].to_numpy(float)
        process_metric = metric_record(observed, process_predicted, "process")
        hybrid_metric = metric_record(observed, hybrid_predicted_doy, "hybrid")
        aggregate_rows.append(
            {
                "stage": stage,
                "process_model": PROCESS_MODEL_LABELS[stage],
                "algorithm": algorithm,
                "n_features": len(features),
                "train_n": int(len(train)),
                "test_n": int(len(test)),
                "train_year_range": f"{int(train['year'].min())}-{int(train['year'].max())}",
                "test_year_range": f"{int(test['year'].min())}-{int(test['year'].max())}",
                **process_metric,
                **hybrid_metric,
                "mae_gain_days": process_metric["process_mae_days"] - hybrid_metric["hybrid_mae_days"],
                "rmse_gain_days": process_metric["process_rmse_days"] - hybrid_metric["hybrid_rmse_days"],
            }
        )
        config_selection_rows.append(
            {
                "stage": stage,
                "algorithm": algorithm,
                "selected_config_id": selected_config_id,
                "selected_config_json": json.dumps(selected_config or {}, sort_keys=True),
                "mean_inner_rmse_days": selected_summary["mean_rmse_days"],
                "mean_inner_mae_days": selected_summary["mean_mae_days"],
                "worst_spatial_fold_mae_days": selected_summary["worst_spatial_fold_mae_days"],
            }
        )
        prediction_tables.append(
            pd.DataFrame(
                {
                    "stage": stage,
                    "algorithm": algorithm,
                    "record_id": test["record_id"].to_numpy(),
                    "site_uid": test["site_uid"].to_numpy(),
                    "country": test["country"].to_numpy(),
                    "year": test["year"].to_numpy(),
                    "event_assigned_outer_fold": test["event_assigned_outer_fold"].to_numpy(),
                    "observed_doy": observed,
                    "mechanistic_predicted_doy": process_predicted,
                    "predicted_residual_days": predicted_residual,
                    "hybrid_predicted_doy": hybrid_predicted_doy,
                }
            )
        )

    elapsed = time.perf_counter() - start
    aggregate = pd.DataFrame(aggregate_rows)
    aggregate["stage_order"] = aggregate["stage"].map({stage: index for index, stage in enumerate(STAGES)})
    aggregate = aggregate.sort_values("stage_order").drop(columns="stage_order")
    config_selection = pd.DataFrame(config_selection_rows)
    config_selection["stage_order"] = config_selection["stage"].map({stage: index for index, stage in enumerate(STAGES)})
    config_selection = config_selection.sort_values("stage_order").drop(columns="stage_order")
    predictions = pd.concat(prediction_tables, ignore_index=True)
    by_country = country_metrics(predictions)

    aggregate.to_csv(args.output_dir / "temporal_holdout_aggregate_metrics.csv", index=False)
    by_country.to_csv(args.output_dir / "temporal_holdout_country_metrics.csv", index=False)
    config_selection.to_csv(args.output_dir / "temporal_holdout_selected_configs.csv", index=False)
    if inner_summary_rows:
        pd.DataFrame(inner_summary_rows).to_csv(
            args.output_dir / "temporal_holdout_inner_config_metrics.csv",
            index=False,
        )
    if inner_fold_rows:
        pd.DataFrame(inner_fold_rows).to_csv(
            args.output_dir / "temporal_holdout_inner_spatial_fold_metrics.csv",
            index=False,
        )
    predictions.to_parquet(args.output_dir / "temporal_holdout_predictions.parquet", index=False)
    audit = {
        "scope": "supplementary temporal holdout for fixed residual hybrid models",
        "data_dir": str(args.data_dir),
        "input_table": "residual_spatial_test.parquet",
        "cutoff_year": args.cutoff_year,
        "train_rule": f"year <= {args.cutoff_year}",
        "test_rule": f"year > {args.cutoff_year}",
        "fixed_algorithms": fixed_by_stage,
        "hyperparameter_rule": "training-period spatial-fold inner RMSE within fixed algorithm",
        "strict_full_pipeline_temporal_validation": False,
        "boundary": (
            "Uses frozen spatial-OOF mechanistic predictions; process models are not "
            "recalibrated using only pre-cutoff years."
        ),
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
        aggregate,
        by_country,
        config_selection,
        args.cutoff_year,
        elapsed,
    )

    print("\nTemporal holdout completed")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print("\nTemporal holdout aggregate metrics")
    display_columns = [
        "stage",
        "algorithm",
        "train_n",
        "test_n",
        "process_mae_days",
        "hybrid_mae_days",
        "mae_gain_days",
        "process_rmse_days",
        "hybrid_rmse_days",
        "rmse_gain_days",
        "hybrid_bias_days",
        "hybrid_within_7d_pct",
    ]
    print(aggregate[display_columns].round(3).to_string(index=False))
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
