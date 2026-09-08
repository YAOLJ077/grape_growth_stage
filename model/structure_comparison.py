"""Literature-fixed responses for threshold-only structural comparisons.

Explicit opt-in preserves historical fits and the general-purpose API defaults.
Scientific provenance and transfer limitations: fig/model_functions/README.md.
"""
from .calibration import FitSettings
from .parameters import default_bounds
from .registry import get_model
from .specification import STAGES

PROFILE = "literature_fixed_responses_v1"
FORCING_BASE = 0.0  # Parker et al. (2011), GFV; four-stage use is an adaptation.
FORCING_CARDINALS = (0.0, 25.4, 35.0)  # Fila (2014), Fbeta5*, Table 8 and §3.2.
CHILLING_CARDINALS = (-1.7, 1.7, 13.2)  # Fila (2014), CF10*, Table 7.


def fixed_parameters(model_name):
    """Same component parameters across stages/sites/models; no thresholds."""
    spec = get_model(model_name)
    result = {}
    if spec.interaction == "none":
        result["start_doy"] = 1  # Common calendar convention, not GFV's fitted DOY 60.
    else:
        result.update(zip(("chilling_minimum", "chilling_optimum", "chilling_maximum"),
                          CHILLING_CARDINALS))
    if spec.interaction == "parallel":
        result["minimum_response"] = 0.2  # Fixed project choice, NOT literature-derived.
    if spec.forcing == "beta":
        result.update(forcing_minimum=FORCING_CARDINALS[0], forcing_maximum=FORCING_CARDINALS[2])
    for stage in STAGES:
        if spec.forcing == "linear":
            result[f"forcing_base_{stage}"] = FORCING_BASE
        else:
            result[f"forcing_optimum_{stage}"] = FORCING_CARDINALS[1]
    return result


def threshold_only_settings(model_name, **optimizer_settings):
    """Only four forcing requirements and, if present, one chilling requirement vary.

Linear sums have a wider upper bound than the historical pilot because its
fitted bases have been replaced by 0 C. This is a search allowance, not a
physiological claim. Test outcomes must not determine bounds or fixed values.
"""
    if {"bounds", "fixed_parameters"} & optimizer_settings.keys():
        raise ValueError("The fixed-response profile owns bounds and fixed parameters")
    fixed = fixed_parameters(model_name)
    beta_limits = {k: v for k, v in fixed.items() if k in {"forcing_minimum", "forcing_maximum"}}
    bounds = default_bounds(model_name, beta_limits)
    for key, value in fixed.items():
        if key in bounds:
            bounds[key] = (value, value)
    if get_model(model_name).forcing == "linear":
        for stage in STAGES:
            bounds[f"forcing_requirement_{stage}"] = (0.001, 3000.0)
    return FitSettings(bounds=bounds, fixed_parameters=beta_limits, **optimizer_settings)
