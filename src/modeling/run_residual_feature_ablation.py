#!/usr/bin/env python
"""Run leakage-controlled residual-feature ablation with a fixed Ridge learner."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from tqdm.auto import tqdm

try:
    from src.modeling.build_residual_ml_dataset import (
        REPO_ROOT,
        WATER_SPATIAL_COUNTRY_ENHANCED_STAGE_FEATURE_SETS,
        WATER_SPATIAL_STAGE_FEATURE_SETS,
    )
    from src.modeling.run_residual_ml_models import STAGES, prediction_metrics
except ModuleNotFoundError:
    from build_residual_ml_dataset import (  # type: ignore
        REPO_ROOT,
        WATER_SPATIAL_COUNTRY_ENHANCED_STAGE_FEATURE_SETS,
        WATER_SPATIAL_STAGE_FEATURE_SETS,
    )
    from run_residual_ml_models import STAGES, prediction_metrics  # type: ignore


DEFAULT_INPUT_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_machine_learning_doyrange21_postflower_water_spatial_country_enhanced"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_feature_ablation_country_derived_ridge"
)
RIDGE_ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0)
SELECTION_METRICS = ("rmse", "mae")
DERIVED_STAGE_FEATURES = {
    "budburst": [
        "budburst_pre15d_gdd5_rate_c_day",
        "budburst_pre30d_gdd5_rate_c_day",
        "budburst_pre15d_frost_degree_days_below0_c_days",
        "budburst_pre30d_frost_degree_days_below0_c_days",
    ],
    "flowering": [
        "flowering_predicted_stage_length_days",
        "budburst_to_flowering_gdd0_rate_c_day",
        "budburst_to_flowering_gdd10_rate_c_day",
        "flowering_pre15d_heat_degree_days_above30_c_days",
        "flowering_pre15d_solar_radiation_mean_mj_m2_day",
    ],
    "veraison": [
        "veraison_predicted_stage_length_days",
        "flowering_to_veraison_gdd0_rate_c_day",
        "flowering_to_veraison_gdd10_rate_c_day",
        "preveraison_30d_vpd_et0_interaction_kpa_mm",
        "preveraison_30d_vpd_precipitation_interaction_kpa_mm",
    ],
    "maturity_or_harvest": [],
}
COUNTRY_STAGE_FEATURES = {
    "budburst": [
        "country_france",
        "country_germany",
        "country_france_x_mechanistic_predicted_doy",
    ],
    "flowering": [
        "country_france",
        "country_germany",
        "country_france_x_mechanistic_predicted_doy",
    ],
    "veraison": [
        "country_france",
        "country_germany",
        "country_france_x_mechanistic_predicted_doy",
        "country_france_x_preveraison_30d_vpd_fao56_mean_kpa",
    ],
    "maturity_or_harvest": [],
}


@dataclass(frozen=True)
class ProfileDefinition:
    profile: str
    description: str
    feature_sets: dict[str, list[str]]


def parse_str_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--stages", type=parse_str_list, default=list(STAGES))
    parser.add_argument(
        "--profiles",
        type=parse_str_list,
        default=[
            "base_water_spatial",
            "base_no_latlon",
            "base_plus_country",
            "base_plus_derived",
            "country_derived_no_latlon",
            "country_derived_full",
        ],
    )
    parser.add_argument("--outer-folds", type=parse_str_list, default=["1", "2", "3", "4", "5"])
    parser.add_argument("--alphas", type=parse_float_list, default=list(RIDGE_ALPHAS))
    parser.add_argument("--selection-metric", choices=SELECTION_METRICS, default="rmse")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def unique(features: list[str]) -> list[str]:
    return list(dict.fromkeys(features))


def remove_coordinates(feature_sets: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        stage: [feature for feature in features if feature not in {"lat", "lon"}]
        for stage, features in feature_sets.items()
    }


def add_stage_features(
    feature_sets: dict[str, list[str]],
    additions: dict[str, list[str]],
) -> dict[str, list[str]]:
    return {
        stage: unique([*features, *additions.get(stage, [])])
        for stage, features in feature_sets.items()
    }


def build_profile_definitions() -> dict[str, ProfileDefinition]:
    base = {stage: list(features) for stage, features in WATER_SPATIAL_STAGE_FEATURE_SETS.items()}
    full = {
        stage: list(features)
        for stage, features in WATER_SPATIAL_COUNTRY_ENHANCED_STAGE_FEATURE_SETS.items()
    }
    definitions = [
        ProfileDefinition(
            "base_water_spatial",
            "Existing water/spatial residual feature set",
            base,
        ),
        ProfileDefinition(
            "base_no_latlon",
            "Existing water/spatial feature set without raw latitude/longitude",
            remove_coordinates(base),
        ),
        ProfileDefinition(
            "base_plus_country",
            "Base profile plus country one-hot and country-specific process-DOY slope terms",
            add_stage_features(base, COUNTRY_STAGE_FEATURES),
        ),
        ProfileDefinition(
            "base_plus_derived",
            "Base profile plus leakage-safe derived stage/weather variables, no country additions",
            add_stage_features(base, DERIVED_STAGE_FEATURES),
        ),
        ProfileDefinition(
            "country_derived_no_latlon",
            "Full country/derived profile without raw latitude/longitude",
            remove_coordinates(full),
        ),
        ProfileDefinition(
            "country_derived_full",
            "Current enhanced country/derived profile",
            full,
        ),
    ]
    return {definition.profile: definition for definition in definitions}


def ridge_pipeline(alpha: float) -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=alpha)),
        ]
    )


def residual_prediction_metrics(frame: pd.DataFrame, predicted_residual: np.ndarray) -> dict[str, float]:
    predicted_doy = frame["mechanistic_predicted_doy"].to_numpy(float) + predicted_residual
    return prediction_metrics(frame["observed_doy"].to_numpy(float), predicted_doy)


def validate_stage_table(table: pd.DataFrame, features: list[str], stage: str) -> None:
    missing = set(features).difference(table.columns)
    if missing:
        raise ValueError(f"{stage}: missing ablation features {sorted(missing)}")
    required = {
        "dataset_role",
        "outer_fold",
        "inner_fold",
        "event_assigned_outer_fold",
        "residual_ml_eligible",
        "mechanistic_predicted_doy",
        "observed_doy",
        "residual_days",
    }
    missing_required = required.difference(table.columns)
    if missing_required:
        raise ValueError(f"{stage}: missing required columns {sorted(missing_required)}")


def select_alpha(
    inner_metrics: pd.DataFrame,
    selection_metric: str,
) -> tuple[float, pd.DataFrame]:
    summary = (
        inner_metrics.groupby("alpha")
        .agg(
            mean_mae_days=("mae_days", "mean"),
            mean_rmse_days=("rmse_days", "mean"),
            mean_abs_bias_days=("bias_days", lambda values: values.abs().mean()),
            sd_mae_days=("mae_days", "std"),
        )
        .reset_index()
    )
    if selection_metric == "rmse":
        sort_columns = ["mean_rmse_days", "mean_mae_days", "mean_abs_bias_days", "alpha"]
    else:
        sort_columns = ["mean_mae_days", "mean_rmse_days", "mean_abs_bias_days", "alpha"]
    selected = float(summary.sort_values(sort_columns).iloc[0]["alpha"])
    return selected, summary


def evaluate_stage_fold(
    table: pd.DataFrame,
    features: list[str],
    profile: str,
    stage: str,
    outer_fold: int,
    alphas: list[float],
    selection_metric: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], pd.DataFrame]:
    eligible = table["residual_ml_eligible"].astype(bool)
    training = table.loc[
        table["dataset_role"].eq("training_region_oof")
        & table["outer_fold"].eq(outer_fold)
        & eligible
    ].copy()
    test = table.loc[
        table["dataset_role"].eq("spatial_test")
        & table["outer_fold"].eq(outer_fold)
        & eligible
    ].copy()
    if not training["event_assigned_outer_fold"].ne(outer_fold).all():
        raise ValueError(f"{profile}/{stage}/fold{outer_fold}: training contains test fold records")
    if not test["event_assigned_outer_fold"].eq(outer_fold).all():
        raise ValueError(f"{profile}/{stage}/fold{outer_fold}: test fold mismatch")
    inner_rows = []
    for alpha in alphas:
        for inner_fold, validation in training.groupby("inner_fold", sort=True):
            fit = training.loc[training["inner_fold"].ne(inner_fold)].copy()
            estimator = ridge_pipeline(alpha)
            estimator.fit(fit[features], fit["residual_days"].to_numpy(float))
            predicted_residual = np.asarray(estimator.predict(validation[features]), dtype=float)
            metrics = residual_prediction_metrics(validation, predicted_residual)
            inner_rows.append(
                {
                    "profile": profile,
                    "stage": stage,
                    "outer_fold": outer_fold,
                    "inner_fold": int(inner_fold),
                    "alpha": alpha,
                    **metrics,
                }
            )
    inner_metrics = pd.DataFrame(inner_rows)
    selected_alpha, alpha_summary = select_alpha(inner_metrics, selection_metric)
    estimator = ridge_pipeline(selected_alpha)
    estimator.fit(training[features], training["residual_days"].to_numpy(float))
    predicted_residual = np.asarray(estimator.predict(test[features]), dtype=float)
    predicted_doy = test["mechanistic_predicted_doy"].to_numpy(float) + predicted_residual
    outer_metrics = residual_prediction_metrics(test, predicted_residual)
    prediction_frame = pd.DataFrame(
        {
            "profile": profile,
            "stage": stage,
            "outer_fold": outer_fold,
            "record_id": test["record_id"].to_numpy(),
            "site_uid": test["site_uid"].to_numpy(),
            "observed_doy": test["observed_doy"].to_numpy(float),
            "mechanistic_predicted_doy": test["mechanistic_predicted_doy"].to_numpy(float),
            "predicted_residual_days": predicted_residual,
            "hybrid_predicted_doy": predicted_doy,
            "selected_alpha": selected_alpha,
        }
    )
    outer_row = {
        "profile": profile,
        "stage": stage,
        "outer_fold": outer_fold,
        "selected_alpha": selected_alpha,
        "selection_metric": selection_metric,
        **outer_metrics,
    }
    alpha_summary.insert(0, "selection_metric", selection_metric)
    alpha_summary.insert(0, "outer_fold", outer_fold)
    alpha_summary.insert(0, "stage", stage)
    alpha_summary.insert(0, "profile", profile)
    return inner_rows, [outer_row], prediction_frame


def aggregate_predictions(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (profile, stage), group in predictions.groupby(["profile", "stage"], sort=True):
        metrics = prediction_metrics(
            group["observed_doy"].to_numpy(float),
            group["hybrid_predicted_doy"].to_numpy(float),
        )
        fold_mae = (
            group.assign(abs_error=(group["hybrid_predicted_doy"] - group["observed_doy"]).abs())
            .groupby("outer_fold")["abs_error"]
            .mean()
        )
        rows.append(
            {
                "profile": profile,
                "stage": stage,
                **metrics,
                "sd_outer_fold_mae_days": float(fold_mae.std(ddof=1)),
                "worst_outer_fold_mae_days": float(fold_mae.max()),
            }
        )
    return pd.DataFrame(rows)


def process_baseline(stage_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for stage, table in stage_tables.items():
        frame = table.loc[
            table["dataset_role"].eq("spatial_test")
            & table["residual_ml_eligible"].astype(bool)
        ].copy()
        metrics = prediction_metrics(
            frame["observed_doy"].to_numpy(float),
            frame["mechanistic_predicted_doy"].to_numpy(float),
        )
        rows.append({"profile": "process", "stage": stage, **metrics})
    return pd.DataFrame(rows)


def profile_manifest(definitions: dict[str, ProfileDefinition], profiles: list[str], stages: list[str]) -> pd.DataFrame:
    records = []
    for profile in profiles:
        definition = definitions[profile]
        for stage in stages:
            features = definition.feature_sets[stage]
            records.append(
                {
                    "profile": profile,
                    "stage": stage,
                    "description": definition.description,
                    "n_features": len(features),
                    "features": ";".join(features),
                    "uses_latlon": int(any(feature in {"lat", "lon"} for feature in features)),
                    "uses_country": int(any(feature.startswith("country_") for feature in features)),
                    "uses_derived": int(any(feature in DERIVED_STAGE_FEATURES.get(stage, []) for feature in features)),
                }
            )
    return pd.DataFrame.from_records(records)


def write_report(
    output_dir: Path,
    manifest: pd.DataFrame,
    aggregate: pd.DataFrame,
    process: pd.DataFrame,
    elapsed_seconds: float,
) -> None:
    stage_order = {stage: index for index, stage in enumerate(STAGES)}
    merged = aggregate.merge(
        process[["stage", "mae_days", "rmse_days", "within_7d_pct"]].rename(
            columns={
                "mae_days": "process_mae_days",
                "rmse_days": "process_rmse_days",
                "within_7d_pct": "process_within_7d_pct",
            }
        ),
        on="stage",
        how="left",
    )
    merged["mae_gain_days"] = merged["process_mae_days"] - merged["mae_days"]
    merged["rmse_gain_days"] = merged["process_rmse_days"] - merged["rmse_days"]
    merged["stage_order"] = merged["stage"].map(stage_order)
    table = merged.sort_values(["stage_order", "mae_days"])[
        [
            "profile",
            "stage",
            "n",
            "mae_days",
            "rmse_days",
            "bias_days",
            "within_7d_pct",
            "mae_gain_days",
            "rmse_gain_days",
        ]
    ].round(3)
    best = (
        merged.sort_values(["stage_order", "rmse_days", "mae_days"])
        .groupby("stage", sort=False)
        .head(1)[["stage", "profile", "mae_days", "rmse_days", "mae_gain_days", "rmse_gain_days"]]
        .round(3)
    )
    lines = [
        "# Residual feature ablation report",
        "",
        "Fixed Ridge residual learner; alpha selected inside each training region using inner spatial CV.",
        "",
        "## Profile matrix",
        "",
        manifest[["profile", "stage", "n_features", "uses_latlon", "uses_country", "uses_derived"]]
        .to_markdown(index=False),
        "",
        "## Aggregate outer-spatial performance",
        "",
        table.to_markdown(index=False),
        "",
        "## Best profile by stage using RMSE",
        "",
        best.to_markdown(index=False),
        "",
        f"Elapsed minutes: {elapsed_seconds / 60.0:.2f}",
    ]
    (output_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    invalid_stages = set(args.stages).difference(STAGES)
    if invalid_stages:
        raise ValueError(f"Unknown stages: {sorted(invalid_stages)}")
    outer_folds = [int(value) for value in args.outer_folds]
    definitions = build_profile_definitions()
    invalid_profiles = set(args.profiles).difference(definitions)
    if invalid_profiles:
        raise ValueError(f"Unknown profiles: {sorted(invalid_profiles)}")
    if args.output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"Output exists: {args.output_dir}; use --overwrite")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    stage_tables = {}
    for stage in args.stages:
        path = args.input_dir / "training_ready" / f"{stage}_residual_ml.parquet"
        stage_tables[stage] = pd.read_parquet(path)

    manifest = profile_manifest(definitions, args.profiles, args.stages)
    manifest.to_csv(args.output_dir / "ablation_matrix.csv", index=False)
    inner_rows: list[dict[str, object]] = []
    outer_rows: list[dict[str, object]] = []
    alpha_summaries = []
    predictions = []
    start = time.perf_counter()
    tasks = [
        (profile, stage, fold)
        for profile in args.profiles
        for stage in args.stages
        for fold in outer_folds
    ]
    for profile, stage, fold in tqdm(tasks, desc="Residual feature ablation", unit="task"):
        features = definitions[profile].feature_sets[stage]
        table = stage_tables[stage]
        validate_stage_table(table, features, stage)
        inner, outer, prediction = evaluate_stage_fold(
            table,
            features,
            profile,
            stage,
            fold,
            list(args.alphas),
            args.selection_metric,
        )
        inner_rows.extend(inner)
        outer_rows.extend(outer)
        predictions.append(prediction)
        selected_alpha = float(prediction["selected_alpha"].iloc[0])
        alpha_summaries.append(
            {
                "profile": profile,
                "stage": stage,
                "outer_fold": fold,
                "selected_alpha": selected_alpha,
            }
        )
    prediction_table = pd.concat(predictions, ignore_index=True)
    inner_table = pd.DataFrame(inner_rows)
    outer_table = pd.DataFrame(outer_rows)
    aggregate = aggregate_predictions(prediction_table)
    process = process_baseline(stage_tables)
    elapsed = time.perf_counter() - start

    inner_table.to_csv(args.output_dir / "ablation_inner_fold_metrics.csv", index=False)
    outer_table.to_csv(args.output_dir / "ablation_outer_fold_metrics.csv", index=False)
    pd.DataFrame(alpha_summaries).to_csv(
        args.output_dir / "ablation_selected_alpha.csv", index=False
    )
    prediction_table.to_parquet(args.output_dir / "ablation_outer_predictions.parquet", index=False)
    aggregate.to_csv(args.output_dir / "ablation_aggregate_metrics.csv", index=False)
    process.to_csv(args.output_dir / "process_baseline_metrics.csv", index=False)
    audit = {
        "scope": "fixed Ridge residual-feature ablation",
        "input_dir": str(args.input_dir),
        "profiles": args.profiles,
        "stages": args.stages,
        "outer_folds": outer_folds,
        "alphas": list(args.alphas),
        "selection_metric": args.selection_metric,
        "test_targets_used_for_training_or_selection": False,
        "elapsed_seconds": elapsed,
        "output_dir": str(args.output_dir),
    }
    (args.output_dir / "run_summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(args.output_dir, manifest, aggregate, process, elapsed)

    display = aggregate.merge(
        process[["stage", "mae_days", "rmse_days"]].rename(
            columns={"mae_days": "process_mae_days", "rmse_days": "process_rmse_days"}
        ),
        on="stage",
        how="left",
    )
    display["mae_gain_days"] = display["process_mae_days"] - display["mae_days"]
    display["rmse_gain_days"] = display["process_rmse_days"] - display["rmse_days"]
    display["stage_order"] = display["stage"].map({stage: index for index, stage in enumerate(STAGES)})
    display = display.sort_values(["stage_order", "rmse_days", "mae_days"])
    print("\nResidual feature ablation completed")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print("\nAggregate ablation metrics")
    print(
        display[
            [
                "profile",
                "stage",
                "n",
                "mae_days",
                "rmse_days",
                "bias_days",
                "within_7d_pct",
                "mae_gain_days",
                "rmse_gain_days",
            ]
        ].round(3).to_string(index=False)
    )
    print("\nBest profile by stage using RMSE")
    print(
        display.groupby("stage", sort=False)
        .head(1)[["stage", "profile", "mae_days", "rmse_days", "mae_gain_days", "rmse_gain_days"]]
        .round(3)
        .to_string(index=False)
    )
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
