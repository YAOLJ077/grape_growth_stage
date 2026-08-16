#!/usr/bin/env python
"""Build a site-to-ERA5-Land 0.1-degree grid topography crosswalk.

Official ECMWF geopotential supplies the model-grid elevation used for lapse-
rate corrections. Copernicus GLO-30 pixels inside each grid cell independently
describe sub-grid terrain heterogeneity; they are not model-grid orography.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITES = REPO_ROOT / "data" / "phenology" / "derived" / "descriptive_phenology" / "site_topography.csv"
DEFAULT_MANIFEST = REPO_ROOT / "data" / "topography" / "metadata" / "copernicus_dem_glo30_country_tiles.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "topography" / "processed" / "site_era5_land_grid_crosswalk.csv"
DEFAULT_GRID_OUTPUT = REPO_ROOT / "data" / "topography" / "processed" / "era5_land_grid_dem_summary.csv"
DEFAULT_COUNTRY_SUMMARY = REPO_ROOT / "data" / "topography" / "processed" / "site_era5_land_grid_country_summary.csv"
DEFAULT_ALTITUDE_SUMMARY = REPO_ROOT / "data" / "topography" / "processed" / "site_era5_land_grid_altitude_band_summary.csv"
DEFAULT_WEATHER_QC = REPO_ROOT / "data" / "weather" / "processed" / "qc" / "weather_site_year_qc.csv"
DEFAULT_GEOPOTENTIAL = REPO_ROOT / "data" / "topography" / "raw" / "era5_land_invariant" / "geopotential_0p1deg.nc"
DEFAULT_LSM = REPO_ROOT / "data" / "topography" / "raw" / "era5_land_invariant" / "land_sea_mask_0p1deg.nc"
STANDARD_GRAVITY_M_S2 = 9.80665


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", type=Path, default=DEFAULT_SITES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--grid-output", type=Path, default=DEFAULT_GRID_OUTPUT)
    parser.add_argument("--country-summary", type=Path, default=DEFAULT_COUNTRY_SUMMARY)
    parser.add_argument("--altitude-summary", type=Path, default=DEFAULT_ALTITUDE_SUMMARY)
    parser.add_argument("--weather-qc", type=Path, default=DEFAULT_WEATHER_QC)
    parser.add_argument("--geopotential", type=Path, default=DEFAULT_GEOPOTENTIAL)
    parser.add_argument("--land-sea-mask", type=Path, default=DEFAULT_LSM)
    parser.add_argument("--grid-size-deg", type=float, default=0.1)
    return parser.parse_args()


def nearest_grid_center(value: float, resolution: float = 0.1) -> float:
    """Return the nearest regular-grid coordinate with lower-cell tie breaking.

    Exact half-cell site coordinates are assigned to the lower coordinate,
    matching the boundary behavior observed in the existing GEE point exports.
    """
    scaled = value / resolution
    rounded = math.floor(scaled + 0.5 - 1e-9)
    return round(rounded * resolution, 10)


def grid_id(latitude: float, longitude: float, resolution: float = 0.1) -> str:
    decimals = max(1, int(round(-math.log10(resolution))))
    return f"ERA5L_{resolution:g}_lat{latitude:+.{decimals}f}_lon{longitude:+.{decimals}f}"


def spatial_block_id(latitude: float, longitude: float, size_deg: float) -> str:
    lat0 = math.floor(latitude / size_deg) * size_deg
    lon0 = math.floor(longitude / size_deg) * size_deg
    return f"block_{size_deg:g}_lat{lat0:+.1f}_lon{lon0:+.1f}"


def manifest_tile_lookup(path: Path) -> dict[tuple[int, int], Path]:
    manifest = pd.read_csv(path)
    lookup: dict[tuple[int, int], Path] = {}
    for row in manifest.itertuples(index=False):
        tile_path = Path(str(row.local_path).replace("\\", "/"))
        if not tile_path.is_absolute():
            tile_path = REPO_ROOT / tile_path
        if tile_path.exists():
            lookup.setdefault((int(row.tile_lat), int(row.tile_lon)), tile_path)
    return lookup


def tile_keys_for_bounds(left: float, bottom: float, right: float, top: float) -> list[tuple[int, int]]:
    epsilon = 1e-10
    latitudes = range(math.floor(bottom), math.floor(top - epsilon) + 1)
    longitudes = range(math.floor(left), math.floor(right - epsilon) + 1)
    return [(lat, lon) for lat in latitudes for lon in longitudes]


def summarize_grid_dem(
    latitude: float,
    longitude: float,
    resolution: float,
    tile_lookup: dict[tuple[int, int], Path],
) -> dict[str, float | int | str]:
    import rasterio
    from rasterio.windows import from_bounds

    half = resolution / 2.0
    left, right = longitude - half, longitude + half
    bottom, top = latitude - half, latitude + half
    values: list[np.ndarray] = []
    used_tiles: list[str] = []

    for key in tile_keys_for_bounds(left, bottom, right, top):
        path = tile_lookup.get(key)
        if path is None:
            continue
        with rasterio.open(path) as src:
            clipped_left = max(left, src.bounds.left)
            clipped_right = min(right, src.bounds.right)
            clipped_bottom = max(bottom, src.bounds.bottom)
            clipped_top = min(top, src.bounds.top)
            if clipped_left >= clipped_right or clipped_bottom >= clipped_top:
                continue
            window = from_bounds(clipped_left, clipped_bottom, clipped_right, clipped_top, src.transform)
            window = window.round_offsets().round_lengths()
            array = src.read(1, window=window, boundless=False).astype("float64")
            if src.nodata is not None:
                array[array == src.nodata] = np.nan
            array[(array < -500) | (array > 9000)] = np.nan
            finite = array[np.isfinite(array)]
            if finite.size:
                values.append(finite)
                used_tiles.append(path.name)

    if not values:
        return {
            "glo30_grid_mean_m": np.nan,
            "glo30_grid_median_m": np.nan,
            "glo30_grid_std_m": np.nan,
            "glo30_grid_min_m": np.nan,
            "glo30_grid_max_m": np.nan,
            "glo30_grid_range_m": np.nan,
            "glo30_grid_n_pixels": 0,
            "glo30_grid_tiles": "",
            "glo30_grid_status": "no_dem_pixels",
        }
    merged = np.concatenate(values)
    return {
        "glo30_grid_mean_m": float(np.mean(merged)),
        "glo30_grid_median_m": float(np.median(merged)),
        "glo30_grid_std_m": float(np.std(merged)),
        "glo30_grid_min_m": float(np.min(merged)),
        "glo30_grid_max_m": float(np.max(merged)),
        "glo30_grid_range_m": float(np.max(merged) - np.min(merged)),
        "glo30_grid_n_pixels": int(merged.size),
        "glo30_grid_tiles": ";".join(sorted(set(used_tiles))),
        "glo30_grid_status": "dem_aggregated",
    }


def attach_era5_invariants(grids: pd.DataFrame, geopotential: Path, land_sea_mask: Path) -> pd.DataFrame:
    """Sample official ERA5-Land invariant fields at already assigned centers."""
    import h5py

    result = grids.copy()
    with h5py.File(geopotential, "r") as geo, h5py.File(land_sea_mask, "r") as lsm:
        latitudes = geo["latitude"][:]
        longitudes = geo["longitude"][:]
        z_values: list[float] = []
        lsm_values: list[float] = []
        for row in result.itertuples(index=False):
            lat_index = int(np.abs(latitudes - row.era5_grid_lat).argmin())
            longitude_360 = row.era5_grid_lon % 360.0
            lon_index = int(np.abs(longitudes - longitude_360).argmin())
            z_values.append(float(geo["z"][0, lat_index, lon_index]))
            lsm_values.append(float(lsm["lsm"][0, lat_index, lon_index]))
    result["era5_grid_geopotential_m2_s2"] = z_values
    result["era5_grid_elevation_m"] = result["era5_grid_geopotential_m2_s2"] / STANDARD_GRAVITY_M_S2
    result["era5_grid_land_fraction"] = lsm_values
    result["era5_grid_is_coastal"] = result["era5_grid_land_fraction"].between(0.0, 1.0, inclusive="neither")
    result["era5_invariant_source"] = "ECMWF_ERA5-Land_0.1deg_invariant"
    return result


def build_crosswalk(
    sites: pd.DataFrame,
    manifest: Path,
    resolution: float,
    geopotential: Path = DEFAULT_GEOPOTENTIAL,
    land_sea_mask: Path = DEFAULT_LSM,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = sites.copy()
    if "site_uid" not in work:
        work["site_uid"] = work["country_name"].astype(str) + "|" + work["source_system"].astype(str) + "|" + work["site_id"].astype(str)
    work["era5_grid_lat"] = work["latitude"].map(lambda value: nearest_grid_center(float(value), resolution))
    work["era5_grid_lon"] = work["longitude"].map(lambda value: nearest_grid_center(float(value), resolution))
    work["era5_grid_id"] = [grid_id(lat, lon, resolution) for lat, lon in zip(work.era5_grid_lat, work.era5_grid_lon)]
    work["era5_grid_assignment_method"] = f"nearest_official_ERA5-Land_{resolution:g}_degree_center"
    scaled_lat = work["latitude"].astype(float) / resolution
    scaled_lon = work["longitude"].astype(float) / resolution
    work["era5_grid_boundary_ambiguity_flag"] = (
        np.isclose(np.abs(scaled_lat - np.floor(scaled_lat)), 0.5, atol=1e-8)
        | np.isclose(np.abs(scaled_lon - np.floor(scaled_lon)), 0.5, atol=1e-8)
    )
    work["spatial_block_1deg_id"] = [spatial_block_id(lat, lon, 1.0) for lat, lon in zip(work.latitude, work.longitude)]
    work["spatial_block_2deg_id"] = [spatial_block_id(lat, lon, 2.0) for lat, lon in zip(work.latitude, work.longitude)]

    grids = work[["era5_grid_id", "era5_grid_lat", "era5_grid_lon"]].drop_duplicates().sort_values("era5_grid_id")
    lookup = manifest_tile_lookup(manifest)
    summaries = []
    total = len(grids)
    for number, row in enumerate(grids.itertuples(index=False), start=1):
        summary = summarize_grid_dem(row.era5_grid_lat, row.era5_grid_lon, resolution, lookup)
        summaries.append({"era5_grid_id": row.era5_grid_id, "era5_grid_lat": row.era5_grid_lat, "era5_grid_lon": row.era5_grid_lon, **summary})
        if number % 250 == 0 or number == total:
            print(f"DEM grid aggregation: {number:,}/{total:,}")
    grid_summary = attach_era5_invariants(pd.DataFrame(summaries), geopotential, land_sea_mask)
    counts = work.groupby("era5_grid_id").size().rename("n_sites_in_era5_grid")
    grid_summary = grid_summary.merge(counts, on="era5_grid_id", how="left", validate="one_to_one")
    grid_summary["glo30_grid_topographic_cv"] = grid_summary["glo30_grid_std_m"] / grid_summary["glo30_grid_mean_m"].abs().clip(lower=1.0)

    crosswalk = work.merge(grid_summary, on=["era5_grid_id", "era5_grid_lat", "era5_grid_lon"], how="left", validate="many_to_one")
    crosswalk["site_minus_grid_elevation_m"] = crosswalk["dem_elevation_m"] - crosswalk["era5_grid_elevation_m"]
    crosswalk["abs_site_grid_elevation_difference_m"] = crosswalk["site_minus_grid_elevation_m"].abs()
    for threshold in (100, 200, 300):
        crosswalk[f"site_grid_difference_gt_{threshold}m"] = crosswalk["abs_site_grid_elevation_difference_m"].gt(threshold)
    columns = [
        "site_uid", "country_name", "source_system", "site_id", "site_name", "latitude", "longitude",
        "era5_grid_id", "era5_grid_lat", "era5_grid_lon", "n_sites_in_era5_grid",
        "era5_grid_assignment_method", "era5_grid_boundary_ambiguity_flag",
        "spatial_block_1deg_id", "spatial_block_2deg_id", "dem_elevation_m", "dem_local_median_m",
        "dem_local_std_m", "dem_local_range_m", "slope_deg", "aspect_deg", "northness", "eastness",
        "era5_grid_geopotential_m2_s2", "era5_grid_elevation_m", "era5_grid_land_fraction",
        "era5_grid_is_coastal", "era5_invariant_source",
        "glo30_grid_mean_m", "glo30_grid_median_m", "glo30_grid_std_m", "glo30_grid_min_m",
        "glo30_grid_max_m", "glo30_grid_range_m", "glo30_grid_topographic_cv", "glo30_grid_n_pixels",
        "glo30_grid_tiles", "glo30_grid_status", "site_minus_grid_elevation_m",
        "abs_site_grid_elevation_difference_m", "site_grid_difference_gt_100m", "site_grid_difference_gt_200m",
        "site_grid_difference_gt_300m", "source_altitude_m", "elevation_difference_m",
        "source_dem_discrepancy_flag", "coordinate_span_m", "coordinate_instability_flag",
    ]
    return crosswalk[[column for column in columns if column in crosswalk]], grid_summary


def attach_weather_qc(crosswalk: pd.DataFrame, path: Path) -> pd.DataFrame:
    if not path.exists():
        return crosswalk
    qc = pd.read_csv(path, dtype={"site_id": "string"}, low_memory=False)
    qc["site_uid"] = qc["country"].astype(str) + "|" + qc["source"].astype(str) + "|" + qc["site_id"].astype(str)
    site_qc = (
        qc.groupby("site_uid", dropna=False)
        .agg(
            n_weather_site_years=("weather_id", "size"),
            n_incomplete_weather_site_years=("weather_period_complete", lambda values: (~values.astype(bool)).sum()),
            n_buffer_fill_site_years=("has_buffer_fill", "sum"),
            all_weather_complete_for_observed_events=("weather_complete_for_observed_events", "all"),
            all_daily_physical_qc_pass=("daily_physical_qc_pass", "all"),
        )
        .reset_index()
    )
    result = crosswalk.merge(site_qc, on="site_uid", how="left", validate="one_to_one")
    result["coastal_or_island_buffer_fill_flag"] = result["n_buffer_fill_site_years"].fillna(0).gt(0)
    return result


def quality_summaries(crosswalk: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    country = (
        crosswalk.groupby("country_name", dropna=False)
        .agg(
            n_sites=("site_uid", "size"), n_era5_grids=("era5_grid_id", "nunique"),
            median_site_dem_m=("dem_elevation_m", "median"), median_era5_grid_elevation_m=("era5_grid_elevation_m", "median"),
            median_abs_site_grid_difference_m=("abs_site_grid_elevation_difference_m", "median"),
            n_site_grid_difference_gt_100m=("site_grid_difference_gt_100m", "sum"),
            n_site_grid_difference_gt_200m=("site_grid_difference_gt_200m", "sum"),
            n_site_grid_difference_gt_300m=("site_grid_difference_gt_300m", "sum"),
            median_glo30_grid_std_m=("glo30_grid_std_m", "median"),
            n_coordinate_instability=("coordinate_instability_flag", "sum"),
            n_source_dem_discrepancy=("source_dem_discrepancy_flag", "sum"),
            n_buffer_fill_sites=("coastal_or_island_buffer_fill_flag", "sum"),
        )
        .reset_index()
    )
    work = crosswalk.copy()
    work["site_elevation_band"] = pd.cut(
        work["dem_elevation_m"], [-np.inf, 100, 250, 500, 1000, np.inf],
        labels=["<100 m", "100-250 m", "250-500 m", "500-1000 m", ">1000 m"],
    )
    altitude = (
        work.groupby(["country_name", "site_elevation_band"], observed=True, dropna=False)
        .agg(
            n_sites=("site_uid", "size"), n_era5_grids=("era5_grid_id", "nunique"),
            median_site_dem_m=("dem_elevation_m", "median"),
            median_abs_site_grid_difference_m=("abs_site_grid_elevation_difference_m", "median"),
            n_site_grid_difference_gt_100m=("site_grid_difference_gt_100m", "sum"),
            median_glo30_grid_std_m=("glo30_grid_std_m", "median"),
        )
        .reset_index()
    )
    return country, altitude


def main() -> int:
    args = parse_args()
    sites = pd.read_csv(args.sites, dtype={"site_id": "string"}, low_memory=False)
    crosswalk, grids = build_crosswalk(
        sites, args.manifest, args.grid_size_deg, args.geopotential, args.land_sea_mask
    )
    crosswalk = attach_weather_qc(crosswalk, args.weather_qc)
    country_summary, altitude_summary = quality_summaries(crosswalk)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.grid_output.parent.mkdir(parents=True, exist_ok=True)
    args.country_summary.parent.mkdir(parents=True, exist_ok=True)
    args.altitude_summary.parent.mkdir(parents=True, exist_ok=True)
    crosswalk.to_csv(args.output, index=False)
    grids.to_csv(args.grid_output, index=False)
    country_summary.to_csv(args.country_summary, index=False)
    altitude_summary.to_csv(args.altitude_summary, index=False)
    print(f"Sites: {len(crosswalk):,}; ERA5-Land grids: {len(grids):,}")
    print(f"Official grid elevation available: {grids['era5_grid_elevation_m'].notna().sum():,}/{len(grids):,}")
    print(f"GLO-30 sub-grid summary available: {grids['glo30_grid_mean_m'].notna().sum():,}/{len(grids):,}")
    for threshold in (100, 200, 300):
        count = int(crosswalk[f'site_grid_difference_gt_{threshold}m'].sum())
        print(f"|site-grid elevation difference| > {threshold} m: {count:,}")
    print(f"Crosswalk: {args.output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
