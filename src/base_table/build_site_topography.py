#!/usr/bin/env python
"""Sample local Copernicus GLO-30 tiles for all 1951+ phenology sites."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "data" / "phenology" / "derived" / "base_table" / "six_country_base_table_1951.csv"
DEFAULT_MANIFEST = REPO_ROOT / "data" / "topography" / "metadata" / "copernicus_dem_glo30_country_tiles.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "phenology" / "derived" / "descriptive_phenology" / "site_topography.csv"
DEFAULT_SUMMARY = REPO_ROOT / "data" / "phenology" / "derived" / "descriptive_phenology" / "site_topography_country_summary.csv"
DEFAULT_DISCREPANCIES = REPO_ROOT / "data" / "phenology" / "derived" / "descriptive_phenology" / "site_topography_elevation_discrepancies.csv"

COUNTRY_KEYS = {
    "France": "france",
    "Germany": "germany",
    "Austria": "austria",
    "Switzerland": "switzerland",
    "Slovakia": "slovakia",
    "Spain": "spain",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--discrepancies", type=Path, default=DEFAULT_DISCREPANCIES)
    parser.add_argument("--start-year", type=int, default=1951)
    return parser.parse_args()


def resolve_manifest_path(value: object, repo_root: Path = REPO_ROOT) -> Path:
    path = Path(str(value).replace("\\", "/"))
    return path if path.is_absolute() else repo_root / path


def summarize_sites(df: pd.DataFrame, start_year: int) -> pd.DataFrame:
    work = df.copy()
    for column in ["year", "latitude", "longitude", "altitude"]:
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work[
        work["year"].ge(start_year)
        & work["country_name"].isin(COUNTRY_KEYS)
        & work["site_id"].notna()
        & work["latitude"].notna()
        & work["longitude"].notna()
    ].copy()
    aggregation: dict[str, tuple[str, str]] = {
        "site_name": ("site_name", "first"),
        "latitude": ("latitude", "median"),
        "longitude": ("longitude", "median"),
        "source_altitude_m": ("altitude", "median"),
        "n_observations": ("site_id", "size"),
        "first_year": ("year", "min"),
        "last_year": ("year", "max"),
        "latitude_min": ("latitude", "min"),
        "latitude_max": ("latitude", "max"),
        "longitude_min": ("longitude", "min"),
        "longitude_max": ("longitude", "max"),
    }
    if "altitude_source" in work.columns:
        aggregation["altitude_source"] = ("altitude_source", "first")
    sites = (
        work.groupby(["country_name", "source_system", "site_id"], dropna=False)
        .agg(**aggregation)
        .reset_index()
    )
    if "altitude_source" not in sites.columns:
        sites["altitude_source"] = pd.NA
    sites["site_uid"] = (
        sites["country_name"].astype(str)
        + "|"
        + sites["source_system"].astype(str)
        + "|"
        + sites["site_id"].astype(str)
    )
    mean_latitude = (sites["latitude_min"] + sites["latitude_max"]) / 2.0
    latitude_span_m = (sites["latitude_max"] - sites["latitude_min"]).abs() * 111_320.0
    longitude_span_m = (
        (sites["longitude_max"] - sites["longitude_min"]).abs()
        * 111_320.0
        * np.cos(np.deg2rad(mean_latitude))
    )
    sites["coordinate_span_m"] = np.hypot(latitude_span_m, longitude_span_m)
    sites["coordinate_instability_flag"] = sites["coordinate_span_m"].gt(100.0)
    sites["tile_lat"] = np.floor(sites["latitude"]).astype(int)
    sites["tile_lon"] = np.floor(sites["longitude"]).astype(int)
    return sites


def load_manifest(path: Path) -> dict[tuple[str, int, int], tuple[Path, str]]:
    manifest = pd.read_csv(path)
    lookup: dict[tuple[str, int, int], tuple[Path, str]] = {}
    for row in manifest.itertuples(index=False):
        local_path = resolve_manifest_path(row.local_path)
        if local_path.exists():
            tile_info = (
                local_path,
                str(row.tile_name),
            )
            lookup[(str(row.country).lower(), int(row.tile_lat), int(row.tile_lon))] = tile_info
            # Copernicus tiles are global and can be reused for a site immediately
            # across a national border even if the manifest lists the tile under
            # the neighbouring country.
            lookup.setdefault(("*", int(row.tile_lat), int(row.tile_lon)), tile_info)
    return lookup


def terrain_metrics(array: np.ndarray, transform, latitude: float) -> tuple[float, float, float]:
    values = np.asarray(array, dtype="float64")
    if values.shape != (3, 3) or not np.isfinite(values[1, 1]):
        return np.nan, np.nan, np.nan
    center = float(values[1, 1])
    if not np.isfinite(values).all():
        return center, np.nan, np.nan
    metres_per_degree = 111_320.0
    x_size = abs(float(transform.a)) * metres_per_degree * max(math.cos(math.radians(latitude)), 0.2)
    y_size = abs(float(transform.e)) * metres_per_degree
    dzdy, dzdx = np.gradient(values, y_size, x_size)
    gx = float(dzdx[1, 1])
    gy = float(dzdy[1, 1])
    slope = math.degrees(math.atan(math.hypot(gx, gy)))
    aspect = (math.degrees(math.atan2(-gx, gy)) + 360.0) % 360.0
    return center, slope, aspect


def sample_sites(sites: pd.DataFrame, manifest_path: Path) -> pd.DataFrame:
    import rasterio
    from rasterio.windows import Window

    lookup = load_manifest(manifest_path)
    result = sites.copy()
    result["dem_elevation_m"] = np.nan
    result["slope_deg"] = np.nan
    result["aspect_deg"] = np.nan
    result["dem_local_median_m"] = np.nan
    result["dem_local_std_m"] = np.nan
    result["dem_local_range_m"] = np.nan
    result["dem_local_valid_pixels"] = 0
    result["dem_tile_name"] = ""
    result["dem_sample_status"] = "tile_not_found"

    grouped = result.groupby(["country_name", "tile_lat", "tile_lon"], sort=False)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        for (country_name, tile_lat, tile_lon), group in grouped:
            key = (COUNTRY_KEYS[str(country_name)], int(tile_lat), int(tile_lon))
            tile_info = lookup.get(key) or lookup.get(("*", int(tile_lat), int(tile_lon)))
            if tile_info is None:
                continue
            tile_path, tile_name = tile_info
            with rasterio.open(tile_path) as src:
                for index, row in group.iterrows():
                    raster_row, raster_col = src.index(float(row["longitude"]), float(row["latitude"]))
                    # Coordinates rounded to an exact integer degree can fall on
                    # the outer pixel boundary; use the nearest pixel in the tile.
                    raster_row = min(max(raster_row, 0), src.height - 1)
                    raster_col = min(max(raster_col, 0), src.width - 1)
                    window = Window(raster_col - 1, raster_row - 1, 3, 3)
                    array = src.read(1, window=window, boundless=True, fill_value=np.nan).astype("float64")
                    if src.nodata is not None:
                        array[array == src.nodata] = np.nan
                    array[(array < -500) | (array > 9000)] = np.nan
                    elevation, slope, aspect = terrain_metrics(array, src.window_transform(window), float(row["latitude"]))
                    local_window = Window(raster_col - 5, raster_row - 5, 11, 11)
                    local_array = src.read(
                        1,
                        window=local_window,
                        boundless=True,
                        fill_value=np.nan,
                    ).astype("float64")
                    if src.nodata is not None:
                        local_array[local_array == src.nodata] = np.nan
                    local_array[(local_array < -500) | (local_array > 9000)] = np.nan
                    local_values = local_array[np.isfinite(local_array)]
                    result.loc[index, "dem_tile_name"] = tile_name
                    if np.isfinite(elevation):
                        result.loc[index, ["dem_elevation_m", "slope_deg", "aspect_deg"]] = [
                            elevation,
                            slope,
                            aspect,
                        ]
                        if local_values.size:
                            result.loc[
                                index,
                                [
                                    "dem_local_median_m",
                                    "dem_local_std_m",
                                    "dem_local_range_m",
                                    "dem_local_valid_pixels",
                                ],
                            ] = [
                                float(np.median(local_values)),
                                float(np.std(local_values)),
                                float(np.max(local_values) - np.min(local_values)),
                                int(local_values.size),
                            ]
                        result.loc[index, "dem_sample_status"] = "sampled"
                    else:
                        result.loc[index, "dem_sample_status"] = "invalid_dem_value"

    result["elevation_difference_m"] = result["source_altitude_m"] - result["dem_elevation_m"]
    result["source_dem_discrepancy_flag"] = result["elevation_difference_m"].abs().gt(100.0)
    aspect_radians = np.deg2rad(result["aspect_deg"])
    result["northness"] = np.cos(aspect_radians)
    result["eastness"] = np.sin(aspect_radians)
    result["terrain_class"] = pd.cut(
        result["dem_elevation_m"],
        bins=[-np.inf, 100, 250, 500, 1000, np.inf],
        labels=["<100 m", "100-250 m", "250-500 m", "500-1000 m", ">1000 m"],
    )
    return result.drop(columns=["tile_lat", "tile_lon"])


def country_summary(topography: pd.DataFrame) -> pd.DataFrame:
    work = topography.assign(
        dem_available=topography["dem_elevation_m"].notna(),
        source_available=topography["source_altitude_m"].notna(),
        absolute_difference=topography["elevation_difference_m"].abs(),
    )
    return (
        work.groupby("country_name", dropna=False)
        .agg(
            n_sites=("site_id", "size"),
            n_dem_available=("dem_available", "sum"),
            n_source_altitude_available=("source_available", "sum"),
            median_dem_elevation_m=("dem_elevation_m", "median"),
            min_dem_elevation_m=("dem_elevation_m", "min"),
            max_dem_elevation_m=("dem_elevation_m", "max"),
            median_abs_source_dem_difference_m=("absolute_difference", "median"),
            n_abs_source_dem_difference_gt_100m=("absolute_difference", lambda value: value.gt(100).sum()),
        )
        .reset_index()
    )


def main() -> int:
    args = parse_args()
    header = pd.read_csv(args.input, nrows=0)
    columns = [
        "country_name",
        "source_system",
        "site_id",
        "site_name",
        "latitude",
        "longitude",
        "altitude",
        "year",
    ]
    if "altitude_source" in header.columns:
        columns.append("altitude_source")
    observations = pd.read_csv(args.input, usecols=columns, dtype={"site_id": "string"}, low_memory=False)
    sites = summarize_sites(observations, args.start_year)
    topography = sample_sites(sites, args.manifest)
    summary = country_summary(topography)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.discrepancies.parent.mkdir(parents=True, exist_ok=True)
    topography.to_csv(args.output, index=False)
    summary.to_csv(args.summary, index=False)
    discrepancies = topography[topography["elevation_difference_m"].abs().gt(100)].copy()
    discrepancies = discrepancies.sort_values("elevation_difference_m", key=lambda value: value.abs(), ascending=False)
    discrepancies.to_csv(args.discrepancies, index=False)
    print(f"Sites: {len(topography):,}")
    print(f"DEM elevations available: {topography['dem_elevation_m'].notna().sum():,}")
    print(summary.to_string(index=False))
    print(f"Output: {args.output}")
    print(f"Elevation discrepancies (>100 m): {len(discrepancies):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
