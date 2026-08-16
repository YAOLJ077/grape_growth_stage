#!/usr/bin/env python
"""Build simplified observation and site-year-stage phenology tables for modeling."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


CORE_PHASES = {"budburst", "flowering", "veraison", "maturity_or_harvest"}
OUTPUT_OBSERVATION_COLUMNS = [
    "record_id",
    "country",
    "source",
    "site_id",
    "site_name",
    "lat",
    "lon",
    "alt_m",
    "year",
    "date",
    "doy",
    "bbch",
    "bbch_major",
    "phenophase",
    "phenophase_order",
    "bbch_confidence",
    "n_years_site_bbch",
    "n_observations_site_bbch",
    "model_tier",
]
OUTPUT_EVENT_COLUMNS = [
    "record_id",
    "country",
    "source",
    "site_id",
    "site_name",
    "lat",
    "lon",
    "alt_m",
    "year",
    "event_date",
    "event_doy",
    "bbch",
    "bbch_major",
    "phenophase",
    "phenophase_order",
    "bbch_confidence",
    "aggregation_method",
    "n_obs",
    "doy_min",
    "doy_median",
    "doy_max",
    "doy_range",
    "date_min",
    "date_max",
    "n_years_site_bbch",
    "n_observations_site_bbch",
    "model_tier",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/phenology/derived/base_table/six_country_base_table_1951.csv"),
        help="Observation-level six-country base table.",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("data/phenology/processed"))
    parser.add_argument("--start-year", type=int, default=1951)
    return parser.parse_args()


def read_base_table(path: Path, start_year: int) -> pd.DataFrame:
    columns = [
        "source_system",
        "country_name",
        "site_id",
        "site_name",
        "latitude",
        "longitude",
        "altitude",
        "date",
        "year",
        "doy",
        "bbch_standard",
        "bbch_major",
        "phenophase_standard",
        "phenophase_order",
        "bbch_mapping_confidence",
        "n_years_site_bbch",
        "n_observations_site_bbch",
    ]
    df = pd.read_csv(path, usecols=columns, low_memory=False)
    for column in ["year", "doy", "latitude", "longitude", "altitude", "phenophase_order"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df[
        df["year"].ge(start_year)
        & df["site_id"].notna()
        & df["date"].notna()
        & df["doy"].between(1, 366)
        & df["latitude"].notna()
        & df["longitude"].notna()
        & df["bbch_standard"].notna()
    ].copy()
    df["bbch_standard"] = df["bbch_standard"].map(normalize_bbch)
    df = df[df["bbch_standard"].ne("")]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()].copy()
    return df


def normalize_bbch(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    try:
        number = int(float(text))
    except ValueError:
        return text
    return f"{number:02d}" if 0 <= number <= 99 else ""


def model_tier(row: pd.Series) -> str:
    if row["phenophase_standard"] not in CORE_PHASES:
        return "extended"
    if row["bbch_mapping_confidence"] == "high" and row["n_years_site_bbch"] >= 10:
        return "core"
    if row["bbch_mapping_confidence"] in {"high", "medium"} and row["n_years_site_bbch"] >= 5:
        return "extended"
    return "sensitivity"


def aggregation_method(bbch: str) -> str:
    number = int(bbch)
    if number <= 19 or 50 <= number <= 61 or number == 81:
        return "min"
    return "median"


def build_observation_table(df: pd.DataFrame) -> pd.DataFrame:
    obs = pd.DataFrame(
        {
            "country": df["country_name"],
            "source": df["source_system"],
            "site_id": df["site_id"],
            "site_name": df["site_name"],
            "lat": df["latitude"],
            "lon": df["longitude"],
            "alt_m": df["altitude"],
            "year": df["year"].astype("Int64"),
            "date": df["date"].dt.strftime("%Y-%m-%d"),
            "doy": df["doy"].astype(float),
            "bbch": df["bbch_standard"],
            "bbch_major": df["bbch_major"].astype(str).str.replace(".0", "", regex=False),
            "phenophase": df["phenophase_standard"],
            "phenophase_order": df["phenophase_order"].astype("Int64"),
            "bbch_confidence": df["bbch_mapping_confidence"],
            "n_years_site_bbch": df["n_years_site_bbch"].astype("Int64"),
            "n_observations_site_bbch": df["n_observations_site_bbch"].astype("Int64"),
        }
    )
    obs["model_tier"] = obs.apply(
        lambda row: model_tier(
            pd.Series(
                {
                    "phenophase_standard": row["phenophase"],
                    "bbch_mapping_confidence": row["bbch_confidence"],
                    "n_years_site_bbch": row["n_years_site_bbch"],
                }
            )
        ),
        axis=1,
    )
    obs["record_id"] = (
        obs["country"].astype(str)
        + "|"
        + obs["source"].astype(str)
        + "|"
        + obs["site_id"].astype(str)
        + "|"
        + obs["year"].astype(str)
        + "|"
        + obs["bbch"].astype(str)
        + "|"
        + obs["doy"].round(3).astype(str)
    )
    return obs[OUTPUT_OBSERVATION_COLUMNS]


def representative_date(group: pd.DataFrame, event_doy: float, method: str) -> str:
    if method == "min":
        row = group.sort_values(["doy", "date"]).iloc[0]
        return row["date"].strftime("%Y-%m-%d")
    idx = (group["doy"] - event_doy).abs().sort_values().index[0]
    return group.loc[idx, "date"].strftime("%Y-%m-%d")


def build_event_table(obs: pd.DataFrame) -> pd.DataFrame:
    group_cols = ["country", "source", "site_id", "year", "bbch"]
    work = obs.copy()
    work["date_dt"] = pd.to_datetime(work["date"], errors="coerce")
    work["tier_rank"] = work["model_tier"].map({"core": 0, "extended": 1, "sensitivity": 2}).fillna(2)
    work["aggregation_method"] = work["bbch"].map(aggregation_method)

    event = (
        work.groupby(group_cols, dropna=False, sort=False)
        .agg(
            site_name=("site_name", first_non_null),
            lat=("lat", "median"),
            lon=("lon", "median"),
            alt_m=("alt_m", "median"),
            bbch_major=("bbch_major", first_non_null),
            phenophase=("phenophase", first_non_null),
            phenophase_order=("phenophase_order", first_non_null),
            bbch_confidence=("bbch_confidence", confidence_label),
            aggregation_method=("aggregation_method", first_non_null),
            n_obs=("doy", "size"),
            doy_min=("doy", "min"),
            doy_median=("doy", "median"),
            doy_max=("doy", "max"),
            date_min=("date_dt", "min"),
            date_max=("date_dt", "max"),
            n_years_site_bbch=("n_years_site_bbch", "max"),
            n_observations_site_bbch=("n_observations_site_bbch", "max"),
            tier_rank=("tier_rank", "min"),
        )
        .reset_index()
    )
    event["event_doy"] = np.where(
        event["aggregation_method"].eq("min"),
        event["doy_min"],
        event["doy_median"],
    )
    event["event_date"] = event.apply(
        lambda row: date_from_year_doy(int(row["year"]), float(row["event_doy"])),
        axis=1,
    )
    event["date_min"] = event["date_min"].dt.strftime("%Y-%m-%d")
    event["date_max"] = event["date_max"].dt.strftime("%Y-%m-%d")
    event["doy_range"] = event["doy_max"] - event["doy_min"]
    event["model_tier"] = event["tier_rank"].map({0: "core", 1: "extended", 2: "sensitivity"})
    event["record_id"] = (
        event["country"].astype(str)
        + "|"
        + event["source"].astype(str)
        + "|"
        + event["site_id"].astype(str)
        + "|"
        + event["year"].astype(str)
        + "|"
        + event["bbch"].astype(str)
    )
    event = event.drop(columns=["tier_rank"])
    event = event.sort_values(["country", "site_id", "bbch", "year"])
    return event[OUTPUT_EVENT_COLUMNS]


def first_non_null(series: pd.Series) -> object:
    values = series.dropna()
    if values.empty:
        return ""
    return values.iloc[0]


def confidence_label(series: pd.Series) -> str:
    values = series.dropna().unique().tolist()
    if not values:
        return ""
    return values[0] if len(values) == 1 else "mixed"


def date_from_year_doy(year: int, doy: float) -> str:
    doy_int = int(round(doy))
    doy_int = max(1, min(366, doy_int))
    date = pd.Timestamp(year=year, month=1, day=1) + pd.Timedelta(days=doy_int - 1)
    return date.strftime("%Y-%m-%d")


def write_readme(out_dir: Path, start_year: int) -> None:
    text = f"""# Model-ready phenology tables

Generated by `src/base_table/build_model_ready_tables.py`.

Inputs:

- `data/phenology/derived/base_table/six_country_base_table_1951.csv`

Outputs:

- `phenology_observations_{start_year}.csv`: simplified observation-level table.
- `phenology_site_year_stage_{start_year}.csv`: one row per site-year-standard-BBCH event.

Aggregation rules for the site-year-stage table:

- Start-like phases use the first observed date (`min` DOY): BBCH 00-19, 50-61, and 81.
- State/proportion/end phases use median DOY: BBCH 62-99 except 81.
- Diagnostic fields are retained: `n_obs`, `doy_min`, `doy_median`, `doy_max`, `doy_range`, `date_min`, `date_max`.

No weather or DEM variables are included in these tables.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    base = read_base_table(args.input, args.start_year)
    observations = build_observation_table(base)
    events = build_event_table(observations)
    obs_path = args.out_dir / f"phenology_observations_{args.start_year}.csv"
    event_path = args.out_dir / f"phenology_site_year_stage_{args.start_year}.csv"
    observations.to_csv(obs_path, index=False)
    events.to_csv(event_path, index=False)
    write_readme(args.out_dir, args.start_year)
    print(f"Observation rows written: {len(observations):,}")
    print(f"Event rows written: {len(events):,}")
    print(f"Observation table: {obs_path}")
    print(f"Event table: {event_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
