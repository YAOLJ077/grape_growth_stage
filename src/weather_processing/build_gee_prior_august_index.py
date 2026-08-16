#!/usr/bin/env python
"""Build the France-Germany site-year index for prior-August GEE export."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COHORT = (
    REPO_ROOT
    / "data/phenology/derived/modeling/france_germany_four_stage/phenology_events_long.csv"
)
DEFAULT_INDEX = REPO_ROOT / "data/gee/weather_download_index_1951_gee_20parts.csv"
DEFAULT_OUTPUT = (
    REPO_ROOT / "data/gee/france_germany_prior_august_site_years_gee_20parts.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--source-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--n-parts", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.n_parts < 1:
        raise ValueError("--n-parts must be positive")

    cohort_ids = pd.read_csv(
        args.cohort, usecols=["weather_id"], low_memory=False
    )["weather_id"].astype(str).drop_duplicates()
    source = pd.read_csv(args.source_index, low_memory=False)
    source["weather_id"] = source["weather_id"].astype(str)
    if source["weather_id"].duplicated().any():
        raise ValueError("Source GEE index contains duplicate weather_id values")

    work = source.loc[source["weather_id"].isin(set(cohort_ids))].copy()
    missing = set(cohort_ids).difference(set(work["weather_id"]))
    if missing:
        raise ValueError(f"{len(missing)} cohort weather IDs are missing from the source index")
    if not set(work["country"]).issubset({"France", "Germany"}):
        raise ValueError("The selected cohort contains countries outside France and Germany")

    work = work.sort_values(["country", "source", "site_id", "year", "weather_id"])
    work = work.reset_index(drop=True)
    work["gee_part"] = work.index % args.n_parts
    work["gee_part_key"] = work["gee_part"].map(
        lambda value: f"part_{int(value):02d}_of_{args.n_parts:02d}"
    )
    work["year"] = pd.to_numeric(work["year"], errors="raise").astype(int)
    work["august_start_date"] = pd.to_datetime(
        {"year": work["year"] - 1, "month": 8, "day": 1}
    ).dt.strftime("%Y-%m-%d")
    work["august_end_date"] = pd.to_datetime(
        {"year": work["year"] - 1, "month": 8, "day": 31}
    ).dt.strftime("%Y-%m-%d")
    work = work.rename(columns={"lat": "latitude", "lon": "longitude"})

    columns = [
        "gee_part", "gee_part_key", "weather_id", "country", "source",
        "site_id", "site_name", "latitude", "longitude", "alt_m", "year",
        "august_start_date", "august_end_date", "model_tier",
    ]
    output = work[columns].copy()
    numeric = ["latitude", "longitude", "year", "gee_part"]
    if output[numeric].isna().any().any():
        raise ValueError("The GEE upload index contains missing required numeric values")
    if not output["latitude"].between(-90, 90).all():
        raise ValueError("Latitude values are outside [-90, 90]")
    if not output["longitude"].between(-180, 180).all():
        raise ValueError("Longitude values are outside [-180, 180]")
    if output["weather_id"].duplicated().any():
        raise ValueError("The GEE upload index contains duplicate weather IDs")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False, encoding="utf-8")
    print(f"rows={len(output):,}")
    print(f"expected_daily_rows={len(output) * 31:,}")
    print(output.groupby(["country"]).size().to_string())
    print(output.groupby("gee_part").size().agg(["min", "max"]).to_string())
    print(f"output={args.output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
