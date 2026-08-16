#!/usr/bin/env python
"""Plot site-level terrain temperature correction strength."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADJUSTMENTS = (
    REPO_ROOT
    / "data/weather/processed/era5_land_daily_france_germany_adjusted/supplementary"
    / "temperature_adjustment_site_summary.csv"
)
DEFAULT_SITES = (
    REPO_ROOT / "data/phenology/derived/modeling/france_germany_four_stage/site_inventory.csv"
)
DEFAULT_BOUNDARIES = REPO_ROOT / "data/topography/metadata/countries.geojson"
DEFAULT_OUTPUT = (
    REPO_ROOT / "fig/results_figure/terrain_temperature_correction_strength.png"
)
COUNTRIES = ("France", "Germany")
COUNTRY_ISO2 = {"France": "FR", "Germany": "DE"}
ADJUSTMENT_COLUMN = "temperature_adjustment_c_main_6p5c_km"
BAND_EDGES = (0.0, 0.25, 0.50, 1.00, np.inf)
BAND_LABELS = ("≤0.25°C", "0.25–0.50°C", "0.50–1.00°C", ">1.00°C")
FIG_WIDTH_IN = 7.0
FIG_HEIGHT_IN = 5.50
BASE_FONT_SIZE = 11
INSET_FONT_SIZE = 8
INSET_LEGEND_FONT_SIZE = 7
BAND_REPRESENTATIVE_VALUES = (0.125, 0.375, 0.75, 1.5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adjustments", type=Path, default=DEFAULT_ADJUSTMENTS)
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
            "font.family": "Times New Roman",
            "font.size": BASE_FONT_SIZE,
            "axes.labelsize": BASE_FONT_SIZE,
            "axes.titlesize": BASE_FONT_SIZE,
            "xtick.labelsize": BASE_FONT_SIZE,
            "ytick.labelsize": BASE_FONT_SIZE,
            "legend.fontsize": BASE_FONT_SIZE,
            "axes.linewidth": 0.75,
            "axes.unicode_minus": False,
            "savefig.dpi": 300,
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
    missing = set(COUNTRY_ISO2.values()) - set(geometries)
    if missing:
        raise ValueError(f"Missing country geometries: {sorted(missing)}")
    return geometries


def iter_polygons(geometry: object):
    if geometry.geom_type == "Polygon":
        yield geometry
    elif geometry.geom_type == "MultiPolygon":
        yield from geometry.geoms
    elif geometry.geom_type == "GeometryCollection":
        for part in geometry.geoms:
            yield from iter_polygons(part)


def draw_country_boundaries(ax, geometries: dict[str, object]) -> None:
    for iso2 in COUNTRY_ISO2.values():
        for polygon in iter_polygons(geometries[iso2]):
            min_lon, min_lat, max_lon, max_lat = polygon.bounds
            if max_lon < -6.0 or min_lon > 16.0 or max_lat < 41.0 or min_lat > 55.5:
                continue
            x, y = polygon.exterior.xy
            ax.fill(x, y, facecolor="#f6f4ed", edgecolor="#555555", linewidth=0.65, zorder=0)
            for interior in polygon.interiors:
                hole_x, hole_y = interior.xy
                ax.fill(hole_x, hole_y, facecolor="white", edgecolor="#777777", linewidth=0.25, zorder=1)


def load_site_adjustments(adjustments_path: Path, sites_path: Path) -> pd.DataFrame:
    adjustments = pd.read_csv(adjustments_path, dtype={"site_id": "string"}, low_memory=False)
    sites = pd.read_csv(
        sites_path,
        dtype={"site_id": "string"},
        usecols=["site_uid", "lat", "lon"],
        low_memory=False,
    )
    required = {
        "country",
        "site_uid",
        "site_minus_grid_elevation_m",
        "abs_site_grid_elevation_difference_m",
        ADJUSTMENT_COLUMN,
    }
    missing = required.difference(adjustments.columns)
    if missing:
        raise ValueError(f"Temperature adjustment table is missing columns: {sorted(missing)}")
    if adjustments["site_uid"].duplicated().any():
        raise ValueError("Temperature adjustment table must contain one row per site_uid")
    if sites["site_uid"].duplicated().any():
        raise ValueError("Site inventory must contain one row per site_uid")
    data = adjustments.merge(sites, on="site_uid", how="left", validate="one_to_one")
    data = data[data["country"].isin(COUNTRIES)].dropna(
        subset=["lat", "lon", "site_minus_grid_elevation_m", ADJUSTMENT_COLUMN]
    ).copy()
    data["abs_temperature_adjustment_c"] = data[ADJUSTMENT_COLUMN].abs()
    data["absolute_correction_band"] = pd.cut(
        data["abs_temperature_adjustment_c"],
        bins=BAND_EDGES,
        labels=BAND_LABELS,
        include_lowest=True,
        right=True,
        ordered=True,
    )
    return data


def plot_spatial_panel(ax, data: pd.DataFrame, geometries: dict[str, object]):
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.ticker import MultipleLocator

    draw_country_boundaries(ax, geometries)
    robust_limit = float(
        np.ceil(
            max(
                abs(data[ADJUSTMENT_COLUMN].quantile(0.01)),
                abs(data[ADJUSTMENT_COLUMN].quantile(0.99)),
            )
            * 2.0
        )
        / 2.0
    )
    robust_limit = max(1.0, robust_limit)
    norm = TwoSlopeNorm(vmin=-robust_limit, vcenter=0.0, vmax=robust_limit)
    scatter = ax.scatter(
        data["lon"],
        data["lat"],
        c=data[ADJUSTMENT_COLUMN],
        cmap=plt.get_cmap("RdBu_r"),
        norm=norm,
        s=7.5,
        alpha=0.82,
        edgecolors="none",
        rasterized=True,
        zorder=3,
    )
    ax.set_xlim(-5.8, 15.8)
    ax.set_ylim(41.0, 55.4)
    ax.set_aspect("equal", adjustable="box")
    ax.xaxis.set_major_locator(MultipleLocator(5))
    ax.yaxis.set_major_locator(MultipleLocator(4))
    ax.grid(color="#bdbdbd", linewidth=0.35, alpha=0.45, zorder=2)
    ax.set_xlabel("Longitude", fontsize=BASE_FONT_SIZE)
    ax.set_ylabel("Latitude", fontsize=BASE_FONT_SIZE)
    ax.tick_params(length=3.0, width=0.7, labelsize=BASE_FONT_SIZE)
    return scatter


def correction_band_colors(scatter) -> tuple[str, ...]:
    from matplotlib.colors import to_hex

    vmax = float(scatter.norm.vmax)
    return tuple(
        to_hex(scatter.cmap(scatter.norm(min(value, vmax))))
        for value in BAND_REPRESENTATIVE_VALUES
    )


def plot_strength_inset(ax, data: pd.DataFrame, band_colors: tuple[str, ...]) -> None:
    counts = (
        data.groupby(["country", "absolute_correction_band"], observed=False)
        .size()
        .unstack(fill_value=0)
        .reindex(index=COUNTRIES, columns=BAND_LABELS, fill_value=0)
    )
    percentages = counts.div(counts.sum(axis=1), axis=0).mul(100.0)
    x_positions = np.arange(len(COUNTRIES))
    bottom = np.zeros(len(COUNTRIES), dtype=float)
    for label, color in zip(BAND_LABELS, band_colors):
        values = percentages[label].to_numpy(dtype=float)
        ax.bar(
            x_positions,
            values,
            bottom=bottom,
            width=0.58,
            color=color,
            edgecolor="white",
            linewidth=0.65,
            label=label,
        )
        bottom += values

    ax.set_xticks(x_positions, COUNTRIES)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 50, 100])
    ax.set_ylabel("Sites (%)", fontsize=INSET_FONT_SIZE)
    ax.grid(axis="y", color="#bdbdbd", linewidth=0.30, alpha=0.5)
    ax.tick_params(axis="both", labelsize=INSET_FONT_SIZE, length=2.2, width=0.55)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_facecolor((1.0, 1.0, 1.0, 0.88))


def add_strength_legend(ax, band_colors: tuple[str, ...]) -> None:
    from matplotlib.patches import Patch

    handles = [
        Patch(facecolor=color, edgecolor="white", label=label)
        for label, color in zip(BAND_LABELS, band_colors)
    ]
    ax.legend(
        handles=handles,
        frameon=False,
        loc="lower right",
        bbox_to_anchor=(0.94, 0.315),
        ncol=2,
        handlelength=1.0,
        handletextpad=0.28,
        columnspacing=0.55,
        labelspacing=0.25,
        fontsize=INSET_LEGEND_FONT_SIZE,
    )


def plot(data: pd.DataFrame, geometries: dict[str, object], output: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(FIG_WIDTH_IN, FIG_HEIGHT_IN))
    map_left = 0.08
    map_bottom = 0.220
    map_width = 0.84
    map_height = 0.725
    map_ax = fig.add_axes([map_left, map_bottom, map_width, map_height])
    scatter = plot_spatial_panel(map_ax, data, geometries)
    band_colors = correction_band_colors(scatter)
    inset_ax = map_ax.inset_axes([0.735, 0.045, 0.205, 0.26])
    plot_strength_inset(inset_ax, data, band_colors)
    add_strength_legend(map_ax, band_colors)
    colorbar_ax = fig.add_axes([map_left, 0.065, map_width, 0.035])
    colorbar = fig.colorbar(scatter, cax=colorbar_ax, orientation="horizontal", extend="both")
    colorbar.set_label("Temperature correction, ΔT (°C)", labelpad=1.5, fontsize=BASE_FONT_SIZE)
    colorbar.ax.tick_params(length=3.0, width=0.7, pad=1.5, labelsize=BASE_FONT_SIZE)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=dpi, facecolor="white")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    data = load_site_adjustments(args.adjustments, args.sites)
    geometries = load_country_geometries(args.country_boundaries)
    plot(data, geometries, args.output, args.dpi)
    adjustment = data[ADJUSTMENT_COLUMN]
    abs_adjustment = data["abs_temperature_adjustment_c"]
    print("Terrain temperature correction strength figure")
    print(f"Sites: {len(data):,}")
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")
    print(
        "Signed ΔT (°C): "
        f"median={adjustment.median():+.3f}, "
        f"P05={adjustment.quantile(0.05):+.3f}, "
        f"P95={adjustment.quantile(0.95):+.3f}"
    )
    print(
        "Absolute |ΔT| (°C): "
        f"median={abs_adjustment.median():.3f}, "
        f"P75={abs_adjustment.quantile(0.75):.3f}, "
        f"P95={abs_adjustment.quantile(0.95):.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
