#!/usr/bin/env python
"""Build the 1951+ France–Germany exact-BBCH four-stage modeling cohort."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVENTS = REPO_ROOT / "data" / "phenology" / "processed" / "phenology_site_year_stage_1951.csv"
DEFAULT_TOPOGRAPHY = REPO_ROOT / "data" / "topography" / "processed" / "site_era5_land_grid_crosswalk.csv"
DEFAULT_WEATHER_QC = REPO_ROOT / "data" / "weather" / "processed" / "qc" / "weather_site_year_qc.csv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "phenology" / "derived" / "modeling" / "france_germany_four_stage"
COUNTRIES = ("France", "Germany")
TARGETS = {
    7: ("budburst", 1),
    65: ("flowering", 2),
    81: ("veraison", 3),
    89: ("maturity_or_harvest", 4),
}
STAGE_DOY_COLUMNS = {
    "budburst": "budburst_doy_bbch07",
    "flowering": "flowering_doy_bbch65",
    "veraison": "veraison_doy_bbch81",
    "maturity_or_harvest": "maturity_or_harvest_doy_bbch89",
}
ELEVATION_BAND_EDGES = (float("-inf"), 100, 250, 500, 1000, float("inf"))
ELEVATION_BAND_LABELS = ("<100 m", "100–249 m", "250–499 m", "500–999 m", "≥1000 m")
ELEVATION_BAND_DEFINITIONS = {
    "<100 m": "lowland or coastal plain",
    "100–249 m": "low hills or lower slopes",
    "250–499 m": "uplands or middle hills",
    "500–999 m": "mountain belt",
    "≥1000 m": "high mountain belt",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--topography", type=Path, default=DEFAULT_TOPOGRAPHY)
    parser.add_argument("--weather-qc", type=Path, default=DEFAULT_WEATHER_QC)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-year", type=int, default=1951)
    return parser.parse_args()


def analysis_role(model_tier: str) -> str:
    return {
        "core": "core_calibration_or_validation",
        "extended": "extended_validation",
        "sensitivity": "sensitivity_only",
    }.get(str(model_tier), "unclassified")


def build_long(
    events: pd.DataFrame,
    topography: pd.DataFrame,
    start_year: int = 1951,
    excluded_weather_ids: set[str] | None = None,
) -> pd.DataFrame:
    work = events.copy()
    work["year"] = pd.to_numeric(work["year"], errors="coerce")
    work["bbch"] = pd.to_numeric(work["bbch"], errors="coerce")
    work = work[
        work["country"].isin(COUNTRIES)
        & work["year"].ge(start_year)
        & work["bbch"].isin(TARGETS)
    ].copy()
    work["bbch"] = work["bbch"].astype(int)
    work["site_id"] = work["site_id"].astype("string")
    work["site_uid"] = work["country"].astype(str) + "|" + work["source"].astype(str) + "|" + work["site_id"].astype(str)
    work["weather_id"] = work["site_uid"] + "|" + work["year"].astype(int).astype(str)
    if excluded_weather_ids:
        work = work.loc[~work["weather_id"].isin(excluded_weather_ids)].copy()
    work["target_stage"] = work["bbch"].map(lambda value: TARGETS[value][0])
    work["target_stage_order"] = work["bbch"].map(lambda value: TARGETS[value][1])
    work["analysis_role"] = work["model_tier"].map(analysis_role)

    topo = topography.copy()
    topo["site_id"] = topo["site_id"].astype("string")
    duplicate = topo["site_uid"].duplicated(keep=False)
    if duplicate.any():
        raise ValueError(f"Topography crosswalk has {int(duplicate.sum())} duplicate site_uid rows")
    topology_columns = [
        "site_uid", "dem_elevation_m", "dem_local_median_m", "dem_local_std_m", "dem_local_range_m",
        "slope_deg", "aspect_deg", "northness", "eastness", "era5_grid_id", "era5_grid_lat",
        "era5_grid_lon", "era5_grid_elevation_m", "era5_grid_land_fraction", "glo30_grid_std_m",
        "glo30_grid_range_m", "site_minus_grid_elevation_m", "abs_site_grid_elevation_difference_m",
        "site_grid_difference_gt_100m", "site_grid_difference_gt_200m", "site_grid_difference_gt_300m",
        "spatial_block_1deg_id", "spatial_block_2deg_id", "source_altitude_m",
        "source_dem_discrepancy_flag", "coordinate_instability_flag", "coastal_or_island_buffer_fill_flag",
        "all_weather_complete_for_observed_events", "all_daily_physical_qc_pass",
    ]
    topology_columns = [column for column in topology_columns if column in topo.columns]
    work = work.merge(topo[topology_columns], on="site_uid", how="left", validate="many_to_one")
    if work["dem_elevation_m"].isna().any():
        missing = int(work["dem_elevation_m"].isna().sum())
        raise ValueError(f"Missing site DEM for {missing} target-stage records")

    keys = ["site_uid", "year"]
    stage_sets = work.groupby(keys)["target_stage"].transform(lambda values: ";".join(sorted(set(values))))
    work["target_stage_set_site_year"] = stage_sets
    work["n_target_stages_site_year"] = work.groupby(keys)["target_stage"].transform("nunique")
    work["four_stage_site_year_complete"] = work["n_target_stages_site_year"].eq(4)
    work["n_target_stage_records_site"] = work.groupby("site_uid")["record_id"].transform("size")
    work["n_target_stages_site"] = work.groupby("site_uid")["target_stage"].transform("nunique")
    work["dataset_scope"] = "France_Germany_1951plus_exact_BBCH07_65_81_89"

    preferred = [
        "record_id", "weather_id", "site_uid", "country", "source", "site_id", "site_name", "lat", "lon",
        "year", "event_date", "event_doy", "bbch", "target_stage", "target_stage_order", "phenophase",
        "phenophase_order", "bbch_confidence", "aggregation_method", "n_obs", "doy_min", "doy_median",
        "doy_max", "doy_range", "date_min", "date_max", "n_years_site_bbch", "n_observations_site_bbch",
        "model_tier", "analysis_role", "target_stage_set_site_year", "n_target_stages_site_year",
        "four_stage_site_year_complete", "n_target_stage_records_site", "n_target_stages_site",
    ]
    remaining = [column for column in work.columns if column not in preferred]
    return work[preferred + remaining].sort_values(["country", "site_id", "year", "target_stage_order"]).reset_index(drop=True)


def build_wide(long: pd.DataFrame) -> pd.DataFrame:
    identifiers = ["site_uid", "country", "source", "site_id", "site_name", "lat", "lon", "year"]
    pivot = long.pivot(index=identifiers, columns="target_stage", values="event_doy").reset_index()
    pivot = pivot.rename(columns=STAGE_DOY_COLUMNS)
    for column in STAGE_DOY_COLUMNS.values():
        if column not in pivot:
            pivot[column] = pd.NA
    static_columns = [
        "site_uid", "dem_elevation_m", "dem_local_median_m", "dem_local_std_m", "dem_local_range_m",
        "slope_deg", "aspect_deg", "northness", "eastness", "era5_grid_id", "era5_grid_lat", "era5_grid_lon",
        "era5_grid_elevation_m", "site_minus_grid_elevation_m", "abs_site_grid_elevation_difference_m",
        "spatial_block_1deg_id", "spatial_block_2deg_id",
    ]
    static_columns = [column for column in static_columns if column in long.columns]
    static = long[static_columns].drop_duplicates("site_uid")
    pivot = pivot.merge(static, on="site_uid", how="left", validate="many_to_one")
    doy_columns = list(STAGE_DOY_COLUMNS.values())
    pivot["n_target_stages_observed"] = pivot[doy_columns].notna().sum(axis=1)
    pivot["four_stage_complete"] = pivot["n_target_stages_observed"].eq(4)
    pivot["budburst_to_flowering_days"] = pivot["flowering_doy_bbch65"] - pivot["budburst_doy_bbch07"]
    pivot["flowering_to_veraison_days"] = pivot["veraison_doy_bbch81"] - pivot["flowering_doy_bbch65"]
    pivot["veraison_to_maturity_harvest_days"] = pivot["maturity_or_harvest_doy_bbch89"] - pivot["veraison_doy_bbch81"]
    def chronology_audit(row: pd.Series) -> tuple[int, bool]:
        observed = row[doy_columns].dropna().to_numpy(dtype=float)
        nonpositive = int((observed[1:] <= observed[:-1]).sum()) if len(observed) > 1 else 0
        return nonpositive, nonpositive == 0

    chronology = pivot.apply(chronology_audit, axis=1, result_type="expand")
    pivot["n_nonpositive_observed_transitions"] = chronology[0].astype(int)
    pivot["chronology_valid"] = chronology[1].astype(bool)
    pivot["recommended_for_sequential_model"] = pivot["four_stage_complete"] & pivot["chronology_valid"]
    return pivot.sort_values(["country", "site_id", "year"]).reset_index(drop=True)


def build_site_inventory(long: pd.DataFrame) -> pd.DataFrame:
    static_columns = [
        "site_uid", "country", "source", "site_id", "site_name", "lat", "lon", "dem_elevation_m",
        "dem_local_std_m", "slope_deg", "aspect_deg", "northness", "eastness", "era5_grid_id",
        "era5_grid_elevation_m", "site_minus_grid_elevation_m", "spatial_block_1deg_id", "spatial_block_2deg_id",
    ]
    static_columns = [column for column in static_columns if column in long.columns]
    static = long[static_columns].drop_duplicates("site_uid").set_index("site_uid")
    grouped = long.groupby("site_uid")
    inventory = grouped.agg(
        n_event_records=("record_id", "size"), n_years=("year", "nunique"), first_year=("year", "min"),
        last_year=("year", "max"), n_target_stages=("target_stage", "nunique"),
        n_complete_four_stage_years=("four_stage_site_year_complete", "sum"),
    )
    inventory["n_complete_four_stage_years"] = (
        long.loc[long["four_stage_site_year_complete"]].groupby("site_uid")["year"].nunique()
    ).reindex(inventory.index, fill_value=0)
    stage_counts = long.pivot_table(index="site_uid", columns="target_stage", values="record_id", aggfunc="size", fill_value=0)
    stage_counts = stage_counts.rename(columns={stage: f"n_{stage}_records" for stage in STAGE_DOY_COLUMNS})
    inventory = static.join(inventory).join(stage_counts).reset_index()
    for stage in STAGE_DOY_COLUMNS:
        column = f"n_{stage}_records"
        if column not in inventory:
            inventory[column] = 0
    return inventory.sort_values(["country", "site_id"]).reset_index(drop=True)


def build_summary(long: pd.DataFrame) -> pd.DataFrame:
    return (
        long.groupby(["country", "target_stage", "bbch", "model_tier"], dropna=False)
        .agg(
            event_records=("record_id", "size"), source_observations=("n_obs", "sum"),
            sites=("site_uid", "nunique"), site_years=("weather_id", "nunique"),
            first_year=("year", "min"), last_year=("year", "max"),
        )
        .reset_index()
        .sort_values(["country", "bbch", "model_tier"])
    )


def build_elevation_band_summary(wide: pd.DataFrame) -> pd.DataFrame:
    """Summarize unique sites and site-years by fixed, interpretable DEM bands."""
    required = {"country", "site_uid", "year", "dem_elevation_m"}
    missing = required.difference(wide.columns)
    if missing:
        raise ValueError(f"Elevation-band summary is missing columns: {sorted(missing)}")
    if wide["dem_elevation_m"].isna().any():
        raise ValueError("Elevation-band summary cannot contain missing site DEM values")

    work = wide.copy()
    work["elevation_band"] = pd.cut(
        work["dem_elevation_m"],
        bins=ELEVATION_BAND_EDGES,
        labels=ELEVATION_BAND_LABELS,
        right=False,
        ordered=True,
    )
    country_totals = work.groupby("country").agg(
        total_sites=("site_uid", "nunique"),
        total_site_years=("year", "size"),
    )
    grouped = (
        work.groupby(["country", "elevation_band"], observed=False)
        .agg(
            n_sites=("site_uid", "nunique"),
            n_site_years=("year", "size"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            median_elevation_m=("dem_elevation_m", "median"),
            min_elevation_m=("dem_elevation_m", "min"),
            max_elevation_m=("dem_elevation_m", "max"),
        )
        .reset_index()
        .merge(country_totals, on="country", how="left", validate="many_to_one")
    )
    grouped["site_share_pct"] = grouped["n_sites"].div(grouped["total_sites"]).mul(100)
    grouped["site_year_share_pct"] = grouped["n_site_years"].div(grouped["total_site_years"]).mul(100)
    grouped["mean_site_years_per_site"] = (
        grouped["n_site_years"].div(grouped["n_sites"].where(grouped["n_sites"].gt(0))).astype(float)
    )
    grouped["geographic_climatic_interpretation"] = grouped["elevation_band"].map(
        ELEVATION_BAND_DEFINITIONS
    )
    grouped["band_order"] = grouped["elevation_band"].cat.codes.add(1)
    grouped["elevation_band"] = grouped["elevation_band"].astype("string")

    numeric_rounding = {
        "site_share_pct": 2,
        "site_year_share_pct": 2,
        "mean_site_years_per_site": 2,
        "median_elevation_m": 1,
        "min_elevation_m": 2,
        "max_elevation_m": 2,
    }
    grouped = grouped.round(numeric_rounding)
    grouped[["first_year", "last_year"]] = grouped[["first_year", "last_year"]].astype("Int64")
    columns = [
        "country", "band_order", "elevation_band", "geographic_climatic_interpretation",
        "n_sites", "site_share_pct", "n_site_years", "site_year_share_pct",
        "mean_site_years_per_site", "first_year", "last_year", "median_elevation_m",
        "min_elevation_m", "max_elevation_m", "total_sites", "total_site_years",
    ]
    return grouped[columns].sort_values(["country", "band_order"]).reset_index(drop=True)


def weather_ids_without_point_weather(weather_qc: pd.DataFrame) -> set[str]:
    """Return site-years whose weather is not a unique ERA5-Land point sample."""
    required = {"weather_id", "has_buffer_fill"}
    missing = required.difference(weather_qc.columns)
    if missing:
        raise ValueError(f"Weather QC is missing columns: {sorted(missing)}")
    has_buffer_fill = weather_qc["has_buffer_fill"].fillna(False).astype(bool)
    return set(weather_qc.loc[has_buffer_fill, "weather_id"].astype(str))


def write_readme(path: Path, start_year: int) -> None:
    text = f"""# France–Germany four-stage modeling cohort

Generated by `src/base_table/build_france_germany_four_stage_dataset.py`.

- Countries: France and Germany
- Study period: {start_year} onward
- Exact targets: BBCH 07 budburst, BBCH 65 flowering, BBCH 81 veraison, BBCH 89 maturity/harvest
- Weather requirement: a unique ERA5-Land point sample is available for the site-year
- `phenology_events_long.csv`: one row per site-year-target BBCH event, with DEM and ERA5-Land grid terrain fields
- `phenology_site_year_wide.csv`: one row per site-year, with four target DOY columns and phase intervals
- `site_inventory.csv`: one row per site for mapping, splitting and coverage audit
- `stage_country_summary.csv`: counts by country, target stage and model tier
- `elevation_band_country_summary.csv`: unique-site and site-year counts in fixed DEM bands; a site-year is counted once if at least one target stage is observed
- `chronology_anomalies.csv`: site-years containing non-increasing observed stage dates

`model_tier` and `analysis_role` are retained. Sensitivity records are not silently promoted to calibration data.
Maturity/harvest is an operational endpoint and should be interpreted separately from strictly physiological stages.
Elevation bands are descriptive terrain strata rather than universal bioclimatic zones: <100, 100–249,
250–499, 500–999 and ≥1000 m. Sparse mountain bands should not be treated as equally powered model strata.
"""
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    events = pd.read_csv(args.events, dtype={"site_id": "string"}, low_memory=False)
    topography = pd.read_csv(args.topography, dtype={"site_id": "string"}, low_memory=False)
    weather_qc = pd.read_csv(args.weather_qc, low_memory=False)
    excluded_weather_ids = weather_ids_without_point_weather(weather_qc)
    candidate = events.loc[
        events["country"].isin(COUNTRIES)
        & pd.to_numeric(events["year"], errors="coerce").ge(args.start_year)
        & pd.to_numeric(events["bbch"], errors="coerce").isin(TARGETS),
        ["country", "source", "site_id", "year"],
    ].copy()
    candidate["weather_id"] = (
        candidate["country"].astype(str) + "|" + candidate["source"].astype(str) + "|"
        + candidate["site_id"].astype(str) + "|" + candidate["year"].astype(int).astype(str)
    )
    excluded_weather_ids.intersection_update(candidate["weather_id"].astype(str))
    long = build_long(events, topography, args.start_year, excluded_weather_ids)
    wide = build_wide(long)
    inventory = build_site_inventory(long)
    summary = build_summary(long)
    elevation_summary = build_elevation_band_summary(wide)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    long.to_csv(args.output_dir / "phenology_events_long.csv", index=False)
    wide.to_csv(args.output_dir / "phenology_site_year_wide.csv", index=False)
    inventory.to_csv(args.output_dir / "site_inventory.csv", index=False)
    summary.to_csv(args.output_dir / "stage_country_summary.csv", index=False)
    elevation_summary.to_csv(args.output_dir / "elevation_band_country_summary.csv", index=False)
    wide.loc[~wide["chronology_valid"]].to_csv(args.output_dir / "chronology_anomalies.csv", index=False)
    write_readme(args.output_dir / "README.md", args.start_year)

    print("France–Germany four-stage cohort")
    print(f"Events: {len(long):,}; site-years: {len(wide):,}; sites: {len(inventory):,}")
    print(f"Complete four-stage site-years: {int(wide['four_stage_complete'].sum()):,}")
    print(f"Chronology anomalies: {int((~wide['chronology_valid']).sum()):,}")
    print(f"Excluded site-years without point weather: {len(excluded_weather_ids):,}")
    print("\nElevation-band site / site-year counts")
    print(elevation_summary[["country", "elevation_band", "n_sites", "n_site_years", "site_year_share_pct"]].to_string(index=False))
    print(summary.groupby(["country", "target_stage"])["event_records"].sum().to_string())
    print(f"Output: {args.output_dir.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
