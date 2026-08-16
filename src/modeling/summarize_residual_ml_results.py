#!/usr/bin/env python
"""Audit and summarize formal nested spatial residual-model results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from tqdm.auto import tqdm

try:
    from src.modeling.run_mechanistic_baselines import REPO_ROOT
    from src.modeling.run_residual_ml_models import (
        ALGORITHMS,
        build_estimator,
        prediction_metrics,
        validate_inputs,
    )
except ModuleNotFoundError:
    from run_mechanistic_baselines import REPO_ROOT  # type: ignore
    from run_residual_ml_models import (  # type: ignore
        ALGORITHMS,
        build_estimator,
        prediction_metrics,
        validate_inputs,
    )


DEFAULT_INPUT_DIR = REPO_ROOT / "results/france_germany_four_stage/residual_machine_learning"
DEFAULT_RESULT_DIR = REPO_ROOT / "results/france_germany_four_stage/residual_modeling/formal"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--result-dir", type=Path, default=DEFAULT_RESULT_DIR)
    parser.add_argument("--n-jobs", type=int, default=4)
    parser.add_argument("--permutation-repeats", type=int, default=10)
    parser.add_argument("--random-state", type=int, default=20260805)
    return parser.parse_args()


def selected_comparison(predictions: pd.DataFrame) -> pd.DataFrame:
    selected = predictions.loc[predictions["selected_by_inner_cv"]].copy()
    selected = selected.rename(columns={"algorithm": "selected_algorithm"})
    mechanism = predictions.loc[predictions["algorithm"].eq("mechanistic")].copy()
    keys = ["stage", "outer_fold", "record_id"]
    merged = selected.merge(
        mechanism[keys + ["hybrid_predicted_doy"]].rename(
            columns={"hybrid_predicted_doy": "mechanistic_doy_check"}
        ),
        on=keys,
        how="left",
        validate="one_to_one",
    )
    if not np.allclose(
        merged["mechanistic_predicted_doy"], merged["mechanistic_doy_check"]
    ):
        raise ValueError("Mechanistic prediction mismatch in selected comparison")
    rows = []
    for stage, group in merged.groupby("stage", sort=False):
        selected_metric = prediction_metrics(
            group["observed_doy"].to_numpy(float),
            group["hybrid_predicted_doy"].to_numpy(float),
        )
        mechanism_metric = prediction_metrics(
            group["observed_doy"].to_numpy(float),
            group["mechanistic_predicted_doy"].to_numpy(float),
        )
        rows.append(
            {
                "stage": stage,
                "n": int(len(group)),
                "mechanistic_mae_days": mechanism_metric["mae_days"],
                "nested_selected_mae_days": selected_metric["mae_days"],
                "mae_improvement_days": (
                    mechanism_metric["mae_days"] - selected_metric["mae_days"]
                ),
                "mae_improvement_pct": (
                    (mechanism_metric["mae_days"] - selected_metric["mae_days"])
                    / mechanism_metric["mae_days"]
                    * 100.0
                ),
                "mechanistic_rmse_days": mechanism_metric["rmse_days"],
                "nested_selected_rmse_days": selected_metric["rmse_days"],
                "mechanistic_bias_days": mechanism_metric["bias_days"],
                "nested_selected_bias_days": selected_metric["bias_days"],
            }
        )
    return pd.DataFrame(rows)


def permutation_tables(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame]:
    selection = pd.read_csv(args.result_dir / "nested_algorithm_selection.csv")
    manifest = pd.read_csv(args.input_dir / "residual_ml_feature_sets.csv")
    records = []
    selected_ml = selection.loc[selection["selected_algorithm"].isin(ALGORITHMS)]
    for item in tqdm(
        selected_ml.itertuples(index=False),
        total=len(selected_ml),
        desc="Selected-model permutation importance",
        unit="model",
    ):
        features = (
            manifest.loc[manifest["stage"].eq(item.stage)]
            .sort_values("feature_order")["feature"]
            .tolist()
        )
        table = pd.read_parquet(
            args.input_dir / "training_ready" / f"{item.stage}_residual_ml.parquet"
        )
        train, test = validate_inputs(table, features, item.stage, int(item.outer_fold))
        config = json.loads(item.selected_config_json)
        estimator = build_estimator(
            item.selected_algorithm,
            config,
            args.n_jobs,
            args.random_state + int(item.outer_fold),
        )
        estimator.fit(train[features], train["residual_days"].to_numpy(float))
        importance = permutation_importance(
            estimator,
            test[features],
            test["residual_days"].to_numpy(float),
            scoring="neg_mean_absolute_error",
            n_repeats=args.permutation_repeats,
            random_state=args.random_state + int(item.outer_fold),
            n_jobs=1,
        )
        for feature, mean, standard_deviation in zip(
            features, importance.importances_mean, importance.importances_std, strict=True
        ):
            records.append(
                {
                    "stage": item.stage,
                    "outer_fold": int(item.outer_fold),
                    "selected_algorithm": item.selected_algorithm,
                    "feature": feature,
                    "mae_increase_days_mean": float(mean),
                    "mae_increase_days_sd": float(standard_deviation),
                }
            )
    fold_table = pd.DataFrame(records)
    if fold_table.empty:
        return fold_table, fold_table
    aggregate = (
        fold_table.groupby(["stage", "feature"], as_index=False)
        .agg(
            n_selected_folds=("outer_fold", "nunique"),
            mean_mae_increase_days=("mae_increase_days_mean", "mean"),
            sd_across_folds=("mae_increase_days_mean", "std"),
        )
        .sort_values(["stage", "mean_mae_increase_days"], ascending=[True, False])
    )
    return fold_table, aggregate


def main() -> int:
    args = parse_args()
    predictions = pd.read_parquet(args.result_dir / "outer_spatial_predictions.parquet")
    selection = pd.read_csv(args.result_dir / "nested_algorithm_selection.csv")
    expected_selected = predictions.groupby(["stage", "outer_fold"])[
        "selected_by_inner_cv"
    ].sum()
    if not expected_selected.eq(
        predictions.groupby(["stage", "outer_fold"])["record_id"].nunique()
    ).all():
        raise ValueError("Each outer-test record must have exactly one inner-selected prediction")

    selected = predictions.loc[predictions["selected_by_inner_cv"]].copy()
    selected["source_algorithm"] = selected["algorithm"]
    selected["algorithm"] = "nested_selected"
    selected.to_parquet(
        args.result_dir / "nested_selected_outer_predictions.parquet", index=False
    )

    comparison = selected_comparison(predictions)
    comparison.to_csv(args.result_dir / "nested_selected_comparison.csv", index=False)
    frequency = (
        selection.groupby(["stage", "selected_algorithm"], as_index=False)
        .size()
        .rename(columns={"size": "n_outer_folds_selected"})
    )
    frequency.to_csv(args.result_dir / "algorithm_selection_frequency.csv", index=False)
    fold_importance, aggregate_importance = permutation_tables(args)
    fold_importance.to_csv(
        args.result_dir / "selected_model_permutation_importance_by_fold.csv", index=False
    )
    aggregate_importance.to_csv(
        args.result_dir / "selected_model_permutation_importance_summary.csv", index=False
    )

    audit = {
        "outer_prediction_rows": int(len(predictions)),
        "selected_prediction_rows": int(len(selected)),
        "unique_selected_records": int(selected["record_id"].nunique()),
        "one_selected_prediction_per_stage_outer_record": True,
        "permutation_importance_uses_outer_targets_only_after_inner_selection": True,
        "permutation_repeats": args.permutation_repeats,
    }
    (args.result_dir / "postrun_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nNested-selected comparison")
    print(comparison.round(3).to_string(index=False))
    print("\nAlgorithm selection frequency")
    print(frequency.to_string(index=False))
    print("\nPost-run audit")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
