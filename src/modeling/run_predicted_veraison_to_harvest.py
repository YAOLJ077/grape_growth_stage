#!/usr/bin/env python
"""Evaluate BBCH81-prediction -> post-veraison GDD -> BBCH89 on common samples.

For each five-fold spatial test round, BBCH81 starts in the training region are
cross-fitted by the training-region four-fold models. Starts in the spatially
held-out test region are predicted by a BBCH81 model fitted only on the current
training region. The BBCH89 GDD threshold is then calibrated on the training
region and evaluated on exactly the same BBCH89 test records as seasonal GDD10.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

try:
    from src.modeling.mechanistic_models import TEMPERATURE_BRANCH_COLUMNS, default_model_specifications
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
    from mechanistic_models import TEMPERATURE_BRANCH_COLUMNS, default_model_specifications  # type: ignore
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
DEFAULT_OUTPUT_DIR = DEFAULT_BASELINE_DIR / "bbch89_independent"


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
        "coverage": float(len(valid) / len(group)),
        "mae_days": float(np.mean(np.abs(complete_errors))) if len(valid) else np.nan,
        "rmse_days": float(np.sqrt(np.mean(complete_errors**2))) if len(valid) else np.nan,
        "bias_days": float(np.mean(complete_errors)) if len(valid) else np.nan,
        "penalized_mae_days": float(np.mean(np.abs(penalized_errors))),
        "penalized_rmse_days": float(np.sqrt(np.mean(penalized_errors**2))),
        "within_5_days_pct": float(np.mean(np.abs(complete_errors) <= 5) * 100) if len(valid) else np.nan,
        "within_7_days_pct": float(np.mean(np.abs(complete_errors) <= 7) * 100) if len(valid) else np.nan,
    }


def evaluate_fold(
    outer_fold: int,
    branch: str,
    maturity: pd.DataFrame,
    expanded_inner: pd.DataFrame,
    weather_store: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]],
    fits: pd.DataFrame,
    selection: pd.DataFrame,
    specifications: dict[str, object],
    n_candidates: int,
) -> tuple[list[dict[str, object]], pd.DataFrame, pd.DataFrame]:
    selected = selection.loc[
        selection["outer_fold"].eq(outer_fold)
        & selection["stage"].eq("veraison")
        & selection["temperature_branch"].eq(branch)
        & selection["selected"].astype(bool)
    ]
    if len(selected) != 1:
        raise ValueError(f"Expected one selected veraison model for fold={outer_fold}, branch={branch}")
    veraison_model_id = str(selected.iloc[0]["model_id"])
    veraison_specification = specifications[veraison_model_id]
    post_veraison_specification = specifications[
        "maturity_or_harvest__calibrated_post_veraison_gdd10"
    ]
    veraison_profiles = build_profiles(weather_store, maturity, veraison_specification, branch)

    train = maturity.loc[maturity["outer_spatial_fold"].ne(outer_fold)].copy()
    test = maturity.loc[maturity["outer_spatial_fold"].eq(outer_fold)].copy()
    inner_assignment = expanded_inner.loc[
        expanded_inner["target_stage"].eq("maturity_or_harvest")
        & expanded_inner["outer_test_fold"].eq(outer_fold),
        ["record_id", "inner_spatial_fold"],
    ]
    train = train.merge(inner_assignment, on="record_id", how="left", validate="one_to_one")
    if train["inner_spatial_fold"].isna().any():
        raise ValueError("Some BBCH89 training events have no training-region fold assignment")

    cross_fitted_starts = []
    for inner_fold in range(1, 5):
        subset = train.loc[train["inner_spatial_fold"].eq(inner_fold)]
        fit_row = fits.loc[
            fits["split"].eq("inner_validation")
            & fits["outer_fold"].eq(outer_fold)
            & fits["inner_fold"].eq(inner_fold)
            & fits["model_id"].eq(veraison_model_id)
            & fits["temperature_branch"].eq(branch)
        ]
        if len(fit_row) != 1:
            raise ValueError("Missing unique training-region BBCH81 fit")
        prediction = predict_events(
            veraison_profiles,
            subset,
            float(fit_row.iloc[0]["forcing_threshold_c_days"]),
        )[["record_id", "predicted_doy"]]
        cross_fitted_starts.append(prediction)
    train_starts = pd.concat(cross_fitted_starts, ignore_index=True).rename(
        columns={"predicted_doy": "predicted_veraison_doy"}
    )
    train = train.merge(train_starts, on="record_id", how="left", validate="one_to_one")

    inner_fit_records: list[dict[str, object]] = []
    inner_prediction_frames: list[pd.DataFrame] = []
    for inner_fold in range(1, 5):
        inner_training = train.loc[train["inner_spatial_fold"].ne(inner_fold)].copy()
        inner_validation = train.loc[train["inner_spatial_fold"].eq(inner_fold)].copy()
        inner_training["previous_stage_doy"] = inner_training["predicted_veraison_doy"]
        inner_validation["previous_stage_doy"] = inner_validation["predicted_veraison_doy"]
        inner_training_profiles = build_profiles(
            weather_store, inner_training, post_veraison_specification, branch
        )
        inner_harvest_fit = calibrate_threshold_fast(
            inner_training_profiles, inner_training, n_candidates
        )
        inner_validation_profiles = build_profiles(
            weather_store, inner_validation, post_veraison_specification, branch
        )
        inner_prediction = predict_events(
            inner_validation_profiles,
            inner_validation,
            float(inner_harvest_fit["forcing_threshold_c_days"]),
        )
        inner_prediction = inner_prediction.merge(
            inner_validation[["record_id", "predicted_veraison_doy"]],
            on="record_id",
            how="left",
            validate="one_to_one",
        )
        inner_prediction.insert(0, "outer_fold", outer_fold)
        inner_prediction.insert(1, "inner_fold", inner_fold)
        inner_prediction.insert(2, "temperature_branch", branch)
        inner_prediction.insert(3, "method", "predicted_veraison_post_gdd10")
        inner_prediction["veraison_model_id"] = veraison_model_id
        inner_prediction["harvest_forcing_threshold_c_days"] = float(
            inner_harvest_fit["forcing_threshold_c_days"]
        )
        inner_prediction["predicted_stage_order_valid"] = (
            inner_prediction["predicted_veraison_doy"] < inner_prediction["predicted_doy"]
        )
        inner_prediction_frames.append(inner_prediction)
        inner_fit_records.append(
            {
                "split": "inner_validation",
                "outer_fold": outer_fold,
                "inner_fold": inner_fold,
                "temperature_branch": branch,
                "veraison_model_id": veraison_model_id,
                "n_bbch89_training_events": int(len(inner_training)),
                "n_bbch89_validation_events": int(len(inner_validation)),
                "training_predicted_veraison_coverage": float(
                    inner_training["predicted_veraison_doy"].notna().mean()
                ),
                "validation_predicted_veraison_coverage": float(
                    inner_validation["predicted_veraison_doy"].notna().mean()
                ),
                **inner_harvest_fit,
            }
        )

    outer_fit = fits.loc[
        fits["split"].eq("outer_test")
        & fits["outer_fold"].eq(outer_fold)
        & fits["model_id"].eq(veraison_model_id)
        & fits["temperature_branch"].eq(branch)
    ]
    if len(outer_fit) != 1:
        raise ValueError("Missing unique current-training-region BBCH81 fit")
    test_start = predict_events(
        veraison_profiles,
        test,
        float(outer_fit.iloc[0]["forcing_threshold_c_days"]),
    )[["record_id", "predicted_doy"]].rename(columns={"predicted_doy": "predicted_veraison_doy"})
    test = test.merge(test_start, on="record_id", how="left", validate="one_to_one")

    train_forcing = train.copy()
    train_forcing["previous_stage_doy"] = train_forcing["predicted_veraison_doy"]
    test_forcing = test.copy()
    test_forcing["previous_stage_doy"] = test_forcing["predicted_veraison_doy"]
    train_profiles = build_profiles(weather_store, train_forcing, post_veraison_specification, branch)
    harvest_fit = calibrate_threshold_fast(train_profiles, train_forcing, n_candidates)
    test_profiles = build_profiles(weather_store, test_forcing, post_veraison_specification, branch)
    prediction = predict_events(
        test_profiles,
        test_forcing,
        float(harvest_fit["forcing_threshold_c_days"]),
    )
    prediction = prediction.merge(
        test[["record_id", "predicted_veraison_doy"]], on="record_id", how="left", validate="one_to_one"
    )
    prediction.insert(0, "outer_fold", outer_fold)
    prediction.insert(1, "temperature_branch", branch)
    prediction.insert(2, "method", "predicted_veraison_post_gdd10")
    prediction["veraison_model_id"] = veraison_model_id
    prediction["veraison_forcing_threshold_c_days"] = float(
        outer_fit.iloc[0]["forcing_threshold_c_days"]
    )
    prediction["harvest_forcing_threshold_c_days"] = float(
        harvest_fit["forcing_threshold_c_days"]
    )
    prediction["predicted_stage_order_valid"] = (
        prediction["predicted_veraison_doy"] < prediction["predicted_doy"]
    )
    fit_record = {
        "split": "outer_test",
        "outer_fold": outer_fold,
        "inner_fold": None,
        "temperature_branch": branch,
        "veraison_model_id": veraison_model_id,
        "n_bbch89_training_events": int(len(train)),
        "n_bbch89_test_events": int(len(test)),
        "training_predicted_veraison_coverage": float(train["predicted_veraison_doy"].notna().mean()),
        "test_predicted_veraison_coverage": float(test["predicted_veraison_doy"].notna().mean()),
        **harvest_fit,
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
    maturity = events.loc[events["target_stage"].eq("maturity_or_harvest")].copy()
    expanded_inner = attach_inner_folds(events, args.validation_dir)
    fits = pd.read_csv(args.baseline_dir / "nested_cv_threshold_fits.csv")
    selection = pd.read_csv(args.baseline_dir / "inner_cv_model_selection.csv")
    specifications = {spec.model_id: spec for spec in default_model_specifications()}
    weather_store = load_weather_store(args.weather_dir, set(maturity["weather_id"]))

    tasks = [(outer_fold, branch) for branch in TEMPERATURE_BRANCH_COLUMNS for outer_fold in range(1, 6)]
    fit_records = []
    prediction_frames = []
    inner_prediction_frames = []
    with ThreadPoolExecutor(max_workers=args.n_jobs) as executor:
        futures = {
            executor.submit(
                evaluate_fold,
                outer_fold,
                branch,
                maturity,
                expanded_inner,
                weather_store,
                fits,
                selection,
                specifications,
                args.n_candidates,
            ): (outer_fold, branch)
            for outer_fold, branch in tasks
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="BBCH81 prediction -> BBCH89", unit="fold"):
            fold_fit_records, prediction, inner_prediction = future.result()
            fit_records.extend(fold_fit_records)
            prediction_frames.append(prediction)
            inner_prediction_frames.append(inner_prediction)

    chain = pd.concat(prediction_frames, ignore_index=True)
    inner_chain = pd.concat(inner_prediction_frames, ignore_index=True)
    seasonal = pd.read_parquet(args.baseline_dir / "selected_model_outer_predictions.parquet")
    seasonal = seasonal.loc[seasonal["stage"].eq("maturity_or_harvest")].copy()
    seasonal = seasonal[
        ["outer_fold", "temperature_branch", "record_id", "weather_id", "country", "year", "observed_doy", "predicted_doy", "threshold_reached"]
    ]
    seasonal.insert(2, "method", "seasonal_gdd10")
    if set(chain["record_id"]) != set(seasonal["record_id"]):
        raise ValueError("Chain and seasonal models do not use identical BBCH89 records")
    if len(chain) != len(seasonal):
        raise ValueError("Chain and seasonal predictions are not one-to-one comparable")
    comparison = pd.concat([seasonal, chain], ignore_index=True, sort=False)
    metric_records = []
    for (method, branch), group in comparison.groupby(["method", "temperature_branch"]):
        metric_records.append(score(group, method, branch, "France+Germany"))
        for country, country_group in group.groupby("country"):
            metric_records.append(score(country_group, method, branch, country))
    metrics = pd.DataFrame(metric_records)

    chain.to_parquet(args.output_dir / "predicted_veraison_to_bbch89_outer_predictions.parquet", index=False)
    inner_chain.to_parquet(
        args.output_dir / "predicted_veraison_to_bbch89_inner_predictions.parquet", index=False
    )
    fit_frame = pd.DataFrame(fit_records).sort_values(
        ["split", "temperature_branch", "outer_fold", "inner_fold"], na_position="last"
    )
    fit_frame.to_csv(
        args.output_dir / "predicted_veraison_to_bbch89_threshold_fits.csv", index=False
    )
    fit_frame.loc[fit_frame["split"].eq("inner_validation")].to_csv(
        args.output_dir / "predicted_veraison_to_bbch89_inner_threshold_fits.csv", index=False
    )
    comparison.to_parquet(args.output_dir / "common_sample_method_comparison.parquet", index=False)
    metrics.to_csv(args.output_dir / "common_sample_method_metrics.csv", index=False)
    summary = {
        "scope": "BBCH89 independent operational endpoint module",
        "bbch89_events": int(len(maturity)),
        "temperature_branches": list(TEMPERATURE_BRANCH_COLUMNS),
        "spatial_test_rounds": 5,
        "training_region_selection_folds_per_round": 4,
        "inner_chain_prediction_rows": int(len(inner_chain)),
        "common_sample_check": True,
        "training_start_rule": "BBCH81 predicted by training-region four-fold cross-fitting",
        "test_start_rule": "BBCH81 predicted by model fitted only on current training region",
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
    print("\nBBCH89 predicted-veraison chain completed")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nCommon-sample metrics")
    print(metrics.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
