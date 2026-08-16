#!/usr/bin/env python
"""Evaluate predicted BBCH65 -> post-flowering GDD -> BBCH81 candidates."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

try:
    from src.modeling.mechanistic_models import (
        TEMPERATURE_BRANCH_COLUMNS,
        ThermalModelSpecification,
        default_model_specifications,
    )
    from src.modeling.run_mechanistic_baselines import (
        DEFAULT_VALIDATION_DIR,
        DEFAULT_WEATHER_DIR,
        REPO_ROOT,
        attach_inner_folds,
        build_profiles,
        calibrate_threshold_fast,
        load_weather_store,
        predict_events,
        read_primary_events,
    )
except ModuleNotFoundError:
    from mechanistic_models import (  # type: ignore
        TEMPERATURE_BRANCH_COLUMNS,
        ThermalModelSpecification,
        default_model_specifications,
    )
    from run_mechanistic_baselines import (  # type: ignore
        DEFAULT_VALIDATION_DIR,
        DEFAULT_WEATHER_DIR,
        REPO_ROOT,
        attach_inner_folds,
        build_profiles,
        calibrate_threshold_fast,
        load_weather_store,
        predict_events,
        read_primary_events,
    )


DEFAULT_BASELINE_DIR = REPO_ROOT / "data/phenology/derived/modeling/france_germany_four_stage/baseline_mechanistic"
DEFAULT_OUTPUT_DIR = DEFAULT_BASELINE_DIR / "bbch81_independent"
CHAIN_MODEL_ID = "veraison__predicted_flowering_post_gdd10"
CHAIN_METHOD = "predicted_flowering_post_gdd10"


@dataclass(frozen=True)
class ChainSpecification:
    model_id: str = CHAIN_MODEL_ID
    base_temperature_c: float = 10.0

    def as_thermal_specification(self) -> ThermalModelSpecification:
        return ThermalModelSpecification(
            model_id=self.model_id,
            stage="veraison",
            family="sequential_gdd",
            comparison_role="predicted_previous_stage_candidate",
            start_mode="previous_observed_stage",
            start_doy=0,
            base_temperature_c=self.base_temperature_c,
            threshold_mode="fit_training_fold_only",
            forcing_threshold_c_days=None,
            parameter_status="ready_for_nested_cv",
            literature_basis=(
                "Stage-continuity thermal-time candidate; accumulation starts after "
                "fold-specific predicted BBCH65, not observed BBCH65."
            ),
            notes="Only the BBCH65-to-BBCH81 forcing threshold is calibrated inside each active training fold.",
            analysis_set="independent_stage",
            selection_eligible=True,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-dir", type=Path, default=DEFAULT_VALIDATION_DIR)
    parser.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER_DIR)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--bbch81-audit-file",
        type=Path,
        default=None,
        help="Optional audited BBCH81 overrides used by the baseline run.",
    )
    parser.add_argument("--n-jobs", type=int, choices=(1, 2, 4), default=2)
    parser.add_argument("--n-candidates", type=int, default=401)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def score(group: pd.DataFrame, method: str, branch: str, country: str) -> dict[str, object]:
    valid = group.dropna(subset=["predicted_doy"])
    complete_errors = valid["predicted_doy"].to_numpy(float) - valid["observed_doy"].to_numpy(float)
    scored = group["predicted_doy"].copy()
    missing = scored.isna()
    if missing.any():
        scored.loc[missing] = group.loc[missing, "year"].map(
            lambda value: pd.Timestamp(int(value), 12, 31).dayofyear + 1
        ).to_numpy(float)
    penalized_errors = scored.to_numpy(float) - group["observed_doy"].to_numpy(float)
    return {
        "method": method,
        "temperature_branch": branch,
        "country_scope": country,
        "n_events": int(len(group)),
        "n_predicted": int(len(valid)),
        "coverage": float(len(valid) / len(group)) if len(group) else np.nan,
        "mae_days": float(np.mean(np.abs(complete_errors))) if len(valid) else np.nan,
        "rmse_days": float(np.sqrt(np.mean(complete_errors**2))) if len(valid) else np.nan,
        "bias_days": float(np.mean(complete_errors)) if len(valid) else np.nan,
        "penalized_mae_days": float(np.mean(np.abs(penalized_errors))) if len(group) else np.nan,
        "penalized_rmse_days": float(np.sqrt(np.mean(penalized_errors**2))) if len(group) else np.nan,
        "within_5_days_pct": float(np.mean(np.abs(complete_errors) <= 5) * 100) if len(valid) else np.nan,
        "within_7_days_pct": float(np.mean(np.abs(complete_errors) <= 7) * 100) if len(valid) else np.nan,
    }


def selected_flowering_model(
    selection: pd.DataFrame,
    outer_fold: int,
    branch: str,
) -> str:
    selected = selection.loc[
        selection["outer_fold"].eq(outer_fold)
        & selection["stage"].eq("flowering")
        & selection["temperature_branch"].eq(branch)
        & selection["selected"].astype(bool)
    ]
    if len(selected) != 1:
        raise ValueError(f"Expected one selected flowering model for fold={outer_fold}, branch={branch}")
    return str(selected.iloc[0]["model_id"])


def predict_flowering_starts(
    flowering_profiles: dict[str, tuple[np.ndarray, np.ndarray]],
    frame: pd.DataFrame,
    fits: pd.DataFrame,
    split: str,
    outer_fold: int,
    branch: str,
    flowering_model_id: str,
    inner_fold: int | None = None,
) -> pd.DataFrame:
    mask = (
        fits["split"].eq(split)
        & fits["outer_fold"].eq(outer_fold)
        & fits["model_id"].eq(flowering_model_id)
        & fits["temperature_branch"].eq(branch)
    )
    if inner_fold is not None:
        mask &= fits["inner_fold"].eq(inner_fold)
    fit_row = fits.loc[mask]
    if len(fit_row) != 1:
        raise ValueError("Missing unique fold-specific BBCH65 fit")
    prediction = predict_events(
        flowering_profiles,
        frame,
        float(fit_row.iloc[0]["forcing_threshold_c_days"]),
    )[["record_id", "predicted_doy"]]
    return prediction.rename(columns={"predicted_doy": "predicted_flowering_doy"})


def evaluate_fold(
    outer_fold: int,
    branch: str,
    veraison: pd.DataFrame,
    expanded_inner: pd.DataFrame,
    weather_store: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]],
    fits: pd.DataFrame,
    selection: pd.DataFrame,
    specifications: dict[str, ThermalModelSpecification],
    chain_specification: ThermalModelSpecification,
    n_candidates: int,
) -> tuple[list[dict[str, object]], pd.DataFrame, pd.DataFrame]:
    flowering_model_id = selected_flowering_model(selection, outer_fold, branch)
    flowering_specification = specifications[flowering_model_id]
    flowering_profiles = build_profiles(weather_store, veraison, flowering_specification, branch)

    train = veraison.loc[veraison["outer_spatial_fold"].ne(outer_fold)].copy()
    test = veraison.loc[veraison["outer_spatial_fold"].eq(outer_fold)].copy()
    inner_assignment = expanded_inner.loc[
        expanded_inner["target_stage"].eq("veraison")
        & expanded_inner["outer_test_fold"].eq(outer_fold),
        ["record_id", "inner_spatial_fold"],
    ]
    train = train.merge(inner_assignment, on="record_id", how="left", validate="one_to_one")
    if train["inner_spatial_fold"].isna().any():
        raise ValueError("Some BBCH81 training events have no training-region fold assignment")

    cross_fitted_starts = []
    for inner_fold in range(1, 5):
        subset = train.loc[train["inner_spatial_fold"].eq(inner_fold)]
        cross_fitted_starts.append(
            predict_flowering_starts(
                flowering_profiles,
                subset,
                fits,
                "inner_validation",
                outer_fold,
                branch,
                flowering_model_id,
                inner_fold,
            )
        )
    train_starts = pd.concat(cross_fitted_starts, ignore_index=True)
    train = train.merge(train_starts, on="record_id", how="left", validate="one_to_one")

    inner_fit_records: list[dict[str, object]] = []
    inner_prediction_frames: list[pd.DataFrame] = []
    for inner_fold in range(1, 5):
        inner_training = train.loc[train["inner_spatial_fold"].ne(inner_fold)].copy()
        inner_validation = train.loc[train["inner_spatial_fold"].eq(inner_fold)].copy()
        inner_training["previous_stage_doy"] = inner_training["predicted_flowering_doy"]
        inner_validation["previous_stage_doy"] = inner_validation["predicted_flowering_doy"]
        inner_training_profiles = build_profiles(
            weather_store, inner_training, chain_specification, branch
        )
        inner_fit = calibrate_threshold_fast(
            inner_training_profiles, inner_training, n_candidates
        )
        inner_validation_profiles = build_profiles(
            weather_store, inner_validation, chain_specification, branch
        )
        inner_prediction = predict_events(
            inner_validation_profiles,
            inner_validation,
            float(inner_fit["forcing_threshold_c_days"]),
        )
        inner_prediction = inner_prediction.merge(
            inner_validation[["record_id", "predicted_flowering_doy"]],
            on="record_id",
            how="left",
            validate="one_to_one",
        )
        inner_prediction.insert(0, "outer_fold", outer_fold)
        inner_prediction.insert(1, "inner_fold", inner_fold)
        inner_prediction.insert(2, "temperature_branch", branch)
        inner_prediction.insert(3, "method", CHAIN_METHOD)
        inner_prediction["flowering_model_id"] = flowering_model_id
        inner_prediction["veraison_forcing_threshold_c_days"] = float(
            inner_fit["forcing_threshold_c_days"]
        )
        inner_prediction["predicted_stage_order_valid"] = (
            inner_prediction["predicted_flowering_doy"] < inner_prediction["predicted_doy"]
        )
        inner_prediction_frames.append(inner_prediction)
        inner_fit_records.append(
            {
                "split": "inner_validation",
                "outer_fold": outer_fold,
                "inner_fold": inner_fold,
                "temperature_branch": branch,
                "flowering_model_id": flowering_model_id,
                "n_bbch81_training_events": int(len(inner_training)),
                "n_bbch81_validation_events": int(len(inner_validation)),
                "training_predicted_flowering_coverage": float(
                    inner_training["predicted_flowering_doy"].notna().mean()
                ),
                "validation_predicted_flowering_coverage": float(
                    inner_validation["predicted_flowering_doy"].notna().mean()
                ),
                **inner_fit,
            }
        )

    test_starts = predict_flowering_starts(
        flowering_profiles,
        test,
        fits,
        "outer_test",
        outer_fold,
        branch,
        flowering_model_id,
    )
    test = test.merge(test_starts, on="record_id", how="left", validate="one_to_one")
    train_forcing = train.copy()
    test_forcing = test.copy()
    train_forcing["previous_stage_doy"] = train_forcing["predicted_flowering_doy"]
    test_forcing["previous_stage_doy"] = test_forcing["predicted_flowering_doy"]
    train_profiles = build_profiles(weather_store, train_forcing, chain_specification, branch)
    outer_fit = calibrate_threshold_fast(train_profiles, train_forcing, n_candidates)
    test_profiles = build_profiles(weather_store, test_forcing, chain_specification, branch)
    prediction = predict_events(
        test_profiles,
        test_forcing,
        float(outer_fit["forcing_threshold_c_days"]),
    )
    prediction = prediction.merge(
        test[["record_id", "predicted_flowering_doy"]],
        on="record_id",
        how="left",
        validate="one_to_one",
    )
    prediction.insert(0, "outer_fold", outer_fold)
    prediction.insert(1, "temperature_branch", branch)
    prediction.insert(2, "method", CHAIN_METHOD)
    prediction["flowering_model_id"] = flowering_model_id
    prediction["veraison_forcing_threshold_c_days"] = float(
        outer_fit["forcing_threshold_c_days"]
    )
    prediction["predicted_stage_order_valid"] = (
        prediction["predicted_flowering_doy"] < prediction["predicted_doy"]
    )
    fit_record = {
        "split": "outer_test",
        "outer_fold": outer_fold,
        "inner_fold": None,
        "temperature_branch": branch,
        "flowering_model_id": flowering_model_id,
        "n_bbch81_training_events": int(len(train)),
        "n_bbch81_test_events": int(len(test)),
        "training_predicted_flowering_coverage": float(train["predicted_flowering_doy"].notna().mean()),
        "test_predicted_flowering_coverage": float(test["predicted_flowering_doy"].notna().mean()),
        **outer_fit,
    }
    return [*inner_fit_records, fit_record], prediction, pd.concat(
        inner_prediction_frames, ignore_index=True
    )


def main() -> int:
    args = parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"Output directory is not empty: {args.output_dir}; use --overwrite")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    events = read_primary_events(
        args.validation_dir, bbch81_audit_file=args.bbch81_audit_file
    )
    veraison = events.loc[events["target_stage"].eq("veraison")].copy()
    expanded_inner = attach_inner_folds(events, args.validation_dir)
    fits = pd.read_csv(args.baseline_dir / "nested_cv_threshold_fits.csv")
    selection = pd.read_csv(args.baseline_dir / "inner_cv_model_selection.csv")
    specifications = {spec.model_id: spec for spec in default_model_specifications()}
    chain_specification = ChainSpecification().as_thermal_specification()
    weather_store = load_weather_store(args.weather_dir, set(veraison["weather_id"]))

    tasks = [(outer_fold, branch) for branch in TEMPERATURE_BRANCH_COLUMNS for outer_fold in range(1, 6)]
    fit_records: list[dict[str, object]] = []
    prediction_frames: list[pd.DataFrame] = []
    inner_prediction_frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=args.n_jobs) as executor:
        futures = {
            executor.submit(
                evaluate_fold,
                outer_fold,
                branch,
                veraison,
                expanded_inner,
                weather_store,
                fits,
                selection,
                specifications,
                chain_specification,
                args.n_candidates,
            ): (outer_fold, branch)
            for outer_fold, branch in tasks
        }
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc="BBCH65 prediction -> BBCH81",
            unit="fold",
        ):
            fold_fit_records, prediction, inner_prediction = future.result()
            fit_records.extend(fold_fit_records)
            prediction_frames.append(prediction)
            inner_prediction_frames.append(inner_prediction)

    chain = pd.concat(prediction_frames, ignore_index=True)
    inner_chain = pd.concat(inner_prediction_frames, ignore_index=True)
    baseline = pd.read_parquet(args.baseline_dir / "selected_model_outer_predictions.parquet")
    baseline = baseline.loc[baseline["stage"].eq("veraison")].copy()
    baseline = baseline[
        ["outer_fold", "temperature_branch", "record_id", "weather_id", "country", "year", "observed_doy", "predicted_doy", "threshold_reached"]
    ]
    baseline.insert(2, "method", "selected_independent_baseline")
    if set(chain["record_id"]) != set(baseline["record_id"]):
        raise ValueError("Chain and selected independent models do not use identical BBCH81 records")
    if len(chain) != len(baseline):
        raise ValueError("Chain and selected independent predictions are not one-to-one comparable")
    comparison = pd.concat([baseline, chain], ignore_index=True, sort=False)
    metric_records = []
    for (method, branch), group in comparison.groupby(["method", "temperature_branch"]):
        metric_records.append(score(group, method, branch, "France+Germany"))
        for country, country_group in group.groupby("country"):
            metric_records.append(score(country_group, method, branch, country))
    metrics = pd.DataFrame(metric_records)

    chain.to_parquet(args.output_dir / "predicted_flowering_to_bbch81_outer_predictions.parquet", index=False)
    inner_chain.to_parquet(
        args.output_dir / "predicted_flowering_to_bbch81_inner_predictions.parquet", index=False
    )
    fit_frame = pd.DataFrame(fit_records).sort_values(
        ["split", "temperature_branch", "outer_fold", "inner_fold"], na_position="last"
    )
    fit_frame.to_csv(
        args.output_dir / "predicted_flowering_to_bbch81_threshold_fits.csv", index=False
    )
    fit_frame.loc[fit_frame["split"].eq("inner_validation")].to_csv(
        args.output_dir / "predicted_flowering_to_bbch81_inner_threshold_fits.csv", index=False
    )
    comparison.to_parquet(args.output_dir / "common_sample_method_comparison.parquet", index=False)
    metrics.to_csv(args.output_dir / "common_sample_method_metrics.csv", index=False)
    summary = {
        "scope": "BBCH81 independent stage-continuity candidate",
        "bbch81_events": int(len(veraison)),
        "temperature_branches": list(TEMPERATURE_BRANCH_COLUMNS),
        "spatial_test_rounds": 5,
        "training_region_selection_folds_per_round": 4,
        "inner_chain_prediction_rows": int(len(inner_chain)),
        "common_sample_check": True,
        "training_start_rule": "BBCH65 predicted by training-region four-fold cross-fitting",
        "test_start_rule": "BBCH65 predicted by model fitted only on current training region",
        "chain_model_id": CHAIN_MODEL_ID,
        "chain_base_temperature_c": chain_specification.base_temperature_c,
        "n_jobs": args.n_jobs,
        "n_candidates": args.n_candidates,
        "bbch81_audit_file": (
            str(args.bbch81_audit_file) if args.bbch81_audit_file is not None else None
        ),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    (args.output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nBBCH81 predicted-flowering chain completed")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nCommon-sample metrics")
    print(metrics.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
