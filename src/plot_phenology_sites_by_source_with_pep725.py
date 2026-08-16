#!/usr/bin/env python
"""Plot grape phenology sites by source, including selected PEP725 countries."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import pandas as pd


DEFAULT_INPUTS = [
    Path("data/phenology/processed/france_grape_phenology_complete.csv"),
    Path("data/phenology/processed/germany_grape_phenology_complete.csv"),
    Path("data/phenology/processed/pep725_selected_countries_grape_phenology_complete.csv"),
]
EXTENT = [-7.5, 23.5, 37.2, 55.5]
COUNTRY_COLORS = {
    "France": "#1f78b4",
    "Germany": "#d95f02",
    "Austria": "#33a02c",
    "Switzerland": "#7570b3",
    "Slovakia": "#e7298a",
    "Croatia": "#66a61e",
    "Spain": "#e6ab02",
}
COUNTRY_ORDER = ["France", "Germany", "Austria", "Switzerland", "Slovakia", "Croatia", "Spain"]
DEFAULT_START_YEAR = 1951


def configure_matplotlib() -> None:
    cache_dir = Path(tempfile.gettempdir()) / "grape_growth_stage_mplconfig"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "axes.unicode_minus": False,
        }
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        default=DEFAULT_INPUTS,
        help="Processed phenology table(s) to map.",
    )
    parser.add_argument(
        "--fig-dir",
        type=Path,
        default=Path("fig/phenology_distribution"),
        help="Directory for map outputs.",
    )
    parser.add_argument(
        "--data-out-dir",
        type=Path,
        default=Path("data/phenology/derived/phenology_distribution"),
        help="Directory for derived CSV summaries.",
    )
    parser.add_argument(
        "--stem",
        type=str,
        default="phenology_sites_by_source_with_pep725",
        help="Output filename stem for PNG/PDF.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Output image resolution.")
    parser.add_argument(
        "--start-year",
        type=int,
        default=DEFAULT_START_YEAR,
        help="Include only observations from this year onward (default: 1951).",
    )
    return parser.parse_args()


def load_data(paths: list[Path], start_year: int = DEFAULT_START_YEAR) -> pd.DataFrame:
    columns = [
        "source_system",
        "source_dataset",
        "country_name",
        "site_id",
        "site_name",
        "latitude",
        "longitude",
        "altitude",
        "year",
        "stage_event",
        "bbch_code",
        "cultivar_group",
    ]
    frames = []
    for path in paths:
        header = pd.read_csv(path, nrows=0)
        usecols = [col for col in columns if col in header.columns]
        frames.append(pd.read_csv(path, usecols=usecols, low_memory=False))

    df = pd.concat(frames, ignore_index=True)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df[df["year"].ge(start_year)].copy()
    df = df.dropna(subset=["latitude", "longitude"])
    df = df[
        df["latitude"].between(EXTENT[2], EXTENT[3])
        & df["longitude"].between(EXTENT[0], EXTENT[1])
    ].copy()
    return df


def site_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["source_system", "country_name", "site_id"], dropna=False)
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


def setup_map(ax, ccrs, cfeature) -> None:
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#e9f0f5", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#f7f5ef", zorder=0)
    ax.add_feature(cfeature.LAKES.with_scale("50m"), facecolor="#e9f0f5", edgecolor="#c7d2da", linewidth=0.25)
    ax.add_feature(cfeature.RIVERS.with_scale("50m"), edgecolor="#bfd0da", linewidth=0.35)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), edgecolor="#7b8790", linewidth=0.45)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor="#737373", linewidth=0.55)
    gridlines = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        linewidth=0.3,
        color="#a9a9a9",
        alpha=0.45,
        linestyle="--",
    )
    gridlines.top_labels = False
    gridlines.right_labels = False
    gridlines.xlabel_style = {"size": 8, "color": "#4d4d4d"}
    gridlines.ylabel_style = {"size": 8, "color": "#4d4d4d"}


def ordered_countries(sites: pd.DataFrame) -> list[str]:
    present = set(sites["country_name"])
    ordered = [country for country in COUNTRY_ORDER if country in present]
    ordered.extend(sorted(present - set(ordered)))
    return ordered


def plot_sites(sites: pd.DataFrame, fig_dir: Path, stem: str, dpi: int) -> None:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig = plt.figure(figsize=(12, 8))
    ax = plt.axes(projection=ccrs.PlateCarree())
    setup_map(ax, ccrs, cfeature)

    max_obs = sites["n_observations"].max()
    handles = []
    for country_name in ordered_countries(sites):
        group = sites[sites["country_name"] == country_name]
        sizes = 14 + 86 * (group["n_observations"] / max_obs).pow(0.45)
        color = COUNTRY_COLORS.get(country_name, "#666666")
        ax.scatter(
            group["longitude"],
            group["latitude"],
            s=sizes,
            c=color,
            alpha=0.64,
            edgecolors="white",
            linewidths=0.25,
            transform=ccrs.PlateCarree(),
            label=country_name,
            zorder=3,
        )
        handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                label=country_name,
                markerfacecolor=color,
                markersize=8,
            )
        )

    ax.legend(handles=handles, loc="lower left", frameon=True, framealpha=0.92, fontsize=9)
    ax.text(
        0.99,
        0.01,
        "Point size scales with observations per site",
        transform=ax.transAxes,
        fontsize=8,
        color="#4d4d4d",
        ha="right",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 3},
    )

    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / f"{stem}.png", dpi=dpi, bbox_inches="tight")
    fig.savefig(fig_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def write_summary(sites: pd.DataFrame, data_out_dir: Path, stem: str) -> None:
    data_out_dir.mkdir(parents=True, exist_ok=True)
    sites.to_csv(data_out_dir / f"{stem}_sites.csv", index=False)
    summary = (
        sites.groupby(["country_name"], dropna=False)
        .agg(
            n_sites=("site_id", "nunique"),
            n_observations=("n_observations", "sum"),
            first_year=("first_year", "min"),
            last_year=("last_year", "max"),
            min_latitude=("latitude", "min"),
            max_latitude=("latitude", "max"),
            min_longitude=("longitude", "min"),
            max_longitude=("longitude", "max"),
        )
        .reset_index()
        .sort_values("country_name")
    )
    summary.to_csv(data_out_dir / f"{stem}_country_summary.csv", index=False)


def main() -> int:
    args = parse_args()
    configure_matplotlib()

    df = load_data(args.input, args.start_year)
    sites = site_summary(df)
    write_summary(sites, args.data_out_dir, args.stem)
    plot_sites(sites, args.fig_dir, args.stem, args.dpi)

    print(f"Input rows: {len(df):,}")
    print(f"Study period: {args.start_year} onward")
    print(f"Unique sites: {len(sites):,}")
    print(f"Figure written to: {args.fig_dir / f'{args.stem}.png'}")
    print(f"Derived CSVs written to: {args.data_out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
