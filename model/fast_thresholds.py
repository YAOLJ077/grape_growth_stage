"""Numba-accelerated fitting for the literature-fixed response profile.

This module deliberately has a narrow contract.  It accepts only settings made
by :func:`model.structure_comparison.threshold_only_settings`, so rate arrays
are fixed for the whole optimization and only thermal requirements vary.
"""
from dataclasses import asdict
import hashlib
import math
import platform
from threading import Lock

import numpy as np
import pandas as pd
import scipy
from scipy.optimize import differential_evolution

try:  # Keep ``import model.fast_thresholds`` harmless in minimal installations.
    from numba import njit, prange
except ModuleNotFoundError:  # pragma: no cover - exercised where optional dependency is absent.
    njit = None
    prange = None

from . import responses
from .calibration import FitResult, FitSettings, UNATTAINED_PENALTY_DAYS, _BalancedLoss, _weather_hash
from .data import observations, prepare_weather
from .parameters import validate_bounds, validate_parameters
from .registry import get_model
from .specification import STAGES
from .structure_comparison import fixed_parameters, threshold_only_settings


_ATTAINED = 0
_PREVIOUS_STAGE_UNATTAINED = 1
_UNMET_CHILLING = 2
_UNMET_FORCING = 3
_STATUS = ("attained", "previous_stage_unattained", "unmet_chilling", "unmet_forcing")
_SEASONAL_KERNEL_LOCK = Lock()


def _require_numba():
    if njit is None:
        raise RuntimeError("model.fast_thresholds requires optional dependency numba")


if njit is not None:
    @njit(cache=False, fastmath=False, parallel=True)
    def _seasonal_batch_parallel(forcing_rates, chilling_cumulative, chilling_before, lengths, forcing_requirements,
                                 chilling_requirement, minimum_response, interaction):
        """Return positions, accumulation starts and statuses for every season.

        ``interaction`` is 0 (forcing), 1 (sequential) or 2 (parallel).  The
        scalar loops preserve the reference model's discarded overshoot and
        next-day restart behavior.
        """
        n = lengths.size
        positions = np.full((n, 4), -1, dtype=np.int64)
        starts = np.full((n, 4), -1, dtype=np.int64)
        statuses = np.full((n, 4), _PREVIOUS_STAGE_UNATTAINED, dtype=np.int64)
        chilling_attained = np.full(n, -1, dtype=np.int64)
        for item in prange(n):
            length = lengths[item]
            start = 0
            if interaction == 1:
                low, high = 0, length
                threshold = chilling_requirement * (1.0 - 1e-12)
                while low < high:
                    middle = low + (high - low) // 2
                    if chilling_cumulative[item, middle] >= threshold:
                        high = middle
                    else:
                        low = middle + 1
                chill_crossing = low
                start = chill_crossing + 1
            failed = False
            for stage in range(4):
                if failed:
                    statuses[item, stage] = _PREVIOUS_STAGE_UNATTAINED
                    continue
                if start < length:
                    starts[item, stage] = start
                if start >= length:
                    statuses[item, stage] = _UNMET_CHILLING if stage == 0 and interaction == 1 else _UNMET_FORCING
                    failed = True
                    if stage == 0 and interaction != 0:
                        chilling_attained[item] = 1 if chilling_cumulative[item, length - 1] >= chilling_requirement - 1e-12 else 0
                    continue
                total = 0.0
                crossing = -1
                for day in range(start, length):
                    rate = forcing_rates[item, stage, day]
                    if stage == 0 and interaction == 2:
                        competence = minimum_response + (1.0 - minimum_response) * min(
                            chilling_before[item, day] / chilling_requirement, 1.0)
                        rate *= competence
                    total += rate
                    if total >= forcing_requirements[stage] * (1.0 - 1e-12):
                        crossing = day
                        break
                if crossing >= 0:
                    positions[item, stage] = crossing
                    statuses[item, stage] = _ATTAINED
                    if stage == 0 and interaction != 0:
                        chilling_attained[item] = 1 if chilling_cumulative[item, crossing] >= chilling_requirement - 1e-12 else 0
                    start = crossing + 1
                else:
                    statuses[item, stage] = _UNMET_FORCING
                    failed = True
                    if stage == 0 and interaction != 0:
                        chilling_attained[item] = 1 if chilling_cumulative[item, length - 1] >= chilling_requirement - 1e-12 else 0
        return positions, starts, statuses, chilling_attained

    def _seasonal_batch(forcing_rates, chilling_cumulative, chilling_before, lengths, forcing_requirements,
                        chilling_requirement, minimum_response, interaction):
        # Independent seasons run in parallel; each season retains scalar daily
        # accumulation. The built-in Numba workqueue rejects concurrent callers,
        # including the runner's two Python fitting threads, so serialize entry.
        with _SEASONAL_KERNEL_LOCK:
            return _seasonal_batch_parallel(
                forcing_rates, chilling_cumulative, chilling_before, lengths, forcing_requirements,
                chilling_requirement, minimum_response, interaction,
            )
else:
    _seasonal_batch = None
    _seasonal_batch_parallel = None


def _fixed_profile_settings(model_name, settings: FitSettings) -> FitSettings:
    """Reject profiles whose rates would change during optimization."""
    settings.validate()
    expected = threshold_only_settings(
        model_name, seeds=settings.seeds, maxiter=settings.maxiter, popsize=settings.popsize,
        tol=settings.tol, temperature_column=settings.temperature_column,
        temperature_input=settings.temperature_input,
    )
    if settings.bounds != expected.bounds or settings.fixed_parameters != expected.fixed_parameters:
        raise ValueError("fast_thresholds accepts only threshold_only_settings with the fixed-response profile")
    return expected


def _rate_cache(model_name, parameters, prepared):
    """Cache fixed float64 daily response arrays once for a batch of seasons."""
    spec = get_model(model_name)
    lengths = np.asarray([len(item.temperature) for item in prepared], dtype=np.int64)
    maximum = int(lengths.max())
    forcing = np.zeros((len(prepared), 4, maximum), dtype=np.float64)
    chilling_cumulative = np.zeros((len(prepared), maximum), dtype=np.float64)
    chilling_before = np.zeros((len(prepared), maximum), dtype=np.float64)
    dates = np.full((len(prepared), maximum), np.datetime64("NaT", "D").astype("int64"), dtype=np.int64)
    for index, item in enumerate(prepared):
        n = lengths[index]
        temperature = np.asarray(item.temperature, dtype=np.float64)
        dates[index, :n] = item.dates.astype("datetime64[D]").astype("int64")
        if spec.chilling != "none":
            rates = (responses.triangular(temperature, parameters["chilling_minimum"],
                                          parameters["chilling_optimum"], parameters["chilling_maximum"])
                     if spec.chilling == "triangular" else
                     responses.beta(temperature, parameters["chilling_minimum"],
                                    parameters["chilling_optimum"], parameters["chilling_maximum"]))
            chilling_cumulative[index, :n] = np.cumsum(rates)
            chilling_before[index, 1:n] = chilling_cumulative[index, :n - 1]
        for stage_index, stage in enumerate(STAGES):
            forcing[index, stage_index, :n] = (
                responses.linear(temperature, parameters[f"forcing_base_{stage}"])
                if spec.forcing == "linear" else
                responses.beta(temperature, parameters["forcing_minimum"],
                               parameters[f"forcing_optimum_{stage}"], parameters["forcing_maximum"])
            )
    return forcing, chilling_cumulative, chilling_before, lengths, dates


def _interaction_code(model_name):
    interaction = get_model(model_name).interaction
    return {"none": 0, "sequential": 1, "parallel": 2}[interaction]


def _requirements(parameters):
    return np.asarray([parameters[f"forcing_requirement_{stage}"] for stage in STAGES], dtype=np.float64)


def _fixed_parameters_for_prediction(model_name, parameters):
    validate_parameters(model_name, parameters)
    required_fixed = fixed_parameters(model_name)
    mismatches = [key for key, value in required_fixed.items()
                  if not math.isclose(float(parameters[key]), float(value), rel_tol=0., abs_tol=0.)]
    if mismatches:
        raise ValueError("fast_thresholds requires the fixed-response profile; differing parameters: " + ", ".join(mismatches))


def _predict_arrays(model_name, parameters, prepared):
    _require_numba()
    _fixed_parameters_for_prediction(model_name, parameters)
    forcing, chilling_cumulative, chilling_before, lengths, dates = _rate_cache(model_name, parameters, prepared)
    positions, starts, statuses, chilling_attained = _seasonal_batch(
        forcing, chilling_cumulative, chilling_before, lengths, _requirements(parameters),
        float(parameters.get("chilling_requirement", 1.0)), float(parameters.get("minimum_response", 0.0)),
        _interaction_code(model_name),
    )
    return positions, starts, statuses, chilling_attained, dates


def _predict_frame(model_name, parameters, prepared, temperature_input):
    positions, starts, statuses, chilling_attained, dates = _predict_arrays(model_name, parameters, prepared)
    records = []
    for item_index, season_weather in enumerate(prepared):
        january = pd.Timestamp(season_weather.season, 1, 1)
        for stage_index, stage in enumerate(STAGES):
            position = positions[item_index, stage_index]
            start = starts[item_index, stage_index]
            date = (pd.Timestamp(dates[item_index, position], unit="D") if position >= 0 else pd.NaT)
            phase_start = (pd.Timestamp(dates[item_index, start], unit="D") if start >= 0 else pd.NaT)
            attained = position >= 0
            chilling_value = chilling_attained[item_index]
            records.append({"site": season_weather.site, "season": season_weather.season,
                            "BBCH": stage, "model_name": model_name, "temperature_input": temperature_input,
                            "predicted_date": date,
                            "predicted_doy": (date - january).days + 1 if attained else np.nan,
                            "status": _STATUS[statuses[item_index, stage_index]],
                            "chilling_attained": None if chilling_value < 0 else bool(chilling_value),
                            "outside_target_year": bool(attained and date.year != season_weather.season),
                            "phase_start_date": phase_start})
    return pd.DataFrame.from_records(records)


def predict_with_starts(model_name, parameters, weather, seasons, *, temperature_column="Tmean", temperature_input="RAW"):
    """Predict fixed-profile stages and expose model-derived accumulation starts."""
    if temperature_input not in {"RAW", "DEM"}:
        raise ValueError("temperature_input must be RAW or DEM")
    _fixed_parameters_for_prediction(model_name, parameters)
    prepared = prepare_weather(weather, seasons, temperature_column, parameters.get("start_doy"))
    return _predict_frame(model_name, parameters, prepared, temperature_input)


def _gather_errors(positions, date_numbers, season_indices, stage_indices, observed_dates):
    """Map attained seasonal positions to exact calendar errors in observation order."""
    selected_positions = positions[season_indices, stage_indices]
    attained = selected_positions >= 0
    values = np.full(len(season_indices), np.nan, dtype=float)
    # Mask before date indexing: -1 denotes nonattainment, not the last day.
    values[attained] = (date_numbers[season_indices[attained], selected_positions[attained]]
                        - observed_dates[attained])
    return values


class _FastObjective:
    def __init__(self, model_name, frame, prepared, bounds, fixed):
        self.name = model_name
        self.names = tuple(bounds)
        self.fixed = fixed
        self.loss = _BalancedLoss(frame)
        self.prepared = prepared
        self.positions, self.starts, self.statuses, self.chilling_attained, self.dates = _predict_arrays(
            model_name, {**fixed, **{key: lo for key, (lo, _) in bounds.items()}}, prepared)
        # The preceding call compiled the backend. Rates are rebuilt below using fixed values;
        # only requirements are subsequently read by the numerical objective.
        (self.forcing, self.chilling_cumulative, self.chilling_before,
         self.lengths, self.date_numbers) = _rate_cache(model_name, fixed, prepared)
        lookup = {(item.site, item.season): index for index, item in enumerate(prepared)}
        self.season_indices = np.asarray([lookup[key] for key in frame[["site", "season"]].itertuples(index=False, name=None)], dtype=np.int64)
        self.stage_indices = frame.BBCH.map({stage: index for index, stage in enumerate(STAGES)}).to_numpy(dtype=np.int64)
        self.observed_dates = frame.Date.to_numpy(dtype="datetime64[D]").astype("int64")
        self.interaction = _interaction_code(model_name)
        self.minimum_response = float(fixed.get("minimum_response", 0.0))

    def decode(self, vector):
        return {**self.fixed, **{key: (int(round(value)) if key == "start_doy" else float(value))
                                for key, value in zip(self.names, vector)}}

    def errors(self, parameters):
        positions, _, _, _ = _seasonal_batch(
            self.forcing, self.chilling_cumulative, self.chilling_before, self.lengths, _requirements(parameters),
            float(parameters.get("chilling_requirement", 1.0)), self.minimum_response, self.interaction,
        )
        return _gather_errors(positions, self.date_numbers, self.season_indices,
                              self.stage_indices, self.observed_dates)

    def __call__(self, vector):
        parameters = self.decode(vector)
        try:
            validate_parameters(self.name, parameters)
        except ValueError:
            return np.inf
        return self.loss(self.errors(parameters))


def fit(model_name, calibration_observations, weather, settings: FitSettings | None = None) -> FitResult:
    """Fit threshold-only fixed-response models with the compiled seasonal kernel."""
    _require_numba()
    settings = _fixed_profile_settings(model_name, settings or FitSettings())
    spec = get_model(model_name)
    frame = observations(calibration_observations)
    _BalancedLoss(frame)
    fixed = fixed_parameters(model_name)
    bounds = validate_bounds(model_name, settings.bounds, settings.fixed_parameters)
    keys = list(frame[["site", "season"]].drop_duplicates().itertuples(index=False, name=None))
    earliest = math.ceil(bounds["start_doy"][0]) if spec.interaction == "none" else None
    prepared = prepare_weather(weather, keys, settings.temperature_column, earliest)
    objective = _FastObjective(model_name, frame, prepared, bounds, fixed)
    restarts, best = [], None
    for seed in settings.seeds:
        result = differential_evolution(objective, list(bounds.values()), seed=seed,
                                        maxiter=settings.maxiter, popsize=settings.popsize, tol=settings.tol,
                                        polish=False, workers=1,
                                        integrality=[key == "start_doy" for key in bounds])
        finite = bool(np.isfinite(result.fun))
        restarts.append({"seed": seed, "objective_value": float(result.fun) if finite else None,
                         "converged": bool(result.success), "message": str(result.message),
                         "nfev": int(result.nfev), "nit": int(result.nit)})
        if finite and (best is None or result.fun < best.fun):
            best = result
    if best is None:
        raise ValueError("No feasible finite calibration solution; inspect parameter bounds")
    parameters = objective.decode(best.x)
    validate_parameters(model_name, parameters)
    errors = objective.errors(parameters)
    attained = {stage: int(np.isfinite(errors[frame.BBCH.to_numpy() == stage]).sum()) for stage in STAGES}
    if not all(attained.values()):
        raise ValueError(f"No finite predictions for at least one calibration stage: {attained}")
    boundary_hits = []
    for key, (lo, hi) in bounds.items():
        if lo != hi:
            tolerance = max(1e-8, (hi - lo) * 1e-4)
            if parameters[key] - lo <= tolerance or hi - parameters[key] <= tolerance:
                boundary_hits.append(key)
    calibration_hash = hashlib.sha256(frame.to_csv(index=False, date_format="%Y-%m-%d").encode()).hexdigest()
    diagnostics = {"objective": "mean_stage_site_balanced_rmse", "unattained_penalty_days": UNATTAINED_PENALTY_DAYS,
                   "n_observations": len(frame), "n_sites": int(frame.site.nunique()), "n_seasons": len(keys),
                   "attained_by_stage": attained, "boundary_hits": boundary_hits,
                   "fixed_by_equal_bounds": [key for key, (lo, hi) in bounds.items() if lo == hi], "restarts": restarts,
                   "engine": "numba", "compiled_backend": True}
    return FitResult(model_name, spec.version, parameters, settings.temperature_input, settings.temperature_column,
                     float(best.fun), bool(best.success), bounds, asdict(settings), calibration_hash,
                     _weather_hash(prepared), diagnostics,
                     {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                      "scipy": scipy.__version__})
