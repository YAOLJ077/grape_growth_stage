#!/usr/bin/env python
"""Plot detailed France and Germany four-stage phenology site distributions."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "data" / "phenology" / "derived" / "modeling" / "france_germany_four_stage" / "site_inventory.csv"
DEFAULT_BOUNDARIES = REPO_ROOT / "data" / "topography" / "metadata" / "countries.geojson"
DEFAULT_FIG_DIR = REPO_ROOT / "fig" / "phenology_distribution"
DEFAULT_STEM = "france_germany_four_stage_site_distribution"
COUNTRY_COLORS = {"France": "#1f78b4", "Germany": "#d95f02"}
COUNTRY_ISO2 = {"France": "FR", "Germany": "DE"}
EXTENTS = {"France": (-6.2, 10.2, 41.0, 52.2), "Germany": (5.0, 16.0, 47.0, 55.8)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--country-boundaries", type=Path, default=DEFAULT_BOUNDARIES)
    parser.add_argument("--fig-dir", type=Path, default=DEFAULT_FIG_DIR)
    parser.add_argument("--stem", default=DEFAULT_STEM)
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
    geometries = {}
    for feature in payload["features"]:
        properties = feature.get("properties", {})
        iso2 = properties.get("ISO3166-1-Alpha-2")
        if properties.get("name") == "France":
            iso2 = "FR"
        if iso2 in COUNTRY_ISO2.values():
            geometries[iso2] = shape(feature["geometry"])
    return geometries


def marker_sizes(values: pd.Series, maximum: float) -> np.ndarray:
    denominator = np.log1p(maximum) if maximum > 0 else 1.0
    return 7.0 + 43.0 * np.log1p(values.to_numpy(dtype=float)) / denominator


def setup_panel(ax, country: str, geometry: object, ccrs, cfeature) -> None:
    from cartopy.io import shapereader
    from matplotlib.ticker import FixedLocator

    ax.set_extent(EXTENTS[country], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#e9f0f5", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#f7f5ef", zorder=0)
    ax.add_feature(cfeature.LAKES.with_scale("50m"), facecolor="#e9f0f5", edgecolor="#bdccd5", linewidth=0.35, zorder=1)
    ax.add_feature(cfeature.RIVERS.with_scale("50m"), edgecolor="#b7cbd6", linewidth=0.38, zorder=1)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), edgecolor="#65747d", linewidth=0.55, zorder=2)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor="#666666", linewidth=0.55, zorder=2)
    admin1_path = shapereader.natural_earth(
        resolution="50m", category="cultural", name="admin_1_states_provinces_lines"
    )
    ax.add_geometries(
        shapereader.Reader(admin1_path).geometries(), ccrs.PlateCarree(),
        facecolor="none", edgecolor="#a9a9a9", linewidth=0.28, alpha=0.7, zorder=2,
    )
    color = COUNTRY_COLORS[country]
    ax.add_geometries(
        [geometry], ccrs.PlateCarree(), facecolor=color, alpha=0.055,
        edgecolor=color, linewidth=1.05, zorder=2,
    )
    gridlines = ax.gridlines(
        crs=ccrs.PlateCarree(), draw_labels=True, linewidth=0.28,
        color="#999999", alpha=0.42, linestyle="--", zorder=1,
    )
    gridlines.top_labels = False
    gridlines.right_labels = False
    gridlines.xlocator = FixedLocator(np.arange(-10, 21, 2))
    gridlines.ylocator = FixedLocator(np.arange(40, 58, 2))
    gridlines.xlabel_style = {"size": 8, "color": "#4d4d4d"}
    gridlines.ylabel_style = {"size": 8, "color": "#4d4d4d"}
    ax.set_title(country, fontsize=12, pad=7)


def plot_sites(sites: pd.DataFrame, geometries: dict[str, object], fig_dir: Path, stem: str, dpi: int) -> None:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, axes = plt.subplots(
        1, 2, figsize=(13.2, 6.6), subplot_kw={"projection": ccrs.PlateCarree()},
        gridspec_kw={"width_ratios": [1.2, 1.0]}, constrained_layout=True,
    )
    maximum = float(sites["n_event_records"].max())
    for label, (ax, country) in zip(("(a)", "(b)"), zip(axes, ("France", "Germany"))):
        setup_panel(ax, country, geometries[COUNTRY_ISO2[country]], ccrs, cfeature)
        group = sites[sites["country"].eq(country)].sort_values("n_event_records")
        ax.scatter(
            group["lon"], group["lat"], s=marker_sizes(group["n_event_records"], maximum),
            c=COUNTRY_COLORS[country], alpha=0.68, edgecolors="white", linewidths=0.28,
            transform=ccrs.PlateCarree(), zorder=4,
        )
        ax.text(0.015, 0.985, label, transform=ax.transAxes, ha="left", va="top", fontsize=11)
        ax.text(
            0.985, 0.018,
            f"{len(group):,} sites · {int(group['n_event_records'].sum()):,} events",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="#4d4d4d",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 2.5},
            zorder=5,
        )

    country_handles = [
        Line2D([0], [0], marker="o", color="none", label=country,
               markerfacecolor=color, markeredgecolor="white", markersize=8)
        for country, color in COUNTRY_COLORS.items()
    ]
    size_values = [10, 50, 200]
    size_handles = [
        Line2D([0], [0], marker="o", color="none", label=f"{value} events",
               markerfacecolor="#777777", markeredgecolor="white",
               markersize=float(np.sqrt(marker_sizes(pd.Series([value]), maximum)[0])))
        for value in size_values
    ]
    fig.legend(
        handles=country_handles + size_handles, loc="outside lower center", ncol=5,
        frameon=True, framealpha=0.94, fontsize=9, handletextpad=0.5, columnspacing=1.3,
    )
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / f"{stem}.png", dpi=dpi, bbox_inches="tight")
    fig.savefig(fig_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    sites = pd.read_csv(args.input, dtype={"site_id": "string"}, low_memory=False)
    sites = sites[sites["country"].isin(COUNTRY_COLORS)].copy()
    geometries = load_country_geometries(args.country_boundaries)
    missing = set(COUNTRY_ISO2.values()) - set(geometries)
    if missing:
        raise ValueError(f"Missing country geometries: {sorted(missing)}")
    plot_sites(sites, geometries, args.fig_dir, args.stem, args.dpi)
    print(f"Sites: {len(sites):,}; events: {int(sites['n_event_records'].sum()):,}")
    print(f"Figure: {(args.fig_dir / f'{args.stem}.png').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
