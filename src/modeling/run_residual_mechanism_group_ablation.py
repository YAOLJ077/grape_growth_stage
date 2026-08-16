#!/usr/bin/env python
"""Run leakage-controlled mechanism-group ablation for fixed residual learners."""

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
    from src.modeling.build_residual_ml_dataset import REPO_ROOT
    from src.modeling.run_residual_ml_models import STAGES, build_estimator, prediction_metrics
except ModuleNotFoundError:
    from build_residual_ml_dataset import REPO_ROOT  # type: ignore
    from run_residual_ml_models import STAGES, build_estimator, prediction_metrics  # type: ignore


DEFAULT_INPUT_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_machine_learning_main_final"
)
DEFAULT_FIXED_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/"
    "main_final_fixed_stage_models_refit"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/"
    "main_final_mechanism_group_ablation"
)
RIDGE_ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0)
GROUPS = (
    "process_anchor",
    "process_timing",
    "temperature_structure",
    "water_drought",
    "radiation_light",
    "terrain_spatial",
)
MECHANISM_GROUPS = (
    "process_timing",
    "temperature_structure",
    "water_drought",
    "radiation_light",
    "terrain_spatial",
)
PROFILE_ORDER = (
    "anchor_only",
    "anchor_plus_process_timing",
    "anchor_plus_temperature_structure",
    "anchor_plus_water_drought",
    "anchor_plus_radiation_light",
    "anchor_plus_terrain_spatial",
    "all_mechanisms",
    "all_minus_process_timing",
    "all_minus_temperature_structure",
    "all_minus_water_drought",
    "all_minus_radiation_light",
    "all_minus_terrain_spatial",
    "environment_only_no_process_state",
)


@dataclass(frozen=True)
class StageProfile:
    stage: str
    profile: str
    feature_groups: tuple[str, ...]
    features: tuple[str, ...]
    description: str
    is_noop: bool


def parse_str_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--fixed-dir", type=Path, default=DEFAULT_FIXED_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--stages", type=parse_str_list, default=list(STAGES))
    parser.add_argument("--outer-folds", type=parse_str_list, default=["1", "2", "3", "4", "5"])
    parser.add_argument("--n-jobs", type=int, default=4)
    parser.add_argument("--random-state", type=int, default=20260805)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def feature_group(feature: str) -> str:
    if feature == "mechanistic_predicted_doy":
        return "process_anchor"
    if feature.endswith("_predicted_stage_length_days"):
        return "process_timing"
    if feature in {
        "dem_elevation_m",
        "dem_local_std_m",
        "northness",
        "lat",
        "lon",
    } or feature.startswith("country_"):
        return "terrain_spatial"
    if any(token in feature for token in ("solar_radiation", "daylength", "photoperiod")):
        return "radiation_light"
    if any(
        token in feature
        for token in (
            "precipitation",
            "vpd",
            "et0",
            "climatic_water_deficit",
            "dry_day",
            "wet_day",
        )
    ):
        return "water_drought"
    if any(
        token in feature
        for token in (
            "tmean",
            "temperature",
            "diurnal",
            "gdd",
            "chill",
            "frost",
            "heat",
            "cool",
        )
    ):
        return "temperature_structure"
    raise ValueError(f"Cannot assign mechanism group for feature: {feature}")


def unique(features: list[str]) -> list[str]:
    return list(dict.fromkeys(features))


def features_in_groups(features: list[str], groups: set[str]) -> list[str]:
    return [feature for feature in features if feature_group(feature) in groups]


def stage_features_from_manifest(input_dir: Path, stages: list[str]) -> dict[str, list[str]]:
    manifest = pd.read_csv(input_dir / "residual_ml_feature_sets.csv")
    missing = set(stages).difference(set(manifest["stage"]))
    if missing:
        raise ValueError(f"Missing stages in residual_ml_feature_sets.csv: {sorted(missing)}")
    return {
        stage: (
            manifest.loc[manifest["stage"].eq(stage)]
            .sort_values("feature_order")["feature"]
            .tolist()
        )
        for stage in stages
    }


def fixed_fold_configs(
    fixed_dir: Path,
    stages: list[str],
    outer_folds: list[int],
) -> dict[tuple[str, int], tuple[str, dict[str, object]]]:
    table = pd.read_csv(fixed_dir / "fixed_stage_outer_fold_metrics.csv")
    required = {"stage", "outer_fold", "algorithm", "selected_config_json"}
    missing = required.difference(table.columns)
    if missing:
        raise ValueError(
            f"fixed_stage_outer_fold_metrics.csv missing columns: {sorted(missing)}"
        )
    configs: dict[tuple[str, int], tuple[str, dict[str, object]]] = {}
    for row in table.to_dict("records"):
        key = (str(row["stage"]), int(row["outer_fold"]))
        if key[0] not in stages or key[1] not in outer_folds:
            continue
        configs[key] = (
            str(row["algorithm"]),
            json.loads(str(row["selected_config_json"])),
        )
    expected = {(stage, fold) for stage in stages for fold in outer_folds}
    missing_configs = expected.difference(configs)
    if missing_configs:
        raise ValueError(f"Missing fixed algorithm/config rows: {sorted(missing_configs)}")
    return configs


def profile_features(features: list[str], profile: str) -> tuple[list[str], tuple[str, ...], str]:
    anchor = features_in_groups(features, {"process_anchor"})
    if not anchor:
        raise ValueError("Every stage profile must contain mechanistic_predicted_doy")
    all_groups = {feature_group(feature) for feature in features}
    all_features = list(features)
    if profile == "anchor_only":
        groups = ("process_anchor",)
        return anchor, groups, "Residual calibration using only the process-model predicted DOY"
    if profile == "anchor_plus_process_timing":
        groups = ("process_anchor", "process_timing")
        return unique([*anchor, *features_in_groups(features, {"process_timing"})]), groups, (
            "Process anchor plus predicted stage-duration state"
        )
    if profile.startswith("anchor_plus_"):
        group = profile.replace("anchor_plus_", "")
        groups = ("process_anchor", group)
        return unique([*anchor, *features_in_groups(features, {group})]), groups, (
            f"Process anchor plus {group} mechanism group"
        )
    if profile == "all_mechanisms":
        return all_features, tuple(group for group in GROUPS if group in all_groups), (
            "All current pruned residual features"
        )
    if profile.startswith("all_minus_"):
        group = profile.replace("all_minus_", "")
        retained = [feature for feature in all_features if feature_group(feature) != group]
        groups = tuple(group_name for group_name in GROUPS if group_name in all_groups and group_name != group)
        return retained, groups, f"All current pruned features except {group}"
    if profile == "environment_only_no_process_state":
        removed = {"process_anchor", "process_timing"}
        retained = [feature for feature in all_features if feature_group(feature) not in removed]
        groups = tuple(group_name for group_name in GROUPS if group_name in all_groups and group_name not in removed)
        return retained, groups, "All environmental/spatial groups without process anchor or timing"
    raise ValueError(f"Unknown profile: {profile}")


def build_stage_profiles(
    stage_features: dict[str, list[str]],
    profiles: tuple[str, ...] = PROFILE_ORDER,
) -> dict[tuple[str, str], StageProfile]:
    definitions: dict[tuple[str, str], StageProfile] = {}
    for stage, features in stage_features.items():
        all_feature_tuple = tuple(features)
        for profile in profiles:
            selected, groups, description = profile_features(features, profile)
            if not selected:
                continue
            definitions[(stage, profile)] = StageProfile(
                stage=stage,
                profile=profile,
                feature_groups=groups,
                features=tuple(selected),
                description=description,
                is_noop=tuple(selected) == all_feature_tuple and profile != "all_mechanisms",
            )
    return definitions


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


def validate_stage_table(table: pd.DataFrame, features: tuple[str, ...], stage: str) -> None:
    missing = set(features).difference(table.columns)
    if missing:
        raise ValueError(f"{stage}: missing mechanism-ablation features {sorted(missing)}")
    required = {
        "dataset_role",
        "outer_fold",
        "inner_fold",
        "event_assigned_outer_fold",
        "residual_ml_eligible",
        "record_id",
        "site_uid",
        "observed_doy",
        "mechanistic_predicted_doy",
        "residual_days",
    }
    missing_required = required.difference(table.columns)
    if missing_required:
        raise ValueError(f"{stage}: missing required columns {sorted(missing_required)}")


def select_alpha(inner_metrics: pd.DataFrame) -> tuple[float, pd.DataFrame]:
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
    selected = float(
        summary.sort_values(
            ["mean_rmse_days", "mean_mae_days", "mean_abs_bias_days", "alpha"]
        ).iloc[0]["alpha"]
    )
    return selected, summary


def evaluate_stage_fold(
    table: pd.DataFrame,
    definition: StageProfile,
    outer_fold: int,
    fixed_configs: dict[tuple[str, int], tuple[str, dict[str, object]]],
    n_jobs: int,
    random_state: int,
) -> tuple[dict[str, object], pd.DataFrame]:
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
        raise ValueError(
            f"{definition.profile}/{definition.stage}/fold{outer_fold}: "
            "training contains test fold records"
        )
    if not test["event_assigned_outer_fold"].eq(outer_fold).all():
        raise ValueError(f"{definition.profile}/{definition.stage}/fold{outer_fold}: test fold mismatch")

    features = list(definition.features)
    algorithm, selected_config = fixed_configs[(definition.stage, outer_fold)]
    estimator = build_estimator(
        algorithm,
        selected_config,
        n_jobs=n_jobs,
        random_state=random_state,
    )
    estimator.fit(training[features], training["residual_days"].to_numpy(float))
    predicted_residual = np.asarray(estimator.predict(test[features]), dtype=float)
    predicted_doy = test["mechanistic_predicted_doy"].to_numpy(float) + predicted_residual
    selected_config_json = json.dumps(selected_config, sort_keys=True)
    prediction_frame = pd.DataFrame(
        {
            "profile": definition.profile,
            "stage": definition.stage,
            "outer_fold": outer_fold,
            "algorithm": algorithm,
            "record_id": test["record_id"].to_numpy(),
            "site_uid": test["site_uid"].to_numpy(),
            "observed_doy": test["observed_doy"].to_numpy(float),
            "mechanistic_predicted_doy": test["mechanistic_predicted_doy"].to_numpy(float),
            "predicted_residual_days": predicted_residual,
            "hybrid_predicted_doy": predicted_doy,
            "selected_config_json": selected_config_json,
        }
    )
    outer_row = {
        "profile": definition.profile,
        "stage": definition.stage,
        "outer_fold": outer_fold,
        "algorithm": algorithm,
        "selected_config_json": selected_config_json,
        "n_features": len(features),
        "feature_groups": ";".join(definition.feature_groups),
        **residual_prediction_metrics(test, predicted_residual),
    }
    return outer_row, prediction_frame


def aggregate_predictions(predictions: pd.DataFrame, manifest: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (profile, stage), group in predictions.groupby(["profile", "stage"], sort=False):
        metrics = prediction_metrics(
            group["observed_doy"].to_numpy(float),
            group["hybrid_predicted_doy"].to_numpy(float),
        )
        fold_mae = (
            group.assign(abs_error=(group["hybrid_predicted_doy"] - group["observed_doy"]).abs())
            .groupby("outer_fold")["abs_error"]
            .mean()
        )
        details = manifest.loc[
            manifest["profile"].eq(profile) & manifest["stage"].eq(stage)
        ].iloc[0]
        rows.append(
            {
                "profile": profile,
                "stage": stage,
                "algorithm": ";".join(sorted(group["algorithm"].unique())),
                "n_features": int(details["n_features"]),
                "feature_groups": details["feature_groups"],
                "is_noop": bool(details["is_noop"]),
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
        rows.append(
            {
                "profile": "process",
                "stage": stage,
                "algorithm": "process",
                "n_features": 0,
                "feature_groups": "",
                "is_noop": False,
                **prediction_metrics(
                    frame["observed_doy"].to_numpy(float),
                    frame["mechanistic_predicted_doy"].to_numpy(float),
                ),
            }
        )
    return pd.DataFrame(rows)


def profile_manifest(definitions: dict[tuple[str, str], StageProfile]) -> pd.DataFrame:
    records = []
    for stage, profile in sorted(
        definitions,
        key=lambda key: (STAGES.index(key[0]), PROFILE_ORDER.index(key[1])),
    ):
        definition = definitions[(stage, profile)]
        records.append(
            {
                "stage": stage,
                "profile": profile,
                "description": definition.description,
                "n_features": len(definition.features),
                "feature_groups": ";".join(definition.feature_groups),
                "features": ";".join(definition.features),
                "is_noop": definition.is_noop,
            }
        )
    return pd.DataFrame.from_records(records)


def group_assignment_table(stage_features: dict[str, list[str]]) -> pd.DataFrame:
    rows = []
    for stage, features in stage_features.items():
        for feature in features:
            rows.append({"stage": stage, "feature": feature, "mechanism_group": feature_group(feature)})
    return pd.DataFrame(rows)


def contribution_summary(aggregate: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stage, group in aggregate.groupby("stage", sort=False):
        by_profile = group.set_index("profile")
        anchor = by_profile.loc["anchor_only"]
        full = by_profile.loc["all_mechanisms"]
        environment = by_profile.loc["environment_only_no_process_state"]
        rows.append(
            {
                "stage": stage,
                "mechanism_group": "process_state",
                "n_group_features": int(full["n_features"] - environment["n_features"]),
                "addon_profile": "anchor_only",
                "addon_mae_gain_vs_anchor_days": 0.0,
                "addon_rmse_gain_vs_anchor_days": 0.0,
                "leaveout_profile": "environment_only_no_process_state",
                "leaveout_mae_cost_vs_all_days": float(environment["mae_days"] - full["mae_days"]),
                "leaveout_rmse_cost_vs_all_days": float(environment["rmse_days"] - full["rmse_days"]),
            }
        )
        for mechanism_group in MECHANISM_GROUPS:
            addon_profile = f"anchor_plus_{mechanism_group}"
            leaveout_profile = f"all_minus_{mechanism_group}"
            if addon_profile not in by_profile.index or leaveout_profile not in by_profile.index:
                continue
            addon = by_profile.loc[addon_profile]
            leaveout = by_profile.loc[leaveout_profile]
            rows.append(
                {
                    "stage": stage,
                    "mechanism_group": mechanism_group,
                    "n_group_features": int(addon["n_features"] - anchor["n_features"]),
                    "addon_profile": addon_profile,
                    "addon_mae_gain_vs_anchor_days": float(anchor["mae_days"] - addon["mae_days"]),
                    "addon_rmse_gain_vs_anchor_days": float(anchor["rmse_days"] - addon["rmse_days"]),
                    "leaveout_profile": leaveout_profile,
                    "leaveout_mae_cost_vs_all_days": float(leaveout["mae_days"] - full["mae_days"]),
                    "leaveout_rmse_cost_vs_all_days": float(leaveout["rmse_days"] - full["rmse_days"]),
                }
            )
    return pd.DataFrame(rows)


def write_report(
    output_dir: Path,
    aggregate: pd.DataFrame,
    process: pd.DataFrame,
    contributions: pd.DataFrame,
    manifest: pd.DataFrame,
    elapsed_seconds: float,
) -> None:
    stage_order = {stage: index for index, stage in enumerate(STAGES)}
    display = aggregate.merge(
        process[["stage", "mae_days", "rmse_days"]].rename(
            columns={"mae_days": "process_mae_days", "rmse_days": "process_rmse_days"}
        ),
        on="stage",
        how="left",
    )
    display["mae_gain_vs_process_days"] = display["process_mae_days"] - display["mae_days"]
    display["rmse_gain_vs_process_days"] = display["process_rmse_days"] - display["rmse_days"]
    display["stage_order"] = display["stage"].map(stage_order)
    performance = display.sort_values(["stage_order", "rmse_days", "mae_days"])[
        [
            "stage",
            "profile",
            "algorithm",
            "n_features",
            "mae_days",
            "rmse_days",
            "bias_days",
            "within_7d_pct",
            "mae_gain_vs_process_days",
            "rmse_gain_vs_process_days",
        ]
    ].round(3)
    contribution_display = contributions.copy()
    numeric_columns = [
        "addon_mae_gain_vs_anchor_days",
        "addon_rmse_gain_vs_anchor_days",
        "leaveout_mae_cost_vs_all_days",
        "leaveout_rmse_cost_vs_all_days",
    ]
    contribution_display[numeric_columns] = contribution_display[numeric_columns].round(3)
    lines = [
        "# 残差学习机制组消融报告",
        "",
        "固定使用 `main_final` 的阶段残差学习算法和每折超参数配置；仅改变机制组特征集合。",
        "",
        "残差定义：`residual_days = observed_doy - mechanistic_predicted_doy`。正残差表示过程模型预测偏早，负残差表示过程模型预测偏晚。",
        "",
        "## 1. 机制组贡献摘要",
        "",
        contribution_display.to_markdown(index=False),
        "",
        "## 2. 外层空间性能矩阵",
        "",
        performance.to_markdown(index=False),
        "",
        "## 3. profile矩阵",
        "",
        manifest[["stage", "profile", "n_features", "feature_groups", "is_noop"]].to_markdown(index=False),
        "",
        f"Elapsed minutes: {elapsed_seconds / 60.0:.2f}",
    ]
    (output_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    invalid_stages = set(args.stages).difference(STAGES)
    if invalid_stages:
        raise ValueError(f"Unknown stages: {sorted(invalid_stages)}")
    outer_folds = [int(value) for value in args.outer_folds]
    if args.output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"Output exists: {args.output_dir}; use --overwrite")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    stage_features = stage_features_from_manifest(args.input_dir, args.stages)
    definitions = build_stage_profiles(stage_features)
    manifest = profile_manifest(definitions)
    manifest.to_csv(args.output_dir / "mechanism_group_matrix.csv", index=False)
    group_assignment_table(stage_features).to_csv(
        args.output_dir / "mechanism_group_feature_assignments.csv", index=False
    )
    fixed_configs = fixed_fold_configs(args.fixed_dir, args.stages, outer_folds)
    fixed_config_table = pd.DataFrame.from_records(
        [
            {
                "stage": stage,
                "outer_fold": outer_fold,
                "algorithm": algorithm,
                "selected_config_json": json.dumps(config, sort_keys=True),
            }
            for (stage, outer_fold), (algorithm, config) in sorted(
                fixed_configs.items(),
                key=lambda item: (STAGES.index(item[0][0]), item[0][1]),
            )
        ]
    )
    fixed_config_table.to_csv(args.output_dir / "mechanism_group_fixed_model_configs.csv", index=False)

    stage_tables = {
        stage: pd.read_parquet(args.input_dir / "training_ready" / f"{stage}_residual_ml.parquet")
        for stage in args.stages
    }
    for (stage, _profile), definition in definitions.items():
        validate_stage_table(stage_tables[stage], definition.features, stage)

    outer_rows: list[dict[str, object]] = []
    predictions = []
    tasks = [
        (stage, profile, fold)
        for stage in args.stages
        for profile in PROFILE_ORDER
        if (stage, profile) in definitions
        for fold in outer_folds
    ]
    start = time.perf_counter()
    for stage, profile, fold in tqdm(tasks, desc="Residual mechanism ablation", unit="task"):
        definition = definitions[(stage, profile)]
        outer, prediction = evaluate_stage_fold(
            stage_tables[stage],
            definition,
            fold,
            fixed_configs,
            args.n_jobs,
            args.random_state,
        )
        outer_rows.append(outer)
        predictions.append(prediction)

    prediction_table = pd.concat(predictions, ignore_index=True)
    outer_table = pd.DataFrame(outer_rows)
    aggregate = aggregate_predictions(prediction_table, manifest)
    process = process_baseline(stage_tables)
    contributions = contribution_summary(aggregate)
    elapsed = time.perf_counter() - start

    outer_table.to_csv(args.output_dir / "mechanism_group_outer_fold_metrics.csv", index=False)
    prediction_table.to_parquet(
        args.output_dir / "mechanism_group_outer_predictions.parquet", index=False
    )
    aggregate.to_csv(args.output_dir / "mechanism_group_aggregate_metrics.csv", index=False)
    process.to_csv(args.output_dir / "process_baseline_metrics.csv", index=False)
    contributions.to_csv(args.output_dir / "mechanism_group_contribution_summary.csv", index=False)
    audit = {
        "scope": "main_final fixed-algorithm residual mechanism-group ablation",
        "residual_definition": "observed_doy - mechanistic_predicted_doy",
        "positive_residual_meaning": "observed later than process prediction; process model predicted too early",
        "input_dir": str(args.input_dir),
        "fixed_dir": str(args.fixed_dir),
        "stages": args.stages,
        "profiles": list(PROFILE_ORDER),
        "outer_folds": outer_folds,
        "fixed_algorithms": fixed_config_table.groupby("stage")["algorithm"].first().to_dict(),
        "configuration_source": "main_final fixed_stage_outer_fold_metrics.csv",
        "test_targets_used_for_training_or_selection": False,
        "n_jobs": args.n_jobs,
        "random_state": args.random_state,
        "elapsed_seconds": elapsed,
        "output_dir": str(args.output_dir),
    }
    (args.output_dir / "run_summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(args.output_dir, aggregate, process, contributions, manifest, elapsed)

    print("\nResidual mechanism-group ablation completed")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print("\nMechanism group contribution summary")
    print(contributions.round(3).to_string(index=False))
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
