import numpy as np
import pandas as pd

from src.modeling.run_residual_ml_models import (
    choose_by_min_mae,
    choose_by_min_rmse,
    choose_by_one_se,
    parameter_candidates,
    prediction_metrics,
    validate_inputs,
)


def test_smoke_search_has_one_configuration_per_algorithm():
    candidates = parameter_candidates("smoke")

    assert set(candidates) == {"ridge", "gam", "rf", "xgboost", "lightgbm"}
    assert all(len(configs) == 1 for configs in candidates.values())


def test_prediction_metrics_use_predicted_minus_observed_bias():
    metrics = prediction_metrics(
        observed=np.array([100.0, 110.0]),
        predicted=np.array([102.0, 106.0]),
    )

    assert metrics["mae_days"] == 3.0
    assert metrics["rmse_days"] == np.sqrt(10.0)
    assert metrics["bias_days"] == -1.0


def test_one_se_rule_excludes_mean_bias_reference_and_prefers_ridge():
    summary = pd.DataFrame(
        {
            "algorithm": ["mechanistic", "mean_bias", "ridge", "gam", "rf"],
            "mean_mae_days": [8.0, 7.1, 7.3, 7.2, 7.0],
            "mean_rmse_days": [11.0, 10.1, 10.3, 10.2, 10.0],
            "se_mae_days": [0.1, 0.1, 0.1, 0.2, 0.5],
        }
    )

    selected, cutoff, numeric_best = choose_by_one_se(summary)

    assert numeric_best == "rf"
    assert cutoff == 7.5
    assert selected == "ridge"


def test_min_mae_rule_excludes_mean_bias_reference_and_selects_numeric_best():
    summary = pd.DataFrame(
        {
            "algorithm": ["mechanistic", "mean_bias", "ridge", "gam", "rf"],
            "mean_mae_days": [8.0, 7.1, 7.3, 7.2, 7.0],
            "mean_rmse_days": [11.0, 10.1, 10.3, 10.2, 10.0],
            "pooled_bias_days": [0.0, 0.0, 0.2, -0.1, 0.3],
        }
    )

    selected, cutoff, numeric_best = choose_by_min_mae(summary)

    assert selected == "rf"
    assert numeric_best == "rf"
    assert cutoff == 7.0


def test_min_rmse_rule_excludes_mean_bias_reference_and_selects_lowest_rmse():
    summary = pd.DataFrame(
        {
            "algorithm": ["mechanistic", "mean_bias", "ridge", "gam", "rf"],
            "mean_mae_days": [8.0, 7.1, 7.3, 7.2, 7.0],
            "mean_rmse_days": [11.0, 10.1, 10.3, 10.0, 10.2],
            "pooled_bias_days": [0.0, 0.0, 0.2, -0.1, 0.3],
        }
    )

    selected, cutoff, numeric_best = choose_by_min_rmse(summary)

    assert selected == "gam"
    assert numeric_best == "gam"
    assert cutoff == 10.0


def test_validate_inputs_blocks_outer_fold_record_overlap():
    rows = []
    for inner_fold in (1, 2, 3, 4):
        rows.append(
            {
                "record_id": f"train-{inner_fold}",
                "dataset_role": "training_region_oof",
                "outer_fold": 1,
                "inner_fold": inner_fold,
                "event_assigned_outer_fold": 2,
                "residual_ml_eligible": True,
                "feature": float(inner_fold),
            }
        )
    rows.append(
        {
            "record_id": "test",
            "dataset_role": "spatial_test",
            "outer_fold": 1,
            "inner_fold": pd.NA,
            "event_assigned_outer_fold": 1,
            "residual_ml_eligible": True,
            "feature": 5.0,
        }
    )
    frame = pd.DataFrame(rows)

    train, test = validate_inputs(frame, ["feature"], "budburst", 1)

    assert len(train) == 4
    assert len(test) == 1
    assert not train["record_id"].isin(test["record_id"]).any()
