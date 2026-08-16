#!/usr/bin/env python
"""Fit and evaluate stage-specific residual models with nested spatial CV."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import time
from pathlib import Path

# Avoid macOS OpenMP conflicts when scikit-learn, XGBoost and LightGBM are
# loaded in the same long-running nested-CV process. Model-level parallelism
# remains controlled by --n-jobs.
for variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ[variable] = "1"

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler
from tqdm.auto import tqdm
from xgboost import XGBRegressor

try:
    from src.modeling.run_mechanistic_baselines import REPO_ROOT
except ModuleNotFoundError:
    from run_mechanistic_baselines import REPO_ROOT  # type: ignore


DEFAULT_INPUT_DIR = REPO_ROOT / "results/france_germany_four_stage/residual_machine_learning"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "results/france_germany_four_stage/residual_modeling/formal"
STAGES = ("budburst", "flowering", "veraison", "maturity_or_harvest")
ALGORITHMS = ("ridge", "gam", "rf", "xgboost", "lightgbm")
BASELINES = ("mechanistic", "mean_bias")
SELECTION_CANDIDATES = ("mechanistic", *ALGORITHMS)
REFERENCE_BASELINES = ("mean_bias",)
COMPLEXITY_ORDER = {
    "mechanistic": 0,
    "ridge": 1,
    "gam": 2,
    "rf": 3,
    "xgboost": 4,
    "lightgbm": 5,
}


def parse_int_list(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_str_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--stages", type=parse_str_list, default=list(STAGES))
    parser.add_argument("--outer-folds", type=parse_int_list, default=[1, 2, 3, 4, 5])
    parser.add_argument("--search-level", choices=["smoke", "formal"], default="formal")
    parser.add_argument(
        "--selection-rule",
        choices=["one_se_min_complexity", "min_mae", "min_rmse"],
        default="one_se_min_complexity",
        help="Inner-CV rule used to select the residual correction algorithm for each stage-fold.",
    )
    parser.add_argument("--n-jobs", type=int, default=4)
    parser.add_argument("--random-state", type=int, default=20260805)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def parameter_candidates(search_level: str) -> dict[str, list[dict[str, object]]]:
    formal = {
        "ridge": [
            {"alpha": alpha}
            for alpha in (0.01, 0.1, 1.0, 10.0, 100.0)
        ],
        "gam": [
            {"n_knots": knots, "alpha": alpha}
            for knots in (4, 6, 8)
            for alpha in (0.1, 1.0, 10.0)
        ],
        "rf": [
            {"n_estimators": 300, "max_depth": None, "min_samples_leaf": 2, "max_features": 0.7},
            {"n_estimators": 300, "max_depth": None, "min_samples_leaf": 5, "max_features": 1.0},
            {"n_estimators": 300, "max_depth": 8, "min_samples_leaf": 5, "max_features": 0.7},
            {"n_estimators": 400, "max_depth": 12, "min_samples_leaf": 5, "max_features": 1.0},
            {"n_estimators": 400, "max_depth": 12, "min_samples_leaf": 10, "max_features": 0.7},
            {"n_estimators": 500, "max_depth": 16, "min_samples_leaf": 10, "max_features": 1.0},
        ],
        "xgboost": [
            {"n_estimators": 300, "max_depth": 2, "learning_rate": 0.03, "min_child_weight": 5, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.0, "reg_lambda": 5.0},
            {"n_estimators": 300, "max_depth": 3, "learning_rate": 0.05, "min_child_weight": 5, "subsample": 0.8, "colsample_bytree": 1.0, "reg_alpha": 0.1, "reg_lambda": 5.0},
            {"n_estimators": 500, "max_depth": 2, "learning_rate": 0.03, "min_child_weight": 10, "subsample": 1.0, "colsample_bytree": 0.8, "reg_alpha": 0.1, "reg_lambda": 10.0},
            {"n_estimators": 500, "max_depth": 3, "learning_rate": 0.03, "min_child_weight": 10, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.0, "reg_lambda": 10.0},
            {"n_estimators": 300, "max_depth": 4, "learning_rate": 0.03, "min_child_weight": 10, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.1, "reg_lambda": 10.0},
            {"n_estimators": 500, "max_depth": 4, "learning_rate": 0.02, "min_child_weight": 15, "subsample": 1.0, "colsample_bytree": 1.0, "reg_alpha": 0.1, "reg_lambda": 10.0},
        ],
        "lightgbm": [
            {"n_estimators": 300, "learning_rate": 0.03, "num_leaves": 7, "max_depth": 4, "min_child_samples": 30, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.0, "reg_lambda": 5.0},
            {"n_estimators": 300, "learning_rate": 0.05, "num_leaves": 15, "max_depth": 6, "min_child_samples": 30, "subsample": 0.8, "colsample_bytree": 1.0, "reg_alpha": 0.1, "reg_lambda": 5.0},
            {"n_estimators": 500, "learning_rate": 0.03, "num_leaves": 15, "max_depth": 6, "min_child_samples": 60, "subsample": 1.0, "colsample_bytree": 0.8, "reg_alpha": 0.1, "reg_lambda": 10.0},
            {"n_estimators": 500, "learning_rate": 0.03, "num_leaves": 31, "max_depth": 8, "min_child_samples": 60, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.0, "reg_lambda": 10.0},
            {"n_estimators": 300, "learning_rate": 0.03, "num_leaves": 31, "max_depth": 8, "min_child_samples": 100, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.1, "reg_lambda": 10.0},
            {"n_estimators": 500, "learning_rate": 0.02, "num_leaves": 15, "max_depth": 6, "min_child_samples": 100, "subsample": 1.0, "colsample_bytree": 1.0, "reg_alpha": 0.1, "reg_lambda": 10.0},
        ],
    }
    if search_level == "smoke":
        return {algorithm: [configs[0]] for algorithm, configs in formal.items()}
    return formal


def config_id(algorithm: str, index: int) -> str:
    return f"{algorithm}_{index + 1:02d}"


def build_estimator(
    algorithm: str,
    config: dict[str, object],
    n_jobs: int,
    random_state: int,
):
    imputer = SimpleImputer(strategy="median")
    if algorithm == "ridge":
        regressor = Pipeline(
            [
                ("imputer", imputer),
                ("scale", StandardScaler()),
                ("ridge", Ridge(alpha=float(config["alpha"]))),
            ]
        )
        return TransformedTargetRegressor(regressor=regressor, transformer=StandardScaler())
    if algorithm == "gam":
        regressor = Pipeline(
            [
                ("imputer", imputer),
                (
                    "splines",
                    SplineTransformer(
                        n_knots=int(config["n_knots"]),
                        degree=3,
                        include_bias=False,
                        extrapolation="linear",
                    ),
                ),
                ("scale", StandardScaler()),
                ("ridge", Ridge(alpha=float(config["alpha"]))),
            ]
        )
        return TransformedTargetRegressor(regressor=regressor, transformer=StandardScaler())
    if algorithm == "rf":
        model = RandomForestRegressor(
            **config,
            random_state=random_state,
            n_jobs=n_jobs,
        )
    elif algorithm == "xgboost":
        model = XGBRegressor(
            **config,
            objective="reg:squarederror",
            tree_method="hist",
            random_state=random_state,
            n_jobs=n_jobs,
            verbosity=0,
        )
    elif algorithm == "lightgbm":
        model = LGBMRegressor(
            **config,
            objective="regression",
            random_state=random_state,
            n_jobs=n_jobs,
            subsample_freq=1,
            verbosity=-1,
        )
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    return Pipeline([("imputer", imputer), ("model", model)])


def prediction_metrics(observed: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - observed
    absolute = np.abs(error)
    return {
        "n": int(len(observed)),
        "mae_days": float(np.mean(absolute)),
        "rmse_days": float(np.sqrt(np.mean(np.square(error)))),
        "bias_days": float(np.mean(error)),
        "within_5d_pct": float(np.mean(absolute <= 5.0) * 100.0),
        "within_7d_pct": float(np.mean(absolute <= 7.0) * 100.0),
    }


def residual_to_doy(frame: pd.DataFrame, predicted_residual: np.ndarray) -> np.ndarray:
    return frame["mechanistic_predicted_doy"].to_numpy(float) + predicted_residual


def fold_summary(frame: pd.DataFrame) -> dict[str, float]:
    return {
        "mean_mae_days": float(frame["mae_days"].mean()),
        "mean_rmse_days": float(frame["rmse_days"].mean()),
        "pooled_bias_days": float(
            np.average(frame["bias_days"], weights=frame["n"])
        ),
        "sd_mae_days": float(frame["mae_days"].std(ddof=1)),
        "se_mae_days": float(frame["mae_days"].std(ddof=1) / math.sqrt(len(frame))),
        "worst_fold_mae_days": float(frame["mae_days"].max()),
    }


def choose_by_one_se(summary: pd.DataFrame) -> tuple[str, float, str]:
    selectable = summary.loc[
        summary["algorithm"].isin(SELECTION_CANDIDATES)
    ].copy()
    if selectable.empty:
        raise ValueError("No selection-eligible residual-model candidates")
    best = selectable.sort_values(["mean_mae_days", "mean_rmse_days"]).iloc[0]
    cutoff = float(best["mean_mae_days"] + best["se_mae_days"])
    eligible = selectable.loc[selectable["mean_mae_days"].le(cutoff)].copy()
    eligible["complexity_order"] = eligible["algorithm"].map(COMPLEXITY_ORDER)
    selected = eligible.sort_values(
        ["complexity_order", "mean_mae_days", "mean_rmse_days"]
    ).iloc[0]
    return str(selected["algorithm"]), cutoff, str(best["algorithm"])


def choose_by_min_mae(summary: pd.DataFrame) -> tuple[str, float, str]:
    selectable = summary.loc[
        summary["algorithm"].isin(SELECTION_CANDIDATES)
    ].copy()
    if selectable.empty:
        raise ValueError("No selection-eligible residual-model candidates")
    selectable["absolute_pooled_bias_days"] = selectable["pooled_bias_days"].abs()
    selected = selectable.sort_values(
        ["mean_mae_days", "mean_rmse_days", "absolute_pooled_bias_days"]
    ).iloc[0]
    return (
        str(selected["algorithm"]),
        float(selected["mean_mae_days"]),
        str(selected["algorithm"]),
    )


def choose_by_min_rmse(summary: pd.DataFrame) -> tuple[str, float, str]:
    selectable = summary.loc[
        summary["algorithm"].isin(SELECTION_CANDIDATES)
    ].copy()
    if selectable.empty:
        raise ValueError("No selection-eligible residual-model candidates")
    selectable["absolute_pooled_bias_days"] = selectable["pooled_bias_days"].abs()
    selected = selectable.sort_values(
        ["mean_rmse_days", "mean_mae_days", "absolute_pooled_bias_days"]
    ).iloc[0]
    return (
        str(selected["algorithm"]),
        float(selected["mean_rmse_days"]),
        str(selected["algorithm"]),
    )


def choose_residual_algorithm(
    summary: pd.DataFrame,
    selection_rule: str,
) -> tuple[str, float, str, str]:
    if selection_rule == "one_se_min_complexity":
        selected, cutoff, numeric_best = choose_by_one_se(summary)
        return (
            selected,
            cutoff,
            numeric_best,
            "lowest-complexity candidate within one SE of minimum inner-fold mean MAE",
        )
    if selection_rule == "min_mae":
        selected, cutoff, numeric_best = choose_by_min_mae(summary)
        return (
            selected,
            cutoff,
            numeric_best,
            "minimum inner-fold mean MAE; RMSE and absolute bias tie-break",
        )
    if selection_rule == "min_rmse":
        selected, cutoff, numeric_best = choose_by_min_rmse(summary)
        return (
            selected,
            cutoff,
            numeric_best,
            "minimum inner-fold mean RMSE; MAE and absolute bias tie-break",
        )
    raise ValueError(f"Unknown selection rule: {selection_rule}")


def validate_inputs(
    table: pd.DataFrame,
    features: list[str],
    stage: str,
    outer_fold: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    missing = set(features).difference(table.columns)
    if missing:
        raise ValueError(f"{stage}: missing frozen features {sorted(missing)}")
    train = table.loc[
        table["dataset_role"].eq("training_region_oof")
        & table["outer_fold"].eq(outer_fold)
        & table["residual_ml_eligible"].astype(bool)
    ].copy()
    test = table.loc[
        table["dataset_role"].eq("spatial_test")
        & table["outer_fold"].eq(outer_fold)
        & table["residual_ml_eligible"].astype(bool)
    ].copy()
    if train.empty or test.empty:
        raise ValueError(f"{stage} outer fold {outer_fold}: empty train or test")
    if not train["event_assigned_outer_fold"].ne(outer_fold).all():
        raise ValueError("Current spatial test fold leaked into residual training rows")
    if not test["event_assigned_outer_fold"].eq(outer_fold).all():
        raise ValueError("Spatial test rows do not match their assigned outer fold")
    if train["record_id"].isin(test["record_id"]).any():
        raise ValueError("Record IDs overlap between current train and spatial test sets")
    if set(pd.to_numeric(train["inner_fold"]).dropna().astype(int)) != {1, 2, 3, 4}:
        raise ValueError("Training-region inner folds are incomplete")
    return train, test


def inner_predictions_for_baseline(
    train: pd.DataFrame,
    algorithm: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    predictions = []
    metrics = []
    for inner_fold in (1, 2, 3, 4):
        fit = train.loc[train["inner_fold"].ne(inner_fold)]
        validation = train.loc[train["inner_fold"].eq(inner_fold)]
        if algorithm == "mechanistic":
            predicted_residual = np.zeros(len(validation), dtype=float)
        elif algorithm == "mean_bias":
            predicted_residual = np.repeat(float(fit["residual_days"].mean()), len(validation))
        else:
            raise ValueError(algorithm)
        predicted_doy = residual_to_doy(validation, predicted_residual)
        metric = prediction_metrics(validation["observed_doy"].to_numpy(float), predicted_doy)
        metrics.append({"inner_fold": inner_fold, **metric})
        predictions.append(
            pd.DataFrame(
                {
                    "residual_row_id": validation["residual_row_id"].to_numpy(),
                    "inner_fold": inner_fold,
                    "observed_doy": validation["observed_doy"].to_numpy(float),
                    "mechanistic_predicted_doy": validation[
                        "mechanistic_predicted_doy"
                    ].to_numpy(float),
                    "predicted_residual_days": predicted_residual,
                    "hybrid_predicted_doy": predicted_doy,
                }
            )
        )
    return pd.concat(predictions, ignore_index=True), pd.DataFrame(metrics)


def evaluate_config_inner(
    train: pd.DataFrame,
    features: list[str],
    algorithm: str,
    config: dict[str, object],
    n_jobs: int,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    predictions = []
    metrics = []
    for inner_fold in (1, 2, 3, 4):
        fit = train.loc[train["inner_fold"].ne(inner_fold)]
        validation = train.loc[train["inner_fold"].eq(inner_fold)]
        estimator = build_estimator(algorithm, config, n_jobs, random_state + inner_fold)
        estimator.fit(fit[features], fit["residual_days"].to_numpy(float))
        predicted_residual = np.asarray(estimator.predict(validation[features]), dtype=float)
        predicted_doy = residual_to_doy(validation, predicted_residual)
        metric = prediction_metrics(validation["observed_doy"].to_numpy(float), predicted_doy)
        metrics.append({"inner_fold": inner_fold, **metric})
        predictions.append(
            pd.DataFrame(
                {
                    "residual_row_id": validation["residual_row_id"].to_numpy(),
                    "inner_fold": inner_fold,
                    "observed_doy": validation["observed_doy"].to_numpy(float),
                    "mechanistic_predicted_doy": validation[
                        "mechanistic_predicted_doy"
                    ].to_numpy(float),
                    "predicted_residual_days": predicted_residual,
                    "hybrid_predicted_doy": predicted_doy,
                }
            )
        )
    return pd.concat(predictions, ignore_index=True), pd.DataFrame(metrics)


def fit_full_and_predict(
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
    algorithm: str,
    config: dict[str, object] | None,
    n_jobs: int,
    random_state: int,
) -> np.ndarray:
    if algorithm == "mechanistic":
        return np.zeros(len(test), dtype=float)
    if algorithm == "mean_bias":
        return np.repeat(float(train["residual_days"].mean()), len(test))
    if config is None:
        raise ValueError(f"Missing selected configuration for {algorithm}")
    estimator = build_estimator(algorithm, config, n_jobs, random_state)
    estimator.fit(train[features], train["residual_days"].to_numpy(float))
    return np.asarray(estimator.predict(test[features]), dtype=float)


def aggregate_outer_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (stage, algorithm), group in predictions.groupby(["stage", "algorithm"], sort=False):
        metric = prediction_metrics(
            group["observed_doy"].to_numpy(float),
            group["hybrid_predicted_doy"].to_numpy(float),
        )
        fold_mae = group.groupby("outer_fold").apply(
            lambda value: np.mean(
                np.abs(value["hybrid_predicted_doy"] - value["observed_doy"])
            ),
            include_groups=False,
        )
        rows.append(
            {
                "stage": stage,
                "algorithm": algorithm,
                **metric,
                "sd_outer_fold_mae_days": float(fold_mae.std(ddof=1)),
                "worst_outer_fold_mae_days": float(fold_mae.max()),
            }
        )
    return pd.DataFrame(rows)


def write_report(
    output_dir: Path,
    aggregate: pd.DataFrame,
    selection: pd.DataFrame,
    elapsed_seconds: float,
) -> None:
    lines = [
        "# Residual model nested spatial-validation report",
        "",
        "The residual target is observed DOY minus strict OOF mechanistic DOY. Model and hyperparameter selection use only the four training-region inner spatial folds; the held-out outer spatial fold is used once for evaluation.",
        "",
        "## Aggregate outer-spatial performance",
        "",
        aggregate.round(3).to_markdown(index=False),
        "",
        "## Inner-selection records",
        "",
        selection.to_markdown(index=False),
        "",
        f"Elapsed time: {elapsed_seconds / 60.0:.2f} minutes.",
    ]
    (output_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    invalid_stages = set(args.stages).difference(STAGES)
    if invalid_stages:
        raise ValueError(f"Unknown stages: {sorted(invalid_stages)}")
    invalid_folds = set(args.outer_folds).difference({1, 2, 3, 4, 5})
    if invalid_folds:
        raise ValueError(f"Unknown outer folds: {sorted(invalid_folds)}")
    if args.output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"Output exists: {args.output_dir}; use --overwrite")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = pd.read_csv(args.input_dir / "residual_ml_feature_sets.csv")
    candidates = parameter_candidates(args.search_level)
    inner_search_rows: list[dict[str, object]] = []
    inner_summary_rows: list[dict[str, object]] = []
    inner_best_predictions: list[pd.DataFrame] = []
    selection_rows: list[dict[str, object]] = []
    outer_prediction_rows: list[pd.DataFrame] = []
    outer_metric_rows: list[dict[str, object]] = []
    start_time = time.perf_counter()

    tasks = [(stage, fold) for stage in args.stages for fold in args.outer_folds]
    for stage, outer_fold in tqdm(tasks, desc="Residual ML outer evaluations", unit="task"):
        features = (
            manifest.loc[manifest["stage"].eq(stage)]
            .sort_values("feature_order")["feature"]
            .tolist()
        )
        table = pd.read_parquet(args.input_dir / "training_ready" / f"{stage}_residual_ml.parquet")
        train, test = validate_inputs(table, features, stage, outer_fold)

        best_configs: dict[str, dict[str, object]] = {}
        algorithm_fold_metrics: dict[str, pd.DataFrame] = {}

        for baseline in BASELINES:
            predictions, metrics = inner_predictions_for_baseline(train, baseline)
            algorithm_fold_metrics[baseline] = metrics
            summary = fold_summary(metrics)
            inner_summary_rows.append(
                {
                    "stage": stage,
                    "outer_fold": outer_fold,
                    "algorithm": baseline,
                    "config_id": baseline,
                    "config_json": "{}",
                    **summary,
                }
            )
            predictions.insert(0, "algorithm", baseline)
            predictions.insert(0, "outer_fold", outer_fold)
            predictions.insert(0, "stage", stage)
            inner_best_predictions.append(predictions)

        for algorithm in ALGORITHMS:
            config_results = []
            for index, config in enumerate(candidates[algorithm]):
                identifier = config_id(algorithm, index)
                _, metrics = evaluate_config_inner(
                    train,
                    features,
                    algorithm,
                    config,
                    args.n_jobs,
                    args.random_state + outer_fold * 100,
                )
                for row in metrics.to_dict("records"):
                    inner_search_rows.append(
                        {
                            "stage": stage,
                            "outer_fold": outer_fold,
                            "algorithm": algorithm,
                            "config_id": identifier,
                            "config_json": json.dumps(config, sort_keys=True),
                            **row,
                        }
                    )
                config_results.append(
                    {
                        "algorithm": algorithm,
                        "config_id": identifier,
                        "config_json": json.dumps(config, sort_keys=True),
                        **fold_summary(metrics),
                    }
                )
            config_table = pd.DataFrame(config_results).sort_values(
                ["mean_mae_days", "mean_rmse_days", "sd_mae_days"]
            )
            best = config_table.iloc[0]
            best_config = json.loads(str(best["config_json"]))
            best_configs[algorithm] = best_config
            best_predictions, best_metrics = evaluate_config_inner(
                train,
                features,
                algorithm,
                best_config,
                args.n_jobs,
                args.random_state + outer_fold * 1000,
            )
            algorithm_fold_metrics[algorithm] = best_metrics
            inner_summary_rows.append(
                {
                    "stage": stage,
                    "outer_fold": outer_fold,
                    **best.to_dict(),
                }
            )
            best_predictions.insert(0, "algorithm", algorithm)
            best_predictions.insert(0, "outer_fold", outer_fold)
            best_predictions.insert(0, "stage", stage)
            inner_best_predictions.append(best_predictions)

        current_summary = pd.DataFrame(
            [
                row
                for row in inner_summary_rows
                if row["stage"] == stage and row["outer_fold"] == outer_fold
            ]
        )
        selected, cutoff, numeric_best, selection_rule_text = choose_residual_algorithm(
            current_summary,
            args.selection_rule,
        )
        selection_rows.append(
            {
                "stage": stage,
                "outer_fold": outer_fold,
                "numeric_best_algorithm": numeric_best,
                "selection_cutoff_mae_days": cutoff,
                "selected_algorithm": selected,
                "selected_config_json": json.dumps(best_configs.get(selected, {}), sort_keys=True),
                "selection_rule": selection_rule_text,
            }
        )

        for algorithm in (*BASELINES, *ALGORITHMS):
            predicted_residual = fit_full_and_predict(
                train,
                test,
                features,
                algorithm,
                best_configs.get(algorithm),
                args.n_jobs,
                args.random_state + outer_fold * 10000,
            )
            predicted_doy = residual_to_doy(test, predicted_residual)
            metric = prediction_metrics(test["observed_doy"].to_numpy(float), predicted_doy)
            outer_metric_rows.append(
                {
                    "stage": stage,
                    "outer_fold": outer_fold,
                    "algorithm": algorithm,
                    "selected_by_inner_cv": algorithm == selected,
                    "n_test_total": int(
                        table.loc[
                            table["dataset_role"].eq("spatial_test")
                            & table["outer_fold"].eq(outer_fold)
                        ].shape[0]
                    ),
                    "coverage_pct": float(
                        len(test)
                        / table.loc[
                            table["dataset_role"].eq("spatial_test")
                            & table["outer_fold"].eq(outer_fold)
                        ].shape[0]
                        * 100.0
                    ),
                    **metric,
                }
            )
            outer_prediction_rows.append(
                pd.DataFrame(
                    {
                        "stage": stage,
                        "outer_fold": outer_fold,
                        "algorithm": algorithm,
                        "selected_by_inner_cv": algorithm == selected,
                        "record_id": test["record_id"].to_numpy(),
                        "site_uid": test["site_uid"].to_numpy(),
                        "observed_doy": test["observed_doy"].to_numpy(float),
                        "mechanistic_predicted_doy": test[
                            "mechanistic_predicted_doy"
                        ].to_numpy(float),
                        "predicted_residual_days": predicted_residual,
                        "hybrid_predicted_doy": predicted_doy,
                    }
                )
            )

    inner_search = pd.DataFrame(inner_search_rows)
    inner_summary = pd.DataFrame(inner_summary_rows)
    inner_predictions = pd.concat(inner_best_predictions, ignore_index=True)
    selection = pd.DataFrame(selection_rows)
    outer_predictions = pd.concat(outer_prediction_rows, ignore_index=True)
    outer_metrics = pd.DataFrame(outer_metric_rows)

    selected_predictions = outer_predictions.loc[outer_predictions["selected_by_inner_cv"]].copy()
    selected_predictions["source_algorithm"] = selected_predictions["algorithm"]
    selected_predictions["algorithm"] = "nested_selected"
    aggregate_input = pd.concat([outer_predictions, selected_predictions], ignore_index=True)
    aggregate = aggregate_outer_metrics(aggregate_input)

    inner_search.to_csv(args.output_dir / "inner_parameter_search_metrics.csv", index=False)
    inner_summary.to_csv(args.output_dir / "inner_best_algorithm_summary.csv", index=False)
    inner_predictions.to_parquet(args.output_dir / "inner_best_oof_predictions.parquet", index=False)
    selection.to_csv(args.output_dir / "nested_algorithm_selection.csv", index=False)
    outer_metrics.to_csv(args.output_dir / "outer_fold_metrics.csv", index=False)
    outer_predictions.to_parquet(args.output_dir / "outer_spatial_predictions.parquet", index=False)
    selected_predictions.to_parquet(
        args.output_dir / "nested_selected_outer_predictions.parquet", index=False
    )
    aggregate.to_csv(args.output_dir / "aggregate_outer_metrics.csv", index=False)

    elapsed = time.perf_counter() - start_time
    audit = {
        "scope": "nested spatial residual-model selection and outer evaluation",
        "stages": list(args.stages),
        "outer_folds": list(args.outer_folds),
        "algorithms": list(ALGORITHMS),
        "baselines": list(BASELINES),
        "selection_candidates": list(SELECTION_CANDIDATES),
        "reference_only_baselines": list(REFERENCE_BASELINES),
        "search_level": args.search_level,
        "selection_rule": args.selection_rule,
        "n_jobs": args.n_jobs,
        "random_state": args.random_state,
        "inner_selection_rule": selection_rule_text,
        "test_targets_used_for_training_or_selection": False,
        "elapsed_seconds": elapsed,
        "output_directory": str(args.output_dir),
    }
    (args.output_dir / "run_summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(args.output_dir, aggregate, selection, elapsed)
    print("\nResidual-model run completed")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print("\nAggregate outer-spatial metrics")
    print(aggregate.round(3).to_string(index=False))
    print("\nNested algorithm selections")
    print(selection.to_string(index=False))
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
