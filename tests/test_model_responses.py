"""Independent response checks: wrong boundaries/shape/registry must fail."""
import importlib
from pathlib import Path

import numpy as np
import pytest


def api(module):
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError:
        pytest.fail(f"Required model module is not implemented: {module}")


def test_linear_is_zero_below_base_and_not_capped():
    np.testing.assert_allclose(api("model.responses").linear([-3, 5, 8, 45], 5), [0, 0, 3, 40])


def test_beta_matches_hand_calculated_symmetric_curve():
    # Tmin=0, Topt=10, Tmax=20 gives T*(20-T)/100 within the bounds.
    np.testing.assert_allclose(api("model.responses").beta([-1, 0, 5, 10, 15, 20, 21], 0, 10, 20),
                               [0, 0, .75, 1, .75, 0, 0])


def test_asymmetric_beta_uses_fila_exponent():
    # At T=5 with cardinal temperatures 0, 10, 30: 25/20 * sqrt(5/10).
    assert api("model.responses").beta(5, 0, 10, 30) == pytest.approx(.8838834764831844)


def test_triangular_chilling_has_two_linear_limbs():
    np.testing.assert_allclose(api("model.responses").triangular([-6, -5, 0, 5, 10, 15, 16], -5, 5, 15),
                               [0, 0, .5, 1, .5, 0, 0])


@pytest.mark.parametrize("function", ["beta", "triangular"])
@pytest.mark.parametrize("cardinals", [(0, 0, 20), (0, 21, 20), (0, np.nan, 20)])
def test_invalid_cardinals_fail(function, cardinals):
    with pytest.raises(ValueError):
        getattr(api("model.responses"), function)(10, *cardinals)


@pytest.mark.parametrize("function,args", [("linear", (5,)), ("beta", (0, 10, 20)),
                                           ("triangular", (-5, 5, 15))])
def test_missing_temperatures_are_not_zero_response(function, args):
    with pytest.raises(ValueError):
        getattr(api("model.responses"), function)([1, np.nan], *args)


def test_registry_loads_every_named_folder_and_excludes_ml_temperature_variants():
    registry = api("model.registry")
    names = {"FL", "FB", "CL-FL-S", "CL-FL-P", "CB-FL-S", "CB-FL-P",
             "CL-FB-S", "CL-FB-P", "CB-FB-S", "CB-FB-P"}
    assert set(registry.list_models()) == names
    for name in names:
        spec = registry.get_model(name)
        assert spec.name == name
        assert spec.forcing == ("linear" if name == "FL" or "-FL-" in name else "beta")
        assert (Path(__file__).parents[1] / "model" / name / "model.py").is_file()
        assert spec.interaction == ("none" if name in {"FL", "FB"} else
                                    "sequential" if name.endswith("-S") else "parallel")
    for invalid in ["FL-RAW", "FL-ML", "CB-FB-P-DEM", "../FL", "unknown"]:
        with pytest.raises(ValueError):
            registry.get_model(invalid)


def test_parameters_enforce_stage_thresholds_and_cardinal_separation():
    mod = api("model.parameters")
    params = mod.default_parameters("CL-FB-P")
    mod.validate_parameters("CL-FB-P", params)
    params["forcing_requirement_65"] = 0
    with pytest.raises(ValueError):
        mod.validate_parameters("CL-FB-P", params)
    params = mod.default_parameters("CL-FB-P")
    params["chilling_optimum"] = params["chilling_minimum"] + .05
    with pytest.raises(ValueError):
        mod.validate_parameters("CL-FB-P", params)


def test_parameters_have_four_independent_stage_responses_and_explicit_fixed_values():
    mod = api("model.parameters")
    for name, expected in [("FL", 9), ("FB", 9), ("CL-FB-S", 12), ("CB-FL-P", 13)]:
        bounds = mod.default_bounds(name)
        assert len(bounds) == expected
        assert all(f"forcing_requirement_{stage}" in bounds for stage in ["07", "65", "81", "89"])
    params = mod.default_parameters("FB")
    assert params["forcing_minimum"] == 0
    assert params["forcing_maximum"] == 40

