"""Hand-derived seasonal dates catch accumulation and calendar mistakes."""
import importlib

import numpy as np
import pandas as pd
import pytest

from model.parameters import default_parameters
from model.registry import list_models


def predict(*args, **kwargs):
    try:
        module = importlib.import_module("model.simulation")
    except ModuleNotFoundError:
        pytest.fail("The shared stage-sequence simulator is not implemented")
    return module.predict(*args, **kwargs)


def weather(year=2000, temperature=10., start=None, site="A"):
    dates = pd.date_range(start or f"{year - 1}-09-01", f"{year}-12-31")
    return pd.DataFrame({"site": site, "Date": dates, "tmean_c": temperature})


def parameters(name):
    p = default_parameters(name)
    for stage in ("07", "65", "81", "89"):
        p[f"forcing_requirement_{stage}"] = 10 if "forcing_base_07" in p else 2
        if "forcing_base_07" in p:
            p[f"forcing_base_{stage}"] = 5
        else:
            p[f"forcing_optimum_{stage}"] = 10
    if "chilling_requirement" in p:
        p.update(chilling_minimum=0, chilling_optimum=10, chilling_maximum=20,
                 chilling_requirement=3)
    return p


@pytest.mark.parametrize("name", list_models())
def test_each_model_runs_the_complete_ordered_sequence(name):
    result = predict(name, parameters(name), weather(), [("A", 2000)])
    assert result.BBCH.tolist() == ["07", "65", "81", "89"]
    assert result.status.tolist() == ["attained"] * 4
    assert result.predicted_date.is_monotonic_increasing
    assert result.predicted_date.diff().dropna().dt.days.tolist() == [2, 2, 2]


def test_forcing_only_threshold_crossing_and_no_overshoot_carry():
    p = parameters("FL")
    p["forcing_requirement_07"] = 6  # 5 units/day; first crossing is Jan 2.
    result = predict("FL", p, weather(), [("A", 2000)])
    assert result.predicted_date.dt.strftime("%Y-%m-%d").tolist() == [
        "2000-01-02", "2000-01-04", "2000-01-06", "2000-01-08"]
    assert result.predicted_doy.tolist() == [2, 4, 6, 8]


def test_sequential_forcing_starts_day_after_chilling_completion():
    result = predict("CL-FL-S", parameters("CL-FL-S"), weather(), [("A", 2000)])
    assert result.iloc[0].predicted_date == pd.Timestamp("1999-09-05")
    assert result.iloc[0].outside_target_year
    assert result.iloc[0].predicted_doy == -117  # Signed relative to Jan 1 = 1.


@pytest.mark.parametrize("minimum,expected", [(0, "1999-09-05"), (1, "1999-09-02")])
def test_parallel_competence_uses_chilling_before_current_day(minimum, expected):
    p = parameters("CL-FL-P")
    p["minimum_response"] = minimum
    # Kmin=0 gives forcing 0, 5/3, 10/3, 5, 5: crosses 10 on Sept 4.
    # Floating arithmetic at an exact boundary must not delay the crossing.
    if minimum == 0:
        expected = "1999-09-04"
    result = predict("CL-FL-P", p, weather(), [("A", 2000)])
    assert result.iloc[0].predicted_date == pd.Timestamp(expected)


def test_parallel_can_burst_without_full_chilling_but_sequential_cannot():
    w = weather(temperature=30)
    p = parameters("CL-FL-P")
    p["minimum_response"] = 1
    parallel = predict("CL-FL-P", p, w, [("A", 2000)])
    sequential_p = parameters("CL-FL-S")
    sequential = predict("CL-FL-S", sequential_p, w, [("A", 2000)])
    assert parallel.iloc[0].predicted_date == pd.Timestamp("1999-09-01")
    assert not parallel.iloc[0].chilling_attained
    assert sequential.status.tolist() == ["unmet_chilling"] + ["previous_stage_unattained"] * 3


def test_unmet_forcing_propagates_without_fabricating_dates():
    p = parameters("FL")
    p["forcing_requirement_65"] = 100000
    result = predict("FL", p, weather(), [("A", 2000)])
    assert result.status.tolist() == ["attained", "unmet_forcing", "previous_stage_unattained", "previous_stage_unattained"]
    assert result.predicted_date.iloc[1:].isna().all()
    assert result.predicted_doy.iloc[1:].isna().all()


def test_arbitrarily_small_positive_requirement_still_needs_positive_forcing():
    p = parameters("FL")
    for stage in ("07", "65", "81", "89"):
        p[f"forcing_requirement_{stage}"] = 1e-13
    result = predict("FL", p, weather(temperature=0.), [("A", 2000)])
    assert result.predicted_date.isna().all()


def test_leap_day_and_signed_prior_year_start():
    p = parameters("FL")
    p.update(start_doy=59, forcing_requirement_07=10)
    assert predict("FL", p, weather(), [("A", 2000)]).iloc[0].predicted_date == pd.Timestamp("2000-02-29")
    p["start_doy"] = -1  # Dec 30, not Dec 31.
    row = predict("FL", p, weather(), [("A", 2000)]).iloc[0]
    assert row.predicted_date == pd.Timestamp("1999-12-31")
    assert row.predicted_doy == 0


def test_temperature_label_has_no_numerical_effect_and_selected_column_is_used():
    w = weather()
    w["corrected"] = w.tmean_c + 5
    raw = predict("FL", parameters("FL"), w, [("A", 2000)], temperature_input="RAW")
    dem = predict("FL", parameters("FL"), w, [("A", 2000)], temperature_input="DEM")
    pd.testing.assert_series_equal(raw.predicted_date, dem.predicted_date)
    changed = predict("FL", parameters("FL"), w, [("A", 2000)],
                      temperature_column="corrected", temperature_input="DEM")
    assert changed.iloc[0].predicted_date == pd.Timestamp("2000-01-01")


@pytest.mark.parametrize("defect", ["duplicate", "gap", "nan", "infinite", "late_start", "early_end", "missing_site"])
def test_bad_weather_is_rejected_not_imputed(defect):
    w = weather()
    if defect == "duplicate":
        w = pd.concat([w, w.iloc[:1]])
    elif defect == "gap":
        w = w.drop(w.index[140])
    elif defect in {"nan", "infinite"}:
        w.loc[140, "tmean_c"] = np.nan if defect == "nan" else np.inf
    elif defect == "late_start":
        w = w.iloc[1:]
    elif defect == "early_end":
        w = w.iloc[:-1]
    else:
        w["site"] = "B"
    with pytest.raises(ValueError):
        predict("CL-FL-S", parameters("CL-FL-S"), w, [("A", 2000)])


def test_forcing_only_does_not_require_irrelevant_previous_september_weather():
    result = predict("FL", parameters("FL"), weather(start="2000-01-01"), [("A", 2000)])
    assert result.iloc[0].predicted_date == pd.Timestamp("2000-01-02")


def test_multiple_sites_and_years_and_no_input_mutation():
    w = pd.concat([weather(), weather(year=2001, site="B", temperature=15)], ignore_index=True)
    before = w.copy(deep=True)
    result = predict("FL", parameters("FL"), w, [("B", 2001), ("A", 2000)])
    assert len(result) == 8
    assert result[result.site.eq("B")].predicted_doy.tolist() == [1, 2, 3, 4]
    pd.testing.assert_frame_equal(w, before)
