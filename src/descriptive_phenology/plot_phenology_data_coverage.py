#!/usr/bin/env python
"""Create phenology data coverage and gradient figures."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


COUNTRY_TABLES = [
    Path("data/phenology_grape/processed/france_grape_phenology_complete.csv"),
    Path("data/phenology_grape/processed/germany_grape_phenology_complete.csv"),
]
KEY_BBCH = ["07", "09", "11", "15", "19", "55", "61", "65", "69", "75", "79", "81", "89"]
MAP_BBCH = ["07", "61", "81", "89"]
BBCH_LABELS = {
    "07": "BBCH 07",
    "09": "BBCH 09",
    "11": "BBCH 11",
    "15": "BBCH 15",
    "19": "BBCH 19",
    "55": "BBCH 55",
    "61": "BBCH 61",
    "65": "BBCH 65",
    "69": "BBCH 69",
    "75": "BBCH 75",
    "79": "BBCH 79",
    "81": "BBCH 81",
    "89": "BBCH 89",
}
COUNTRY_COLORS = {"France": "#2f6f9f", "Germany": "#b45f06"}
AXIS_LABEL_SIZE = 14
TICK_LABEL_SIZE = 12
SUBTITLE_SIZE = 15
LEGEND_SIZE = 11


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", default=COUNTRY_TABLES)
    parser.add_argument("--fig-dir", type=Path, default=Path("fig/descriptive_phenology"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/phenology_grape/derived/descriptive_phenology"))
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
            "axes.labelsize": AXIS_LABEL_SIZE,
            "axes.titlesize": SUBTITLE_SIZE,
            "xtick.labelsize": TICK_LABEL_SIZE,
            "ytick.labelsize": TICK_LABEL_SIZE,
            "legend.fontsize": LEGEND_SIZE,
            "axes.unicode_minus": False,
        }
    )


def normalize_bbch(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        number = int(float(text))
    except ValueError:
        return text
    return f"{number:02d}"


def load_data(paths: list[Path]) -> pd.DataFrame:
    columns = [
        "source_system",
        "country_name",
        "site_id",
        "site_name",
        "latitude",
        "longitude",
        "altitude",
        "bbch_code",
        "year",
        "doy",
    ]
    df = pd.concat(
        [pd.read_csv(path, usecols=columns, low_memory=False) for path in paths],
        ignore_index=True,
    )
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["doy"] = pd.to_numeric(df["doy"], errors="coerce")
    for column in ["latitude", "longitude", "altitude"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["bbch_norm"] = df["bbch_code"].map(normalize_bbch)
    df = df.dropna(subset=["country_name", "site_id", "latitude", "longitude", "year", "doy"])
    df = df[df["bbch_norm"].isin(KEY_BBCH) & df["doy"].between(1, 366)].copy()
    df["year"] = df["year"].astype(int)
    return df


def save_figure(fig, fig_dir: Path, stem: str, dpi: int) -> None:
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / f"{stem}.png", dpi=dpi, bbox_inches="tight")
    fig.savefig(fig_dir / f"{stem}.pdf", bbox_inches="tight")


def build_summary_tables(df: pd.DataFrame, data_dir: Path) -> dict[str, pd.DataFrame]:
    data_dir.mkdir(parents=True, exist_ok=True)

    coverage = (
        df.groupby(["country_name", "year", "bbch_norm"], dropna=False)
        .agg(n_observations=("doy", "size"), n_sites=("site_id", "nunique"))
        .reset_index()
        .sort_values(["country_name", "year", "bbch_norm"])
    )
    coverage.to_csv(data_dir / "coverage_year_by_bbch.csv", index=False)

    site_span = (
        df.groupby(["country_name", "source_system", "site_id"], dropna=False)
        .agg(
            site_name=("site_name", "first"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
            altitude=("altitude", "first"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            n_years=("year", "nunique"),
            n_observations=("doy", "size"),
            n_bbch=("bbch_norm", "nunique"),
        )
        .reset_index()
    )
    site_span.to_csv(data_dir / "site_observation_span.csv", index=False)

    site_bbch = (
        df[df["bbch_norm"].isin(MAP_BBCH)]
        .groupby(["country_name", "source_system", "site_id", "bbch_norm"], dropna=False)
        .agg(
            site_name=("site_name", "first"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
            altitude=("altitude", "first"),
            median_doy=("doy", "median"),
            n_observations=("doy", "size"),
            first_year=("year", "min"),
            last_year=("year", "max"),
        )
        .reset_index()
    )
    site_bbch.to_csv(data_dir / "site_bbch_median_doy.csv", index=False)

    gradient_base = site_bbch.dropna(subset=["latitude", "altitude"]).copy()
    gradient_base["latitude_bin"] = (gradient_base["latitude"] * 2).round() / 2
    gradient_base["altitude_bin"] = (gradient_base["altitude"] / 100).round() * 100
    latitude_bins = (
        gradient_base.groupby(["country_name", "bbch_norm", "latitude_bin"], dropna=False)
        .agg(n_sites=("site_id", "nunique"), median_doy=("median_doy", "median"))
        .reset_index()
        .sort_values(["country_name", "bbch_norm", "latitude_bin"])
    )
    altitude_bins = (
        gradient_base.groupby(["country_name", "bbch_norm", "altitude_bin"], dropna=False)
        .agg(n_sites=("site_id", "nunique"), median_doy=("median_doy", "median"))
        .reset_index()
        .sort_values(["country_name", "bbch_norm", "altitude_bin"])
    )
    latitude_bins.to_csv(data_dir / "latitude_bbch_median_doy_bins.csv", index=False)
    altitude_bins.to_csv(data_dir / "altitude_bbch_median_doy_bins.csv", index=False)

    return {
        "coverage": coverage,
        "site_span": site_span,
        "site_bbch": site_bbch,
        "latitude_bins": latitude_bins,
        "altitude_bins": altitude_bins,
    }


def plot_coverage_heatmap(coverage: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import matplotlib.colors as colors
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(16, 8), sharey=True)
    for ax, country in zip(axes, ["France", "Germany"], strict=False):
        subset = coverage[coverage["country_name"].eq(country)]
        years = np.arange(subset["year"].min(), subset["year"].max() + 1)
        matrix = (
            subset.pivot_table(index="bbch_norm", columns="year", values="n_observations", aggfunc="sum")
            .reindex(index=KEY_BBCH, columns=years)
            .to_numpy(dtype=float)
        )
        masked = np.ma.masked_invalid(matrix)
        masked = np.ma.masked_where(masked <= 0, masked)
        im = ax.imshow(masked, aspect="auto", interpolation="nearest", cmap="YlGnBu", norm=colors.LogNorm(vmin=1))
        ax.set_title(country)
        ax.set_ylabel("BBCH code")
        ax.set_yticks(np.arange(len(KEY_BBCH)))
        ax.set_yticklabels(KEY_BBCH)
        tick_idx = np.linspace(0, len(years) - 1, min(10, len(years))).round().astype(int)
        ax.set_xticks(tick_idx)
        ax.set_xticklabels(years[tick_idx], rotation=0)
        ax.set_xlabel("Year")
        cbar = fig.colorbar(im, ax=ax, pad=0.01, shrink=0.85)
        cbar.set_label("Observation count")
    fig.tight_layout()
    save_figure(fig, fig_dir, "bbch_year_coverage_heatmap", dpi)
    plt.close(fig)


def setup_map(ax, ccrs, cfeature, extent: list[float]) -> None:
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#e9f0f5", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#f7f5ef", zorder=0)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), edgecolor="#7b8790", linewidth=0.4)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor="#737373", linewidth=0.5)
    gridlines = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        linewidth=0.25,
        color="#a9a9a9",
        alpha=0.4,
        linestyle="--",
    )
    gridlines.top_labels = False
    gridlines.right_labels = False
    gridlines.xlabel_style = {"size": 9}
    gridlines.ylabel_style = {"size": 9}


def plot_site_span_maps(site_span: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt

    extent = [-6.5, 16.0, 41.0, 55.5]
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), subplot_kw={"projection": ccrs.PlateCarree()})
    for row, country in enumerate(["France", "Germany"]):
        subset = site_span[site_span["country_name"].eq(country)]
        for col, field in enumerate(["first_year", "last_year"]):
            ax = axes[row, col]
            setup_map(ax, ccrs, cfeature, extent)
            values = subset[field]
            sc = ax.scatter(
                subset["longitude"],
                subset["latitude"],
                c=values,
                s=10 + 40 * np.sqrt(subset["n_observations"] / subset["n_observations"].max()),
                cmap="viridis",
                alpha=0.72,
                linewidths=0,
                transform=ccrs.PlateCarree(),
                zorder=3,
            )
            ax.set_title(f"{country}: {field.replace('_', ' ')}")
            cbar = fig.colorbar(sc, ax=ax, shrink=0.72, pad=0.02)
            cbar.set_label("Year")
    fig.tight_layout()
    save_figure(fig, fig_dir, "site_first_last_year_maps", dpi)
    plt.close(fig)


def plot_bbch_median_doy_maps(site_bbch: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt

    extent = [-6.5, 16.0, 41.0, 55.5]
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), subplot_kw={"projection": ccrs.PlateCarree()})
    for ax, bbch in zip(axes.ravel(), MAP_BBCH, strict=False):
        subset = site_bbch[site_bbch["bbch_norm"].eq(bbch)]
        setup_map(ax, ccrs, cfeature, extent)
        if subset.empty:
            ax.set_axis_off()
            continue
        sc = ax.scatter(
            subset["longitude"],
            subset["latitude"],
            c=subset["median_doy"],
            s=12 + 30 * np.sqrt(subset["n_observations"] / subset["n_observations"].max()),
            cmap="magma",
            alpha=0.72,
            linewidths=0,
            transform=ccrs.PlateCarree(),
            zorder=3,
        )
        ax.set_title(f"{BBCH_LABELS[bbch]} median DOY")
        cbar = fig.colorbar(sc, ax=ax, shrink=0.72, pad=0.02)
        cbar.set_label("Median DOY")
    fig.tight_layout()
    save_figure(fig, fig_dir, "site_bbch_median_doy_maps", dpi)
    plt.close(fig)


def plot_geographic_gradients(tables: dict[str, pd.DataFrame], fig_dir: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, len(MAP_BBCH), figsize=(16, 8), sharey=False)
    for col, bbch in enumerate(MAP_BBCH):
        lat_ax = axes[0, col]
        alt_ax = axes[1, col]
        for country in ["France", "Germany"]:
            lat = tables["latitude_bins"][
                tables["latitude_bins"]["country_name"].eq(country)
                & tables["latitude_bins"]["bbch_norm"].eq(bbch)
                & tables["latitude_bins"]["n_sites"].ge(5)
            ]
            alt = tables["altitude_bins"][
                tables["altitude_bins"]["country_name"].eq(country)
                & tables["altitude_bins"]["bbch_norm"].eq(bbch)
                & tables["altitude_bins"]["n_sites"].ge(5)
            ]
            if not lat.empty:
                lat_ax.plot(lat["latitude_bin"], lat["median_doy"], marker="o", linewidth=1.6, color=COUNTRY_COLORS[country], label=country)
            if not alt.empty:
                alt_ax.plot(alt["altitude_bin"], alt["median_doy"], marker="o", linewidth=1.6, color=COUNTRY_COLORS[country], label=country)
        lat_ax.set_title(BBCH_LABELS[bbch])
        lat_ax.set_xlabel("Latitude")
        lat_ax.set_ylabel("Median DOY")
        alt_ax.set_xlabel("Altitude (m)")
        alt_ax.set_ylabel("Median DOY")
        lat_ax.grid(color="#dddddd", linewidth=0.5)
        alt_ax.grid(color="#dddddd", linewidth=0.5)
        if col == 0:
            lat_ax.legend(frameon=False, loc="best")
    fig.tight_layout()
    save_figure(fig, fig_dir, "latitude_altitude_bbch_doy_gradients", dpi)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    args.fig_dir.mkdir(parents=True, exist_ok=True)
    args.data_dir.mkdir(parents=True, exist_ok=True)

    df = load_data(args.input)
    tables = build_summary_tables(df, args.data_dir)
    plot_coverage_heatmap(tables["coverage"], args.fig_dir, args.dpi)
    plot_site_span_maps(tables["site_span"], args.fig_dir, args.dpi)
    plot_bbch_median_doy_maps(tables["site_bbch"], args.fig_dir, args.dpi)
    plot_geographic_gradients(tables, args.fig_dir, args.dpi)

    print(f"Input records used: {len(df):,}")
    print(f"Sites summarized: {len(tables['site_span']):,}")
    print(f"Figures written to: {args.fig_dir}")
    print(f"Derived CSVs written to: {args.data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
