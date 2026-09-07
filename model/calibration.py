"""Joint four-stage calibration using only explicitly supplied calibration records."""
from dataclasses import asdict, dataclass
import hashlib
import math
import platform

import numpy as np
import pandas as pd
import scipy
from scipy.optimize import NonlinearConstraint, differential_evolution

from .data import observations, prepare_weather
from .parameters import default_bounds, default_parameters, validate_bounds, validate_parameters
from .registry import get_model
from .simulation import simulate_season
from .specification import STAGES

UNATTAINED_PENALTY_DAYS = 1000.


@dataclass(frozen=True)
class FitSettings:
    bounds: dict | None = None
    fixed_parameters: dict | None = None
    seeds: tuple[int, ...] = (20260907, 20260908, 20260909)
    maxiter: int = 300
    popsize: int = 15
    tol: float = .001
    temperature_column: str = "tmean_c"
    temperature_input: str = "RAW"

    def validate(self):
        if (not self.seeds or any(isinstance(s, bool) or not isinstance(s, int)
                                 or not 0 <= s < 2**32 for s in self.seeds)):
            raise ValueError("seeds must contain integer seeds within [0, 2**32)")
        if any(isinstance(v, bool) or not isinstance(v, int) or v < minimum
               for v, minimum in ((self.maxiter, 0), (self.popsize, 1))):
            raise ValueError("maxiter must be a nonnegative integer and popsize a positive integer")
        if not math.isfinite(self.tol) or self.tol < 0:
            raise ValueError("tol must be finite and nonnegative")
        if self.temperature_input not in {"RAW", "DEM"}:
            raise ValueError("temperature_input must be RAW or DEM")


@dataclass(frozen=True)
class FitResult:
    model_name: str
    definition_version: str
    parameters: dict
    temperature_input: str
    temperature_column: str
    objective_value: float
    optimizer_converged: bool
    bounds: dict
    settings: dict
    calibration_hash: str
    weather_hash: str
    diagnostics: dict
    versions: dict

    def to_dict(self):
        return asdict(self)


class _BalancedLoss:
    def __init__(self, frame):
        self.size = len(frame)
        if set(frame.BBCH) != set(STAGES):
            raise ValueError("Joint calibration requires observations for each of the four stages somewhere")
        self.parts = []
        for stage in STAGES:
            indices = np.flatnonzero(frame.BBCH.to_numpy() == stage)
            stage_sites = frame.iloc[indices].site
            counts = stage_sites.map(stage_sites.value_counts()).to_numpy(dtype=float)
            weights = 1. / (counts * stage_sites.nunique())
            self.parts.append((indices, weights))

    def __call__(self, errors):
        errors = np.asarray(errors, dtype=float)
        if errors.shape != (self.size,):
            raise ValueError("An error or non-attainment is required for every observation")
        errors = np.where(np.isfinite(errors), errors, UNATTAINED_PENALTY_DAYS)
        return float(np.mean([np.sqrt(np.sum(errors[idx] ** 2 * weights)) for idx, weights in self.parts]))


def balanced_loss(observation_keys: pd.DataFrame, errors: np.ndarray) -> float:
    """Mean stage RMSE, with equal site weights and explicit missing-event penalty."""
    return _BalancedLoss(observation_keys)(errors)


class _Objective:
    def __init__(self, name, frame, prepared, bounds, fixed):
        self.name, self.prepared, self.names = name, prepared, tuple(bounds)
        self.fixed = fixed
        self.loss = _BalancedLoss(frame)
        lookup = {(item.site, item.season): i for i, item in enumerate(prepared)}
        self.season_indices = np.array([lookup[(site, year)] for site, year in
                                       frame[["site", "season"]].itertuples(index=False, name=None)])
        self.stage_indices = frame.BBCH.map({stage: i for i, stage in enumerate(STAGES)}).to_numpy()
        self.observed_dates = frame.Date.to_numpy(dtype="datetime64[D]")

    def decode(self, vector):
        return {**self.fixed, **{key: (int(round(value)) if key == "start_doy" else float(value))
                                for key, value in zip(self.names, vector)}}

    def errors(self, parameters):
        predicted = np.array([simulate_season(self.name, parameters, item)[0]
                              for item in self.prepared], dtype="datetime64[D]")
        selected = predicted[self.season_indices, self.stage_indices]
        errors = (selected - self.observed_dates).astype("timedelta64[D]").astype(float)
        errors[np.isnat(selected)] = np.nan
        return errors

    def __call__(self, vector):
        parameters = self.decode(vector)
        try:
            validate_parameters(self.name, parameters)
        except ValueError:
            return np.inf
        return self.loss(self.errors(parameters))


def _cardinal_constraints(name, objective, bounds, fixed):
    spec = get_model(name)
    triples = []
    if spec.chilling != "none":
        triples.append(("chilling_minimum", "chilling_optimum", "chilling_maximum"))
    if spec.forcing == "beta":
        triples.extend(("forcing_minimum", f"forcing_optimum_{stage}", "forcing_maximum") for stage in STAGES)
    if not triples:
        return ()
    ranges = {**{key: (value, value) for key, value in fixed.items()}, **bounds}
    for minimum, optimum, maximum in triples:
        low = max(ranges[optimum][0], ranges[minimum][0] + .1)
        high = min(ranges[optimum][1], ranges[maximum][1] - .1)
        if low > high + 1e-12:
            raise ValueError("Search bounds admit no ordered cardinal temperatures with 0.1 degree gaps")

    def gaps(vector):
        p = objective.decode(vector)
        return np.array([gap for lower, middle, upper in triples
                         for gap in (p[middle] - p[lower], p[upper] - p[middle])])
    return (NonlinearConstraint(gaps, .1 - 1e-12, np.inf),)


def _weather_hash(prepared):
    digest = hashlib.sha256()
    for item in sorted(prepared, key=lambda x: (x.site, x.season)):
        digest.update(f"{item.site}\0{item.season}\0".encode())
        digest.update(item.dates.astype("datetime64[D]").astype("<i8").tobytes())
        digest.update(item.temperature.astype("<f8").tobytes())
    return digest.hexdigest()


def fit(model_name, calibration_observations, weather, settings: FitSettings | None = None) -> FitResult:
    """Fit all stages jointly; never selects a split, reads test observations or fits ML."""
    spec = get_model(model_name)
    settings = settings or FitSettings()
    settings.validate()
    frame = observations(calibration_observations)
    _BalancedLoss(frame)  # Reject an unidentified stage before preparing or optimizing.
    fixed = ({"forcing_minimum": 0., "forcing_maximum": 40.} if spec.forcing == "beta" else {})
    fixed.update(settings.fixed_parameters or {})
    bounds = validate_bounds(model_name, settings.bounds if settings.bounds is not None else
                             default_bounds(model_name, fixed), fixed)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in fixed.values()):
        raise ValueError("Fixed parameters must be finite numbers")
    keys = list(frame[["site", "season"]].drop_duplicates().itertuples(index=False, name=None))
    earliest = math.ceil(bounds["start_doy"][0]) if spec.interaction == "none" else None
    prepared = prepare_weather(weather, keys, settings.temperature_column, earliest)
    objective = _Objective(model_name, frame, prepared, bounds, fixed)
    constraints = _cardinal_constraints(model_name, objective, bounds, fixed)
    restarts, best = [], None
    for seed in settings.seeds:
        result = differential_evolution(objective, list(bounds.values()), seed=seed,
                                        maxiter=settings.maxiter, popsize=settings.popsize, tol=settings.tol,
                                        polish=False, workers=1, constraints=constraints,
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
    return FitResult(model_name, spec.version, parameters, settings.temperature_input,
                     settings.temperature_column, float(best.fun), bool(best.success), bounds, asdict(settings),
                     calibration_hash, _weather_hash(prepared),
                     {"objective": "mean_stage_site_balanced_rmse", "unattained_penalty_days": UNATTAINED_PENALTY_DAYS,
                      "n_observations": len(frame), "n_sites": int(frame.site.nunique()), "n_seasons": len(keys),
                      "attained_by_stage": attained, "boundary_hits": boundary_hits,
                      "fixed_by_equal_bounds": [key for key, (lo, hi) in bounds.items() if lo == hi], "restarts": restarts},
                     {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                      "scipy": scipy.__version__})
