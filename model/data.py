"""Validated in-memory inputs; no weather interpolation or observation aggregation."""
from dataclasses import dataclass
from numbers import Number

import numpy as np
import pandas as pd

from .specification import STAGES


def dates(values: pd.Series, label="Date") -> pd.Series:
    if pd.api.types.is_numeric_dtype(values.dtype) or values.map(lambda value: isinstance(value, Number)).any():
        raise ValueError(f"{label} requires calendar dates, not numeric timestamps")
    try:
        parsed = pd.to_datetime(values, errors="raise", format="mixed")
        if parsed.dt.tz is not None or parsed.isna().any() or not parsed.eq(parsed.dt.normalize()).all():
            raise ValueError("Dates must be nonmissing, timezone-free calendar dates")
    except (TypeError, AttributeError, OverflowError) as exc:
        raise ValueError(f"Invalid {label}") from exc
    return parsed


def sites(values: pd.Series) -> pd.Series:
    if values.isna().any():
        raise ValueError("Missing site identifier")
    if not values.map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise ValueError("Site identifiers must be nonempty strings; preserve leading zeros")
    return values.astype(str)


def observations(frame: pd.DataFrame) -> pd.DataFrame:
    if not {"site", "Date", "BBCH"}.issubset(frame.columns) or frame.empty:
        raise ValueError("Observations require site, Date and BBCH and cannot be empty")
    result = frame.copy(deep=True).reset_index(drop=True)
    result["site"] = sites(result.site)
    result["Date"] = dates(result.Date)
    # Accept integer BBCH codes without accepting fractional or missing codes.
    codes = result.BBCH.astype(str).str.fullmatch(r"0?7|65|81|89")
    if not codes.all():
        raise ValueError("Only BBCH07, 65, 81 and 89 are model targets")
    result["BBCH"] = result.BBCH.astype(str).str.zfill(2)
    result["season"] = result.Date.dt.year
    return result


def season_keys(seasons) -> tuple[tuple[str, int], ...]:
    if isinstance(seasons, pd.DataFrame):
        if not {"site", "season"}.issubset(seasons):
            raise ValueError("Seasons require site and season columns")
        pairs = list(seasons[["site", "season"]].itertuples(index=False, name=None))
    else:
        pairs = list(seasons)
    result = []
    for site, year in pairs:
        if not isinstance(site, str) or not site.strip():
            raise ValueError("Season site must be a nonempty string")
        if isinstance(year, (bool, str)) or not np.isfinite(year) or int(year) != year or not 1679 <= year <= 2261:
            raise ValueError("Season must be an integer calendar year in [1679,2261]")
        result.append((site, int(year)))
    if not result or len(result) != len(set(result)):
        raise ValueError("Requested site-season pairs must be nonempty and unique")
    return tuple(result)


@dataclass(frozen=True)
class SeasonWeather:
    site: str
    season: int
    dates: np.ndarray
    temperature: np.ndarray


def prepare_weather(weather: pd.DataFrame, seasons, temperature_column: str,
                    start_doy: int | None = None) -> tuple[SeasonWeather, ...]:
    """None means prior September 1; an integer means signed forcing start DOY."""
    keys = season_keys(seasons)
    required = {"site", "Date", temperature_column}
    if not required.issubset(weather.columns) or temperature_column in {"site", "Date"}:
        raise ValueError(f"Weather requires site, Date and temperature column {temperature_column!r}")
    frame = weather.loc[:, ["site", "Date", temperature_column]].copy()
    frame["site"] = sites(frame.site)
    frame["Date"] = dates(frame.Date)
    try:
        frame[temperature_column] = pd.to_numeric(frame[temperature_column], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("Weather temperatures must be numeric Celsius values") from exc
    series = {site: group for site, group in frame.groupby("site", sort=False)}
    result = []
    for site, year in keys:
        start = (pd.Timestamp(year - 1, 9, 1) if start_doy is None else
                 pd.Timestamp(year, 1, 1) + pd.Timedelta(days=int(start_doy) - 1))
        expected = pd.date_range(start, pd.Timestamp(year, 12, 31))
        if site not in series:
            raise ValueError(f"Missing weather for site {site}")
        subset = series[site].loc[lambda f: f.Date.between(start, expected[-1])].sort_values("Date")
        if subset.Date.duplicated().any():
            raise ValueError(f"Duplicate daily weather for {site}, season {year}")
        if not pd.DatetimeIndex(subset.Date).equals(expected):
            raise ValueError(f"Incomplete daily weather for {site}, season {year}: require {start.date()} through {year}-12-31")
        values = subset[temperature_column].to_numpy(dtype=float, copy=True)
        if not np.isfinite(values).all():
            raise ValueError(f"Nonfinite temperature for {site}, season {year}")
        values.flags.writeable = False
        result.append(SeasonWeather(site, year, expected.to_numpy(), values))
    return tuple(result)
