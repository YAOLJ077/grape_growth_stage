"""Versioned JSON fits and explicit CSV inputs; existing outputs are never overwritten."""
import json
import math
from pathlib import Path
import re

import pandas as pd

from .calibration import FitResult, FitSettings
from .parameters import validate_bounds, validate_parameters
from .registry import get_model


def _reject_constant(value):
    raise ValueError(f"Nonfinite JSON constant is not allowed: {value}")


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream, parse_constant=_reject_constant)


def read_csv(path):
    # Preserve source-qualified/zero-padded IDs, BBCH07 and empty cultivar labels.
    return pd.read_csv(path, dtype={"site": str, "BBCH": str}, keep_default_na=False)


def write_csv(frame, path):
    path = Path(path)
    contents = frame.to_csv(index=False, date_format="%Y-%m-%d")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(contents)


def _validate_fit(result):
    spec = get_model(result.model_name)
    if result.definition_version != spec.version:
        raise ValueError("Saved model definition version does not match this implementation")
    validate_parameters(result.model_name, result.parameters)
    if result.temperature_input not in {"RAW", "DEM"} or not isinstance(result.temperature_column, str) or not result.temperature_column:
        raise ValueError("Saved temperature metadata is invalid")
    if not isinstance(result.objective_value, (int, float)) or not math.isfinite(result.objective_value) or result.objective_value < 0:
        raise ValueError("Saved objective must be finite and nonnegative")
    if not isinstance(result.optimizer_converged, bool):
        raise ValueError("Saved convergence status must be boolean")
    if not all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)
               for v in (result.calibration_hash, result.weather_hash)):
        raise ValueError("Saved input hashes must be SHA-256 digests")
    fixed = {key: result.parameters[key] for key in ("forcing_minimum", "forcing_maximum") if key in result.parameters}
    bounds = validate_bounds(result.model_name, result.bounds, fixed)
    if any(result.parameters[key] < lo - 1e-10 or result.parameters[key] > hi + 1e-10 for key, (lo, hi) in bounds.items()):
        raise ValueError("Saved fitted parameter is outside its recorded search bounds")


def save_fit(result: FitResult, path) -> None:
    _validate_fit(result)
    contents = json.dumps({"schema_version": 1, **result.to_dict()}, indent=2, allow_nan=False) + "\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(contents)


def load_fit(path) -> FitResult:
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.pop("schema_version", None) != 1:
        raise ValueError("Unsupported saved-fit schema")
    try:
        payload["bounds"] = {key: tuple(value) for key, value in payload["bounds"].items()}
        result = FitResult(**payload)
        _validate_fit(result)
    except (TypeError, KeyError, AttributeError) as exc:
        raise ValueError("Invalid saved-fit structure") from exc
    return result


def load_settings(path=None) -> FitSettings:
    payload = read_json(path) if path else {}
    if not isinstance(payload, dict):
        raise ValueError("Settings must be a JSON object")
    if "seeds" in payload:
        payload["seeds"] = tuple(payload["seeds"])
    try:
        result = FitSettings(**payload)
        result.validate()
    except TypeError as exc:
        raise ValueError("Unknown or invalid fitting setting") from exc
    return result
