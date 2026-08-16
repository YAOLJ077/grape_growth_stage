#!/usr/bin/env python
"""Plot France–Germany four-stage sites over country-clipped GLO-30 DEM."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITES = REPO_ROOT / "data" / "phenology" / "derived" / "modeling" / "france_germany_four_stage" / "site_inventory.csv"
DEFAULT_MANIFEST = REPO_ROOT / "data" / "topography" / "metadata" / "copernicus_dem_glo30_country_tiles.csv"
DEFAULT_BOUNDARIES = REPO_ROOT / "data" / "topography" / "metadata" / "countries.geojson"
DEFAULT_FIG_DIR = REPO_ROOT / "fig" / "phenology_distribution"
DEFAULT_STEM = "france_germany_four_stage_site_distribution_dem_overlap"
COUNTRY_KEYS = {"France": "france", "Germany": "germany"}
COUNTRY_ISO2 = {"France": "FR", "Germany": "DE"}
COUNTRY_COLORS = {"France": "#0072B2", "Germany": "#CC79A7"}
EXTENTS = {"France": (-6.2, 10.2, 41.0, 52.2), "Germany": (5.0, 16.0, 47.0, 55.8)}
ELEVATION_BOUNDS = list(range(0, 1801, 100))
ELEVATION_COLORS = [
    "#ffffe5", "#f3f6bd", "#dcefa5", "#bde38c", "#91d477", "#61c267",
    "#32a95b", "#16854f", "#d7c56b", "#c7a85f", "#b58a52", "#9f6d47",
    "#89543e", "#713f37", "#59322f", "#42292b", "#2d2327", "#181a1e",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", type=Path, default=DEFAULT_SITES)
    parser.add_argument("--dem-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--country-boundaries", type=Path, default=DEFAULT_BOUNDARIES)
    parser.add_argument("--fig-dir", type=Path, default=DEFAULT_FIG_DIR)
    parser.add_argument("--stem", default=DEFAULT_STEM)
    parser.add_argument("--dem-resolution", type=float, default=0.02)
    parser.add_argument("--dpi", type=int, default=300)
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
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def load_country_geometries(path: Path) -> dict[str, object]:
    from shapely.geometry import shape

    payload = json.loads(path.read_text(encoding="utf-8"))
    geometries: dict[str, object] = {}
    for feature in payload["features"]:
        properties = feature.get("properties", {})
        iso2 = properties.get("ISO3166-1-Alpha-2")
        if properties.get("name") == "France":
            iso2 = "FR"
        if iso2 in COUNTRY_ISO2.values():
            geometries[iso2] = shape(feature["geometry"])
    return geometries


def resolve_local_path(value: object) -> Path:
    path = Path(str(value).replace("\\", "/"))
    return path if path.is_absolute() else REPO_ROOT / path


def load_raw_dem_by_country(manifest: Path, resolution: float) -> dict[str, pd.DataFrame]:
    import rasterio
    from rasterio.enums import Resampling

    tile_size = max(8, int(round(1.0 / resolution)))
    table = pd.read_csv(manifest)
    table = table[table["country"].isin(COUNTRY_KEYS.values())].copy()
    table["resolved_local_path"] = table["local_path"].map(resolve_local_path)
    table = table[table["resolved_local_path"].map(Path.exists)].copy()
    output: dict[str, pd.DataFrame] = {}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        for country, key in COUNTRY_KEYS.items():
            frames: list[pd.DataFrame] = []
            tiles = table[table["country"].eq(key)].drop_duplicates("tile_name")
            for row in tiles.itertuples(index=False):
                with rasterio.open(row.resolved_local_path) as src:
                    array = src.read(
                        1, out_shape=(tile_size, tile_size), resampling=Resampling.average
                    ).astype("float64")
                    bounds = src.bounds
                array[(array < -50) | (array > 9000)] = np.nan
                x_step = (bounds.right - bounds.left) / tile_size
                y_step = (bounds.top - bounds.bottom) / tile_size
                longitude = np.linspace(bounds.left, bounds.right, tile_size, endpoint=False) + x_step / 2
                latitude = np.linspace(bounds.top, bounds.bottom, tile_size, endpoint=False) - y_step / 2
                lon_grid, lat_grid = np.meshgrid(longitude, latitude)
                valid = np.isfinite(array)
                if valid.any():
                    frames.append(
                        pd.DataFrame(
                            {
                                "longitude": lon_grid[valid],
                                "latitude": lat_grid[valid],
                                "elevation_m": array[valid],
                            }
                        )
                    )
            output[country] = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
                columns=["longitude", "latitude", "elevation_m"]
            )
    return output


def clip_dem(dem: pd.DataFrame, geometry: object, extent: tuple[float, float, float, float]) -> pd.DataFrame:
    subset = dem[
        dem["longitude"].between(extent[0], extent[1])
        & dem["latitude"].between(extent[2], extent[3])
    ].copy()
    try:
        from shapely import contains_xy

        keep = contains_xy(geometry, subset["longitude"].to_numpy(), subset["latitude"].to_numpy())
    except ImportError:
        from shapely.geometry import Point
        from shapely.prepared import prep

        prepared = prep(geometry)
        keep = [prepared.contains(Point(lon, lat)) for lon, lat in zip(subset.longitude, subset.latitude)]
    return subset.loc[keep].reset_index(drop=True)


def dem_to_regular_grid(
    dem: pd.DataFrame, resolution: float
) -> tuple[np.ndarray, np.ndarray, np.ma.MaskedArray]:
    """Convert cell centers to a contiguous masked grid for seam-free rendering."""
    work = dem.copy()
    work["longitude_key"] = (
        np.rint((work["longitude"] - resolution / 2.0) / resolution) * resolution
        + resolution / 2.0
    ).round(6)
    work["latitude_key"] = (
        np.rint((work["latitude"] - resolution / 2.0) / resolution) * resolution
        + resolution / 2.0
    ).round(6)
    grid = work.pivot_table(
        index="latitude_key", columns="longitude_key", values="elevation_m", aggfunc="mean"
    ).sort_index().sort_index(axis=1)
    longitude = grid.columns.to_numpy(dtype=float)
    latitude = grid.index.to_numpy(dtype=float)

    def edges(centers: np.ndarray) -> np.ndarray:
        interior = (centers[:-1] + centers[1:]) / 2.0
        return np.concatenate(
            ([centers[0] - (interior[0] - centers[0])], interior, [centers[-1] + (centers[-1] - interior[-1])])
        )

    values = np.ma.masked_invalid(grid.to_numpy(dtype=float))
    return edges(longitude), edges(latitude), values


def setup_panel(ax, country: str, ccrs, cfeature) -> None:
    from cartopy.io import shapereader
    from matplotlib.ticker import FixedLocator

    ax.set_extent(EXTENTS[country], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#e8f1f6", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#f5f3eb", zorder=0)
    ax.add_feature(cfeature.LAKES.with_scale("50m"), facecolor="#e8f1f6", edgecolor="#b9c9d3", linewidth=0.28, zorder=3)
    ax.add_feature(cfeature.RIVERS.with_scale("50m"), edgecolor="#afc4d0", linewidth=0.28, alpha=0.72, zorder=3)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), edgecolor="#3f464b", linewidth=0.6, zorder=5)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor="#2f2f2f", linewidth=0.85, zorder=5)
    admin1_path = shapereader.natural_earth(
        resolution="50m", category="cultural", name="admin_1_states_provinces_lines"
    )
    ax.add_geometries(
        shapereader.Reader(admin1_path).geometries(), ccrs.PlateCarree(),
        facecolor="none", edgecolor="#7a7a7a", linewidth=0.24, alpha=0.48, zorder=4,
    )
    gridlines = ax.gridlines(
        crs=ccrs.PlateCarree(), draw_labels=True, linewidth=0.25,
        color="#8a8a8a", alpha=0.35, linestyle="--", zorder=2,
    )
    gridlines.top_labels = False
    gridlines.right_labels = False
    gridlines.xlocator = FixedLocator(np.arange(-10, 21, 2))
    gridlines.ylocator = FixedLocator(np.arange(40, 58, 2))
    gridlines.xlabel_style = {"size": 10.0, "color": "#404040"}
    gridlines.ylabel_style = {"size": 10.0, "color": "#404040"}


def plot_map(
    sites: pd.DataFrame,
    dem_by_country: dict[str, pd.DataFrame],
    dem_resolution: float,
    fig_dir: Path,
    stem: str,
    dpi: int,
) -> None:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap

    cmap = ListedColormap(ELEVATION_COLORS, name="stepped_low_light_high_dark_dem")
    norm = BoundaryNorm(ELEVATION_BOUNDS, cmap.N, clip=True)
    fig = plt.figure(figsize=(7.35, 3.4))
    grid = fig.add_gridspec(
        1, 2, width_ratios=[1.17, 1.0], left=0.055, right=0.98,
        bottom=0.28, top=0.98, wspace=0.15,
    )
    axes = [
        fig.add_subplot(grid[0, 0], projection=ccrs.PlateCarree()),
        fig.add_subplot(grid[0, 1], projection=ccrs.PlateCarree()),
    ]
    terrain = None
    for label, (ax, country) in zip(("(a)", "(b)"), zip(axes, ("France", "Germany"))):
        setup_panel(ax, country, ccrs, cfeature)
        dem = dem_by_country[country]
        longitude_edges, latitude_edges, elevation_grid = dem_to_regular_grid(dem, dem_resolution)
        terrain = ax.pcolormesh(
            longitude_edges, latitude_edges, elevation_grid, cmap=cmap, norm=norm,
            alpha=0.82, shading="flat", antialiased=False, rasterized=True,
            transform=ccrs.PlateCarree(), zorder=1,
        )
        group = sites[sites["country"].eq(country)]
        ax.scatter(
            group["lon"], group["lat"], s=7.2, c=COUNTRY_COLORS[country], alpha=0.84,
            edgecolors="white", linewidths=0.22, transform=ccrs.PlateCarree(), zorder=6,
        )
        ax.text(0.015, 0.985, label, transform=ax.transAxes, ha="left", va="top", fontsize=11.0, zorder=7)
        ax.text(
            0.018, 0.018, f"{len(group):,} sites", transform=ax.transAxes,
            ha="left", va="bottom", fontsize=10.0, color="#404040",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.80, "pad": 2.0}, zorder=7,
        )

    if terrain is None:
        raise RuntimeError("No DEM terrain was rendered")
    fig.canvas.draw()
    positions = [ax.get_position() for ax in axes]
    map_bottom = min(position.y0 for position in positions)
    map_left = min(position.x0 for position in positions)
    map_right = max(position.x1 for position in positions)
    colorbar_ax = fig.add_axes([map_left, map_bottom - 0.14, map_right - map_left, 0.035])
    colorbar = fig.colorbar(
        terrain, cax=colorbar_ax, boundaries=ELEVATION_BOUNDS, ticks=ELEVATION_BOUNDS,
        spacing="uniform", orientation="horizontal",
    )
    colorbar.set_label("Elevation (m)", fontsize=11.0, labelpad=3)
    colorbar.ax.tick_params(labelsize=10.0, length=2.3, width=0.55, pad=1.5)
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / f"{stem}.png", dpi=dpi)
    fig.savefig(fig_dir / f"{stem}.pdf")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    sites = pd.read_csv(args.sites, dtype={"site_id": "string"}, low_memory=False)
    sites = sites[sites["country"].isin(COUNTRY_KEYS)].copy()
    geometries = load_country_geometries(args.country_boundaries)
    missing = set(COUNTRY_ISO2.values()) - set(geometries)
    if missing:
        raise ValueError(f"Missing country geometries: {sorted(missing)}")
    raw = load_raw_dem_by_country(args.dem_manifest, args.dem_resolution)
    clipped = {
        country: clip_dem(raw[country], geometries[COUNTRY_ISO2[country]], EXTENTS[country])
        for country in COUNTRY_KEYS
    }
    if any(frame.empty for frame in clipped.values()):
        raise RuntimeError("A country DEM layer is empty; check raw tiles and country boundaries")
    plot_map(sites, clipped, args.dem_resolution, args.fig_dir, args.stem, args.dpi)
    print(f"Sites: {len(sites):,}; France DEM cells: {len(clipped['France']):,}; Germany DEM cells: {len(clipped['Germany']):,}")
    print(f"Figure: {(args.fig_dir / f'{args.stem}.png').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
