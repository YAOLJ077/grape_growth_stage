"""Reusable thermal-time model primitives for grape phenology.

This module intentionally contains no global calibration. Parameters are fitted
inside caller-supplied training folds, and prediction consumes explicit weather
and temperature-column inputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


TEMPERATURE_BRANCH_COLUMNS = {
    "raw": {
        "tmean": "temperature_2m_c",
        "tmin": "temperature_2m_min_c",
        "tmax": "temperature_2m_max_c",
    },
    "adjusted_6p5": {
        "tmean": "temperature_2m_c_adjusted_main_6p5c_km",
        "tmin": "temperature_2m_min_c_adjusted_main_6p5c_km",
        "tmax": "temperature_2m_max_c_adjusted_main_6p5c_km",
    },
}


@dataclass(frozen=True)
class ThermalModelSpecification:
    model_id: str
    stage: str
    family: str
    comparison_role: str
    start_mode: str
    start_doy: int
    base_temperature_c: float
    threshold_mode: str
    forcing_threshold_c_days: float | None
    parameter_status: str
    literature_basis: str
    notes: str
    analysis_set: str
    selection_eligible: bool

    def as_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ThermalModelFit:
    model_id: str
    forcing_threshold_c_days: float
    objective: str
    objective_value_days: float
    n_training_events: int
    n_threshold_candidates: int


def default_model_specifications() -> list[ThermalModelSpecification]:
    """Return the frozen four-stage comparison set.

    Fully external thresholds are included only when a defensible published
    cultivar set is available. Literature-median thresholds are diagnostic
    transfer benchmarks, not claimed universal grapevine constants.
    """
    budburst_reference = (
        "García de Cortázar-Atauri et al. 2009, "
        "doi:10.1007/s00484-009-0217-4, Table 8."
    )
    parker_reference = (
        "Parker et al. 2011, doi:10.1111/j.1755-0238.2011.00140.x, "
        "Tables 5-7."
    )
    specifications = [
        ThermalModelSpecification(
            model_id="budburst__fixed_gdd5_external_median",
            stage="budburst",
            family="conventional_gdd",
            comparison_role="external_fixed_reference_only",
            start_mode="calendar_doy",
            start_doy=1,
            base_temperature_c=5.0,
            threshold_mode="fixed_external",
            forcing_threshold_c_days=265.3,
            parameter_status="ready_fixed_external",
            literature_basis=budburst_reference,
            notes="F*=265.3 degC d is the precomputed median of 10 published cultivar-specific GDD5 thresholds; it is not a universal constant.",
            analysis_set="independent_stage",
            selection_eligible=False,
        ),
        ThermalModelSpecification(
            model_id="budburst__calibrated_gdd5",
            stage="budburst",
            family="conventional_gdd",
            comparison_role="calibrated_candidate",
            start_mode="calendar_doy",
            start_doy=1,
            base_temperature_c=5.0,
            threshold_mode="fit_training_fold_only",
            forcing_threshold_c_days=None,
            parameter_status="ready_for_nested_cv",
            literature_basis=budburst_reference,
            notes="Only F* is calibrated within the active training fold.",
            analysis_set="independent_stage",
            selection_eligible=True,
        ),
        ThermalModelSpecification(
            model_id="budburst__calibrated_brin_aug1",
            stage="budburst",
            family="brin_bidabe_richardson",
            comparison_role="calibrated_candidate",
            start_mode="dormancy_break",
            start_doy=213,
            base_temperature_c=5.0,
            threshold_mode="fit_brin_training_fold_only",
            forcing_threshold_c_days=None,
            parameter_status="ready_for_nested_cv",
            literature_basis=budburst_reference,
            notes=(
                "BRIN structure with Q10=2.17, T0B=5 degC and TMB=25 degC. "
                "The weather window begins on the published previous-year August 1; "
                "both Cc and Gh are fitted only inside the active training fold."
            ),
            analysis_set="independent_stage",
            selection_eligible=True,
        ),
    ]
    for stage, external_threshold in (("flowering", 1266.0), ("veraison", 2598.0)):
        specifications.extend(
            [
                ThermalModelSpecification(
                    model_id=f"{stage}__calibrated_gdd10",
                    stage=stage,
                    family="conventional_gdd",
                    comparison_role="calibrated_candidate",
                    start_mode="calendar_doy",
                    start_doy=1,
                    base_temperature_c=10.0,
                    threshold_mode="fit_training_fold_only",
                    forcing_threshold_c_days=None,
                    parameter_status="ready_for_nested_cv",
                    literature_basis=parker_reference,
                    notes="Classical Jan-1 GDD10 structure; only F* is calibrated within the active training fold.",
                    analysis_set="independent_stage",
                    selection_eligible=True,
                ),
                ThermalModelSpecification(
                    model_id=f"{stage}__fixed_gfv_external_median",
                    stage=stage,
                    family="gfv_spring_warming",
                    comparison_role="external_fixed_reference_only",
                    start_mode="calendar_doy",
                    start_doy=60,
                    base_temperature_c=0.0,
                    threshold_mode="fixed_external",
                    forcing_threshold_c_days=external_threshold,
                    parameter_status="ready_fixed_external",
                    literature_basis=parker_reference,
                    notes="F* is the precomputed median of 11 published cultivar-specific GFV thresholds; it is a diagnostic transfer benchmark.",
                    analysis_set="independent_stage",
                    selection_eligible=False,
                ),
                ThermalModelSpecification(
                    model_id=f"{stage}__calibrated_gfv",
                    stage=stage,
                    family="gfv_spring_warming",
                    comparison_role="calibrated_candidate",
                    start_mode="calendar_doy",
                    start_doy=60,
                    base_temperature_c=0.0,
                    threshold_mode="fit_training_fold_only",
                    forcing_threshold_c_days=None,
                    parameter_status="ready_for_nested_cv",
                    literature_basis=parker_reference,
                    notes="GFV structure is fixed; only F* is calibrated within the active training fold.",
                    analysis_set="independent_stage",
                    selection_eligible=True,
                ),
            ]
        )
    specifications.extend(
        [
            ThermalModelSpecification(
                model_id="maturity_or_harvest__calibrated_seasonal_gdd10",
                stage="maturity_or_harvest",
                family="conventional_gdd",
                comparison_role="calibrated_candidate",
                start_mode="calendar_doy",
                start_doy=1,
                base_temperature_c=10.0,
                threshold_mode="fit_training_fold_only",
                forcing_threshold_c_days=None,
                parameter_status="ready_for_nested_cv",
                literature_basis="Conventional seasonal GDD10 comparator; no universal BBCH89 F* is imposed.",
                notes="Only F* is calibrated within the active training fold; BBCH89 is interpreted as an operational maturity/harvest endpoint.",
                analysis_set="independent_stage",
                selection_eligible=True,
            ),
            ThermalModelSpecification(
                model_id="maturity_or_harvest__calibrated_post_veraison_gdd10",
                stage="maturity_or_harvest",
                family="sequential_gdd",
                comparison_role="conditional_candidate",
                start_mode="previous_observed_stage",
                start_doy=0,
                base_temperature_c=10.0,
                threshold_mode="fit_training_fold_only",
                forcing_threshold_c_days=None,
                parameter_status="ready_for_nested_cv",
                literature_basis="Thermal-time phase-duration comparator; no universal BBCH81-to-BBCH89 F* is imposed.",
                notes="Accumulation begins on the day after observed BBCH81. This conditional model is evaluated separately and is not directly ranked against the full-sample seasonal model.",
                analysis_set="conditional_previous_stage",
                selection_eligible=False,
            ),
        ]
    )
    return specifications


def daily_gdd(temperature_c: pd.Series | np.ndarray, base_temperature_c: float) -> np.ndarray:
    values = np.asarray(temperature_c, dtype=float)
    return np.maximum(values - float(base_temperature_c), 0.0)


def brin_hourly_temperature(
    daily_minimum_c: float,
    daily_maximum_c: float,
    next_daily_minimum_c: float,
) -> np.ndarray:
    """Reconstruct BRIN hourly temperatures using the published linear rule."""
    hours = np.arange(1.0, 25.0, dtype=float)
    daytime = daily_minimum_c + hours * (daily_maximum_c - daily_minimum_c) / 12.0
    nighttime = daily_maximum_c - (hours - 12.0) * (
        daily_maximum_c - next_daily_minimum_c
    ) / 12.0
    return np.where(hours <= 12.0, daytime, nighttime)


def brin_daily_chill_action(
    daily_minimum_c: pd.Series | np.ndarray,
    daily_maximum_c: pd.Series | np.ndarray,
    q10: float = 2.17,
) -> np.ndarray:
    """Return Bidabe daily cold actions used by BRIN."""
    minimum = np.asarray(daily_minimum_c, dtype=float)
    maximum = np.asarray(daily_maximum_c, dtype=float)
    if minimum.shape != maximum.shape:
        raise ValueError("BRIN minimum and maximum temperature arrays must have equal shapes")
    if q10 <= 0:
        raise ValueError("BRIN Q10 must be positive")
    return np.power(float(q10), -maximum / 10.0) + np.power(
        float(q10), -minimum / 10.0
    )


def brin_daily_gdh(
    daily_minimum_c: pd.Series | np.ndarray,
    daily_maximum_c: pd.Series | np.ndarray,
    base_temperature_c: float = 5.0,
    maximum_temperature_c: float = 25.0,
) -> np.ndarray:
    """Return Richardson growing-degree hours from BRIN hourly interpolation."""
    minimum = np.asarray(daily_minimum_c, dtype=float)
    maximum = np.asarray(daily_maximum_c, dtype=float)
    if minimum.shape != maximum.shape:
        raise ValueError("BRIN minimum and maximum temperature arrays must have equal shapes")
    if len(minimum) == 0:
        return np.asarray([], dtype=float)
    next_minimum = np.concatenate([minimum[1:], minimum[-1:]])
    upper_response = float(maximum_temperature_c) - float(base_temperature_c)
    if upper_response <= 0:
        raise ValueError("BRIN maximum temperature must exceed the base temperature")
    hours = np.arange(1.0, 25.0, dtype=float)[None, :]
    tmin = minimum[:, None]
    tmax = maximum[:, None]
    next_tmin = next_minimum[:, None]
    daytime = tmin + hours * (tmax - tmin) / 12.0
    nighttime = tmax - (hours - 12.0) * (tmax - next_tmin) / 12.0
    hourly = np.where(hours <= 12.0, daytime, nighttime)
    return np.clip(
        hourly - float(base_temperature_c), 0.0, upper_response
    ).sum(axis=1)


def validate_weather_frame(weather: pd.DataFrame, temperature_column: str) -> None:
    required = {"weather_id", "year", "weather_year", "weather_doy", temperature_column}
    missing = required.difference(weather.columns)
    if missing:
        raise ValueError(f"Weather frame is missing columns: {sorted(missing)}")
    if weather[["weather_id", "year", "weather_year", "weather_doy", temperature_column]].isna().any().any():
        raise ValueError("Thermal model weather inputs cannot contain missing values")
    duplicate = weather.duplicated(["weather_id", "weather_year", "weather_doy"])
    if duplicate.any():
        raise ValueError("Weather frame contains duplicate weather_id-year-DOY rows")


def build_forcing_profiles(
    weather: pd.DataFrame,
    temperature_column: str,
    start_doy: int,
    base_temperature_c: float,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Build target-year DOY and cumulative-forcing arrays for each weather_id."""
    validate_weather_frame(weather, temperature_column)
    target_year = pd.to_numeric(weather["year"], errors="raise").astype(int)
    weather_year = pd.to_numeric(weather["weather_year"], errors="raise").astype(int)
    weather_doy = pd.to_numeric(weather["weather_doy"], errors="raise").astype(int)
    mask = weather_year.eq(target_year) & weather_doy.ge(int(start_doy))
    work = weather.loc[mask, ["weather_id", "weather_doy", temperature_column]].copy()
    work["weather_doy"] = pd.to_numeric(work["weather_doy"], errors="raise").astype(int)
    work["daily_forcing"] = daily_gdd(work[temperature_column], base_temperature_c)
    work = work.sort_values(["weather_id", "weather_doy"])
    work["cumulative_forcing"] = work.groupby("weather_id")["daily_forcing"].cumsum()
    profiles: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for weather_id, group in work.groupby("weather_id", sort=False):
        profiles[str(weather_id)] = (
            group["weather_doy"].to_numpy(dtype=int),
            group["cumulative_forcing"].to_numpy(dtype=float),
        )
    return profiles


def predict_from_profiles(
    profiles: dict[str, tuple[np.ndarray, np.ndarray]],
    forcing_threshold_c_days: float,
    weather_ids: list[str] | np.ndarray | pd.Series | None = None,
) -> pd.DataFrame:
    if forcing_threshold_c_days <= 0:
        raise ValueError("Forcing threshold must be positive")
    identifiers = list(profiles) if weather_ids is None else [str(value) for value in weather_ids]
    records: list[dict[str, object]] = []
    for weather_id in identifiers:
        if weather_id not in profiles:
            records.append({"weather_id": weather_id, "predicted_doy": np.nan, "threshold_reached": False})
            continue
        doy, cumulative = profiles[weather_id]
        crossing = int(np.searchsorted(cumulative, forcing_threshold_c_days, side="left"))
        reached = crossing < len(doy)
        records.append(
            {
                "weather_id": weather_id,
                "predicted_doy": float(doy[crossing]) if reached else np.nan,
                "threshold_reached": bool(reached),
            }
        )
    return pd.DataFrame.from_records(records)


def forcing_at_observed_events(
    profiles: dict[str, tuple[np.ndarray, np.ndarray]],
    observations: pd.DataFrame,
) -> pd.DataFrame:
    required = {"weather_id", "event_doy"}
    missing = required.difference(observations.columns)
    if missing:
        raise ValueError(f"Observations are missing columns: {sorted(missing)}")
    records: list[dict[str, object]] = []
    for row in observations[["weather_id", "event_doy"]].itertuples(index=False):
        weather_id = str(row.weather_id)
        if weather_id not in profiles:
            continue
        doy, cumulative = profiles[weather_id]
        position = int(np.searchsorted(doy, int(row.event_doy), side="right") - 1)
        if position >= 0:
            records.append(
                {
                    "weather_id": weather_id,
                    "event_doy": float(row.event_doy),
                    "forcing_at_event": float(cumulative[position]),
                }
            )
    return pd.DataFrame.from_records(records)


def calibrate_forcing_threshold(
    profiles: dict[str, tuple[np.ndarray, np.ndarray]],
    observations: pd.DataFrame,
    specification: ThermalModelSpecification,
    objective: str = "rmse",
    n_candidates: int = 401,
) -> ThermalModelFit:
    """Fit F* on supplied training observations only using a deterministic grid."""
    if specification.threshold_mode != "fit_training_fold_only":
        raise ValueError("Only training-fold-calibrated specifications can be fitted")
    if objective not in {"rmse", "mae"}:
        raise ValueError("objective must be 'rmse' or 'mae'")
    observed_forcing = forcing_at_observed_events(profiles, observations)
    if len(observed_forcing) < 2:
        raise ValueError("At least two training events with forcing profiles are required")
    lower = max(float(observed_forcing["forcing_at_event"].min()), 1e-6)
    upper = float(observed_forcing["forcing_at_event"].max())
    if not upper > lower:
        raise ValueError("Training events do not identify a positive forcing-threshold range")
    candidates = np.linspace(lower, upper, int(n_candidates))
    observed = observations[["weather_id", "event_doy"]].copy()
    observed["weather_id"] = observed["weather_id"].astype(str)
    best_threshold = None
    best_value = np.inf
    for threshold in candidates:
        predicted = predict_from_profiles(profiles, float(threshold), observed["weather_id"])
        comparison = observed.merge(predicted, on="weather_id", how="left", validate="one_to_one")
        errors = comparison["predicted_doy"] - comparison["event_doy"]
        errors = errors.dropna().to_numpy(dtype=float)
        if not len(errors):
            continue
        value = float(np.sqrt(np.mean(errors**2))) if objective == "rmse" else float(np.mean(np.abs(errors)))
        if value < best_value:
            best_value = value
            best_threshold = float(threshold)
    if best_threshold is None:
        raise RuntimeError("No forcing threshold produced a valid prediction")
    return ThermalModelFit(
        model_id=specification.model_id,
        forcing_threshold_c_days=best_threshold,
        objective=objective,
        objective_value_days=best_value,
        n_training_events=int(len(observations)),
        n_threshold_candidates=int(n_candidates),
    )


def predict_thermal_model(
    weather: pd.DataFrame,
    specification: ThermalModelSpecification,
    temperature_branch: str,
    forcing_threshold_c_days: float | None = None,
    weather_ids: list[str] | np.ndarray | pd.Series | None = None,
) -> pd.DataFrame:
    if temperature_branch not in TEMPERATURE_BRANCH_COLUMNS:
        raise ValueError(f"Unknown temperature branch: {temperature_branch}")
    threshold = forcing_threshold_c_days
    if threshold is None:
        threshold = specification.forcing_threshold_c_days
    if threshold is None:
        raise ValueError(
            f"{specification.model_id} has no frozen or fitted forcing threshold"
        )
    temperature_column = TEMPERATURE_BRANCH_COLUMNS[temperature_branch]["tmean"]
    profiles = build_forcing_profiles(
        weather,
        temperature_column,
        specification.start_doy,
        specification.base_temperature_c,
    )
    predictions = predict_from_profiles(profiles, float(threshold), weather_ids)
    predictions.insert(1, "model_id", specification.model_id)
    predictions.insert(2, "temperature_branch", temperature_branch)
    return predictions
