#!/usr/bin/env python
"""Map site-level France-Germany temperature adjustments."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    REPO_ROOT
    / "data/weather/processed/era5_land_daily_france_germany_adjusted/supplementary"
    / "temperature_adjustment_site_summary.csv"
)
DEFAULT_SITES = (
    REPO_ROOT / "data/phenology/derived/modeling/france_germany_four_stage/site_inventory.csv"
)
DEFAULT_BOUNDARIES = REPO_ROOT / "data/topography/metadata/countries.geojson"
DEFAULT_OUTPUT = (
    REPO_ROOT / "fig/weather_processing/france_germany_temperature_adjustment_spatial_distribution.png"
)
COUNTRIES = ("France", "Germany")
EXTENTS = {"France": (-5.8, 9.8, 41.0, 51.7), "Germany": (5.4, 15.7, 47.0, 55.3)}
ADJUSTMENT_COLUMN = "temperature_adjustment_c_main_6p5c_km"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--sites", type=Path, default=DEFAULT_SITES)
    parser.add_argument("--country-boundaries", type=Path, default=DEFAULT_BOUNDARIES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
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
            "font.size": 7.5,
            "axes.labelsize": 8,
            "axes.titlesize": 8.5,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "axes.linewidth": 0.65,
            "axes.unicode_minus": False,
        }
    )


def load_geometries(path: Path) -> list[tuple[str, object]]:
    from shapely.geometry import shape

    payload = json.loads(path.read_text(encoding="utf-8"))
    return [(feature.get("properties", {}).get("name", ""), shape(feature["geometry"])) for feature in payload["features"]]


def iter_polygons(geometry: object):
    if geometry.geom_type == "Polygon":
        yield geometry
    elif geometry.geom_type == "MultiPolygon":
        yield from geometry.geoms


def draw_boundaries(ax, geometries: list[tuple[str, object]], extent: tuple[float, float, float, float]) -> None:
    from shapely.geometry import box

    viewport = box(extent[0], extent[2], extent[1], extent[3])
    for _, geometry in geometries:
        if not geometry.intersects(viewport):
            continue
        clipped = geometry.intersection(viewport)
        for polygon in iter_polygons(clipped):
            x, y = polygon.exterior.xy
            ax.fill(x, y, facecolor="#f3f1ea", edgecolor="#666666", linewidth=0.45, zorder=0)
            for interior in polygon.interiors:
                hx, hy = interior.xy
                ax.fill(hx, hy, facecolor="white", edgecolor="#9a9a9a", linewidth=0.25, zorder=1)


def degree_lon(value: float, _: int) -> str:
    if np.isclose(value, 0):
        return "0°"
    return f"{abs(value):g}°{'E' if value > 0 else 'W'}"


def degree_lat(value: float, _: int) -> str:
    return f"{abs(value):g}°{'N' if value >= 0 else 'S'}"


def plot(data: pd.DataFrame, geometries: list[tuple[str, object]], output: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.ticker import FuncFormatter, MultipleLocator

    required = {"country", "site_uid", "lat", "lon", ADJUSTMENT_COLUMN}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Site summary is missing columns: {sorted(missing)}")
    work = data[data["country"].isin(COUNTRIES)].dropna(subset=list(required)).copy()
    if work["site_uid"].duplicated().any():
        raise ValueError("Spatial distribution input must contain one row per site_uid")

    robust_limit = float(np.ceil(work[ADJUSTMENT_COLUMN].abs().quantile(0.99) * 2.0) / 2.0)
    robust_limit = max(1.0, robust_limit)
    norm = TwoSlopeNorm(vmin=-robust_limit, vcenter=0.0, vmax=robust_limit)
    cmap = plt.get_cmap("RdBu_r")

    fig = plt.figure(figsize=(7.2, 3.15))
    axes_bottom = 0.245
    axes_height = 0.72
    france_width = 0.317
    germany_width = 0.247
    panel_gap = 0.025
    group_width = france_width + panel_gap + germany_width
    group_left = (1.0 - group_width) / 2.0
    axes = [
        fig.add_axes([group_left, axes_bottom, france_width, axes_height]),
        fig.add_axes(
            [group_left + france_width + panel_gap, axes_bottom, germany_width, axes_height]
        ),
    ]
    scatter = None
    for label, country, ax in zip(("(a)", "(b)"), COUNTRIES, axes):
        extent = EXTENTS[country]
        draw_boundaries(ax, geometries, extent)
        group = work[work["country"].eq(country)]
        scatter = ax.scatter(
            group["lon"],
            group["lat"],
            c=group[ADJUSTMENT_COLUMN],
            cmap=cmap,
            norm=norm,
            s=8.0,
            edgecolors="white",
            linewidths=0.18,
            alpha=0.88,
            zorder=3,
            rasterized=True,
        )
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
        midpoint = (extent[2] + extent[3]) / 2.0
        ax.set_aspect(1.0 / np.cos(np.deg2rad(midpoint)))
        ax.set_anchor("E" if country == "France" else "W")
        ax.xaxis.set_major_locator(MultipleLocator(2))
        ax.yaxis.set_major_locator(MultipleLocator(2))
        ax.xaxis.set_major_formatter(FuncFormatter(degree_lon))
        ax.yaxis.set_major_formatter(FuncFormatter(degree_lat))
        if country == "Germany":
            ax.yaxis.tick_right()
        ax.grid(color="#9d9d9d", linewidth=0.28, linestyle="--", alpha=0.45, zorder=2)
        ax.tick_params(length=2.3, width=0.55)
        ax.text(
            0.018,
            0.978,
            label,
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8.5,
            fontweight="bold",
            zorder=4,
        )
        ax.text(
            0.02,
            0.025,
            f"{len(group):,} sites",
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=7,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 1.7},
            zorder=4,
        )

    if scatter is None:
        raise RuntimeError("No site adjustments were plotted")
    fig.canvas.draw()
    positions = [ax.get_position() for ax in axes]
    map_left = min(position.x0 for position in positions)
    map_right = max(position.x1 for position in positions)
    colorbar_ax = fig.add_axes([map_left, 0.105, map_right - map_left, 0.036])
    colorbar = fig.colorbar(scatter, cax=colorbar_ax, orientation="horizontal", extend="both")
    colorbar.set_label(r"Temperature adjustment, $\Delta T$ (°C)", labelpad=2.5)
    colorbar.ax.tick_params(labelsize=7, length=2.3, width=0.55, pad=1.5)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=dpi)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    adjustments = pd.read_csv(args.input, dtype={"site_id": "string"}, low_memory=False)
    sites = pd.read_csv(
        args.sites,
        dtype={"site_id": "string"},
        usecols=["site_uid", "lat", "lon"],
        low_memory=False,
    )
    if sites["site_uid"].duplicated().any():
        raise ValueError("Site inventory must contain one row per site_uid")
    data = adjustments.merge(sites, on="site_uid", how="left", validate="one_to_one")
    geometries = load_geometries(args.country_boundaries)
    plot(data, geometries, args.output, args.dpi)
    print(f"Sites: {len(data):,}; output: {args.output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
