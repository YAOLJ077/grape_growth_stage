#!/usr/bin/env python
"""Run nested spatial-CV thermal baselines for France and Germany.

The primary cohort pools core and extended records without using model tier as
a feature, weight or stratum. Sensitivity records and chronology anomalies are
excluded. Progress is shown with tqdm; fold fits can use a small thread pool.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from tqdm.auto import tqdm

try:
    from src.modeling.mechanistic_models import (
        TEMPERATURE_BRANCH_COLUMNS,
        ThermalModelSpecification,
        brin_daily_chill_action,
        brin_daily_gdh,
        daily_gdd,
        default_model_specifications,
    )
    from src.modeling.stage_model_selection import build_final_selection_record, formal_stage_selection
except ModuleNotFoundError:
    from mechanistic_models import (  # type: ignore
        TEMPERATURE_BRANCH_COLUMNS,
        ThermalModelSpecification,
        brin_daily_chill_action,
        brin_daily_gdh,
        daily_gdd,
        default_model_specifications,
    )
    from stage_model_selection import build_final_selection_record, formal_stage_selection  # type: ignore


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VALIDATION_DIR = REPO_ROOT / "data/phenology/derived/modeling/france_germany_four_stage/validation"
DEFAULT_WEATHER_DIR = REPO_ROOT / "data/weather/processed/era5_land_daily_france_germany_adjusted"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/phenology/derived/modeling/france_germany_four_stage/baseline_mechanistic"
PRIMARY_TIERS = {"core", "extended"}


@dataclass(frozen=True)
class FoldTask:
    split: str
    outer_fold: int
    inner_fold: int | None
    training_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]


@dataclass(frozen=True)
class WeatherSeries:
    weather_year: np.ndarray
    weather_doy: np.ndarray
    raw_mean: np.ndarray
    adjusted_mean: np.ndarray
    raw_minimum: np.ndarray
    raw_maximum: np.ndarray
    adjusted_minimum: np.ndarray
    adjusted_maximum: np.ndarray


@dataclass(frozen=True)
class BrinPreparedSeries:
    chill_cumulative: np.ndarray
    gdh_cumulative: np.ndarray
    target_positions: np.ndarray
    target_doy: np.ndarray


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-dir", type=Path, default=DEFAULT_VALIDATION_DIR)
    parser.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--n-jobs", type=int, choices=(1, 2, 4), default=2)
    parser.add_argument("--n-candidates", type=int, default=401)
    parser.add_argument(
        "--brin-chill-candidates",
        type=int,
        default=20,
        help="Number of literature-bounded Cc grid values for BRIN-Aug1.",
    )
    parser.add_argument(
        "--brin-forcing-candidates",
        type=int,
        default=201,
        help="Number of Gh grid values fitted for each BRIN-Aug1 Cc candidate.",
    )
    parser.add_argument(
        "--bbch81-audit-file",
        type=Path,
        default=None,
        help="Optional audited BBCH81 record overrides; spatial folds remain frozen.",
    )
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument(
        "--smoke-events-per-country-stage",
        type=int,
        default=0,
        help="Deterministically cap each country-stage group; 0 runs the full cohort.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def apply_bbch81_audit(events: pd.DataFrame, audit_file: Path | None) -> pd.DataFrame:
    if audit_file is None:
        return events
    audit = pd.read_csv(audit_file)
    required = {
        "record_id", "bbch81_use_in_primary", "audited_event_doy",
        "audited_event_date", "audited_n_obs", "audited_doy_min",
        "audited_doy_median", "audited_doy_max", "audited_doy_range",
    }
    missing = required.difference(audit.columns)
    if missing:
        raise ValueError(f"BBCH81 audit is missing columns: {sorted(missing)}")
    if audit["record_id"].duplicated().any():
        raise ValueError("BBCH81 audit record_id values must be unique")
    work = events.merge(
        audit[list(required)], on="record_id", how="left", validate="one_to_one"
    )
    is_veraison = work["target_stage"].eq("veraison")
    missing_audit = is_veraison & work["bbch81_use_in_primary"].isna()
    if missing_audit.any():
        raise ValueError(f"BBCH81 audit is missing {int(missing_audit.sum())} veraison records")
    audited_use = (
        work["bbch81_use_in_primary"].astype("boolean").fillna(False).to_numpy(bool)
    )
    work = work.loc[~(is_veraison & ~audited_use)].copy()
    is_veraison = work["target_stage"].eq("veraison")
    replacements = {
        "event_doy": "audited_event_doy",
        "event_date": "audited_event_date",
        "n_obs": "audited_n_obs",
        "doy_min": "audited_doy_min",
        "doy_median": "audited_doy_median",
        "doy_max": "audited_doy_max",
        "doy_range": "audited_doy_range",
    }
    for destination, source in replacements.items():
        if destination in work:
            work.loc[is_veraison, destination] = work.loc[is_veraison, source].to_numpy()
    audited_by_weather = work.loc[is_veraison].set_index("weather_id")["event_doy"]
    maturity = work["target_stage"].eq("maturity_or_harvest")
    has_audited_start = work.loc[maturity, "weather_id"].isin(audited_by_weather.index)
    maturity_index = work.index[maturity]
    work.loc[maturity_index, "previous_stage_doy"] = work.loc[
        maturity_index, "weather_id"
    ].map(audited_by_weather)
    work.loc[maturity_index, "previous_stage_observed"] = has_audited_start.to_numpy()
    work.loc[maturity_index, "sequential_observed_start_eligible"] = (
        has_audited_start.to_numpy()
        & work.loc[maturity_index, "previous_stage_doy"].lt(
            work.loc[maturity_index, "event_doy"]
        ).to_numpy()
    )
    return work.drop(columns=[column for column in required if column != "record_id"], errors="ignore")


def read_primary_events(
    validation_dir: Path,
    smoke_cap: int = 0,
    bbch81_audit_file: Path | None = None,
) -> pd.DataFrame:
    events = pd.read_csv(validation_dir / "modeling_event_index.csv", low_memory=False)
    events = apply_bbch81_audit(events, bbch81_audit_file)
    mask = (
        events["model_tier"].isin(PRIMARY_TIERS)
        & events["chronology_valid"].astype(bool)
        & events["independent_stage_weather_eligible"].astype(bool)
        & events["temperature_branch_raw_available"].astype(bool)
        & events["temperature_branch_adjusted_6p5_available"].astype(bool)
    )
    events = events.loc[mask].copy()
    if smoke_cap > 0:
        events = (
            events.sort_values(["country", "target_stage", "validation_block_1deg_id", "year", "record_id"])
            .groupby(["country", "target_stage"], group_keys=False)
            .head(smoke_cap)
            .copy()
        )
    if events["record_id"].duplicated().any():
        raise ValueError("Primary event index has duplicate record_id values")
    # A weather_id can contain several stages, but never two records of the same stage.
    duplicate_stage = events.duplicated(["weather_id", "target_stage"])
    if duplicate_stage.any():
        raise ValueError("Primary event index has duplicate weather_id-stage records")
    events["weather_id"] = events["weather_id"].astype(str)
    events["record_id"] = events["record_id"].astype(str)
    return events.reset_index(drop=True)


def attach_inner_folds(events: pd.DataFrame, validation_dir: Path) -> pd.DataFrame:
    inner = pd.read_csv(validation_dir / "inner_spatial_block_folds.csv")
    expanded = events.merge(inner, on="validation_block_1deg_id", how="inner", validate="many_to_many")
    expanded = expanded.loc[expanded["outer_spatial_fold"].ne(expanded["outer_test_fold"])].copy()
    expected = len(events) * 4
    if len(expanded) != expected:
        raise ValueError(f"Inner-fold expansion has {len(expanded)} rows; expected {expected}")
    return expanded


def estimate_work(events: pd.DataFrame, weather_dir: Path, specifications: list[ThermalModelSpecification]) -> dict[str, object]:
    files = sorted(weather_dir.glob("era5_land_daily_france_germany_adjusted_part_*.parquet"))
    weather_rows = sum(pq.ParquetFile(path).metadata.num_rows for path in files)
    combinations = len(specifications) * len(TEMPERATURE_BRANCH_COLUMNS)
    return {
        "primary_events": int(len(events)),
        "primary_site_years": int(events["weather_id"].nunique()),
        "events_by_country_stage": {
            f"{country}|{stage}": int(count)
            for (country, stage), count in events.groupby(["country", "target_stage"]).size().items()
        },
        "weather_files": len(files),
        "weather_rows_on_disk": int(weather_rows),
        "model_structures": len(specifications),
        "temperature_model_combinations": combinations,
        "fold_evaluations": combinations * 25,
        "calibrated_fold_fits": sum(
            spec.threshold_mode in {"fit_training_fold_only", "fit_brin_training_fold_only"}
            for spec in specifications
        )
        * len(TEMPERATURE_BRANCH_COLUMNS)
        * 25,
        "threshold_candidates_per_fit": 401,
    }


def load_weather_store(weather_dir: Path, weather_ids: set[str]) -> dict[str, WeatherSeries]:
    columns = [
        "weather_id",
        "year",
        "weather_year",
        "weather_doy",
        TEMPERATURE_BRANCH_COLUMNS["raw"]["tmean"],
        TEMPERATURE_BRANCH_COLUMNS["adjusted_6p5"]["tmean"],
        TEMPERATURE_BRANCH_COLUMNS["raw"]["tmin"],
        TEMPERATURE_BRANCH_COLUMNS["raw"]["tmax"],
        TEMPERATURE_BRANCH_COLUMNS["adjusted_6p5"]["tmin"],
        TEMPERATURE_BRANCH_COLUMNS["adjusted_6p5"]["tmax"],
    ]
    frames: list[pd.DataFrame] = []
    files = sorted(weather_dir.glob("era5_land_daily_france_germany_adjusted_part_*.parquet"))
    if not files:
        raise FileNotFoundError(f"No adjusted weather parquet files in {weather_dir}")
    for path in tqdm(files, desc="Reading weather partitions", unit="file"):
        frame = pd.read_parquet(path, columns=columns)
        frame["weather_id"] = frame["weather_id"].astype(str)
        frame = frame.loc[frame["weather_id"].isin(weather_ids)]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        raise ValueError("No weather rows matched the primary event cohort")
    weather = pd.concat(frames, ignore_index=True)
    duplicate = weather.duplicated(["weather_id", "weather_year", "weather_doy"])
    if duplicate.any():
        raise ValueError("Target-year weather contains duplicate weather_id-DOY rows")
    missing_ids = weather_ids.difference(set(weather["weather_id"]))
    if missing_ids:
        raise ValueError(f"Missing target-year weather for {len(missing_ids)} primary weather_ids")
    raw_column = TEMPERATURE_BRANCH_COLUMNS["raw"]["tmean"]
    adjusted_column = TEMPERATURE_BRANCH_COLUMNS["adjusted_6p5"]["tmean"]
    store: dict[str, WeatherSeries] = {}
    for weather_id, group in tqdm(
        weather.sort_values(["weather_id", "weather_doy"]).groupby("weather_id", sort=False),
        total=weather["weather_id"].nunique(),
        desc="Indexing site-year weather",
        unit="site-year",
    ):
        store[str(weather_id)] = WeatherSeries(
            weather_year=group["weather_year"].to_numpy(dtype=np.int16),
            weather_doy=group["weather_doy"].to_numpy(dtype=np.int16),
            raw_mean=group[raw_column].to_numpy(dtype=np.float32),
            adjusted_mean=group[adjusted_column].to_numpy(dtype=np.float32),
            raw_minimum=group[TEMPERATURE_BRANCH_COLUMNS["raw"]["tmin"]].to_numpy(dtype=np.float32),
            raw_maximum=group[TEMPERATURE_BRANCH_COLUMNS["raw"]["tmax"]].to_numpy(dtype=np.float32),
            adjusted_minimum=group[TEMPERATURE_BRANCH_COLUMNS["adjusted_6p5"]["tmin"]].to_numpy(dtype=np.float32),
            adjusted_maximum=group[TEMPERATURE_BRANCH_COLUMNS["adjusted_6p5"]["tmax"]].to_numpy(dtype=np.float32),
        )
    return store


def build_profiles(
    weather_store: dict[str, WeatherSeries],
    events: pd.DataFrame,
    specification: ThermalModelSpecification,
    temperature_branch: str,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    previous_doy = events.set_index("weather_id")["previous_stage_doy"].to_dict()
    identifiers = events["weather_id"].astype(str).unique()
    profiles: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for weather_id in identifiers:
        series = weather_store[weather_id]
        target_year = int(events.loc[events["weather_id"].eq(weather_id), "year"].iloc[0])
        target_mask = series.weather_year == target_year
        doy = series.weather_doy[target_mask]
        temperature = (
            series.raw_mean[target_mask]
            if temperature_branch == "raw"
            else series.adjusted_mean[target_mask]
        )
        if specification.start_mode == "calendar_doy":
            mask = doy >= int(specification.start_doy)
        elif specification.start_mode == "previous_observed_stage":
            start = previous_doy.get(weather_id)
            if pd.isna(start):
                continue
            mask = doy > int(start)
        else:
            raise ValueError(f"Unsupported start mode: {specification.start_mode}")
        selected_doy = doy[mask].astype(np.int16, copy=False)
        forcing = daily_gdd(temperature[mask], specification.base_temperature_c)
        profiles[weather_id] = (selected_doy, np.cumsum(forcing, dtype=np.float64))
    return profiles


def prepare_brin_weather(
    weather_store: dict[str, WeatherSeries],
    events: pd.DataFrame,
    temperature_branch: str,
    q10: float = 2.17,
    base_temperature_c: float = 5.0,
    maximum_temperature_c: float = 25.0,
) -> dict[str, BrinPreparedSeries]:
    """Precompute chill and GDH sequences that do not depend on fitted Cc."""
    event_year = events.set_index("weather_id")["year"].astype(int).to_dict()
    prepared: dict[str, BrinPreparedSeries] = {}
    for weather_id in events["weather_id"].astype(str).unique():
        series = weather_store[weather_id]
        year = int(event_year[weather_id])
        minimum = (
            series.raw_minimum
            if temperature_branch == "raw"
            else series.adjusted_minimum
        )
        maximum = (
            series.raw_maximum
            if temperature_branch == "raw"
            else series.adjusted_maximum
        )
        chill = np.cumsum(brin_daily_chill_action(minimum, maximum, q10=q10))
        daily_gdh = brin_daily_gdh(
            minimum,
            maximum,
            base_temperature_c=base_temperature_c,
            maximum_temperature_c=maximum_temperature_c,
        )
        cumulative_gdh = np.cumsum(daily_gdh, dtype=np.float64)
        target_mask = series.weather_year == year
        target_positions = np.flatnonzero(target_mask)
        target_doy = series.weather_doy[target_mask].astype(np.int16, copy=False)
        prepared[weather_id] = BrinPreparedSeries(
            chill_cumulative=chill,
            gdh_cumulative=cumulative_gdh,
            target_positions=target_positions,
            target_doy=target_doy,
        )
    return prepared


def build_brin_profiles(
    prepared: dict[str, BrinPreparedSeries],
    chill_threshold_cu: float,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Build BRIN-Aug1 GDH profiles after fold-specific dormancy release."""
    profiles: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for weather_id, series in prepared.items():
        break_position = int(
            np.searchsorted(series.chill_cumulative, float(chill_threshold_cu), side="left")
        )
        target_positions = series.target_positions
        target_doy = series.target_doy
        if not len(target_positions):
            profiles[weather_id] = (target_doy, np.asarray([], dtype=float))
            continue
        if break_position >= len(series.chill_cumulative):
            profiles[weather_id] = (target_doy, np.zeros(len(target_doy), dtype=float))
            continue
        offset = (
            float(series.gdh_cumulative[break_position - 1]) if break_position > 0 else 0.0
        )
        target_forcing = series.gdh_cumulative[target_positions] - offset
        target_forcing[target_positions < break_position] = 0.0
        profiles[weather_id] = (
            target_doy,
            np.maximum.accumulate(np.maximum(target_forcing, 0.0)),
        )
    return profiles


def brin_chill_grid(n_candidates: int) -> np.ndarray:
    """Return a reproducible Cc grid bounded by the published mean +/- 2 SD."""
    if n_candidates < 5:
        raise ValueError("BRIN requires at least five chill-threshold candidates")
    grid = np.linspace(30.0, 210.0, int(n_candidates), dtype=float)
    return np.unique(np.append(grid, 119.0))


def run_brin_branch(
    weather_store: dict[str, WeatherSeries],
    stage_events: pd.DataFrame,
    fold_tasks: list[FoldTask],
    specification: ThermalModelSpecification,
    temperature_branch: str,
    n_chill_candidates: int,
    n_forcing_candidates: int,
    n_jobs: int,
) -> tuple[list[dict[str, object]], list[pd.DataFrame]]:
    """Fit both BRIN thresholds inside each fold, then predict its held-out region."""
    event_lookup = stage_events.set_index("record_id", drop=False)
    best: dict[tuple[str, int, int | None], tuple[tuple[float, ...], float, dict[str, float | int]]] = {}
    candidates = brin_chill_grid(n_chill_candidates)
    prepared = prepare_brin_weather(
        weather_store,
        stage_events,
        temperature_branch,
        base_temperature_c=specification.base_temperature_c,
    )

    def calibrate_one(
        task: FoldTask,
        profiles: dict[str, tuple[np.ndarray, np.ndarray]],
    ) -> tuple[FoldTask, dict[str, float | int] | None]:
        training = event_lookup.loc[list(task.training_ids)]
        try:
            fit = calibrate_threshold_fast(
                profiles, training, n_candidates=n_forcing_candidates
            )
        except ValueError:
            fit = None
        return task, fit

    for chill_threshold in tqdm(
        candidates,
        desc=f"{specification.model_id} | {temperature_branch} | Cc grid",
        unit="Cc",
    ):
        profiles = build_brin_profiles(prepared, float(chill_threshold))
        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            futures = [executor.submit(calibrate_one, task, profiles) for task in fold_tasks]
            for future in as_completed(futures):
                task, fit = future.result()
                if fit is None:
                    continue
                key = (task.split, task.outer_fold, task.inner_fold)
                score = (
                    float(fit["training_rmse_days"]),
                    float(fit["training_mae_days"]),
                    -float(fit["training_coverage"]),
                    float(chill_threshold),
                )
                if key not in best or score < best[key][0]:
                    best[key] = (score, float(chill_threshold), fit)
        del profiles

    expected_keys = {(task.split, task.outer_fold, task.inner_fold) for task in fold_tasks}
    missing_keys = expected_keys.difference(best)
    if missing_keys:
        raise RuntimeError(f"BRIN calibration failed for fold tasks: {sorted(missing_keys)}")

    fit_records: list[dict[str, object]] = []
    prediction_frames: list[pd.DataFrame] = []
    selected_thresholds = sorted({value[1] for value in best.values()})
    for chill_threshold in selected_thresholds:
        profiles = build_brin_profiles(prepared, chill_threshold)
        for task in fold_tasks:
            key = (task.split, task.outer_fold, task.inner_fold)
            _, selected_chill, fit = best[key]
            if selected_chill != chill_threshold:
                continue
            threshold = float(fit["forcing_threshold_c_days"])
            validation = event_lookup.loc[list(task.validation_ids)]
            prediction = predict_events(profiles, validation, threshold)
            prediction.insert(0, "split", task.split)
            prediction.insert(1, "outer_fold", task.outer_fold)
            prediction.insert(2, "inner_fold", task.inner_fold)
            prediction.insert(3, "model_id", specification.model_id)
            prediction.insert(4, "stage", specification.stage)
            prediction.insert(5, "analysis_set", specification.analysis_set)
            prediction.insert(6, "selection_eligible", specification.selection_eligible)
            prediction.insert(7, "temperature_branch", temperature_branch)
            prediction.insert(8, "forcing_threshold_c_days", threshold)
            prediction.insert(9, "chill_threshold_cu", selected_chill)
            prediction_frames.append(prediction)
            fit_records.append(
                {
                    "split": task.split,
                    "outer_fold": task.outer_fold,
                    "inner_fold": task.inner_fold,
                    "model_id": specification.model_id,
                    "stage": specification.stage,
                    "analysis_set": specification.analysis_set,
                    "selection_eligible": specification.selection_eligible,
                    "temperature_branch": temperature_branch,
                    "chill_threshold_cu": selected_chill,
                    "brin_q10": 2.17,
                    "brin_base_temperature_c": specification.base_temperature_c,
                    "brin_maximum_temperature_c": 25.0,
                    "brin_chill_start_month_day": "08-01",
                    **fit,
                }
            )
        del profiles
    del prepared
    return fit_records, prediction_frames


def forcing_at_event(profile: tuple[np.ndarray, np.ndarray], event_doy: int) -> float | None:
    doy, cumulative = profile
    if len(doy) == 0:
        return 0.0
    position = int(np.searchsorted(doy, int(event_doy), side="right") - 1)
    # A predicted previous stage can occur after the observed target stage.
    # Its available forcing at the observed target is then zero; retain the
    # record so this unavoidable stage-order error contributes to calibration.
    return float(cumulative[position]) if position >= 0 else 0.0


def calibrate_threshold_fast(
    profiles: dict[str, tuple[np.ndarray, np.ndarray]],
    observations: pd.DataFrame,
    n_candidates: int,
) -> dict[str, float | int]:
    rows: list[tuple[np.ndarray, np.ndarray, float]] = []
    observed_forcing: list[float] = []
    for row in observations[["weather_id", "event_doy"]].itertuples(index=False):
        profile = profiles.get(str(row.weather_id))
        if profile is None:
            continue
        value = forcing_at_event(profile, int(row.event_doy))
        if value is not None:
            rows.append((profile[0], profile[1], float(row.event_doy)))
            observed_forcing.append(value)
    if len(rows) < 2:
        raise ValueError("At least two training events with valid forcing profiles are required")
    lower = max(min(observed_forcing), 1e-6)
    upper = max(observed_forcing)
    if not upper > lower:
        raise ValueError("Training events do not identify a positive threshold range")
    candidates = np.linspace(lower, upper, int(n_candidates), dtype=np.float64)
    sum_squared = np.zeros(len(candidates), dtype=np.float64)
    sum_absolute = np.zeros(len(candidates), dtype=np.float64)
    reached = np.zeros(len(candidates), dtype=np.int64)
    for doy, cumulative, observed_doy in rows:
        positions = np.searchsorted(cumulative, candidates, side="left")
        valid = positions < len(doy)
        if not valid.any():
            continue
        errors = doy[positions[valid]].astype(float) - observed_doy
        sum_squared[valid] += errors**2
        sum_absolute[valid] += np.abs(errors)
        reached[valid] += 1
    if int(reached.max()) == 0:
        raise RuntimeError("No candidate threshold yielded a prediction")
    # An unreached threshold means the modeled event lies beyond the available
    # target year. Penalize it at the day after the profile ends. This retains
    # every training event in the objective and prevents low thresholds from
    # winning merely because they maximize prediction coverage.
    for doy, cumulative, observed_doy in rows:
        positions = np.searchsorted(cumulative, candidates, side="left")
        missing = positions >= len(doy)
        if missing.any():
            errors = float(doy[-1] + 1) - observed_doy
            sum_squared[missing] += errors**2
            sum_absolute[missing] += abs(errors)
    rmse = np.sqrt(sum_squared / len(rows))
    mae = sum_absolute / len(rows)
    best_pool = np.flatnonzero(rmse == np.nanmin(rmse))
    minimum_mae = np.nanmin(mae[best_pool])
    best_pool = best_pool[mae[best_pool] == minimum_mae]
    best = int(best_pool[np.argmax(reached[best_pool])])
    return {
        "forcing_threshold_c_days": float(candidates[best]),
        "training_rmse_days": float(rmse[best]),
        "training_mae_days": float(mae[best]),
        "training_coverage": float(reached[best] / len(rows)),
        "n_training_events": int(len(rows)),
        "n_threshold_candidates": int(n_candidates),
    }


def predict_events(
    profiles: dict[str, tuple[np.ndarray, np.ndarray]],
    observations: pd.DataFrame,
    threshold: float,
) -> pd.DataFrame:
    records = []
    for row in observations[["record_id", "weather_id", "event_doy", "country", "year"]].itertuples(index=False):
        profile = profiles.get(str(row.weather_id))
        predicted = np.nan
        reached = False
        if profile is not None:
            doy, cumulative = profile
            position = int(np.searchsorted(cumulative, threshold, side="left"))
            reached = position < len(doy)
            if reached:
                predicted = float(doy[position])
        records.append(
            {
                "record_id": str(row.record_id),
                "weather_id": str(row.weather_id),
                "country": row.country,
                "year": int(row.year),
                "observed_doy": float(row.event_doy),
                "predicted_doy": predicted,
                "threshold_reached": reached,
            }
        )
    return pd.DataFrame.from_records(records)


def build_fold_tasks(stage_events: pd.DataFrame, expanded_inner: pd.DataFrame) -> list[FoldTask]:
    tasks: list[FoldTask] = []
    stage = str(stage_events["target_stage"].iloc[0])
    for outer_fold in range(1, 6):
        training = stage_events.loc[stage_events["outer_spatial_fold"].ne(outer_fold), "record_id"].astype(str)
        validation = stage_events.loc[stage_events["outer_spatial_fold"].eq(outer_fold), "record_id"].astype(str)
        if len(training) and len(validation):
            tasks.append(FoldTask("outer_test", outer_fold, None, tuple(training), tuple(validation)))
        inner_stage = expanded_inner.loc[
            expanded_inner["target_stage"].eq(stage) & expanded_inner["outer_test_fold"].eq(outer_fold)
        ]
        for inner_fold in range(1, 5):
            inner_training = inner_stage.loc[
                inner_stage["inner_spatial_fold"].ne(inner_fold), "record_id"
            ].astype(str)
            inner_validation = inner_stage.loc[
                inner_stage["inner_spatial_fold"].eq(inner_fold), "record_id"
            ].astype(str)
            if len(inner_training) and len(inner_validation):
                tasks.append(
                    FoldTask(
                        "inner_validation",
                        outer_fold,
                        inner_fold,
                        tuple(inner_training),
                        tuple(inner_validation),
                    )
                )
    return tasks


def run_fold_task(
    task: FoldTask,
    event_lookup: pd.DataFrame,
    profiles: dict[str, tuple[np.ndarray, np.ndarray]],
    specification: ThermalModelSpecification,
    temperature_branch: str,
    n_candidates: int,
) -> tuple[dict[str, object], pd.DataFrame]:
    training = event_lookup.loc[list(task.training_ids)]
    validation = event_lookup.loc[list(task.validation_ids)]
    if specification.threshold_mode == "fixed_external":
        threshold = float(specification.forcing_threshold_c_days)
        fit = {
            "forcing_threshold_c_days": threshold,
            "training_rmse_days": np.nan,
            "training_mae_days": np.nan,
            "training_coverage": np.nan,
            "n_training_events": int(len(training)),
            "n_threshold_candidates": 0,
        }
    else:
        fit = calibrate_threshold_fast(profiles, training, n_candidates)
        threshold = float(fit["forcing_threshold_c_days"])
    fit_record: dict[str, object] = {
        "split": task.split,
        "outer_fold": task.outer_fold,
        "inner_fold": task.inner_fold,
        "model_id": specification.model_id,
        "stage": specification.stage,
        "analysis_set": specification.analysis_set,
        "selection_eligible": specification.selection_eligible,
        "temperature_branch": temperature_branch,
        **fit,
    }
    prediction = predict_events(profiles, validation, threshold)
    prediction.insert(0, "split", task.split)
    prediction.insert(1, "outer_fold", task.outer_fold)
    prediction.insert(2, "inner_fold", task.inner_fold)
    prediction.insert(3, "model_id", specification.model_id)
    prediction.insert(4, "stage", specification.stage)
    prediction.insert(5, "analysis_set", specification.analysis_set)
    prediction.insert(6, "selection_eligible", specification.selection_eligible)
    prediction.insert(7, "temperature_branch", temperature_branch)
    prediction.insert(8, "forcing_threshold_c_days", threshold)
    return fit_record, prediction


def metric_record(group: pd.DataFrame, grouping: dict[str, object]) -> dict[str, object]:
    valid = group.dropna(subset=["predicted_doy"])
    errors = valid["predicted_doy"].to_numpy(float) - valid["observed_doy"].to_numpy(float)
    observed = valid["observed_doy"].to_numpy(float)
    penalized_prediction = group["predicted_doy"].copy()
    missing = penalized_prediction.isna()
    if missing.any():
        year_end_next_doy = group.loc[missing, "year"].map(
            lambda value: pd.Timestamp(year=int(value), month=12, day=31).dayofyear + 1
        )
        penalized_prediction.loc[missing] = year_end_next_doy.to_numpy(float)
    penalized_errors = penalized_prediction.to_numpy(float) - group["observed_doy"].to_numpy(float)
    result: dict[str, object] = {
        **grouping,
        "n_events": int(len(group)),
        "n_predicted": int(len(valid)),
        "coverage": float(len(valid) / len(group)) if len(group) else np.nan,
        "rmse_days": float(np.sqrt(np.mean(errors**2))) if len(errors) else np.nan,
        "mae_days": float(np.mean(np.abs(errors))) if len(errors) else np.nan,
        "bias_days": float(np.mean(errors)) if len(errors) else np.nan,
        "penalized_rmse_days": float(np.sqrt(np.mean(penalized_errors**2))) if len(group) else np.nan,
        "penalized_mae_days": float(np.mean(np.abs(penalized_errors))) if len(group) else np.nan,
    }
    denominator = float(np.sum((observed - observed.mean()) ** 2)) if len(observed) else 0.0
    result["nse"] = float(1.0 - np.sum(errors**2) / denominator) if denominator > 0 else np.nan
    return result


def build_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    keys = [
        "split", "outer_fold", "inner_fold", "model_id", "stage", "analysis_set",
        "selection_eligible", "temperature_branch",
    ]
    records: list[dict[str, object]] = []
    for values, group in predictions.groupby(keys, dropna=False, sort=False):
        grouping = dict(zip(keys, values, strict=True))
        records.append(metric_record(group, {**grouping, "country_scope": "France+Germany"}))
        for country, country_group in group.groupby("country"):
            records.append(metric_record(country_group, {**grouping, "country_scope": country}))
    return pd.DataFrame.from_records(records)


def select_models(
    predictions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply the formal rule while retaining branch-specific outputs for chaining."""
    eligible = predictions.loc[
        predictions["analysis_set"].eq("independent_stage")
        & predictions["selection_eligible"].astype(bool)
    ].copy()
    metrics, stability, decisions, consensus = formal_stage_selection(eligible)
    selected_outer = []
    for row in metrics.loc[metrics["selected_within_temperature_branch"]].itertuples(index=False):
        outer = predictions.loc[
            predictions["split"].eq("outer_test")
            & predictions["outer_fold"].eq(row.outer_fold)
            & predictions["stage"].eq(row.stage)
            & predictions["temperature_branch"].eq(row.temperature_branch)
            & predictions["model_id"].eq(row.model_id)
        ].copy()
        outer["selected_by_inner_cv"] = True
        selected_outer.append(outer)
    backward = metrics.rename(
        columns={
            "mean_penalized_rmse_days": "inner_oof_rmse_days",
            "mean_penalized_mae_days": "inner_oof_mae_days",
            "pooled_complete_case_rmse_days": "inner_oof_complete_case_rmse_days",
            "mean_coverage_qc": "inner_oof_coverage",
            "selected_within_temperature_branch": "selected",
        }
    )
    return (
        backward,
        metrics,
        pd.concat(selected_outer, ignore_index=True),
        stability,
        decisions,
        consensus,
    )


def main() -> int:
    args = parse_args()
    if args.n_candidates < 21:
        raise ValueError("--n-candidates must be at least 21")
    if args.brin_forcing_candidates < 21:
        raise ValueError("--brin-forcing-candidates must be at least 21")
    if args.brin_chill_candidates < 5:
        raise ValueError("--brin-chill-candidates must be at least 5")
    specifications = default_model_specifications()
    events = read_primary_events(
        args.validation_dir,
        args.smoke_events_per_country_stage,
        args.bbch81_audit_file,
    )
    estimate = estimate_work(events, args.weather_dir, specifications)
    estimate["threshold_candidates_per_fit"] = args.n_candidates
    print("Mechanistic baseline work estimate")
    print(json.dumps(estimate, ensure_ascii=False, indent=2))
    if args.estimate_only:
        return 0

    output_dir = args.output_dir
    if args.smoke_events_per_country_stage > 0 and output_dir == DEFAULT_OUTPUT_DIR:
        output_dir = output_dir.with_name(output_dir.name + "_smoke")
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"Output directory is not empty: {output_dir}; use --overwrite")
    output_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    expanded_inner = attach_inner_folds(events, args.validation_dir)
    weather_store = load_weather_store(args.weather_dir, set(events["weather_id"]))
    fit_records: list[dict[str, object]] = []
    prediction_frames: list[pd.DataFrame] = []

    for specification in specifications:
        stage_events = events.loc[events["target_stage"].eq(specification.stage)].copy()
        if specification.analysis_set == "conditional_previous_stage":
            stage_events = stage_events.loc[stage_events["sequential_observed_start_eligible"].astype(bool)].copy()
        stage_expanded = expanded_inner.loc[expanded_inner["record_id"].isin(stage_events["record_id"])].copy()
        if stage_events.empty:
            continue
        event_lookup = stage_events.set_index("record_id", drop=False)
        fold_tasks = build_fold_tasks(stage_events, stage_expanded)
        for branch in TEMPERATURE_BRANCH_COLUMNS:
            if specification.family == "brin_bidabe_richardson":
                brin_fits, brin_predictions = run_brin_branch(
                    weather_store,
                    stage_events,
                    fold_tasks,
                    specification,
                    branch,
                    args.brin_chill_candidates,
                    args.brin_forcing_candidates,
                    args.n_jobs,
                )
                fit_records.extend(brin_fits)
                prediction_frames.extend(brin_predictions)
                continue
            profiles = build_profiles(weather_store, stage_events, specification, branch)
            label = f"{specification.model_id} | {branch}"
            with ThreadPoolExecutor(max_workers=args.n_jobs) as executor:
                futures = [
                    executor.submit(
                        run_fold_task,
                        task,
                        event_lookup,
                        profiles,
                        specification,
                        branch,
                        args.n_candidates,
                    )
                    for task in fold_tasks
                ]
                for future in tqdm(as_completed(futures), total=len(futures), desc=label, unit="fold"):
                    fit, prediction = future.result()
                    fit_records.append(fit)
                    prediction_frames.append(prediction)
            del profiles

    fits = pd.DataFrame.from_records(fit_records)
    predictions = pd.concat(prediction_frames, ignore_index=True)
    metrics = build_metrics(predictions)
    selection, formal_metrics, selected_outer, stability, decisions, consensus = select_models(predictions)
    selected_metrics = build_metrics(selected_outer)

    predictions.to_parquet(output_dir / "nested_cv_predictions.parquet", index=False)
    fits.to_csv(output_dir / "nested_cv_threshold_fits.csv", index=False)
    metrics.to_csv(output_dir / "nested_cv_metrics.csv", index=False)
    selection.to_csv(output_dir / "inner_cv_model_selection.csv", index=False)
    formal_metrics.to_csv(output_dir / "stage_model_selection_metrics.csv", index=False)
    stability.to_csv(output_dir / "stage_model_stability.csv", index=False)
    decisions.to_csv(output_dir / "stage_model_selection_decisions.csv", index=False)
    consensus.to_csv(output_dir / "stage_model_selection_consensus.csv", index=False)
    build_final_selection_record(consensus).to_csv(
        output_dir / "stage_model_final_selection.csv", index=False
    )
    selected_outer.to_parquet(output_dir / "selected_model_outer_predictions.parquet", index=False)
    selected_metrics.to_csv(output_dir / "selected_model_outer_metrics.csv", index=False)
    primary_export = events.drop(columns=["model_tier", "analysis_role"], errors="ignore")
    primary_export.to_csv(output_dir / "primary_analysis_event_index.csv", index=False)

    elapsed = time.perf_counter() - started
    summary = {
        **estimate,
        "n_jobs": args.n_jobs,
        "bbch81_audit_file": str(args.bbch81_audit_file) if args.bbch81_audit_file else None,
        "brin_chill_candidates": int(len(brin_chill_grid(args.brin_chill_candidates))),
        "brin_forcing_candidates": args.brin_forcing_candidates,
        "brin_chill_start_month_day": "08-01",
        "smoke_events_per_country_stage": args.smoke_events_per_country_stage,
        "elapsed_seconds": round(elapsed, 3),
        "prediction_rows": int(len(predictions)),
        "fit_rows": int(len(fits)),
        "selected_outer_prediction_rows": int(len(selected_outer)),
        "primary_tier_handling": "core and extended pooled; tier columns removed from analysis export",
        "output_directory": display_path(output_dir),
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nMechanistic baseline completed")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
