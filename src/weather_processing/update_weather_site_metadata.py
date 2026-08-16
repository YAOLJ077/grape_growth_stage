#!/usr/bin/env python
"""Refresh coordinates and source altitude in completed weather CSV parts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = REPO_ROOT / "data" / "gee" / "weather_download_index_1951.csv"
DEFAULT_WEATHER_DIR = REPO_ROOT / "data" / "weather" / "processed" / "era5_land_daily_complete"
DEFAULT_SUMMARY = REPO_ROOT / "data" / "weather" / "processed" / "weather_complete_merge_summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER_DIR)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--chunksize", type=int, default=200_000)
    return parser.parse_args()


def refresh_chunk(chunk: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    original_columns = list(chunk.columns)
    chunk = chunk.drop(columns=[column for column in ["lat", "lon", "alt_m"] if column in chunk.columns])
    chunk = chunk.merge(lookup, on="weather_id", how="left", validate="many_to_one")
    ordered = [column for column in original_columns if column not in {"lat", "lon", "alt_m"}]
    insert_at = ordered.index("site_name") + 1 if "site_name" in ordered else 7
    ordered[insert_at:insert_at] = ["lat", "lon", "alt_m"]
    return chunk[[column for column in ordered if column in chunk.columns]]


def main() -> int:
    args = parse_args()
    lookup = pd.read_csv(args.index, usecols=["weather_id", "lat", "lon", "alt_m"])
    if lookup["weather_id"].duplicated().any():
        raise ValueError("weather index contains duplicate weather_id values")
    files = sorted(args.weather_dir.glob("era5_land_daily_grape_1951_part_*_of_20.csv"))
    if not files:
        raise FileNotFoundError(f"No completed weather parts found in {args.weather_dir}")

    total_rows = 0
    missing_altitude_rows = 0
    for path in files:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.unlink(missing_ok=True)
        first = True
        file_rows = 0
        for chunk in pd.read_csv(path, chunksize=args.chunksize, low_memory=False):
            refreshed = refresh_chunk(chunk, lookup)
            file_rows += len(refreshed)
            missing_altitude_rows += int(refreshed["alt_m"].isna().sum())
            refreshed.to_csv(temporary, mode="w" if first else "a", header=first, index=False)
            first = False
        temporary.replace(path)
        total_rows += file_rows
        print(f"refreshed {path.name}: {file_rows:,} rows")
    print(f"Total rows refreshed: {total_rows:,}")
    if args.summary.exists():
        summary = json.loads(args.summary.read_text(encoding="utf-8"))
        summary["site_metadata_refresh"] = {
            "script": "src/weather_processing/update_weather_site_metadata.py",
            "index": str(args.index.relative_to(REPO_ROOT)),
            "rows_refreshed": total_rows,
            "metadata_mismatches_after_refresh": 0,
            "missing_source_altitude_rows": missing_altitude_rows,
            "note": (
                "lat, lon, and source alt_m were refreshed after France altitudeIgn harmonization; "
                "uniform DEM elevation is stored in site_topography.csv"
            ),
        }
        args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
