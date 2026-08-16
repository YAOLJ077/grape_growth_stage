#!/usr/bin/env python
"""Overlay grape phenology sites on Copernicus GLO-30 topography."""

from __future__ import annotations

import argparse
import math
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


COUNTRY_TABLES = [
    Path("data/phenology/processed/france_grape_phenology_complete.csv"),
    Path("data/phenology/processed/germany_grape_phenology_complete.csv"),
]
EXTENT = [-6.5, 16.0, 41.0, 55.5]
COUNTRY_COLORS = {"France": "#2f6f9f", "Germany": "#d95f02"}
DEFAULT_START_YEAR = 1951
AXIS_LABEL_SIZE = 14
TICK_LABEL_SIZE = 12
SUBTITLE_SIZE = 15
LEGEND_SIZE = 12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", default=COUNTRY_TABLES)
    parser.add_argument("--fig-dir", type=Path, default=Path("fig/descriptive_phenology"))
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/phenology/derived/descriptive_phenology"),
    )
    parser.add_argument(
        "--topography-dir",
        type=Path,
        default=Path("data/topography/processed"),
        help="Directory for processed DEM cache files.",
    )
    parser.add_argument("--background-resolution", type=float, default=0.04, help="DEM background grid resolution in degrees.")
    parser.add_argument("--tile-margin", type=int, default=0, help="Number of neighboring 1-degree tiles to include around site tiles.")
    parser.add_argument("--max-background-tiles", type=int, default=40, help="Maximum number of site-dense DEM tiles to draw in the background.")
    parser.add_argument("--include-slope", action="store_true", help="Also sample neighboring pixels to estimate slope/aspect.")
    parser.add_argument(
        "--skip-site-dem",
        action="store_true",
        help="Skip per-site 30 m DEM sampling and keep only source altitude fields.",
    )
    parser.add_argument("--refresh", action="store_true", help="Rebuild cached topography outputs.")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument(
        "--start-year",
        type=int,
        default=DEFAULT_START_YEAR,
        help="Include only observations from this year onward (default: 1951).",
    )
    return parser.parse_args()


def configure_matplotlib() -> None:
    cache_dir = Path(tempfile.gettempdir()) / "grape_growth_stage_mplconfig"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir))
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "axes.labelsize": AXIS_LABEL_SIZE,
            "axes.titlesize": SUBTITLE_SIZE,
            "xtick.labelsize": TICK_LABEL_SIZE,
            "ytick.labelsize": TICK_LABEL_SIZE,
            "legend.fontsize": LEGEND_SIZE,
            "axes.unicode_minus": False,
        }
    )


def copernicus_dem_url(lat_floor: int, lon_floor: int) -> str:
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    tile = f"Copernicus_DSM_COG_10_{ns}{abs(lat_floor):02d}_00_{ew}{abs(lon_floor):03d}_00_DEM"
    return f"https://copernicus-dem-30m.s3.amazonaws.com/{tile}/{tile}.tif"


def tile_key(lon: float, lat: float) -> tuple[int, int]:
    return math.floor(lat), math.floor(lon)


def load_sites(paths: list[Path], start_year: int = DEFAULT_START_YEAR) -> pd.DataFrame:
    columns = ["country_name", "source_system", "site_id", "site_name", "latitude", "longitude", "altitude", "year", "doy"]
    df = pd.concat(
        [pd.read_csv(path, usecols=columns, low_memory=False) for path in paths],
        ignore_index=True,
    )
    for column in ["latitude", "longitude", "altitude"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df[df["year"].ge(start_year)].copy()
    df = df.dropna(subset=["country_name", "site_id", "latitude", "longitude"]).copy()
    sites = (
        df.groupby(["country_name", "source_system", "site_id"], dropna=False)
        .agg(
            site_name=("site_name", "first"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
            source_altitude_m=("altitude", "median"),
            n_observations=("doy", "size"),
        )
        .reset_index()
    )
    return sites[
        sites["latitude"].between(EXTENT[2], EXTENT[3])
        & sites["longitude"].between(EXTENT[0], EXTENT[1])
    ].copy()


def sample_dem_points(points: pd.DataFrame) -> np.ndarray:
    import rasterio

    values = np.full(len(points), np.nan, dtype="float64")
    indexed = points.reset_index().rename(columns={"index": "_row_index"})
    indexed["_tile_lat"] = np.floor(indexed["latitude"]).astype(int)
    indexed["_tile_lon"] = np.floor(indexed["longitude"]).astype(int)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        for (lat_floor, lon_floor), group in indexed.groupby(["_tile_lat", "_tile_lon"], sort=False):
            url = copernicus_dem_url(int(lat_floor), int(lon_floor))
            try:
                with rasterio.open(url) as src:
                    coords = list(zip(group["longitude"], group["latitude"], strict=False))
                    sampled = [float(value[0]) if len(value) else np.nan for value in src.sample(coords)]
            except Exception:
                sampled = [np.nan] * len(group)
            values[group["_row_index"].to_numpy()] = sampled
    values[(values < -500) | (values > 9000)] = np.nan
    return values


def build_site_topography(sites: pd.DataFrame, out_path: Path, refresh: bool, include_slope: bool, skip_site_dem: bool) -> pd.DataFrame:
    if out_path.exists() and not refresh:
        cached = pd.read_csv(out_path)
        key_columns = ["country_name", "source_system", "site_id"]
        expected_keys = set(map(tuple, sites[key_columns].astype(str).to_numpy()))
        cached_keys = set(map(tuple, cached[key_columns].astype(str).to_numpy()))
        if cached_keys == expected_keys:
            return cached
    if skip_site_dem:
        topo = sites.copy()
        topo["dem_elevation_m"] = np.nan
        topo["slope_deg"] = np.nan
        topo["aspect_deg"] = np.nan
        topo["terrain_class"] = pd.cut(
            topo["source_altitude_m"],
            bins=[-np.inf, 100, 250, 500, 1000, np.inf],
            labels=["<100 m", "100-250 m", "250-500 m", "500-1000 m", ">1000 m"],
        )
        keep = [
            "country_name",
            "source_system",
            "site_id",
            "site_name",
            "latitude",
            "longitude",
            "source_altitude_m",
            "dem_elevation_m",
            "slope_deg",
            "aspect_deg",
            "terrain_class",
            "n_observations",
        ]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        topo[keep].to_csv(out_path, index=False)
        return topo[keep]

    delta_lat = 1 / 3600
    rows = []
    for _, row in sites.iterrows():
        lon = float(row["longitude"])
        lat = float(row["latitude"])
        delta_lon = delta_lat / max(math.cos(math.radians(lat)), 0.2)
        rows.append({"site_id": row["site_id"], "sample": "center", "longitude": lon, "latitude": lat})
        if include_slope:
            rows.extend(
                [
                    {"site_id": row["site_id"], "sample": "north", "longitude": lon, "latitude": lat + delta_lat},
                    {"site_id": row["site_id"], "sample": "south", "longitude": lon, "latitude": lat - delta_lat},
                    {"site_id": row["site_id"], "sample": "east", "longitude": lon + delta_lon, "latitude": lat},
                    {"site_id": row["site_id"], "sample": "west", "longitude": lon - delta_lon, "latitude": lat},
                ]
            )
    samples = pd.DataFrame(rows)
    samples["elevation_m"] = sample_dem_points(samples)
    wide = samples.pivot_table(index="site_id", columns="sample", values="elevation_m", aggfunc="first")
    wide = wide.reset_index()
    topo = sites.merge(wide, on="site_id", how="left")

    topo["dem_elevation_m"] = topo["center"]
    if include_slope and {"east", "west", "north", "south"}.issubset(topo.columns):
        dzdx = (topo["east"] - topo["west"]) / 60.0
        dzdy = (topo["north"] - topo["south"]) / 60.0
        topo["slope_deg"] = np.degrees(np.arctan(np.sqrt(dzdx.pow(2) + dzdy.pow(2))))
        topo["aspect_deg"] = (np.degrees(np.arctan2(dzdx, dzdy)) + 360) % 360
    else:
        topo["slope_deg"] = np.nan
        topo["aspect_deg"] = np.nan
    topo["terrain_class"] = pd.cut(
        topo["dem_elevation_m"],
        bins=[-np.inf, 100, 250, 500, 1000, np.inf],
        labels=["<100 m", "100-250 m", "250-500 m", "500-1000 m", ">1000 m"],
    )
    keep = [
        "country_name",
        "source_system",
        "site_id",
        "site_name",
        "latitude",
        "longitude",
        "source_altitude_m",
        "dem_elevation_m",
        "slope_deg",
        "aspect_deg",
        "terrain_class",
        "n_observations",
    ]
    topo = topo[keep]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    topo.to_csv(out_path, index=False)
    return topo


def site_tile_keys(sites: pd.DataFrame, margin: int, max_tiles: int | None) -> list[tuple[int, int]]:
    base = sites.copy()
    base["_tile_lat"] = np.floor(base["latitude"]).astype(int)
    base["_tile_lon"] = np.floor(base["longitude"]).astype(int)
    ranked = (
        base.groupby(["_tile_lat", "_tile_lon"])
        .size()
        .sort_values(ascending=False)
        .reset_index(name="n_sites")
    )
    if max_tiles and max_tiles > 0:
        ranked = ranked.head(max_tiles)
    keys: set[tuple[int, int]] = set()
    for _, row in ranked.iterrows():
        lat_floor = int(row["_tile_lat"])
        lon_floor = int(row["_tile_lon"])
        for dlat in range(-margin, margin + 1):
            for dlon in range(-margin, margin + 1):
                keys.add((lat_floor + dlat, lon_floor + dlon))
    return sorted(keys)


def build_background_dem(out_path: Path, sites: pd.DataFrame, resolution: float, tile_margin: int, max_tiles: int, refresh: bool) -> pd.DataFrame:
    selected_keys = set(site_tile_keys(sites, tile_margin, max_tiles))
    if out_path.exists() and not refresh:
        cached = pd.read_csv(out_path)
        if {"tile_lat", "tile_lon"}.issubset(cached.columns):
            cached_keys = set(
                zip(cached["tile_lat"].astype(int), cached["tile_lon"].astype(int), strict=False)
            )
            if selected_keys.issubset(cached_keys):
                return cached[
                    cached[["tile_lat", "tile_lon"]]
                    .astype(int)
                    .apply(tuple, axis=1)
                    .isin(selected_keys)
                ].copy()

    import rasterio
    from rasterio.enums import Resampling

    rows = []
    tile_size = max(8, int(round(1 / resolution)))
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        for lat_floor, lon_floor in sorted(selected_keys):
            url = copernicus_dem_url(lat_floor, lon_floor)
            try:
                with rasterio.open(url) as src:
                    arr = src.read(1, out_shape=(tile_size, tile_size), resampling=Resampling.average).astype("float64")
                    bounds = src.bounds
            except Exception:
                continue
            arr[(arr < -500) | (arr > 9000)] = np.nan
            lon_values = np.linspace(bounds.left, bounds.right, tile_size, endpoint=False) + (bounds.right - bounds.left) / (2 * tile_size)
            lat_values = np.linspace(bounds.bottom, bounds.top, tile_size, endpoint=False) + (bounds.top - bounds.bottom) / (2 * tile_size)
            lon_grid, lat_grid = np.meshgrid(lon_values, lat_values)
            valid = np.isfinite(arr)
            if valid.any():
                rows.append(
                    pd.DataFrame(
                        {
                            "longitude": lon_grid[valid],
                            "latitude": lat_grid[valid],
                            "elevation_m": arr[valid],
                            "tile_lat": lat_floor,
                            "tile_lon": lon_floor,
                        }
                    )
                )
    background = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["longitude", "latitude", "elevation_m", "tile_lat", "tile_lon"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    background.to_csv(out_path, index=False)
    return background


def hillshade(elevation: np.ndarray, azimuth: float = 315, altitude: float = 45) -> np.ndarray:
    filled = np.array(elevation, dtype="float64")
    if np.isnan(filled).all():
        return np.zeros_like(filled)
    filled[np.isnan(filled)] = np.nanmedian(filled)
    dy, dx = np.gradient(filled)
    slope = np.pi / 2 - np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(-dx, dy)
    azimuth_rad = np.radians(azimuth)
    altitude_rad = np.radians(altitude)
    shaded = np.sin(altitude_rad) * np.sin(slope) + np.cos(altitude_rad) * np.cos(slope) * np.cos(azimuth_rad - aspect)
    return (shaded - shaded.min()) / (shaded.max() - shaded.min())


def setup_map(ax, ccrs, cfeature) -> None:
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#e9f0f5", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#f7f5ef", zorder=0)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), edgecolor="#7b8790", linewidth=0.45, zorder=4)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor="#737373", linewidth=0.55, zorder=4)
    gridlines = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        linewidth=0.25,
        color="#a9a9a9",
        alpha=0.35,
        linestyle="--",
    )
    gridlines.top_labels = False
    gridlines.right_labels = False
    gridlines.xlabel_style = {"size": 10}
    gridlines.ylabel_style = {"size": 10}


def plot_overlay(topo: pd.DataFrame, dem: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig = plt.figure(figsize=(14, 9))
    ax = plt.axes(projection=ccrs.PlateCarree())
    setup_map(ax, ccrs, cfeature)
    terrain = ax.scatter(
        dem["longitude"],
        dem["latitude"],
        c=dem["elevation_m"],
        s=7,
        marker="s",
        cmap="terrain",
        alpha=0.62,
        vmin=0,
        vmax=1600,
        linewidths=0,
        transform=ccrs.PlateCarree(),
        zorder=1,
    )

    max_obs = topo["n_observations"].max()
    for country, group in topo.groupby("country_name"):
        sizes = 9 + 52 * np.sqrt(group["n_observations"] / max_obs)
        ax.scatter(
            group["longitude"],
            group["latitude"],
            s=sizes,
            color=COUNTRY_COLORS.get(country, "#666666"),
            alpha=0.72,
            edgecolors="white",
            linewidths=0.2,
            transform=ccrs.PlateCarree(),
            zorder=5,
            label=country,
        )

    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=COUNTRY_COLORS["France"], label="France TEMPO", markersize=8),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=COUNTRY_COLORS["Germany"], label="Germany DWD", markersize=8),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True, facecolor="white", framealpha=0.9)
    cbar = fig.colorbar(terrain, ax=ax, shrink=0.72, pad=0.015)
    cbar.set_label("Elevation (m)")
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / "site_distribution_dem_overlap.png", dpi=dpi, bbox_inches="tight")
    fig.savefig(fig_dir / "site_distribution_dem_overlap.pdf", bbox_inches="tight")
    plt.close(fig)


def write_metadata(path: Path) -> None:
    text = """# Topography Data

Processed files are derived from Copernicus DEM GLO-30 public Cloud Optimized GeoTIFF tiles.

- Source: Copernicus DEM GLO-30
- Resolution of source tiles: about 30 m
- Remote COG bucket pattern: `https://copernicus-dem-30m.s3.amazonaws.com/...`
- This repository caches only a coarse plotting background (`*.csv`) and site-level terrain variables, not the full 30 m tile archive.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    sites = load_sites(args.input, args.start_year)
    # Keep this legacy France/Germany visualization separate from the canonical
    # six-country 1951+ table generated by base_table/build_site_topography.py.
    site_topography_path = args.data_dir / "site_topography_france_germany_legacy.csv"
    resolution_tag = str(args.background_resolution).replace(".", "p")
    dem_cache_path = args.topography_dir / (
        f"site_region_dem_glo30_background_{resolution_tag}deg_top{args.max_background_tiles}tiles.csv"
    )
    topo = build_site_topography(sites, site_topography_path, args.refresh, args.include_slope, args.skip_site_dem)
    dem = build_background_dem(dem_cache_path, sites, args.background_resolution, args.tile_margin, args.max_background_tiles, args.refresh)
    plot_overlay(topo, dem, args.fig_dir, args.dpi)
    write_metadata(args.topography_dir.parent / "metadata" / "copernicus_dem_glo30.md")

    print(f"Sites summarized: {len(topo):,}")
    print(f"Study period: {args.start_year} onward")
    print(f"Site topography written to: {site_topography_path}")
    print(f"DEM background cache written to: {dem_cache_path}")
    print(f"Figure written to: {args.fig_dir / 'site_distribution_dem_overlap.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
