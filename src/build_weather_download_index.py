#!/usr/bin/env python
"""Build a site-year weather download index from processed phenology data."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        default=[
            Path("data/phenology_grape/processed/france_grape_phenology_complete.csv"),
            Path("data/phenology_grape/processed/germany_grape_phenology_complete.csv"),
        ],
        help="Processed country phenology table(s).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/phenology_grape/index/grape_weather_download_index.csv"),
        help="Output weather download index CSV.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    usecols = [
        "country_name",
        "region",
        "federal_state",
        "latitude",
        "longitude",
        "year",
        "date",
    ]
    df = pd.concat(
        [pd.read_csv(path, usecols=usecols, low_memory=False) for path in args.input],
        ignore_index=True,
    )
    df = df.dropna(subset=["country_name", "latitude", "longitude", "year"]).copy()
    df["year"] = df["year"].astype(int)

    df["区域"] = df["region"].where(df["region"].notna(), df["federal_state"])
    df["区域"] = df["区域"].fillna("")

    df["国家"] = df["country_name"]
    df["经度"] = df["longitude"].round(6)
    df["纬度"] = df["latitude"].round(6)
    df["年份"] = df["year"]

    out = (
        df.groupby(["国家", "区域", "经度", "纬度", "年份"], dropna=False)
        .agg(起始日=("date", "min"), 结束日=("date", "max"))
        .reset_index()
        .sort_values(["国家", "区域", "经度", "纬度", "年份"], kind="mergesort")
        .reset_index(drop=True)
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    print(f"Wrote {len(out):,} rows to {args.output}")
    print(out.groupby("国家").size().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
