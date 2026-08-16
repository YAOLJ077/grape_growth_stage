#!/usr/bin/env python
"""Create elevation-adjusted ERA5-Land temperatures for the France-Germany cohort.

The primary adjustment uses a fixed 6.5 degC km-1 environmental lapse rate.
Additional 4.5 and 6.0 degC km-1 columns support sensitivity analyses. The
script preserves all model-ready weather variables and writes compressed,
partitioned Parquet files plus site-year QC and supplementary summaries.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "weather" / "processed" / "era5_land_daily_model_ready"
DEFAULT_COHORT = (
    REPO_ROOT
    / "data"
    / "phenology"
    / "derived"
    / "modeling"
    / "france_germany_four_stage"
    / "phenology_events_long.csv"
)
DEFAULT_TOPOGRAPHY = REPO_ROOT / "data" / "topography" / "processed" / "site_era5_land_grid_crosswalk.csv"
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "data" / "weather" / "processed" / "era5_land_daily_france_germany_adjusted"
)
DEFAULT_PRIOR_AUGUST_DIR = (
    REPO_ROOT / "data" / "weather" / "processed" / "grape_phenology_era5_land_prior_august"
)

TEMPERATURE_COLUMNS = ("temperature_2m_c", "temperature_2m_min_c", "temperature_2m_max_c")
RAW_AUGUST_COLUMNS = [
    "temperature_2m", "temperature_2m_min", "temperature_2m_max",
    "dewpoint_temperature_2m", "total_precipitation_sum", "surface_pressure",
    "surface_solar_radiation_downwards_sum", "u_component_of_wind_10m",
    "v_component_of_wind_10m",
]
MODEL_DAILY_COLUMNS = [
    "weather_date", "weather_year", "weather_month", "weather_doy",
    "temperature_2m_c", "temperature_2m_min_c", "temperature_2m_max_c",
    "dewpoint_temperature_2m_c", "total_precipitation_mm", "surface_pressure_kpa",
    "surface_solar_radiation_downwards_mj_m2", "u_component_of_wind_10m_m_s",
    "v_component_of_wind_10m_m_s", "wind_speed_10m_m_s",
]
LAPSE_RATES_C_PER_KM = {
    "sensitivity_4p5c_km": 4.5,
    "sensitivity_6p0c_km": 6.0,
    "main_6p5c_km": 6.5,
}
MAIN_RATE_LABEL = "main_6p5c_km"
BUFFER_FILL_METHOD = "era5_land_buffer_mean"
DZ_BINS_M = (-np.inf, 50.0, 100.0, 200.0, 300.0, np.inf)
DZ_LABELS = ("<=50 m", "50-100 m", "100-200 m", "200-300 m", ">300 m")

TOPOGRAPHY_COLUMNS = [
    "site_uid",
    "dem_elevation_m",
    "era5_grid_id",
    "era5_grid_elevation_m",
    "site_minus_grid_elevation_m",
    "abs_site_grid_elevation_difference_m",
    "coordinate_instability_flag",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--topography", type=Path, default=DEFAULT_TOPOGRAPHY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--prior-august-dir", type=Path, default=DEFAULT_PRIOR_AUGUST_DIR)
    parser.add_argument("--chunksize", type=int, default=150_000)
    parser.add_argument("--compression", default="zstd", choices=("zstd", "snappy", "gzip"))
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def standardize_prior_august(raw: pd.DataFrame, base_metadata: pd.DataFrame) -> pd.DataFrame:
    """Convert downloaded prior-August rows and attach trusted local metadata."""
    required = {"weather_id", "weather_date", "weather_year", "weather_month", "weather_doy", *RAW_AUGUST_COLUMNS}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"Prior-August data are missing columns: {sorted(missing)}")
    daily = raw[["weather_id", "weather_date", "weather_year", "weather_month", "weather_doy", *RAW_AUGUST_COLUMNS]].copy()
    daily["temperature_2m_c"] = daily["temperature_2m"] - 273.15
    daily["temperature_2m_min_c"] = daily["temperature_2m_min"] - 273.15
    daily["temperature_2m_max_c"] = daily["temperature_2m_max"] - 273.15
    daily["dewpoint_temperature_2m_c"] = daily["dewpoint_temperature_2m"] - 273.15
    daily["total_precipitation_mm"] = daily["total_precipitation_sum"].clip(lower=0.0) * 1000.0
    daily["surface_pressure_kpa"] = daily["surface_pressure"] / 1000.0
    daily["surface_solar_radiation_downwards_mj_m2"] = daily[
        "surface_solar_radiation_downwards_sum"
    ] / 1_000_000.0
    daily["u_component_of_wind_10m_m_s"] = daily["u_component_of_wind_10m"]
    daily["v_component_of_wind_10m_m_s"] = daily["v_component_of_wind_10m"]
    daily["wind_speed_10m_m_s"] = np.hypot(
        daily["u_component_of_wind_10m"], daily["v_component_of_wind_10m"]
    )
    daily = daily.drop(columns=RAW_AUGUST_COLUMNS)
    metadata_columns = [column for column in base_metadata.columns if column not in MODEL_DAILY_COLUMNS]
    metadata = base_metadata[metadata_columns].drop_duplicates("weather_id")
    out = daily.merge(metadata, on="weather_id", how="left", validate="many_to_one")
    if out["site_uid"].isna().any():
        raise ValueError("Prior-August rows did not match trusted model-ready metadata")
    out["weather_start_date"] = pd.to_datetime(
        {"year": out["year"].astype(int) - 1, "month": 8, "day": 1}
    ).dt.strftime("%Y-%m-%d")
    return out[base_metadata.columns]


def rate_suffix(rate_label: str) -> str:
    return rate_label


def adjusted_column(source_column: str, rate_label: str) -> str:
    return f"{source_column}_adjusted_{rate_suffix(rate_label)}"


def adjustment_column(rate_label: str) -> str:
    return f"temperature_adjustment_c_{rate_suffix(rate_label)}"


def load_inputs(cohort_path: Path, topography_path: Path) -> tuple[set[str], pd.DataFrame]:
    cohort = pd.read_csv(cohort_path, usecols=["weather_id", "site_uid", "country"], low_memory=False)
    cohort = cohort[cohort["country"].isin(["France", "Germany"])].drop_duplicates("weather_id")
    if cohort["weather_id"].duplicated().any():
        raise ValueError("Cohort contains duplicate weather_id rows after deduplication")

    topography = pd.read_csv(topography_path, usecols=lambda column: column in TOPOGRAPHY_COLUMNS)
    missing_columns = set(TOPOGRAPHY_COLUMNS).difference(topography.columns)
    if missing_columns:
        raise ValueError(f"Topography is missing columns: {sorted(missing_columns)}")
    if topography["site_uid"].duplicated().any():
        raise ValueError("Topography contains duplicate site_uid rows")
    topography["coordinate_instability_flag"] = topography["coordinate_instability_flag"].fillna(False).astype(bool)
    topography = topography[topography["site_uid"].isin(cohort["site_uid"])].copy()
    return set(cohort["weather_id"].astype(str)), topography


def add_adjusted_temperatures(frame: pd.DataFrame, topography: pd.DataFrame) -> pd.DataFrame:
    """Attach terrain fields and add primary and sensitivity temperature columns."""
    required_weather = {
        "site_uid", "weather_id", "weather_fill_method", *TEMPERATURE_COLUMNS,
    }
    missing_weather = required_weather.difference(frame.columns)
    if missing_weather:
        raise ValueError(f"Weather frame is missing columns: {sorted(missing_weather)}")

    topo_fields = [column for column in TOPOGRAPHY_COLUMNS if column != "site_uid"]
    overlap = set(topo_fields).intersection(frame.columns)
    if overlap:
        raise ValueError(f"Weather frame already contains topography columns: {sorted(overlap)}")
    out = frame.merge(topography[TOPOGRAPHY_COLUMNS], on="site_uid", how="left", validate="many_to_one")

    missing_dem = out["dem_elevation_m"].isna()
    missing_grid = out["era5_grid_elevation_m"].isna()
    buffer_fill = out["weather_fill_method"].eq(BUFFER_FILL_METHOD)
    if buffer_fill.any():
        raise ValueError(
            "Cohort contains weather without a unique ERA5-Land point sample; "
            "exclude those site-years before temperature adjustment"
        )
    unstable_coordinate = out["coordinate_instability_flag"].fillna(True)
    eligible = ~(missing_dem | missing_grid | unstable_coordinate)

    out["temperature_elevation_adjustment_eligible"] = eligible
    out["temperature_adjustment_excluded_coordinate_instability"] = unstable_coordinate
    out["temperature_adjustment_excluded_missing_elevation"] = missing_dem | missing_grid
    out["temperature_adjustment_abs_dz_gt_300m"] = out[
        "abs_site_grid_elevation_difference_m"
    ].gt(300.0)
    out["temperature_adjustment_abs_dz_gt_500m"] = out[
        "abs_site_grid_elevation_difference_m"
    ].gt(500.0)

    delta_z = out["site_minus_grid_elevation_m"]
    for label, rate_c_per_km in LAPSE_RATES_C_PER_KM.items():
        adjustment = -rate_c_per_km / 1000.0 * delta_z
        adjustment = adjustment.where(eligible)
        out[adjustment_column(label)] = adjustment
        for source_column in TEMPERATURE_COLUMNS:
            out[adjusted_column(source_column, label)] = out[source_column] + adjustment
    return out


def temperature_order_bad(frame: pd.DataFrame, rate_label: str) -> pd.Series:
    tmean = frame[adjusted_column("temperature_2m_c", rate_label)]
    tmin = frame[adjusted_column("temperature_2m_min_c", rate_label)]
    tmax = frame[adjusted_column("temperature_2m_max_c", rate_label)]
    return tmin.gt(tmean) | tmean.gt(tmax)


def summarize_chunk(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["adjusted_temperature_order_bad"] = temperature_order_bad(work, MAIN_RATE_LABEL)
    work["adjusted_main_missing"] = work[
        adjusted_column("temperature_2m_c", MAIN_RATE_LABEL)
    ].isna()
    grouped = work.groupby("weather_id", dropna=False).agg(
        country=("country", "first"),
        source=("source", "first"),
        site_id=("site_id", "first"),
        site_uid=("site_uid", "first"),
        year=("year", "first"),
        n_daily_rows=("weather_date", "size"),
        n_eligible_rows=("temperature_elevation_adjustment_eligible", "sum"),
        n_coordinate_instability_rows=("temperature_adjustment_excluded_coordinate_instability", "sum"),
        n_missing_elevation_rows=("temperature_adjustment_excluded_missing_elevation", "sum"),
        n_adjusted_main_missing=("adjusted_main_missing", "sum"),
        n_adjusted_temperature_order_bad=("adjusted_temperature_order_bad", "sum"),
        dem_elevation_m=("dem_elevation_m", "first"),
        era5_grid_elevation_m=("era5_grid_elevation_m", "first"),
        site_minus_grid_elevation_m=("site_minus_grid_elevation_m", "first"),
        abs_site_grid_elevation_difference_m=("abs_site_grid_elevation_difference_m", "first"),
        temperature_adjustment_c_sensitivity_4p5c_km=(
            adjustment_column("sensitivity_4p5c_km"), "first"
        ),
        temperature_adjustment_c_sensitivity_6p0c_km=(
            adjustment_column("sensitivity_6p0c_km"), "first"
        ),
        temperature_adjustment_c_main_6p5c_km=(adjustment_column(MAIN_RATE_LABEL), "first"),
    )
    return grouped.reset_index()


def combine_site_year_qc(parts: list[pd.DataFrame]) -> pd.DataFrame:
    work = pd.concat(parts, ignore_index=True)
    additive = [
        "n_daily_rows", "n_eligible_rows", "n_coordinate_instability_rows",
        "n_missing_elevation_rows", "n_adjusted_main_missing", "n_adjusted_temperature_order_bad",
    ]
    first = [column for column in work.columns if column not in {"weather_id", *additive}]
    aggregations = {column: "sum" for column in additive}
    aggregations.update({column: "first" for column in first})
    qc = work.groupby("weather_id", as_index=False).agg(aggregations)
    qc["temperature_elevation_adjustment_eligible"] = qc["n_eligible_rows"].eq(qc["n_daily_rows"])
    qc["has_coordinate_instability"] = qc["n_coordinate_instability_rows"].gt(0)
    qc["has_missing_elevation"] = qc["n_missing_elevation_rows"].gt(0)
    qc["abs_dz_gt_300m"] = qc["abs_site_grid_elevation_difference_m"].gt(300.0)
    qc["abs_dz_gt_500m"] = qc["abs_site_grid_elevation_difference_m"].gt(500.0)
    return qc.sort_values(["country", "site_id", "year"]).reset_index(drop=True)


def build_sensitivity_summary(qc: pd.DataFrame) -> pd.DataFrame:
    work = qc.copy()
    work["abs_dz_band"] = pd.cut(
        work["abs_site_grid_elevation_difference_m"],
        bins=DZ_BINS_M,
        labels=DZ_LABELS,
        right=True,
        include_lowest=True,
        ordered=True,
    )
    grouped = work.groupby(["country", "abs_dz_band"], observed=False).agg(
        n_sites=("site_uid", "nunique"),
        n_site_years=("weather_id", "size"),
        n_eligible_site_years=("temperature_elevation_adjustment_eligible", "sum"),
        median_abs_dz_m=("abs_site_grid_elevation_difference_m", "median"),
        min_delta_z_m=("site_minus_grid_elevation_m", "min"),
        median_delta_z_m=("site_minus_grid_elevation_m", "median"),
        max_delta_z_m=("site_minus_grid_elevation_m", "max"),
        median_adjustment_4p5c_km=("temperature_adjustment_c_sensitivity_4p5c_km", "median"),
        median_adjustment_6p0c_km=("temperature_adjustment_c_sensitivity_6p0c_km", "median"),
        median_adjustment_6p5c_km=("temperature_adjustment_c_main_6p5c_km", "median"),
        min_adjustment_6p5c_km=("temperature_adjustment_c_main_6p5c_km", "min"),
        max_adjustment_6p5c_km=("temperature_adjustment_c_main_6p5c_km", "max"),
    ).reset_index()
    grouped["eligible_site_year_share_pct"] = (
        grouped["n_eligible_site_years"].div(grouped["n_site_years"].replace(0, np.nan)).mul(100)
    )
    numeric = grouped.select_dtypes(include="number").columns
    grouped[numeric] = grouped[numeric].round(3)
    grouped["abs_dz_band"] = grouped["abs_dz_band"].astype("string")
    return grouped


def build_site_summary(qc: pd.DataFrame) -> pd.DataFrame:
    return (
        qc.groupby(["country", "source", "site_id", "site_uid"], as_index=False)
        .agg(
            first_year=("year", "min"),
            last_year=("year", "max"),
            n_site_years=("weather_id", "size"),
            n_eligible_site_years=("temperature_elevation_adjustment_eligible", "sum"),
            dem_elevation_m=("dem_elevation_m", "first"),
            era5_grid_elevation_m=("era5_grid_elevation_m", "first"),
            site_minus_grid_elevation_m=("site_minus_grid_elevation_m", "first"),
            abs_site_grid_elevation_difference_m=("abs_site_grid_elevation_difference_m", "first"),
            temperature_adjustment_c_sensitivity_4p5c_km=(
                "temperature_adjustment_c_sensitivity_4p5c_km", "first"
            ),
            temperature_adjustment_c_sensitivity_6p0c_km=(
                "temperature_adjustment_c_sensitivity_6p0c_km", "first"
            ),
            temperature_adjustment_c_main_6p5c_km=("temperature_adjustment_c_main_6p5c_km", "first"),
        )
        .sort_values(["country", "site_id"])
        .reset_index(drop=True)
    )


def build_stage_sensitivity_summary(qc: pd.DataFrame, cohort_path: Path) -> pd.DataFrame:
    events = pd.read_csv(
        cohort_path,
        usecols=["weather_id", "country", "target_stage", "bbch"],
        low_memory=False,
    ).drop_duplicates(["weather_id", "target_stage", "bbch"])
    fields = [
        "weather_id", "site_uid", "temperature_elevation_adjustment_eligible",
        "site_minus_grid_elevation_m", "abs_site_grid_elevation_difference_m",
        "temperature_adjustment_c_sensitivity_4p5c_km",
        "temperature_adjustment_c_sensitivity_6p0c_km",
        "temperature_adjustment_c_main_6p5c_km",
    ]
    work = events.merge(qc[fields], on="weather_id", how="left", validate="many_to_one")
    if work["site_uid"].isna().any():
        raise ValueError("Stage sensitivity summary contains unmatched weather IDs")
    grouped = work.groupby(["country", "target_stage", "bbch"], as_index=False).agg(
        event_records=("weather_id", "size"),
        site_years=("weather_id", "nunique"),
        sites=("site_uid", "nunique"),
        eligible_site_years=("temperature_elevation_adjustment_eligible", "sum"),
        median_delta_z_m=("site_minus_grid_elevation_m", "median"),
        median_abs_delta_z_m=("abs_site_grid_elevation_difference_m", "median"),
        median_adjustment_4p5c_km=("temperature_adjustment_c_sensitivity_4p5c_km", "median"),
        median_adjustment_6p0c_km=("temperature_adjustment_c_sensitivity_6p0c_km", "median"),
        median_adjustment_6p5c_km=("temperature_adjustment_c_main_6p5c_km", "median"),
        min_adjustment_6p5c_km=("temperature_adjustment_c_main_6p5c_km", "min"),
        max_adjustment_6p5c_km=("temperature_adjustment_c_main_6p5c_km", "max"),
    )
    grouped["eligible_site_year_share_pct"] = (
        grouped["eligible_site_years"].div(grouped["site_years"]).mul(100)
    )
    numeric = grouped.select_dtypes(include="number").columns
    grouped[numeric] = grouped[numeric].round(3)
    return grouped.sort_values(["country", "bbch"]).reset_index(drop=True)


def reference_table() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "lapse_rate_c_per_km": 6.5,
            "analysis_role": "primary",
            "justification": "Common constant environmental lapse rate for elevation correction of reanalysis air temperature",
            "references": "Dutra et al. 2020, doi:10.1029/2019EA000984; Mihalevich et al. 2022, doi:10.1029/2021WR031294",
        },
        {
            "lapse_rate_c_per_km": 6.0,
            "analysis_role": "sensitivity",
            "justification": "Upper end of the 0.53-0.60 degC per 100 m vineyard growing-season gradient",
            "references": "Alikadic et al. 2019, doi:10.1016/j.agrformet.2019.02.030",
        },
        {
            "lapse_rate_c_per_km": 4.5,
            "analysis_role": "sensitivity",
            "justification": "Lower constant rate representing weaker near-surface gradients",
            "references": "Dutra et al. 2020, doi:10.1029/2019EA000984",
        },
    ])


def output_name(source_path: Path) -> str:
    match = re.search(r"(part_\d+_of_\d+)", source_path.stem)
    part = match.group(1) if match else source_path.stem
    return f"era5_land_daily_france_germany_adjusted_{part}.parquet"


def write_readme(path: Path) -> None:
    path.write_text(
        """# France-Germany elevation-adjusted ERA5-Land temperature

Generated by `src/weather_processing/adjust_france_germany_temperature_elevation.py`.

- Cohort: France and Germany, 1951+, exact BBCH 07/65/81/89 site-years.
- Primary lapse rate: 6.5 degC km-1.
- Sensitivity lapse rates: 4.5 and 6.0 degC km-1.
- Original model-ready weather variables are retained and the previous August is prepended.
- Adjusted daily files are compressed Parquet partitions with `adjusted` in every filename.
- Every included site-year has a unique ERA5-Land point sample and grid elevation.

Supporting outputs:

- `qc/temperature_adjustment_site_year_qc.csv`
- `qc/temperature_adjustment_summary.json`
- `supplementary/temperature_adjustment_site_summary.csv`
- `supplementary/temperature_adjustment_sensitivity_by_abs_dz_band.csv`
- `supplementary/temperature_adjustment_sensitivity_by_stage_country.csv`
- `supplementary/temperature_adjustment_lapse_rate_references.csv`

Method provenance: `note/data_process/era5_land_temperature_elevation_adjustment.md`.
""",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    files = sorted(args.input_dir.glob("era5_land_daily_grape_1951_part_*_of_20.csv"))
    if not files:
        raise FileNotFoundError(f"No model-ready weather files found in {args.input_dir}")
    target_weather_ids, topography = load_inputs(args.cohort, args.topography)
    august_files = sorted(args.prior_august_dir.glob("era5_land_daily_france_germany_prior_august_part_*_of_20.csv"))
    if len(august_files) != 20:
        raise FileNotFoundError(f"Expected 20 prior-August files, found {len(august_files)}")
    prior_august = pd.concat(
        [pd.read_csv(path, low_memory=False) for path in august_files], ignore_index=True
    )
    prior_august["weather_id"] = prior_august["weather_id"].astype(str)
    if prior_august.duplicated(["weather_id", "weather_date"]).any():
        raise ValueError("Prior-August download contains duplicate weather_id-date rows")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    qc_dir = args.output_dir / "qc"
    supplementary_dir = args.output_dir / "supplementary"
    qc_dir.mkdir(parents=True, exist_ok=True)
    supplementary_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(args.output_dir.glob("era5_land_daily_france_germany_adjusted_*.parquet"))
    if existing and not args.overwrite:
        raise FileExistsError(f"Adjusted outputs already exist; use --overwrite: {existing[0]}")
    if args.overwrite:
        for existing_path in existing:
            existing_path.unlink()

    qc_parts: list[pd.DataFrame] = []
    output_files: list[dict[str, object]] = []
    found_weather_ids: set[str] = set()
    total_rows = 0
    for file_number, source_path in enumerate(files, start=1):
        adjusted_chunks: list[pd.DataFrame] = []
        metadata_chunks: list[pd.DataFrame] = []
        file_rows = 0
        for chunk in pd.read_csv(source_path, chunksize=args.chunksize, low_memory=False):
            selected = chunk[chunk["weather_id"].astype(str).isin(target_weather_ids)].copy()
            if selected.empty:
                continue
            metadata_chunks.append(selected.drop_duplicates("weather_id"))
            adjusted = add_adjusted_temperatures(selected, topography)
            qc_parts.append(summarize_chunk(adjusted))
            adjusted_chunks.append(adjusted)
            file_rows += len(adjusted)
            total_rows += len(adjusted)
            found_weather_ids.update(adjusted["weather_id"].astype(str).unique())
        if not adjusted_chunks:
            continue
        part_match = re.search(r"(part_\d+_of_\d+)", source_path.stem)
        if not part_match:
            raise ValueError(f"Cannot identify partition label in {source_path.name}")
        base_metadata = pd.concat(metadata_chunks, ignore_index=True).drop_duplicates("weather_id")
        base_ids = set(base_metadata["weather_id"].astype(str))
        august_raw = prior_august.loc[prior_august["weather_id"].isin(base_ids)].copy()
        august_ids = set(august_raw["weather_id"].astype(str))
        if august_ids != base_ids:
            raise ValueError(
                f"Prior-August IDs differ in {part_match.group(1)}: "
                f"missing={len(base_ids - august_ids)}, extra={len(august_ids - base_ids)}"
            )
        august_ready = standardize_prior_august(august_raw, base_metadata)
        august_adjusted = add_adjusted_temperatures(august_ready, topography)
        qc_parts.append(summarize_chunk(august_adjusted))
        adjusted_chunks.append(august_adjusted)
        file_rows += len(august_adjusted)
        total_rows += len(august_adjusted)
        output_path = args.output_dir / output_name(source_path)
        combined = pd.concat(adjusted_chunks, ignore_index=True)
        combined["weather_date"] = pd.to_datetime(combined["weather_date"]).dt.strftime("%Y-%m-%d")
        if combined.duplicated(["weather_id", "weather_date"]).any():
            raise ValueError(f"Duplicate weather dates after August merge: {part_match.group(1)}")
        combined = combined.sort_values(["weather_id", "weather_date"]).reset_index(drop=True)
        combined.to_parquet(output_path, index=False, compression=args.compression)
        output_files.append({
            "file": str(output_path.relative_to(REPO_ROOT)),
            "rows": file_rows,
            "bytes": output_path.stat().st_size,
        })
        print(f"Temperature adjustment: {file_number}/{len(files)} {output_path.name} rows={file_rows:,}")

    if not qc_parts:
        raise RuntimeError("No France-Germany cohort weather rows were found")
    missing_weather_ids = target_weather_ids.difference(found_weather_ids)
    if missing_weather_ids:
        sample = sorted(missing_weather_ids)[:10]
        raise ValueError(f"Missing {len(missing_weather_ids)} cohort weather IDs; examples: {sample}")

    qc = combine_site_year_qc(qc_parts)
    qc_path = qc_dir / "temperature_adjustment_site_year_qc.csv"
    qc.to_csv(qc_path, index=False)
    site_summary = build_site_summary(qc)
    site_summary.to_csv(supplementary_dir / "temperature_adjustment_site_summary.csv", index=False)
    sensitivity = build_sensitivity_summary(qc)
    sensitivity.to_csv(
        supplementary_dir / "temperature_adjustment_sensitivity_by_abs_dz_band.csv", index=False
    )
    build_stage_sensitivity_summary(qc, args.cohort).to_csv(
        supplementary_dir / "temperature_adjustment_sensitivity_by_stage_country.csv", index=False
    )
    reference_table().to_csv(
        supplementary_dir / "temperature_adjustment_lapse_rate_references.csv", index=False
    )

    eligible = qc["temperature_elevation_adjustment_eligible"]
    summary = {
        "input_dir": str(args.input_dir.relative_to(REPO_ROOT)),
        "prior_august_dir": str(args.prior_august_dir.relative_to(REPO_ROOT)),
        "cohort": str(args.cohort.relative_to(REPO_ROOT)),
        "topography": str(args.topography.relative_to(REPO_ROOT)),
        "output_dir": str(args.output_dir.relative_to(REPO_ROOT)),
        "primary_lapse_rate_c_per_km": 6.5,
        "sensitivity_lapse_rates_c_per_km": [4.5, 6.0],
        "n_output_files": len(output_files),
        "n_daily_rows": int(total_rows),
        "n_site_years": int(len(qc)),
        "n_sites": int(qc["site_uid"].nunique()),
        "n_eligible_site_years": int(eligible.sum()),
        "n_ineligible_site_years": int((~eligible).sum()),
        "n_coordinate_instability_site_years": int(qc["has_coordinate_instability"].sum()),
        "n_missing_elevation_site_years": int(qc["has_missing_elevation"].sum()),
        "n_abs_dz_gt_300m_site_years": int(qc["abs_dz_gt_300m"].sum()),
        "n_abs_dz_gt_500m_site_years": int(qc["abs_dz_gt_500m"].sum()),
        "n_adjusted_temperature_order_bad": int(qc["n_adjusted_temperature_order_bad"].sum()),
        "output_files": output_files,
    }
    (qc_dir / "temperature_adjustment_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_readme(args.output_dir / "README.md")
    print(json.dumps({key: value for key, value in summary.items() if key != "output_files"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
