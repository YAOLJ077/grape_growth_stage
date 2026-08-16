#!/usr/bin/env python
"""Plot phenology sites by source over a DEM elevation background."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


COUNTRY_TABLES = [
    Path("data/phenology/derived/base_table/six_country_base_table_1951.csv"),
]
EXTENT = [-7.5, 23.5, 37.2, 55.5]
COUNTRY_NAMES = {"France", "Germany", "Austria", "Switzerland", "Slovakia", "Spain"}
COUNTRY_ISO3 = {"FRA", "DEU", "AUT", "CHE", "SVK", "ESP"}
COUNTRY_ORDER = ["France", "Germany", "Austria", "Switzerland", "Slovakia", "Spain"]
COUNTRY_COLORS = {
    "France": "#0072B2",
    "Germany": "#CC79A7",
    "Austria": "#00BFC4",
    "Switzerland": "#7570b3",
    "Slovakia": "#e7298a",
    "Spain": "#E66100",
}
COUNTRY_LABELS = {
    "France": "France",
    "Germany": "Germany",
    "Austria": "Austria",
    "Switzerland": "Switzerland",
    "Slovakia": "Slovakia",
    "Spain": "Spain",
}
DEFAULT_START_YEAR = 1951


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        default=COUNTRY_TABLES,
        help="1951+ standardized study base table(s); defaults to the final six-country base table.",
    )
    parser.add_argument("--fig-dir", type=Path, default=Path("fig/phenology_distribution"))
    parser.add_argument(
        "--data-out-dir",
        type=Path,
        default=Path("data/phenology/derived/phenology_distribution"),
    )
    parser.add_argument(
        "--dem-background",
        type=Path,
        default=Path("data/topography/processed/site_region_dem_glo30_background_0p1deg.csv"),
        help="Processed DEM background CSV used when rasterio is unavailable.",
    )
    parser.add_argument(
        "--dem-manifest",
        type=Path,
        default=Path("data/topography/metadata/copernicus_dem_glo30_country_tiles.csv"),
        help="Manifest for full-country raw DEM GeoTIFF tiles.",
    )
    parser.add_argument(
        "--use-raw-dem",
        action="store_true",
        default=True,
        help="Build the background from raw GeoTIFF tiles. Requires rasterio. Enabled by default.",
    )
    parser.add_argument(
        "--use-processed-dem",
        action="store_false",
        dest="use_raw_dem",
        help="Use the lower-resolution processed DEM background CSV instead of raw GeoTIFF tiles.",
    )
    parser.add_argument(
        "--country-boundaries",
        type=Path,
        default=Path("data/topography/metadata/countries.geojson"),
        help="Country boundary GeoJSON used to clip the DEM background.",
    )
    parser.add_argument(
        "--raw-dem-resolution",
        type=float,
        default=0.04,
        help="Degree spacing for downsampled raw DEM points when --use-raw-dem is set.",
    )
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
            "axes.unicode_minus": False,
        }
    )


def load_observations(paths: list[Path], start_year: int = DEFAULT_START_YEAR) -> pd.DataFrame:
    columns = [
        "source_system",
        "country_name",
        "site_id",
        "site_name",
        "latitude",
        "longitude",
        "altitude",
        "year",
        "stage_event",
        "doy",
    ]
    frames = []
    for path in paths:
        header = pd.read_csv(path, nrows=0)
        usecols = [column for column in columns if column in header.columns]
        frames.append(pd.read_csv(path, usecols=usecols, low_memory=False))
    df = pd.concat(frames, ignore_index=True)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df[df["year"].ge(start_year)].copy()
    df = df.dropna(subset=["latitude", "longitude"])
    df = df[
        df["latitude"].between(EXTENT[2], EXTENT[3])
        & df["longitude"].between(EXTENT[0], EXTENT[1])
    ].copy()
    df = df[df["country_name"].isin(COUNTRY_NAMES)].copy()
    df["source_label"] = df["country_name"].map(COUNTRY_LABELS).fillna(df["source_system"])
    return df


def site_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["source_system", "source_label", "country_name", "site_id"], dropna=False)
        .agg(
            site_name=("site_name", "first"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
            altitude=("altitude", "median"),
            n_observations=("site_id", "size"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            n_years=("year", "nunique"),
            n_stages=("stage_event", "nunique"),
        )
        .reset_index()
    )


def load_processed_dem(path: Path) -> pd.DataFrame:
    dem = pd.read_csv(path)
    dem = dem.dropna(subset=["longitude", "latitude", "elevation_m"])
    dem = dem[
        dem["latitude"].between(EXTENT[2], EXTENT[3])
        & dem["longitude"].between(EXTENT[0], EXTENT[1])
    ].copy()
    return dem


def feature_matches_country(feature: dict) -> bool:
    props = feature.get("properties", {})
    name = props.get("name")
    iso3 = props.get("ISO3166-1-Alpha-3")
    return name in COUNTRY_NAMES or iso3 in COUNTRY_ISO3


def europe_country_geometry(boundaries_path: Path):
    from shapely.geometry import box, shape
    from shapely.ops import unary_union

    with boundaries_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    features = data["features"]
    pieces = [shape(feature["geometry"]) for feature in features if feature_matches_country(feature)]
    if not pieces:
        raise ValueError(f"No selected country boundaries found in {boundaries_path}")
    geometry = unary_union(pieces)
    return geometry.intersection(box(*EXTENT))


def clip_dem_to_geometry(dem: pd.DataFrame, geometry) -> pd.DataFrame:
    from shapely.geometry import Point
    from shapely.prepared import prep

    prepared = prep(geometry)
    keep = [
        prepared.contains(Point(float(row.longitude), float(row.latitude)))
        for row in dem.itertuples(index=False)
    ]
    clipped = dem.loc[keep].copy()
    clipped = clipped[clipped["elevation_m"] > -50].copy()
    return clipped


def resolve_local_path(value: object) -> Path:
    """Resolve manifest paths written with either POSIX or Windows separators."""
    return Path(str(value).replace("\\", "/"))


def load_raw_dem(manifest: Path, resolution: float) -> pd.DataFrame:
    try:
        import rasterio
        from rasterio.enums import Resampling
    except ImportError as exc:
        raise RuntimeError(
            "Raw DEM mode requires rasterio. Install rasterio or pass --use-processed-dem "
            "to use the processed DEM background CSV."
        ) from exc

    rows = []
    tile_size = max(8, int(round(1 / resolution)))
    tiles = pd.read_csv(manifest)
    tiles["resolved_local_path"] = tiles["local_path"].map(resolve_local_path)
    tiles = tiles[tiles["resolved_local_path"].map(Path.exists)].copy()
    tiles = tiles.drop_duplicates(subset=["tile_name"]).reset_index(drop=True)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        for row in tiles.itertuples(index=False):
            path = row.resolved_local_path
            with rasterio.open(path) as src:
                arr = src.read(1, out_shape=(tile_size, tile_size), resampling=Resampling.average).astype("float64")
                bounds = src.bounds
            arr[(arr < -500) | (arr > 9000)] = np.nan
            lon_values = np.linspace(bounds.left, bounds.right, tile_size, endpoint=False)
            lat_values = np.linspace(bounds.top, bounds.bottom, tile_size, endpoint=False)
            lon_values += (bounds.right - bounds.left) / (2 * tile_size)
            lat_values += (bounds.bottom - bounds.top) / (2 * tile_size)
            lon_grid, lat_grid = np.meshgrid(lon_values, lat_values)
            valid = np.isfinite(arr)
            if valid.any():
                rows.append(
                    pd.DataFrame(
                        {
                            "longitude": lon_grid[valid],
                            "latitude": lat_grid[valid],
                            "elevation_m": arr[valid],
                        }
                    )
                )
    if not rows:
        return pd.DataFrame(columns=["longitude", "latitude", "elevation_m"])
    dem = pd.concat(rows, ignore_index=True)
    dem = dem[
        dem["latitude"].between(EXTENT[2], EXTENT[3])
        & dem["longitude"].between(EXTENT[0], EXTENT[1])
    ].copy()
    return dem


def setup_map(ax, ccrs, cfeature) -> None:
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#e8f1f6", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#f5f3eb", zorder=0)
    ax.add_feature(cfeature.LAKES.with_scale("50m"), facecolor="#e8f1f6", edgecolor="#b9c9d3", linewidth=0.25, zorder=3)
    ax.add_feature(cfeature.RIVERS.with_scale("50m"), edgecolor="#b9c9d3", linewidth=0.25, alpha=0.65, zorder=3)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), edgecolor="#3f464b", linewidth=0.6, zorder=5)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor="#2f2f2f", linewidth=0.9, zorder=5)
    gridlines = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        linewidth=0.25,
        color="#8a8a8a",
        alpha=0.35,
        linestyle="--",
    )
    gridlines.top_labels = False
    gridlines.right_labels = False
    gridlines.xlabel_style = {"size": 8, "color": "#404040"}
    gridlines.ylabel_style = {"size": 8, "color": "#404040"}


def ordered_countries(sites: pd.DataFrame) -> list[str]:
    present = set(sites["country_name"])
    ordered = [country for country in COUNTRY_ORDER if country in present]
    ordered.extend(sorted(present - set(ordered)))
    return ordered


def plot_overlap(sites: pd.DataFrame, dem: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.lines import Line2D

    fig = plt.figure(figsize=(11, 9))
    ax = plt.axes(projection=ccrs.PlateCarree())
    setup_map(ax, ccrs, cfeature)

    elevation_bounds = [0, 200, 400, 600, 800, 1000, 1200, 1400, 1600, 1800]
    dem_cmap = ListedColormap(
        [
            "#f2f7d5",
            "#cfeaa5",
            "#93cf83",
            "#55a86d",
            "#d0bd63",
            "#b07a3a",
            "#7b4e32",
            "#4b332b",
            "#211d1b",
        ],
        name="stepped_low_light_high_dark_dem",
    )
    dem_norm = BoundaryNorm(elevation_bounds, dem_cmap.N, clip=True)
    terrain = ax.scatter(
        dem["longitude"],
        dem["latitude"],
        c=dem["elevation_m"],
        s=9,
        marker="s",
        cmap=dem_cmap,
        norm=dem_norm,
        alpha=0.72,
        linewidths=0,
        transform=ccrs.PlateCarree(),
        zorder=1,
    )

    site_marker_size = 16
    for country_name in ordered_countries(sites):
        group = sites[sites["country_name"] == country_name]
        ax.scatter(
            group["longitude"],
            group["latitude"],
            s=site_marker_size,
            c=COUNTRY_COLORS.get(country_name, "#666666"),
            alpha=0.82,
            edgecolors="#ffffff",
            linewidths=0.32,
            transform=ccrs.PlateCarree(),
            label=COUNTRY_LABELS.get(country_name, country_name),
            zorder=6,
        )

    handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            label=COUNTRY_LABELS.get(country_name, country_name),
            markerfacecolor=COUNTRY_COLORS.get(country_name, "#666666"),
            markersize=8,
        )
        for country_name in ordered_countries(sites)
    ]
    ax.legend(handles=handles, loc="lower right", frameon=True, framealpha=0.93, fontsize=9)
    cax = ax.inset_axes([1.025, 0.0, 0.035, 1.0], transform=ax.transAxes)
    cbar = fig.colorbar(terrain, cax=cax, boundaries=elevation_bounds, ticks=elevation_bounds)
    cbar.set_label("Elevation (m)")
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / "phenology_sites_by_source_dem_overlap.png", dpi=dpi, bbox_inches="tight")
    fig.savefig(fig_dir / "phenology_sites_by_source_dem_overlap.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    observations = load_observations(args.input, args.start_year)
    sites = site_summary(observations)
    args.data_out_dir.mkdir(parents=True, exist_ok=True)
    sites.to_csv(args.data_out_dir / "map_sites_dem_overlap.csv", index=False)

    if args.use_raw_dem:
        dem = load_raw_dem(args.dem_manifest, args.raw_dem_resolution)
    else:
        dem = load_processed_dem(args.dem_background)
    if args.country_boundaries.exists():
        dem = clip_dem_to_geometry(dem, europe_country_geometry(args.country_boundaries))
    if dem.empty:
        raise RuntimeError(
            "DEM background is empty; check the manifest paths or pass --use-processed-dem."
        )

    plot_overlap(sites, dem, args.fig_dir, args.dpi)
    print(f"Input rows: {len(observations):,}")
    print(f"Study period: {args.start_year} onward")
    print(f"Unique sites: {len(sites):,}")
    print(f"DEM background points: {len(dem):,}")
    print(f"Figure written to: {args.fig_dir / 'phenology_sites_by_source_dem_overlap.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
