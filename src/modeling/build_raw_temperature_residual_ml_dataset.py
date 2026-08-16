#!/usr/bin/env python
"""Build a raw-temperature residual-ML dataset comparable to the main adjusted run."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

REPO_ROOT_CANDIDATE = Path(__file__).resolve().parents[2]
if str(REPO_ROOT_CANDIDATE) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_CANDIDATE))

try:
    from src.modeling import build_residual_ml_dataset as base
    from src.modeling.mechanistic_models import brin_daily_chill_action, brin_daily_gdh
    from src.modeling.run_mechanistic_baselines import DEFAULT_WEATHER_DIR, REPO_ROOT
    from src.modeling.select_stage_mechanistic_models import HARVEST_CHAIN_MODEL_ID
    from src.weather_processing.add_evaporative_demand_features import (
        REFERENCE_CROP_ALBEDO,
        STEFAN_BOLTZMANN_MJ_K4_M2_DAY,
        extraterrestrial_radiation_mj_m2_day,
        saturation_vapor_pressure_kpa as fao_saturation_vapor_pressure_kpa,
        slope_saturation_vapor_pressure_curve_kpa_c,
        wind_speed_at_2m,
    )
except ModuleNotFoundError:
    import build_residual_ml_dataset as base  # type: ignore
    from mechanistic_models import brin_daily_chill_action, brin_daily_gdh  # type: ignore
    from run_mechanistic_baselines import DEFAULT_WEATHER_DIR, REPO_ROOT  # type: ignore
    from select_stage_mechanistic_models import HARVEST_CHAIN_MODEL_ID  # type: ignore
    from add_evaporative_demand_features import (  # type: ignore
        REFERENCE_CROP_ALBEDO,
        STEFAN_BOLTZMANN_MJ_K4_M2_DAY,
        extraterrestrial_radiation_mj_m2_day,
        saturation_vapor_pressure_kpa as fao_saturation_vapor_pressure_kpa,
        slope_saturation_vapor_pressure_curve_kpa_c,
        wind_speed_at_2m,
    )


DEFAULT_BASELINE_DIR = base.DEFAULT_BASELINE_DIR
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/"
    "residual_machine_learning_raw_temperature_doyrange21_postflower_water_spatial_ablation_pruned"
)
RAW_TEMPERATURE_BRANCH = "raw"
RAW_PROCESS_MODELS = {
    "budburst": "budburst__calibrated_brin_aug1",
    "flowering": "flowering__calibrated_gfv",
    "veraison": "veraison__calibrated_gfv",
    "maturity_or_harvest": HARVEST_CHAIN_MODEL_ID,
}
RAW_UPSTREAM_MODEL_BY_STAGE = {
    "flowering": "budburst__calibrated_brin_aug1",
    "veraison": "flowering__calibrated_gfv",
    "maturity_or_harvest": "veraison__calibrated_gfv",
}
RAW_UPSTREAM_STAGE_BY_STAGE = {
    "flowering": "budburst",
    "veraison": "flowering",
    "maturity_or_harvest": "veraison",
}
RAW_UPSTREAM_START_DOY = {
    "budburst__calibrated_brin_aug1": np.nan,
    "flowering__calibrated_gfv": 60.0,
    "veraison__calibrated_gfv": 60.0,
}
RAW_UPSTREAM_BASE_TEMPERATURE_C = {
    "budburst__calibrated_brin_aug1": 5.0,
    "flowering__calibrated_gfv": 0.0,
    "veraison__calibrated_gfv": 10.0,
}
RAW_WEATHER_COLUMNS = [
    "weather_id",
    "year",
    "weather_date",
    "weather_year",
    "weather_doy",
    "lat",
    "dem_elevation_m",
    "temperature_2m_c",
    "temperature_2m_min_c",
    "temperature_2m_max_c",
    "dewpoint_temperature_2m_c",
    "total_precipitation_mm",
    "surface_pressure_kpa",
    "surface_solar_radiation_downwards_mj_m2",
    "wind_speed_10m_m_s",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    parser.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--reference-sample-dir",
        type=Path,
        default=None,
        help="Optional existing residual-ML dataset whose stage/fold/record rows define the analysis sample.",
    )
    parser.add_argument(
        "--feature-profile",
        choices=sorted(base.FEATURE_PROFILES),
        default="water_spatial_ablation_pruned",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def apply_reference_sample(
    combined: pd.DataFrame,
    reference_sample_dir: Path | None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if reference_sample_dir is None:
        return combined, {
            "reference_sample_dir": None,
            "reference_sample_filter_applied": False,
        }
    reference_path = reference_sample_dir / "residual_nested_spatial_cv.parquet"
    if not reference_path.exists():
        raise FileNotFoundError(f"Reference residual table is missing: {reference_path}")
    key_columns = ["dataset_role", "stage", "outer_fold", "record_id"]
    reference = pd.read_parquet(reference_path, columns=key_columns).drop_duplicates()
    before = (
        combined.groupby(["dataset_role", "stage"], sort=True)
        .size()
        .rename("n_before_reference_filter")
        .reset_index()
    )
    filtered = combined.merge(
        reference.assign(_reference_keep=True),
        on=key_columns,
        how="left",
        validate="many_to_one",
    )
    filtered = filtered.loc[filtered["_reference_keep"].eq(True)].drop(columns="_reference_keep")
    after = (
        filtered.groupby(["dataset_role", "stage"], sort=True)
        .size()
        .rename("n_after_reference_filter")
        .reset_index()
    )
    audit_table = before.merge(after, on=["dataset_role", "stage"], how="left").fillna(
        {"n_after_reference_filter": 0}
    )
    audit_table["n_removed_by_reference_filter"] = (
        audit_table["n_before_reference_filter"]
        - audit_table["n_after_reference_filter"].astype(int)
    )
    return filtered.reset_index(drop=True), {
        "reference_sample_dir": base.display_path(reference_sample_dir),
        "reference_sample_filter_applied": True,
        "reference_sample_key": key_columns,
        "reference_sample_filter_by_stage": audit_table.to_dict("records"),
    }


def raw_training_oof_predictions(baseline_dir: Path) -> pd.DataFrame:
    baseline = pd.read_parquet(baseline_dir / "nested_cv_predictions.parquet")
    baseline = baseline.loc[
        baseline["split"].eq("inner_validation")
        & baseline["analysis_set"].eq("independent_stage")
        & baseline["selection_eligible"].astype(bool)
    ].copy()
    harvest_chain = base.standardize_chain(
        pd.read_parquet(
            baseline_dir
            / "bbch89_independent"
            / "predicted_veraison_to_bbch89_inner_predictions.parquet"
        ),
        "inner_validation",
        HARVEST_CHAIN_MODEL_ID,
        "maturity_or_harvest",
    )
    candidates = pd.concat([baseline, harvest_chain], ignore_index=True, sort=False)
    mask = candidates["temperature_branch"].eq(RAW_TEMPERATURE_BRANCH)
    for stage, model_id in RAW_PROCESS_MODELS.items():
        mask &= candidates["stage"].ne(stage) | candidates["model_id"].eq(model_id)
    selected = candidates.loc[mask & candidates["stage"].isin(RAW_PROCESS_MODELS)].copy()
    selected["dataset_role"] = "training_region_oof"
    return selected


def raw_spatial_test_predictions(baseline_dir: Path) -> pd.DataFrame:
    baseline = pd.read_parquet(baseline_dir / "nested_cv_predictions.parquet")
    baseline = baseline.loc[
        baseline["split"].eq("outer_test")
        & baseline["analysis_set"].eq("independent_stage")
        & baseline["selection_eligible"].astype(bool)
    ].copy()
    harvest_chain = base.standardize_chain(
        pd.read_parquet(
            baseline_dir
            / "bbch89_independent"
            / "predicted_veraison_to_bbch89_outer_predictions.parquet"
        ),
        "outer_test",
        HARVEST_CHAIN_MODEL_ID,
        "maturity_or_harvest",
    )
    candidates = pd.concat([baseline, harvest_chain], ignore_index=True, sort=False)
    mask = candidates["temperature_branch"].eq(RAW_TEMPERATURE_BRANCH)
    for stage, model_id in RAW_PROCESS_MODELS.items():
        mask &= candidates["stage"].ne(stage) | candidates["model_id"].eq(model_id)
    selected = candidates.loc[mask & candidates["stage"].isin(RAW_PROCESS_MODELS)].copy()
    selected["dataset_role"] = "spatial_test"
    return selected


def attach_raw_upstream_parameters(frame: pd.DataFrame, baseline_dir: Path) -> pd.DataFrame:
    result = frame.copy()
    result["upstream_stage"] = result["stage"].map(RAW_UPSTREAM_STAGE_BY_STAGE)
    result["upstream_model_id"] = result["stage"].map(RAW_UPSTREAM_MODEL_BY_STAGE)
    result["upstream_temperature_branch"] = RAW_TEMPERATURE_BRANCH
    result["upstream_model_start_doy"] = result["upstream_model_id"].map(
        RAW_UPSTREAM_START_DOY
    )
    result["upstream_model_base_temperature_c"] = result["upstream_model_id"].map(
        RAW_UPSTREAM_BASE_TEMPERATURE_C
    )
    result["upstream_forcing_threshold_c_days"] = np.nan
    result["upstream_chill_threshold_cu"] = np.nan
    fits = pd.read_csv(baseline_dir / "nested_cv_threshold_fits.csv")

    for role, split in (
        ("training_region_oof", "inner_validation"),
        ("spatial_test", "outer_test"),
    ):
        row_mask = result["dataset_role"].eq(role) & result["upstream_model_id"].notna()
        if not row_mask.any():
            continue
        left_columns = [
            "residual_row_id",
            "outer_fold",
            "inner_fold",
            "upstream_temperature_branch",
            "upstream_model_id",
        ]
        left = result.loc[row_mask, left_columns].copy()
        fit = fits.loc[fits["split"].eq(split)].copy().rename(
            columns={
                "model_id": "upstream_model_id",
                "temperature_branch": "upstream_temperature_branch",
                "forcing_threshold_c_days": "upstream_forcing_threshold_c_days",
                "chill_threshold_cu": "upstream_chill_threshold_cu",
            }
        )
        keys = ["outer_fold", "upstream_temperature_branch", "upstream_model_id"]
        if split == "inner_validation":
            left["inner_fold"] = pd.to_numeric(left["inner_fold"]).astype(int)
            fit["inner_fold"] = pd.to_numeric(fit["inner_fold"]).astype(int)
            keys.append("inner_fold")
        else:
            left = left.drop(columns="inner_fold")
            fit = fit.drop(columns="inner_fold", errors="ignore")
        matched = left.merge(
            fit[
                [
                    *keys,
                    "upstream_forcing_threshold_c_days",
                    "upstream_chill_threshold_cu",
                ]
            ],
            on=keys,
            how="left",
            validate="many_to_one",
        )
        missing = matched["upstream_forcing_threshold_c_days"].isna()
        if missing.any():
            examples = matched.loc[missing, keys].drop_duplicates().head().to_dict("records")
            raise ValueError(f"Missing raw upstream threshold for {role}: {examples}")
        forcing_lookup = matched.set_index("residual_row_id")[
            "upstream_forcing_threshold_c_days"
        ]
        chill_lookup = matched.set_index("residual_row_id")["upstream_chill_threshold_cu"]
        result.loc[row_mask, "upstream_forcing_threshold_c_days"] = result.loc[
            row_mask, "residual_row_id"
        ].map(forcing_lookup)
        result.loc[row_mask, "upstream_chill_threshold_cu"] = result.loc[
            row_mask, "residual_row_id"
        ].map(chill_lookup)
    return result


def prepare_raw_residual_rows(baseline_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    training = raw_training_oof_predictions(baseline_dir)
    test = raw_spatial_test_predictions(baseline_dir)
    events = pd.read_csv(
        baseline_dir / "primary_analysis_event_index.csv",
        usecols=base.STATIC_COLUMNS,
        low_memory=False,
    ).rename(columns={"outer_spatial_fold": "event_assigned_outer_fold"})
    keep = [
        "split",
        "outer_fold",
        "inner_fold",
        "model_id",
        "stage",
        "temperature_branch",
        "forcing_threshold_c_days",
        "record_id",
        "weather_id",
        "country",
        "year",
        "observed_doy",
        "predicted_doy",
        "threshold_reached",
        "dataset_role",
        "predicted_flowering_doy",
        "predicted_veraison_doy",
    ]
    frames = []
    for frame in (training, test):
        for column in keep:
            if column not in frame:
                frame[column] = pd.NA
        subset = frame[keep].copy()
        subset["inner_fold"] = pd.to_numeric(subset["inner_fold"], errors="coerce").astype(
            "Int64"
        )
        frames.append(subset)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.merge(
        events,
        on=["record_id", "weather_id", "country", "year"],
        how="left",
        validate="many_to_one",
    )
    if combined["site_uid"].isna().any():
        raise ValueError("Some raw residual rows did not match the primary event index")
    combined["mechanistic_predicted_doy"] = combined["predicted_doy"].astype(float)
    combined["residual_days"] = (
        combined["observed_doy"].astype(float) - combined["mechanistic_predicted_doy"]
    )
    combined["absolute_mechanistic_error_days"] = combined["residual_days"].abs()
    combined["residual_ml_eligible"] = combined["mechanistic_predicted_doy"].notna()
    combined["model_forcing_start_doy"] = np.select(
        [
            combined["stage"].eq("budburst"),
            combined["stage"].isin(["flowering", "veraison"]),
            combined["stage"].eq("maturity_or_harvest"),
        ],
        [1.0, 60.0, combined["predicted_veraison_doy"].astype(float) + 1.0],
        default=np.nan,
    )
    combined["residual_row_id"] = (
        combined["dataset_role"].astype(str)
        + "|test_fold="
        + combined["outer_fold"].astype(str)
        + "|"
        + combined["record_id"].astype(str)
    )
    if combined["residual_row_id"].duplicated().any():
        raise ValueError("Raw residual row identifiers are not unique")
    combined["country_network"] = combined["country"].map(
        {"France": "France_TEMPO", "Germany": "Germany_DWD"}
    )
    combined = attach_raw_upstream_parameters(combined, baseline_dir)
    training = combined.loc[combined["dataset_role"].eq("training_region_oof")].copy()
    test = combined.loc[combined["dataset_role"].eq("spatial_test")].copy()
    if not training["event_assigned_outer_fold"].ne(training["outer_fold"]).all():
        raise ValueError("Raw training residuals contain current spatial test-fold records")
    if not test["event_assigned_outer_fold"].eq(test["outer_fold"]).all():
        raise ValueError("Raw spatial-test residual rows do not match assigned test fold")
    return training, test


def read_raw_weather_partition(path: Path) -> pd.DataFrame:
    available = base.parquet_column_names(path)
    missing = set(RAW_WEATHER_COLUMNS).difference(available)
    if missing:
        raise ValueError(f"{path.name} is missing raw-weather columns: {sorted(missing)}")
    columns = [column for column in RAW_WEATHER_COLUMNS + base.OPTIONAL_WEATHER_COLUMNS if column in available]
    weather = pd.read_parquet(path, columns=columns)
    for column in base.OPTIONAL_WEATHER_COLUMNS:
        if column not in weather:
            weather[column] = np.nan
    return weather


def raw_evaporative_demand(subset: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    tmean = subset["temperature_2m_c"].astype(float)
    tmin = subset["temperature_2m_min_c"].astype(float)
    tmax = subset["temperature_2m_max_c"].astype(float)
    dewpoint = subset["dewpoint_temperature_2m_c"].astype(float)
    pressure = subset["surface_pressure_kpa"].astype(float)
    radiation = subset["surface_solar_radiation_downwards_mj_m2"].astype(float).clip(lower=0.0)
    elevation = subset["dem_elevation_m"].astype(float)
    wind_2m = wind_speed_at_2m(subset["wind_speed_10m_m_s"])

    es_min = fao_saturation_vapor_pressure_kpa(tmin)
    es_max = fao_saturation_vapor_pressure_kpa(tmax)
    es_mean = (es_min + es_max) / 2.0
    es_tmean = fao_saturation_vapor_pressure_kpa(tmean)
    ea = np.minimum(fao_saturation_vapor_pressure_kpa(dewpoint), es_mean)
    ea = np.maximum(ea, 0.0)
    vpd_mean = np.maximum(es_tmean - ea, 0.0)
    vpd_fao56 = np.maximum(es_mean - ea, 0.0)

    slope = slope_saturation_vapor_pressure_curve_kpa_c(tmean)
    psychrometric = 0.000665 * pressure
    ra = extraterrestrial_radiation_mj_m2_day(subset["lat"], subset["weather_doy"])
    clear_sky = np.maximum((0.75 + 0.00002 * elevation) * ra, 1e-6)
    relative_shortwave = np.clip(np.asarray(radiation, dtype=float) / clear_sky, 0.0, 1.0)
    net_shortwave = (1.0 - REFERENCE_CROP_ALBEDO) * np.asarray(radiation, dtype=float)
    tmin_k = np.asarray(tmin, dtype=float) + 273.16
    tmax_k = np.asarray(tmax, dtype=float) + 273.16
    cloudiness = np.maximum((1.35 * relative_shortwave) - 0.35, 0.0)
    humidity = np.maximum(0.34 - 0.14 * np.sqrt(ea), 0.0)
    net_longwave = (
        STEFAN_BOLTZMANN_MJ_K4_M2_DAY
        * ((np.power(tmax_k, 4.0) + np.power(tmin_k, 4.0)) / 2.0)
        * humidity
        * cloudiness
    )
    net_radiation = net_shortwave - net_longwave
    numerator = (
        0.408 * slope * net_radiation
        + psychrometric
        * (900.0 / (np.asarray(tmean, dtype=float) + 273.0))
        * wind_2m
        * vpd_fao56
    )
    denominator = slope + psychrometric * (1.0 + 0.34 * wind_2m)
    et0 = np.maximum(numerator / denominator, 0.0)
    water_deficit = et0 - subset["total_precipitation_mm"].to_numpy(float)
    return vpd_mean, vpd_fao56, et0, water_deficit


def summarize_raw_window(group: pd.DataFrame, mask: np.ndarray) -> dict[str, float]:
    if not mask.any():
        return base.summarize_window(group, mask)
    subset = group.loc[mask]
    tmean = subset["temperature_2m_c"].to_numpy(float)
    tmin = subset["temperature_2m_min_c"].to_numpy(float)
    tmax = subset["temperature_2m_max_c"].to_numpy(float)
    dewpoint = subset["dewpoint_temperature_2m_c"].to_numpy(float)
    fallback_vpd = np.maximum(
        base.saturation_vapor_pressure_kpa(tmean) - base.saturation_vapor_pressure_kpa(dewpoint),
        0.0,
    )
    vpd_mean, vpd_fao56, et0, water_deficit = raw_evaporative_demand(subset)
    rootzone = base.rootzone_soil_water_l1_l3(subset)
    radiation = subset["surface_solar_radiation_downwards_mj_m2"].to_numpy(float)
    result = {
        "n_days": float(len(subset)),
        "tmean_adjusted_mean_c": float(np.nanmean(tmean)),
        "tmean_adjusted_sd_c": float(np.nanstd(tmean, ddof=0)),
        "tmin_adjusted_min_c": float(np.nanmin(tmin)),
        "tmax_adjusted_max_c": float(np.nanmax(tmax)),
        "diurnal_temperature_range_mean_c": float(np.nanmean(tmax - tmin)),
        "cool_days_tmean_lt10c": float(np.sum(tmean < 10.0)),
        "cool_degree_days_below10_c_days": float(np.nansum(np.maximum(10.0 - tmean, 0.0))),
        "frost_days": float(np.sum(tmin < 0.0)),
        "frost_degree_days_below0_c_days": float(np.nansum(np.maximum(-tmin, 0.0))),
        "hot_days_ge30": float(np.sum(tmax >= 30.0)),
        "hot_days_ge35": float(np.sum(tmax >= 35.0)),
        "heat_degree_days_above30_c_days": float(np.nansum(np.maximum(tmax - 30.0, 0.0))),
        "heat_degree_days_above35_c_days": float(np.nansum(np.maximum(tmax - 35.0, 0.0))),
        "gdd0_adjusted_c_days": float(np.nansum(np.maximum(tmean, 0.0))),
        "gdd5_adjusted_c_days": float(np.nansum(np.maximum(tmean - 5.0, 0.0))),
        "gdd10_adjusted_c_days": float(np.nansum(np.maximum(tmean - 10.0, 0.0))),
        "precipitation_sum_mm": float(np.nansum(subset["total_precipitation_mm"])),
        "solar_radiation_sum_mj_m2": float(np.nansum(radiation)),
        "solar_radiation_mean_mj_m2_day": float(np.nanmean(radiation)),
        "vpd_raw_grid_mean_kpa": base.finite_mean(fallback_vpd),
        "vpd_mean_kpa": base.finite_mean(vpd_mean),
        "vpd_fao56_mean_kpa": base.finite_mean(vpd_fao56),
        "et0_fao56_sum_mm": base.finite_sum(et0),
        "et0_fao56_mean_mm_day": base.finite_mean(et0),
        "climatic_water_deficit_sum_mm": base.finite_sum(water_deficit),
        "positive_climatic_water_deficit_sum_mm": base.finite_sum(
            np.maximum(water_deficit, 0.0)
        ),
        "soil_water_rootzone_l1_l3_mean_m3_m3": base.finite_mean(rootzone),
        "soil_water_rootzone_l1_l3_min_m3_m3": base.finite_min(rootzone),
        "wind_speed_mean_m_s": float(np.nanmean(subset["wind_speed_10m_m_s"])),
    }
    for layer in range(1, 5):
        soil = base.soil_layer_array(subset, layer)
        result[f"soil_water_layer{layer}_mean_m3_m3"] = base.finite_mean(soil)
        result[f"soil_water_layer{layer}_min_m3_m3"] = base.finite_min(soil)
    for threshold in base.VPD_THRESHOLDS_KPA:
        suffix = base.vpd_threshold_suffix(threshold)
        result[f"vpd_days_above{suffix}_kpa"] = float(np.sum(vpd_mean > threshold))
        result[f"vpd_degree_days_above{suffix}_kpa_days"] = float(
            np.nansum(np.maximum(vpd_mean - threshold, 0.0))
        )
    return result


def upstream_prediction_from_raw_weather(request: object, group: pd.DataFrame) -> float:
    if request.stage == "maturity_or_harvest" and pd.notna(request.predicted_veraison_doy):
        return float(request.predicted_veraison_doy)
    if (
        request.upstream_model_id == "budburst__calibrated_brin_aug1"
        and pd.notna(request.upstream_chill_threshold_cu)
        and pd.notna(request.upstream_forcing_threshold_c_days)
    ):
        minimum = group["temperature_2m_min_c"].to_numpy(float)
        maximum = group["temperature_2m_max_c"].to_numpy(float)
        chill = np.cumsum(brin_daily_chill_action(minimum, maximum, q10=2.17))
        break_position = int(
            np.searchsorted(chill, float(request.upstream_chill_threshold_cu), side="left")
        )
        daily_gdh = brin_daily_gdh(
            minimum,
            maximum,
            base_temperature_c=5.0,
            maximum_temperature_c=25.0,
        )
        cumulative_gdh = np.cumsum(daily_gdh)
        target_positions = np.flatnonzero(group["weather_year"].to_numpy(int) == int(request.year))
        if break_position < len(group) and len(target_positions):
            offset = cumulative_gdh[break_position - 1] if break_position > 0 else 0.0
            forcing = np.maximum(cumulative_gdh[target_positions] - offset, 0.0)
            forcing[target_positions < break_position] = 0.0
            position = int(
                np.searchsorted(
                    np.maximum.accumulate(forcing),
                    float(request.upstream_forcing_threshold_c_days),
                    side="left",
                )
            )
            if position < len(target_positions):
                return float(group.iloc[target_positions[position]]["weather_doy"])
    if pd.notna(request.upstream_forcing_threshold_c_days):
        target_year = group.loc[group["weather_year"].eq(int(request.year))]
        target_year = target_year.loc[
            target_year["weather_doy"].ge(int(request.upstream_model_start_doy))
        ]
        temperature = target_year["temperature_2m_c"].to_numpy(float)
        cumulative = np.cumsum(
            np.maximum(temperature - float(request.upstream_model_base_temperature_c), 0.0)
        )
        position = int(
            np.searchsorted(
                cumulative,
                float(request.upstream_forcing_threshold_c_days),
                side="left",
            )
        )
        if position < len(target_year):
            return float(target_year.iloc[position]["weather_doy"])
    return np.nan


def build_raw_weather_features(rows: pd.DataFrame, weather_dir: Path) -> pd.DataFrame:
    requests = rows.loc[
        rows["residual_ml_eligible"],
        [
            "residual_row_id",
            "weather_id",
            "year",
            "mechanistic_predicted_doy",
            "model_forcing_start_doy",
            "stage",
            "lat",
            "predicted_veraison_doy",
            "upstream_model_start_doy",
            "upstream_model_base_temperature_c",
            "upstream_forcing_threshold_c_days",
            "upstream_model_id",
            "upstream_temperature_branch",
            "upstream_chill_threshold_cu",
        ],
    ].copy()
    request_ids = set(requests["weather_id"].astype(str))
    records: list[dict[str, object]] = []
    for path in tqdm(base.weather_partition_files(weather_dir), desc="Raw residual weather features", unit="file"):
        weather = read_raw_weather_partition(path)
        weather["weather_id"] = weather["weather_id"].astype(str)
        weather = weather.loc[weather["weather_id"].isin(request_ids)].copy()
        if weather.empty:
            continue
        weather["weather_date"] = pd.to_datetime(weather["weather_date"])
        grouped = {
            key: value.sort_values("weather_date")
            for key, value in weather.groupby("weather_id")
        }
        part_requests = requests.loc[requests["weather_id"].isin(grouped)]
        for request in part_requests.itertuples(index=False):
            group = grouped[str(request.weather_id)]
            cutoff = int(round(float(request.mechanistic_predicted_doy)))
            start = int(round(float(request.model_forcing_start_doy)))
            row: dict[str, object] = {"residual_row_id": request.residual_row_id}
            for window, mask in base.feature_masks(group, int(request.year), cutoff, start).items():
                prefix = base.WINDOW_PREFIXES[window]
                for name, value in summarize_raw_window(group, mask).items():
                    row[f"{prefix}_{name}"] = value

            dates = group["weather_date"].to_numpy(dtype="datetime64[D]")
            year = int(request.year)
            chill_start = np.datetime64(pd.Timestamp(year - 1, 8, 1), "D")
            leap_end = 29 if pd.Timestamp(year, 12, 31).is_leap_year else 28
            chill_end = np.datetime64(pd.Timestamp(year, 2, leap_end), "D")
            chill_mask = (dates >= chill_start) & (dates <= chill_end)
            chill_tmean = group.loc[chill_mask, "temperature_2m_c"].to_numpy(float)
            chill_tmin = group.loc[chill_mask, "temperature_2m_min_c"].to_numpy(float)
            row["preseason_chill_days_tmean_0_10c"] = float(
                np.sum((chill_tmean >= 0.0) & (chill_tmean <= 10.0))
            )
            row["preseason_frost_degree_days_below0_c_days"] = float(
                np.nansum(np.maximum(-chill_tmin, 0.0))
            )
            row["forcing_temperature_variability_c"] = row["ty_tmean_adjusted_sd_c"]

            upstream_prediction = upstream_prediction_from_raw_weather(request, group)
            row["upstream_mechanistic_predicted_doy"] = upstream_prediction
            row["mechanistic_interval_from_upstream_days"] = (
                float(request.mechanistic_predicted_doy) - upstream_prediction
                if np.isfinite(upstream_prediction)
                else np.nan
            )
            stage_prefix = base.STAGE_WINDOW_PREFIXES.get(str(request.stage))
            if stage_prefix is not None:
                stage_mask = base.predicted_stage_window_mask(
                    group,
                    int(request.year),
                    upstream_prediction,
                    float(request.mechanistic_predicted_doy),
                )
                for name, value in summarize_raw_window(group, stage_mask).items():
                    row[f"{stage_prefix}_{name}"] = value
            if request.stage == "flowering":
                row["flowering_pre15d_cool_days_tmean_lt10c"] = row[
                    "t15_cool_days_tmean_lt10c"
                ]
                row["flowering_pre15d_frost_degree_days_below0_c_days"] = row[
                    "t15_frost_degree_days_below0_c_days"
                ]
                row["flowering_pre15d_vpd_fao56_mean_kpa"] = row[
                    "t15_vpd_fao56_mean_kpa"
                ]
                row["flowering_pre15d_et0_fao56_sum_mm"] = row[
                    "t15_et0_fao56_sum_mm"
                ]
                row["flowering_pre15d_positive_climatic_water_deficit_sum_mm"] = row[
                    "t15_positive_climatic_water_deficit_sum_mm"
                ]
            elif request.stage == "veraison":
                row["preveraison_30d_heat_degree_days_above35_c_days"] = row[
                    "t30_heat_degree_days_above35_c_days"
                ]
                row["preveraison_30d_vpd_raw_grid_mean_kpa"] = row[
                    "t30_vpd_raw_grid_mean_kpa"
                ]
                row["preveraison_30d_precipitation_sum_mm"] = row[
                    "t30_precipitation_sum_mm"
                ]
                row["preveraison_30d_vpd_fao56_mean_kpa"] = row[
                    "t30_vpd_fao56_mean_kpa"
                ]
                row["preveraison_30d_et0_fao56_sum_mm"] = row[
                    "t30_et0_fao56_sum_mm"
                ]
                row["preveraison_30d_positive_climatic_water_deficit_sum_mm"] = row[
                    "t30_positive_climatic_water_deficit_sum_mm"
                ]
                row["preveraison_30d_soil_water_rootzone_l1_l3_mean_m3_m3"] = row[
                    "t30_soil_water_rootzone_l1_l3_mean_m3_m3"
                ]
                row["preveraison_30d_soil_water_rootzone_l1_l3_min_m3_m3"] = row[
                    "t30_soil_water_rootzone_l1_l3_min_m3_m3"
                ]
            records.append(row)
    features = pd.DataFrame.from_records(records)
    if features["residual_row_id"].duplicated().any():
        raise ValueError("Raw weather feature rows are duplicated")
    missing = set(requests["residual_row_id"]).difference(set(features["residual_row_id"]))
    if missing:
        raise ValueError(f"Raw weather features are missing for {len(missing)} eligible residual rows")
    return features


def write_outputs(
    combined: pd.DataFrame,
    feature_sets: dict[str, list[str]],
    output_dir: Path,
    feature_profile: str,
    weather_feature_rows: int,
    reference_audit: dict[str, object],
) -> None:
    combined = base.add_derived_residual_features(combined)
    training = combined.loc[combined["dataset_role"].eq("training_region_oof")].copy()
    test = combined.loc[combined["dataset_role"].eq("spatial_test")].copy()
    training.to_parquet(output_dir / "residual_training_oof.parquet", index=False)
    test.to_parquet(output_dir / "residual_spatial_test.parquet", index=False)
    combined.to_parquet(output_dir / "residual_nested_spatial_cv.parquet", index=False)
    base.feature_dictionary(combined, feature_sets).to_csv(
        output_dir / "residual_feature_dictionary.csv", index=False
    )
    manifest = base.feature_set_manifest(feature_sets)
    missing_features = set(manifest["feature"]).difference(combined.columns)
    if missing_features:
        raise ValueError(f"Raw residual-ML features are missing: {sorted(missing_features)}")
    manifest.to_csv(output_dir / "residual_ml_feature_sets.csv", index=False)
    base.feature_exclusion_log().to_csv(
        output_dir / "residual_ml_feature_exclusion_log.csv", index=False
    )

    ready_dir = output_dir / "training_ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    control_columns = [
        "residual_row_id",
        "record_id",
        "weather_id",
        "site_uid",
        "dataset_role",
        "outer_fold",
        "inner_fold",
        "event_assigned_outer_fold",
        "validation_block_1deg_id",
        "stage",
        "model_id",
        "temperature_branch",
        "observed_doy",
        "mechanistic_predicted_doy",
        "residual_days",
        "residual_ml_eligible",
        "threshold_reached",
    ]
    for stage, features in feature_sets.items():
        stage_columns = list(dict.fromkeys([*control_columns, *features]))
        stage_table = combined.loc[combined["stage"].eq(stage), stage_columns].copy()
        stage_table.to_parquet(ready_dir / f"{stage}_residual_ml.parquet", index=False)

    summary_rows = []
    for (role, stage), group in combined.groupby(["dataset_role", "stage"], sort=True):
        eligible = group["residual_ml_eligible"].astype(bool)
        summary_rows.append(
            {
                "dataset_role": role,
                "stage": stage,
                "n_rows": int(len(group)),
                "n_unique_events": int(group["record_id"].nunique()),
                "n_residual_ml_eligible": int(eligible.sum()),
                "eligible_pct": float(eligible.mean() * 100),
                "residual_mean_days": float(group.loc[eligible, "residual_days"].mean()),
                "residual_mae_days": float(group.loc[eligible, "residual_days"].abs().mean()),
                "residual_sd_days": float(group.loc[eligible, "residual_days"].std()),
            }
        )
    summary_table = pd.DataFrame(summary_rows)
    summary_table.to_csv(output_dir / "residual_dataset_summary.csv", index=False)
    audit = {
        "scope": "raw-temperature strict nested spatial-CV residual ML foundation",
        "process_temperature_branch": RAW_TEMPERATURE_BRANCH,
        "weather_temperature_branch": RAW_TEMPERATURE_BRANCH,
        "temperature_feature_values": "raw ERA5-Land temperature; feature column names retain adjusted/gdd suffixes for schema comparability",
        "raw_vpd_et0": "VPD and FAO-56 ET0 recalculated from raw Tmean/Tmin/Tmax with ERA5-Land dewpoint, pressure, radiation, wind, latitude and DEM elevation",
        "raw_process_models": RAW_PROCESS_MODELS,
        "residual_definition": "observed_doy - mechanistic_predicted_doy",
        "training_oof_rows": int(len(training)),
        "spatial_test_rows": int(len(test)),
        "unique_events": int(combined["record_id"].nunique()),
        "training_rows_per_event_expected": 4,
        "training_rows_per_event_check": bool(training.groupby("record_id").size().eq(4).all()),
        "spatial_test_rows_per_event_check": bool(test.groupby("record_id").size().eq(1).all()),
        "current_test_fold_excluded_from_training_residuals": bool(
            training["event_assigned_outer_fold"].ne(training["outer_fold"]).all()
        ),
        "weather_feature_cutoff": "mechanistic predicted DOY; never observed event DOY",
        "weather_feature_rows": weather_feature_rows,
        "feature_profile": feature_profile,
        **reference_audit,
        "frozen_selected_features_by_stage": {
            stage: len(features) for stage, features in feature_sets.items()
        },
        "output_directory": base.display_path(output_dir),
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    readme = [
        "# Raw-temperature residual machine-learning foundation",
        "",
        "Generated by `src/modeling/build_raw_temperature_residual_ml_dataset.py`.",
        "",
        "- Process predictions use the raw temperature branch for the same stage model structures as the main analysis.",
        "- Weather features use raw ERA5-Land temperature and raw-temperature FAO-56 VPD/ET0 recalculation.",
        "- Feature names are retained from the main schema so `run_residual_ml_models.py` and `run_fixed_stage_hybrid_models.py` can be reused without changing the model formula.",
        "- Residual definition is `observed_doy - mechanistic_predicted_doy`.",
        "- Weather windows end at the mechanistic predicted date, never the observed event date.",
    ]
    (output_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    print("\nRaw-temperature residual ML dataset completed")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print("\nRaw residual summary")
    print(summary_table.round(3).to_string(index=False))
    print("\nFrozen residual-ML feature sets")
    for stage, features in feature_sets.items():
        print(f"\n[{stage}] selected ({len(features)})")
        print("  " + ", ".join(features))


def main() -> int:
    args = parse_args()
    feature_sets = base.feature_sets_for_profile(args.feature_profile)
    if args.output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"Output exists: {args.output_dir}; use --overwrite")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    training, test = prepare_raw_residual_rows(args.baseline_dir)
    combined = pd.concat([training, test], ignore_index=True)
    combined, reference_audit = apply_reference_sample(combined, args.reference_sample_dir)
    weather_features = build_raw_weather_features(combined, args.weather_dir)
    combined = combined.merge(
        weather_features,
        on="residual_row_id",
        how="left",
        validate="one_to_one",
    )
    write_outputs(
        combined,
        feature_sets,
        args.output_dir,
        args.feature_profile,
        int(len(weather_features)),
        reference_audit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
