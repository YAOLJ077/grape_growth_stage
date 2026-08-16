#!/usr/bin/env python
"""Standardize ERA5-Land units and audit daily site-year weather coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "weather" / "processed" / "era5_land_daily_complete"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "weather" / "processed" / "era5_land_daily_model_ready"
DEFAULT_QC_DIR = REPO_ROOT / "data" / "weather" / "processed" / "qc"

RAW_WEATHER_COLUMNS = [
    "temperature_2m", "temperature_2m_min", "temperature_2m_max", "dewpoint_temperature_2m",
    "total_precipitation_sum", "surface_pressure", "surface_solar_radiation_downwards_sum",
    "u_component_of_wind_10m", "v_component_of_wind_10m",
]
PRECIPITATION_NEGATIVE_TOLERANCE_M = -1e-6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--qc-dir", type=Path, default=DEFAULT_QC_DIR)
    parser.add_argument("--chunksize", type=int, default=200_000)
    return parser.parse_args()


def standardize_units(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["site_uid"] = out["country"].astype(str) + "|" + out["source"].astype(str) + "|" + out["site_id"].astype(str)
    out["temperature_2m_c"] = out["temperature_2m"] - 273.15
    out["temperature_2m_min_c"] = out["temperature_2m_min"] - 273.15
    out["temperature_2m_max_c"] = out["temperature_2m_max"] - 273.15
    out["dewpoint_temperature_2m_c"] = out["dewpoint_temperature_2m"] - 273.15
    # Earth Engine CSV exports contain sub-1e-7 m negative round-off noise.
    # Precipitation is physically non-negative; retain the source values in the
    # immutable complete layer and clamp only the standardized model-ready copy.
    out["total_precipitation_mm"] = out["total_precipitation_sum"].clip(lower=0.0) * 1000.0
    out["surface_pressure_kpa"] = out["surface_pressure"] / 1000.0
    out["surface_solar_radiation_downwards_mj_m2"] = out["surface_solar_radiation_downwards_sum"] / 1_000_000.0
    out["u_component_of_wind_10m_m_s"] = out["u_component_of_wind_10m"]
    out["v_component_of_wind_10m_m_s"] = out["v_component_of_wind_10m"]
    out["wind_speed_10m_m_s"] = np.hypot(out["u_component_of_wind_10m"], out["v_component_of_wind_10m"])
    return out.drop(columns=RAW_WEATHER_COLUMNS)


def update_stats(stats: dict[str, dict], chunk: pd.DataFrame) -> None:
    work = chunk.copy()
    work["weather_date_parsed"] = pd.to_datetime(work["weather_date"], errors="coerce")
    work["temperature_order_bad"] = (
        work["temperature_2m_min"].gt(work["temperature_2m"])
        | work["temperature_2m"].gt(work["temperature_2m_max"])
    )
    work["material_negative_precipitation"] = work["total_precipitation_sum"].lt(PRECIPITATION_NEGATIVE_TOLERANCE_M)
    work["tiny_negative_precipitation_clipped"] = work["total_precipitation_sum"].lt(0.0) & ~work["material_negative_precipitation"]
    work["negative_radiation"] = work["surface_solar_radiation_downwards_sum"].lt(-1e-6)
    work["dewpoint_above_temperature"] = work["dewpoint_temperature_2m"].gt(work["temperature_2m"] + 0.5)
    work["missing_weather_values"] = work[RAW_WEATHER_COLUMNS].isna().any(axis=1)
    duplicate_counts = (
        work.groupby(["weather_id", "weather_date"], dropna=False)
        .size()
        .sub(1)
        .clip(lower=0)
        .groupby(level=0)
        .sum()
        .rename("n_duplicate_dates")
    )
    grouped = work.groupby("weather_id", dropna=False).agg(
        country=("country", "first"), source=("source", "first"), site_id=("site_id", "first"), year=("year", "first"),
        expected_start_date=("weather_start_date", "first"), expected_end_date=("weather_end_date", "first"),
        first_event_date=("first_event_date", "first"), last_event_date=("last_event_date", "first"),
        actual_start_date=("weather_date_parsed", "min"), actual_end_date=("weather_date_parsed", "max"),
        n_rows=("weather_date_parsed", "size"), n_valid_dates=("weather_date_parsed", "count"),
        n_missing_weather_rows=("missing_weather_values", "sum"), n_temperature_order_bad=("temperature_order_bad", "sum"),
        n_material_negative_precipitation=("material_negative_precipitation", "sum"),
        n_tiny_negative_precipitation_clipped=("tiny_negative_precipitation_clipped", "sum"),
        n_negative_radiation=("negative_radiation", "sum"),
        n_dewpoint_above_temperature=("dewpoint_above_temperature", "sum"),
        n_buffer_fill_rows=("weather_fill_method", lambda values: values.eq("era5_land_buffer_mean").sum()),
    )
    grouped = grouped.join(duplicate_counts, how="left")
    grouped["n_duplicate_dates"] = grouped["n_duplicate_dates"].fillna(0).astype(int)
    for weather_id, row in grouped.iterrows():
        current = stats.get(str(weather_id))
        record = row.to_dict()
        if current is None:
            stats[str(weather_id)] = record
            continue
        current["actual_start_date"] = min(current["actual_start_date"], record["actual_start_date"])
        current["actual_end_date"] = max(current["actual_end_date"], record["actual_end_date"])
        for field in [
            "n_rows", "n_valid_dates", "n_missing_weather_rows", "n_temperature_order_bad",
            "n_material_negative_precipitation", "n_tiny_negative_precipitation_clipped", "n_negative_radiation",
            "n_dewpoint_above_temperature", "n_buffer_fill_rows",
            "n_duplicate_dates",
        ]:
            current[field] += record[field]


def finalize_qc(stats: dict[str, dict]) -> pd.DataFrame:
    qc = pd.DataFrame.from_dict(stats, orient="index").rename_axis("weather_id").reset_index()
    for column in ["expected_start_date", "expected_end_date", "first_event_date", "last_event_date", "actual_start_date", "actual_end_date"]:
        qc[column] = pd.to_datetime(qc[column], errors="coerce")
    qc["n_expected_days"] = (qc["expected_end_date"] - qc["expected_start_date"]).dt.days + 1
    qc["n_unique_dates"] = qc["n_valid_dates"] - qc["n_duplicate_dates"]
    qc["n_missing_dates"] = (qc["n_expected_days"] - qc["n_unique_dates"]).clip(lower=0)
    qc["weather_period_complete"] = (
        qc["actual_start_date"].eq(qc["expected_start_date"])
        & qc["actual_end_date"].eq(qc["expected_end_date"])
        & qc["n_missing_dates"].eq(0)
        & qc["n_duplicate_dates"].eq(0)
    )
    qc["weather_complete_for_observed_events"] = (
        qc["actual_start_date"].le(qc["expected_start_date"])
        & qc["actual_end_date"].ge(qc["last_event_date"])
        & qc["n_missing_weather_rows"].eq(0)
    )
    qc["has_buffer_fill"] = qc["n_buffer_fill_rows"].gt(0)
    qc["daily_physical_qc_pass"] = (
        qc["n_missing_weather_rows"].eq(0)
        & qc["n_temperature_order_bad"].eq(0)
        & qc["n_material_negative_precipitation"].eq(0)
        & qc["n_negative_radiation"].eq(0)
    )
    for column in ["expected_start_date", "expected_end_date", "first_event_date", "last_event_date", "actual_start_date", "actual_end_date"]:
        qc[column] = qc[column].dt.strftime("%Y-%m-%d")
    return qc.sort_values(["country", "source", "site_id", "year"])


def main() -> int:
    args = parse_args()
    files = sorted(args.input_dir.glob("era5_land_daily_grape_1951_part_*_of_20.csv"))
    if not files:
        raise FileNotFoundError(f"No complete weather files found in {args.input_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.qc_dir.mkdir(parents=True, exist_ok=True)
    stats: dict[str, dict] = {}
    total_rows = 0
    output_files = []
    for file_number, source_path in enumerate(files, start=1):
        output_path = args.output_dir / source_path.name
        if output_path.exists():
            output_path.unlink()
        first_chunk = True
        file_rows = 0
        for chunk in pd.read_csv(source_path, chunksize=args.chunksize, low_memory=False):
            file_rows += len(chunk)
            total_rows += len(chunk)
            update_stats(stats, chunk)
            normalized = standardize_units(chunk)
            normalized.to_csv(output_path, mode="w" if first_chunk else "a", header=first_chunk, index=False)
            first_chunk = False
        output_files.append({"file": str(output_path.relative_to(REPO_ROOT)), "rows": file_rows})
        print(f"Weather standardization: {file_number}/{len(files)} {source_path.name} rows={file_rows:,}")

    qc = finalize_qc(stats)
    qc_path = args.qc_dir / "weather_site_year_qc.csv"
    qc.to_csv(qc_path, index=False)
    units = pd.DataFrame([
        ("temperature_2m_c", "degree_Celsius", "temperature_2m - 273.15"),
        ("temperature_2m_min_c", "degree_Celsius", "temperature_2m_min - 273.15"),
        ("temperature_2m_max_c", "degree_Celsius", "temperature_2m_max - 273.15"),
        ("dewpoint_temperature_2m_c", "degree_Celsius", "dewpoint_temperature_2m - 273.15"),
        ("total_precipitation_mm", "mm day-1", "total_precipitation_sum * 1000"),
        ("surface_pressure_kpa", "kPa", "surface_pressure / 1000"),
        ("surface_solar_radiation_downwards_mj_m2", "MJ m-2 day-1", "surface_solar_radiation_downwards_sum / 1e6"),
        ("u_component_of_wind_10m_m_s", "m s-1", "unchanged"),
        ("v_component_of_wind_10m_m_s", "m s-1", "unchanged"),
        ("wind_speed_10m_m_s", "m s-1", "sqrt(u^2 + v^2)"),
    ], columns=["column", "unit", "conversion"])
    units.to_csv(args.qc_dir / "weather_model_ready_units.csv", index=False)
    summary = {
        "input_dir": str(args.input_dir.relative_to(REPO_ROOT)),
        "output_dir": str(args.output_dir.relative_to(REPO_ROOT)),
        "n_files": len(files), "n_daily_rows": total_rows, "n_site_years": int(len(qc)),
        "n_complete_full_period_site_years": int(qc["weather_period_complete"].sum()),
        "n_complete_for_observed_events": int(qc["weather_complete_for_observed_events"].sum()),
        "n_partial_period_site_years": int((~qc["weather_period_complete"]).sum()),
        "n_site_years_with_buffer_fill": int(qc["has_buffer_fill"].sum()),
        "n_site_years_failing_daily_physical_qc": int((~qc["daily_physical_qc_pass"]).sum()),
        "site_year_qc": str(qc_path.relative_to(REPO_ROOT)), "output_files": output_files,
    }
    (args.qc_dir / "weather_model_ready_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "output_files"}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
