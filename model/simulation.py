"""Daily process simulation with strictly ordered predicted developmental stages."""
import numpy as np
import pandas as pd

from . import responses
from .data import SeasonWeather, prepare_weather
from .parameters import validate_parameters
from .registry import get_model
from .specification import STAGES


def _crossing(cumulative, requirement):
    # Protect exact daily boundaries from summation round-off, not biological rounding.
    return int(np.searchsorted(cumulative, requirement * (1 - 1e-12), side="left"))


def simulate_season(model_name, parameters, weather: SeasonWeather):
    """Internal array kernel; inputs and parameters validated once by its caller."""
    spec = get_model(model_name)
    t = weather.temperature
    dates = weather.dates
    chilling = None
    competence = None
    if spec.chilling != "none":
        fn = responses.triangular if spec.chilling == "triangular" else responses.beta
        rate = fn(t, parameters["chilling_minimum"], parameters["chilling_optimum"],
                  parameters["chilling_maximum"])
        chilling = np.cumsum(rate)
        if spec.interaction == "sequential":
            start = _crossing(chilling, parameters["chilling_requirement"]) + 1
        else:
            before = np.concatenate(([0.], chilling[:-1]))
            minimum = parameters["minimum_response"]
            competence = minimum + (1 - minimum) * np.minimum(before / parameters["chilling_requirement"], 1)
            start = 0
    else:
        first = np.datetime64(pd.Timestamp(weather.season, 1, 1)
                              + pd.Timedelta(days=int(parameters["start_doy"]) - 1))
        start = int(np.searchsorted(dates, first))
    predicted = []
    statuses = []
    chill_reached = None
    previous_failed = False
    for stage in STAGES:
        if previous_failed:
            predicted.append(np.datetime64("NaT"))
            statuses.append("previous_stage_unattained")
            continue
        if spec.forcing == "linear":
            rate = responses.linear(t, parameters[f"forcing_base_{stage}"])
        else:
            rate = responses.beta(t, parameters["forcing_minimum"],
                                  parameters[f"forcing_optimum_{stage}"], parameters["forcing_maximum"])
        if stage == "07" and competence is not None:
            rate = rate * competence
        cumulative = np.cumsum(rate[start:])
        crossing = _crossing(cumulative, parameters[f"forcing_requirement_{stage}"])
        position = start + crossing
        if position < len(dates):
            predicted.append(dates[position])
            statuses.append("attained")
            if stage == "07" and chilling is not None:
                chill_reached = bool(chilling[position] >= parameters["chilling_requirement"] - 1e-12)
            start = position + 1
        else:
            predicted.append(np.datetime64("NaT"))
            # Completing chilling on the last day is unmet forcing, not unmet chilling.
            unmet_chill = (stage == "07" and spec.interaction == "sequential"
                           and _crossing(chilling, parameters["chilling_requirement"]) >= len(dates))
            statuses.append("unmet_chilling" if unmet_chill else "unmet_forcing")
            previous_failed = True
            if stage == "07" and chilling is not None:
                chill_reached = bool(chilling[-1] >= parameters["chilling_requirement"] - 1e-12)
    return np.asarray(predicted, dtype="datetime64[ns]"), statuses, chill_reached


def predict_prepared(model_name, parameters, prepared, temperature_input="RAW"):
    records = []
    for season_weather in prepared:
        predicted, statuses, chilling = simulate_season(model_name, parameters, season_weather)
        january = pd.Timestamp(season_weather.season, 1, 1)
        for stage, date, status in zip(STAGES, predicted, statuses):
            date = pd.Timestamp(date)
            attained = not pd.isna(date)
            records.append({"site": season_weather.site, "season": season_weather.season,
                            "BBCH": stage, "model_name": model_name, "temperature_input": temperature_input,
                            "predicted_date": date, "predicted_doy": (date - january).days + 1 if attained else np.nan,
                            "status": status, "chilling_attained": chilling,
                            "outside_target_year": bool(attained and date.year != season_weather.season)})
    return pd.DataFrame.from_records(records)


def predict(model_name, parameters, weather, seasons, *, temperature_column="tmean_c", temperature_input="RAW"):
    """Predict all four stages; no observations, calibration or implicit DEM correction."""
    validate_parameters(model_name, parameters)
    if temperature_input not in {"RAW", "DEM"}:
        raise ValueError("temperature_input must be RAW or DEM")
    prepared = prepare_weather(weather, seasons, temperature_column,
                               parameters.get("start_doy"))
    return predict_prepared(model_name, parameters, prepared, temperature_input)
