"""Formal multi-metric selection for spatially cross-validated stage models."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


SELECTION_KEYS = ["outer_fold", "stage", "temperature_branch", "model_id"]


def _penalized_prediction(frame: pd.DataFrame) -> pd.Series:
    scored = frame["predicted_doy"].copy()
    missing = scored.isna()
    if missing.any():
        scored.loc[missing] = frame.loc[missing, "year"].map(
            lambda year: pd.Timestamp(year=int(year), month=12, day=31).dayofyear + 1
        ).to_numpy(float)
    return scored.astype(float)


def build_stability_table(predictions: pd.DataFrame) -> pd.DataFrame:
    """Return one metric row per candidate and training-region validation fold."""
    required = {
        "split", "outer_fold", "inner_fold", "model_id", "stage",
        "selection_eligible", "temperature_branch", "observed_doy",
        "predicted_doy", "year",
    }
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"Selection predictions are missing columns: {sorted(missing)}")
    candidates = predictions.loc[
        predictions["split"].eq("inner_validation")
        & predictions["selection_eligible"].astype(bool)
    ].copy()
    if candidates.empty:
        raise ValueError("No selection-eligible inner-validation predictions were found")
    records: list[dict[str, object]] = []
    keys = [*SELECTION_KEYS, "inner_fold"]
    for values, group in candidates.groupby(keys, sort=True, dropna=False):
        grouping = dict(zip(keys, values, strict=True))
        valid = group.dropna(subset=["predicted_doy"])
        complete_errors = (
            valid["predicted_doy"].to_numpy(float) - valid["observed_doy"].to_numpy(float)
        )
        penalized_errors = (
            _penalized_prediction(group).to_numpy(float)
            - group["observed_doy"].to_numpy(float)
        )
        records.append(
            {
                **grouping,
                "n_events": int(len(group)),
                "n_predicted": int(len(valid)),
                "coverage": float(len(valid) / len(group)),
                "penalized_mae_days": float(np.mean(np.abs(penalized_errors))),
                "penalized_rmse_days": float(np.sqrt(np.mean(penalized_errors**2))),
                "complete_case_mae_days": (
                    float(np.mean(np.abs(complete_errors))) if len(valid) else np.nan
                ),
                "complete_case_rmse_days": (
                    float(np.sqrt(np.mean(complete_errors**2))) if len(valid) else np.nan
                ),
                "bias_days": float(np.mean(complete_errors)) if len(valid) else np.nan,
            }
        )
    result = pd.DataFrame.from_records(records)
    expected = result.groupby(SELECTION_KEYS, dropna=False)["inner_fold"].nunique()
    if not expected.eq(4).all():
        bad = expected.loc[~expected.eq(4)].to_dict()
        raise ValueError(f"Every candidate must have four training-region validation folds: {bad}")
    return result.sort_values(keys).reset_index(drop=True)


def aggregate_candidate_metrics(
    predictions: pd.DataFrame, stability: pd.DataFrame
) -> pd.DataFrame:
    """Aggregate fold stability and pooled out-of-fold diagnostics by candidate."""
    candidates = predictions.loc[
        predictions["split"].eq("inner_validation")
        & predictions["selection_eligible"].astype(bool)
    ].copy()
    records: list[dict[str, object]] = []
    for values, group in candidates.groupby(SELECTION_KEYS, sort=True):
        grouping = dict(zip(SELECTION_KEYS, values, strict=True))
        fold = stability
        for key, value in grouping.items():
            fold = fold.loc[fold[key].eq(value)]
        valid = group.dropna(subset=["predicted_doy"])
        complete_errors = (
            valid["predicted_doy"].to_numpy(float) - valid["observed_doy"].to_numpy(float)
        )
        penalized_errors = (
            _penalized_prediction(group).to_numpy(float)
            - group["observed_doy"].to_numpy(float)
        )
        mae_sd = float(fold["penalized_mae_days"].std(ddof=1))
        records.append(
            {
                **grouping,
                "n_inner_oof_events": int(len(group)),
                "n_inner_folds": int(len(fold)),
                "mean_penalized_mae_days": float(fold["penalized_mae_days"].mean()),
                "sd_penalized_mae_days": mae_sd,
                "se_penalized_mae_days": mae_sd / math.sqrt(len(fold)),
                "max_penalized_mae_days": float(fold["penalized_mae_days"].max()),
                "mean_penalized_rmse_days": float(fold["penalized_rmse_days"].mean()),
                "sd_penalized_rmse_days": float(fold["penalized_rmse_days"].std(ddof=1)),
                "pooled_penalized_mae_days": float(np.mean(np.abs(penalized_errors))),
                "pooled_penalized_rmse_days": float(np.sqrt(np.mean(penalized_errors**2))),
                "pooled_complete_case_mae_days": (
                    float(np.mean(np.abs(complete_errors))) if len(valid) else np.nan
                ),
                "pooled_complete_case_rmse_days": (
                    float(np.sqrt(np.mean(complete_errors**2))) if len(valid) else np.nan
                ),
                "pooled_bias_days": float(np.mean(complete_errors)) if len(valid) else np.nan,
                "abs_pooled_bias_days": (
                    float(abs(np.mean(complete_errors))) if len(valid) else np.nan
                ),
                "mean_coverage_qc": float(fold["coverage"].mean()),
                "min_coverage_qc": float(fold["coverage"].min()),
                "bias_sign_consistent": bool(
                    (fold["bias_days"].dropna() >= 0).all()
                    or (fold["bias_days"].dropna() <= 0).all()
                ),
            }
        )
    return pd.DataFrame.from_records(records).sort_values(SELECTION_KEYS).reset_index(drop=True)


def _rank_one_group(group: pd.DataFrame) -> pd.DataFrame:
    result = group.copy()
    best_mae_row = result.sort_values(
        ["mean_penalized_mae_days", "model_id", "temperature_branch"]
    ).iloc[0]
    cutoff = float(
        best_mae_row["mean_penalized_mae_days"]
        + best_mae_row["se_penalized_mae_days"]
    )
    result["one_se_mae_cutoff_days"] = cutoff
    result["within_one_se"] = result["mean_penalized_mae_days"].le(cutoff + 1e-12)
    eligible = result.loc[result["within_one_se"]].sort_values(
        [
            "mean_penalized_rmse_days",
            "abs_pooled_bias_days",
            "sd_penalized_mae_days",
            "max_penalized_mae_days",
            "model_id",
            "temperature_branch",
        ],
        kind="mergesort",
    )
    winner_index = eligible.index[0]
    result["selected"] = result.index.to_numpy() == winner_index
    result["selection_rank"] = np.nan
    ordered = pd.concat(
        [eligible, result.loc[~result["within_one_se"]].sort_values(
            ["mean_penalized_mae_days", "mean_penalized_rmse_days", "model_id"]
        )]
    )
    result.loc[ordered.index, "selection_rank"] = np.arange(1, len(result) + 1)
    result["selection_rank"] = result["selection_rank"].astype(int)
    return result


def select_candidates(
    metrics: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Select structure within temperature branch, then select final branch."""
    within_frames = []
    for _, group in metrics.groupby(
        ["outer_fold", "stage", "temperature_branch"], sort=True
    ):
        within_frames.append(_rank_one_group(group))
    within = pd.concat(within_frames, ignore_index=True)
    within = within.rename(
        columns={
            "within_one_se": "within_branch_one_se",
            "selected": "selected_within_temperature_branch",
            "selection_rank": "within_branch_rank",
            "one_se_mae_cutoff_days": "within_branch_one_se_mae_cutoff_days",
        }
    )

    branch_winners = within.loc[within["selected_within_temperature_branch"]].copy()
    final_frames = []
    for _, group in branch_winners.groupby(["outer_fold", "stage"], sort=True):
        final_frames.append(_rank_one_group(group))
    final_ranked = pd.concat(final_frames, ignore_index=True).rename(
        columns={
            "within_one_se": "final_one_se",
            "selected": "selected_final",
            "selection_rank": "final_rank",
            "one_se_mae_cutoff_days": "final_one_se_mae_cutoff_days",
        }
    )
    final_columns = [
        "outer_fold", "stage", "temperature_branch", "model_id",
        "final_one_se", "selected_final", "final_rank",
        "final_one_se_mae_cutoff_days",
    ]
    annotated = within.merge(
        final_ranked[final_columns],
        on=["outer_fold", "stage", "temperature_branch", "model_id"],
        how="left",
        validate="many_to_one",
    )
    annotated["final_one_se"] = annotated["final_one_se"].eq(True)
    annotated["selected_final"] = annotated["selected_final"].eq(True)

    decisions = final_ranked.loc[final_ranked["selected_final"]].copy()
    decisions = decisions[
        [
            "outer_fold", "stage", "temperature_branch", "model_id",
            "mean_penalized_mae_days", "mean_penalized_rmse_days",
            "pooled_bias_days", "sd_penalized_mae_days",
            "max_penalized_mae_days", "mean_coverage_qc",
            "final_one_se_mae_cutoff_days",
        ]
    ].rename(
        columns={
            "temperature_branch": "selected_temperature_branch",
            "model_id": "selected_model_id",
        }
    )
    decisions["selection_basis"] = (
        "four-fold spatial OOF; one-SE MAE screen; RMSE, absolute bias, and stability tie-break"
    )

    consensus = (
        decisions.groupby(
            ["stage", "selected_temperature_branch", "selected_model_id"], sort=True
        )
        .size()
        .rename("n_selected_outer_rounds")
        .reset_index()
    )
    consensus["selection_frequency"] = consensus["n_selected_outer_rounds"] / 5.0
    consensus["unanimous_across_outer_rounds"] = consensus["n_selected_outer_rounds"].eq(5)
    return (
        annotated.sort_values(["outer_fold", "stage", "within_branch_rank"]).reset_index(drop=True),
        decisions.sort_values(["stage", "outer_fold"]).reset_index(drop=True),
        consensus.sort_values(
            ["stage", "n_selected_outer_rounds", "selected_model_id"],
            ascending=[True, False, True],
        ).reset_index(drop=True),
    )


def formal_stage_selection(
    predictions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    stability = build_stability_table(predictions)
    metrics = aggregate_candidate_metrics(predictions, stability)
    annotated, decisions, consensus = select_candidates(metrics)
    return annotated, stability, decisions, consensus


def build_final_selection_record(consensus: pd.DataFrame) -> pd.DataFrame:
    """Freeze model structure and temperature branch at their supported levels.

    A model structure can be unanimous even when raw and adjusted temperature
    alternate across rounds.  In that case the structure is frozen, while the
    temperature branch remains explicitly unresolved.
    """
    records: list[dict[str, object]] = []
    for stage, group in consensus.groupby("stage", sort=True):
        unanimous = group.loc[group["unanimous_across_outer_rounds"].astype(bool)]
        if len(unanimous) == 1:
            row = unanimous.iloc[0]
            records.append(
                {
                    "stage": stage,
                    "final_temperature_branch": row["selected_temperature_branch"],
                    "final_model_id": row["selected_model_id"],
                    "n_consistent_outer_rounds": int(row["n_selected_outer_rounds"]),
                    "selection_status": "frozen_unanimous_5_of_5",
                }
            )
        else:
            structure = (
                group.groupby("selected_model_id", dropna=False)["n_selected_outer_rounds"]
                .sum()
                .sort_values(ascending=False)
            )
            unanimous_structure = structure.loc[structure.eq(5)]
            if len(unanimous_structure) == 1:
                records.append(
                    {
                        "stage": stage,
                        "final_temperature_branch": pd.NA,
                        "final_model_id": unanimous_structure.index[0],
                        "n_consistent_outer_rounds": 5,
                        "selection_status": "model_frozen_5_of_5_temperature_branch_unresolved",
                    }
                )
                continue
            records.append(
                {
                    "stage": stage,
                    "final_temperature_branch": pd.NA,
                    "final_model_id": pd.NA,
                    "n_consistent_outer_rounds": int(group["n_selected_outer_rounds"].max()),
                    "selection_status": "unresolved_no_unanimous_candidate",
                }
            )
    return pd.DataFrame.from_records(records)
