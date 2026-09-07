"""Process-based grapevine phenology; no fitting or I/O at import time."""
from .registry import get_model, list_models

__all__ = ["get_model", "list_models", "predict", "fit", "FitSettings", "FitResult"]


def __getattr__(name):
    # Keep discovery usable without importing the numerical stack.
    if name == "predict":
        from .simulation import predict
        return predict
    if name in {"fit", "FitSettings", "FitResult"}:
        from . import calibration
        return getattr(calibration, name)
    raise AttributeError(name)
