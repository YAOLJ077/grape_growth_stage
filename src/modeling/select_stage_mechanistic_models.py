#!/usr/bin/env python
"""Select France-Germany stage models from training-region spatial OOF predictions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

try:
    from src.modeling.run_mechanistic_baselines import DEFAULT_OUTPUT_DIR, build_metrics
    from src.modeling.stage_model_selection import build_final_selection_record, formal_stage_selection
except ModuleNotFoundError:
    from run_mechanistic_baselines import DEFAULT_OUTPUT_DIR, build_metrics  # type: ignore
    from stage_model_selection import build_final_selection_record, formal_stage_selection  # type: ignore


VERAISON_CHAIN_MODEL_ID = "veraison__predicted_flowering_post_gdd10"
HARVEST_CHAIN_MODEL_ID = "maturity_or_harvest__predicted_veraison_post_gdd10"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--require-bbch89-chain", action="store_true")
    return parser.parse_args()


def standardize_chain_predictions(
    frame: pd.DataFrame,
    split: str,
    model_id: str,
    stage: str,
) -> pd.DataFrame:
    result = frame.copy()
    result["split"] = split
    result["model_id"] = model_id
    result["stage"] = stage
    result["analysis_set"] = "independent_stage"
    result["selection_eligible"] = True
    if "forcing_threshold_c_days" not in result:
        if "harvest_forcing_threshold_c_days" in result:
            result["forcing_threshold_c_days"] = result["harvest_forcing_threshold_c_days"]
        elif "veraison_forcing_threshold_c_days" in result:
            result["forcing_threshold_c_days"] = result["veraison_forcing_threshold_c_days"]
        else:
            raise ValueError("Chain predictions do not contain a forcing threshold column")
    columns = [
        "split", "outer_fold", "inner_fold", "model_id", "stage", "analysis_set",
        "selection_eligible", "temperature_branch", "forcing_threshold_c_days",
        "record_id", "weather_id", "country", "year", "observed_doy",
        "predicted_doy", "threshold_reached",
    ]
    for optional in ("predicted_flowering_doy", "predicted_veraison_doy"):
        if optional in result:
            columns.append(optional)
    return result[columns]


def load_selection_predictions(baseline_dir: Path, require_chain: bool) -> tuple[pd.DataFrame, bool]:
    baseline = pd.read_parquet(baseline_dir / "nested_cv_predictions.parquet")
    baseline = baseline.loc[
        baseline["analysis_set"].eq("independent_stage")
        & baseline["selection_eligible"].astype(bool)
    ].copy()
    chain_frames = []
    veraison_inner_path = (
        baseline_dir / "bbch81_independent" / "predicted_flowering_to_bbch81_inner_predictions.parquet"
    )
    if veraison_inner_path.exists():
        chain_frames.append(
            standardize_chain_predictions(
                pd.read_parquet(veraison_inner_path),
                "inner_validation",
                VERAISON_CHAIN_MODEL_ID,
                "veraison",
            )
        )
    harvest_inner_path = (
        baseline_dir / "bbch89_independent" / "predicted_veraison_to_bbch89_inner_predictions.parquet"
    )
    if harvest_inner_path.exists():
        chain_frames.append(
            standardize_chain_predictions(
                pd.read_parquet(harvest_inner_path),
                "inner_validation",
                HARVEST_CHAIN_MODEL_ID,
                "maturity_or_harvest",
            )
        )
    if not chain_frames:
        if require_chain:
            raise FileNotFoundError(f"Required chain predictions are missing under {baseline_dir}")
        return baseline, False
    return pd.concat([baseline, *chain_frames], ignore_index=True, sort=False), True


def selected_outer_predictions(
    baseline_dir: Path, decisions: pd.DataFrame, chain_available: bool
) -> pd.DataFrame:
    baseline = pd.read_parquet(baseline_dir / "nested_cv_predictions.parquet")
    baseline = baseline.loc[baseline["split"].eq("outer_test")].copy()
    frames = [baseline]
    veraison_chain_path = (
        baseline_dir / "bbch81_independent" / "predicted_flowering_to_bbch81_outer_predictions.parquet"
    )
    if chain_available and veraison_chain_path.exists():
        chain = pd.read_parquet(veraison_chain_path).copy()
        chain["inner_fold"] = pd.NA
        frames.append(
            standardize_chain_predictions(chain, "outer_test", VERAISON_CHAIN_MODEL_ID, "veraison")
        )
    harvest_chain_path = (
        baseline_dir / "bbch89_independent" / "predicted_veraison_to_bbch89_outer_predictions.parquet"
    )
    if chain_available and harvest_chain_path.exists():
        chain = pd.read_parquet(harvest_chain_path).copy()
        chain["inner_fold"] = pd.NA
        frames.append(
            standardize_chain_predictions(
                chain, "outer_test", HARVEST_CHAIN_MODEL_ID, "maturity_or_harvest"
            )
        )
    outer = pd.concat(frames, ignore_index=True, sort=False)
    chosen = decisions.rename(
        columns={
            "selected_temperature_branch": "temperature_branch",
            "selected_model_id": "model_id",
        }
    )[["outer_fold", "stage", "temperature_branch", "model_id"]]
    result = outer.merge(
        chosen,
        on=["outer_fold", "stage", "temperature_branch", "model_id"],
        how="inner",
        validate="many_to_one",
    )
    if result.duplicated(["record_id", "stage"]).any():
        raise ValueError("Formal selected outer predictions contain duplicate record-stage rows")
    if result.empty or result["outer_fold"].nunique() != 5:
        raise ValueError("Formal selected outer predictions do not cover all spatial test rounds")
    return result


def main() -> int:
    args = parse_args()
    predictions, chain_available = load_selection_predictions(
        args.baseline_dir, args.require_bbch89_chain
    )
    metrics, stability, decisions, consensus = formal_stage_selection(predictions)
    final_record = build_final_selection_record(consensus)

    metrics.to_csv(args.baseline_dir / "stage_model_selection_metrics.csv", index=False)
    stability.to_csv(args.baseline_dir / "stage_model_stability.csv", index=False)
    decisions.to_csv(args.baseline_dir / "stage_model_selection_decisions.csv", index=False)
    consensus.to_csv(args.baseline_dir / "stage_model_selection_consensus.csv", index=False)
    final_record.to_csv(args.baseline_dir / "stage_model_final_selection.csv", index=False)

    backward = metrics.rename(
        columns={
            "mean_penalized_rmse_days": "inner_oof_rmse_days",
            "mean_penalized_mae_days": "inner_oof_mae_days",
            "pooled_complete_case_rmse_days": "inner_oof_complete_case_rmse_days",
            "mean_coverage_qc": "inner_oof_coverage",
            "selected_within_temperature_branch": "selected",
        }
    )
    backward.to_csv(args.baseline_dir / "inner_cv_model_selection.csv", index=False)

    outer = selected_outer_predictions(args.baseline_dir, decisions, chain_available)
    outer.to_parquet(args.baseline_dir / "formal_selected_model_outer_predictions.parquet", index=False)
    outer_metrics = build_metrics(outer)
    outer_metrics.to_csv(args.baseline_dir / "formal_selected_model_outer_metrics.csv", index=False)

    summary = {
        "selection_scope": "training-region four-fold spatial OOF predictions only",
        "bbch89_predicted_veraison_chain_included": chain_available,
        "candidate_rows": int(len(metrics)),
        "stability_rows": int(len(stability)),
        "decision_rows": int(len(decisions)),
        "stages": sorted(decisions["stage"].unique().tolist()),
        "independent_test_used_for_selection": False,
    }
    (args.baseline_dir / "stage_model_selection_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nFormal stage-model selection completed")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nSelection decisions")
    print(decisions.round(3).to_string(index=False))
    print("\nSelection consensus")
    print(consensus.round(3).to_string(index=False))
    print("\nFinal selection record")
    print(final_record.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
