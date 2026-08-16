import pandas as pd

from src.modeling.stage_model_selection import (
    build_final_selection_record,
    formal_stage_selection,
)


def selection_predictions() -> pd.DataFrame:
    rows = []
    candidates = [
        ("adjusted_6p5", "model_a", 1.0),
        ("adjusted_6p5", "model_b", 2.0),
        ("raw", "model_a", 3.0),
    ]
    record = 0
    for branch, model_id, error in candidates:
        for inner_fold in range(1, 5):
            for replicate in range(2):
                record += 1
                rows.append(
                    {
                        "split": "inner_validation",
                        "outer_fold": 1,
                        "inner_fold": inner_fold,
                        "model_id": model_id,
                        "stage": "flowering",
                        "analysis_set": "independent_stage",
                        "selection_eligible": True,
                        "temperature_branch": branch,
                        "record_id": f"r{record}",
                        "year": 2000,
                        "observed_doy": 150.0,
                        "predicted_doy": 150.0 + error,
                    }
                )
    return pd.DataFrame(rows)


def test_formal_selection_builds_fold_stability_and_hierarchical_decision():
    metrics, stability, decisions, consensus = formal_stage_selection(
        selection_predictions()
    )

    assert len(metrics) == 3
    assert len(stability) == 12
    assert stability.groupby(
        ["outer_fold", "stage", "temperature_branch", "model_id"]
    )["inner_fold"].nunique().eq(4).all()

    within_adjusted = metrics.loc[
        metrics["temperature_branch"].eq("adjusted_6p5")
        & metrics["selected_within_temperature_branch"]
    ]
    assert within_adjusted["model_id"].tolist() == ["model_a"]
    assert decisions.loc[0, "selected_temperature_branch"] == "adjusted_6p5"
    assert decisions.loc[0, "selected_model_id"] == "model_a"
    assert consensus.loc[0, "n_selected_outer_rounds"] == 1


def test_final_record_requires_unanimous_five_round_consensus():
    consensus = pd.DataFrame(
        {
            "stage": ["flowering", "veraison"],
            "selected_temperature_branch": ["adjusted_6p5", "raw"],
            "selected_model_id": ["gfv", "gfv"],
            "n_selected_outer_rounds": [5, 4],
            "selection_frequency": [1.0, 0.8],
            "unanimous_across_outer_rounds": [True, False],
        }
    )

    result = build_final_selection_record(consensus).set_index("stage")

    assert result.loc["flowering", "final_model_id"] == "gfv"
    assert result.loc["flowering", "selection_status"] == "frozen_unanimous_5_of_5"
    assert pd.isna(result.loc["veraison", "final_model_id"])


def test_final_record_can_freeze_structure_when_temperature_branch_varies():
    consensus = pd.DataFrame(
        {
            "stage": ["budburst", "budburst"],
            "selected_temperature_branch": ["adjusted_6p5", "raw"],
            "selected_model_id": ["brin", "brin"],
            "n_selected_outer_rounds": [3, 2],
            "selection_frequency": [0.6, 0.4],
            "unanimous_across_outer_rounds": [False, False],
        }
    )

    result = build_final_selection_record(consensus).iloc[0]

    assert result["final_model_id"] == "brin"
    assert pd.isna(result["final_temperature_branch"])
    assert result["selection_status"] == (
        "model_frozen_5_of_5_temperature_branch_unresolved"
    )


def test_unreached_threshold_is_included_in_penalized_selection_error():
    frame = selection_predictions()
    mask = frame["temperature_branch"].eq("raw") & frame["inner_fold"].eq(1)
    frame.loc[mask, "predicted_doy"] = pd.NA

    metrics, stability, _, _ = formal_stage_selection(frame)
    raw = metrics.loc[metrics["temperature_branch"].eq("raw")].iloc[0]
    raw_fold = stability.loc[
        stability["temperature_branch"].eq("raw")
        & stability["inner_fold"].eq(1)
    ].iloc[0]

    assert raw_fold["coverage"] == 0.0
    assert raw_fold["penalized_mae_days"] == 217.0
    assert raw["mean_penalized_mae_days"] > raw["pooled_complete_case_mae_days"]
