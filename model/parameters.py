"""Stage-specific parameter schemas, explicit search bounds and validation."""
import math

from .registry import get_model
from .specification import STAGES

CARDINAL_GAP = 0.1


def default_bounds(model_name: str, fixed_parameters=None) -> dict[str, tuple[float, float]]:
    spec = get_model(model_name)
    fixed = fixed_parameters or {}
    if set(fixed) - ({"forcing_minimum", "forcing_maximum"} if spec.forcing == "beta" else set()):
        raise ValueError("Only beta forcing minimum/maximum are fixed parameters")
    bounds = {}
    if spec.interaction == "none":
        bounds["start_doy"] = (-60, 90)
    else:
        bounds.update(chilling_minimum=(-5, 5), chilling_optimum=(0, 10),
                      chilling_maximum=(0, 20), chilling_requirement=(.001, 200))
    if spec.interaction == "parallel":
        bounds["minimum_response"] = (0, 1)
    for stage in STAGES:
        if spec.forcing == "linear":
            bounds[f"forcing_base_{stage}"] = (0, 15)
            bounds[f"forcing_requirement_{stage}"] = (.001, 1000)
        else:
            lo = max(10, fixed.get("forcing_minimum", 0) + CARDINAL_GAP)
            hi = min(39.9, fixed.get("forcing_maximum", 40) - CARDINAL_GAP)
            if not math.isfinite(lo) or not math.isfinite(hi) or lo > hi:
                raise ValueError("Fixed forcing cardinals leave no default optimum range")
            bounds[f"forcing_optimum_{stage}"] = (lo, hi)
            bounds[f"forcing_requirement_{stage}"] = (.001, 200)
    return bounds


def default_parameters(model_name: str) -> dict[str, float]:
    spec = get_model(model_name)
    parameters = {}
    if spec.interaction == "none":
        parameters["start_doy"] = 1
    else:
        parameters.update(chilling_minimum=-5., chilling_optimum=5.,
                          chilling_maximum=15., chilling_requirement=60.)
    if spec.interaction == "parallel":
        parameters["minimum_response"] = .2
    if spec.forcing == "beta":
        parameters.update(forcing_minimum=0., forcing_maximum=40.)
    for stage, beta_sum in zip(STAGES, (30., 60., 60., 40.)):
        if spec.forcing == "linear":
            parameters[f"forcing_base_{stage}"] = 5.
            parameters[f"forcing_requirement_{stage}"] = 300.
        else:
            parameters[f"forcing_optimum_{stage}"] = 25.
            parameters[f"forcing_requirement_{stage}"] = beta_sum
    return parameters


def validate_parameters(model_name: str, parameters: dict) -> None:
    expected = set(default_parameters(model_name))
    if set(parameters) != expected:
        raise ValueError(f"Parameter keys differ: missing={expected - set(parameters)}, "
                         f"extra={set(parameters) - expected}")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in parameters.values()):
        raise ValueError("All parameters must be finite numbers")
    for name, value in parameters.items():
        if "requirement" in name and value <= 0:
            raise ValueError(f"{name} must be positive")
    spec = get_model(model_name)
    if spec.interaction == "none":
        start = parameters["start_doy"]
        if not float(start).is_integer() or not -60 <= start <= 90:
            raise ValueError("start_doy must be an integer from -60 to 90")
    else:
        _validate_cardinal_gaps(*(parameters[f"chilling_{x}"] for x in ("minimum", "optimum", "maximum")))
    if spec.interaction == "parallel" and not 0 <= parameters["minimum_response"] <= 1:
        raise ValueError("minimum_response must be between zero and one")
    if spec.forcing == "beta":
        for stage in STAGES:
            _validate_cardinal_gaps(parameters["forcing_minimum"], parameters[f"forcing_optimum_{stage}"],
                                    parameters["forcing_maximum"])


def _validate_cardinal_gaps(minimum, optimum, maximum):
    if optimum - minimum < CARDINAL_GAP - 1e-12 or maximum - optimum < CARDINAL_GAP - 1e-12:
        raise ValueError("Cardinal temperatures require at least 0.1 degrees separation")


def validate_bounds(model_name: str, bounds: dict, fixed_parameters=None) -> dict:
    expected = default_bounds(model_name, fixed_parameters)
    if set(bounds) != set(expected):
        raise ValueError("Search bounds must specify every fitted parameter exactly once")
    result = {}
    for name, pair in bounds.items():
        if len(pair) != 2:
            raise ValueError(f"Invalid bound for {name}")
        lo, hi = map(float, pair)
        if not math.isfinite(lo) or not math.isfinite(hi) or lo > hi:
            raise ValueError(f"Invalid bound for {name}")
        if "requirement" in name and lo <= 0:
            raise ValueError("Requirement bounds must be positive")
        if name == "minimum_response" and not 0 <= lo <= hi <= 1:
            raise ValueError("minimum_response bounds must lie within [0,1]")
        if name == "start_doy" and (not -60 <= lo <= hi <= 90 or math.ceil(lo) > math.floor(hi)):
            raise ValueError("start_doy bounds require an integer within [-60,90]")
        result[name] = (lo, hi)
    return result
