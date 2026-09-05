#!/usr/bin/env python
"""Plot France and Germany grape phenology observation distributions."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import pandas as pd


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
        default=[
            Path("data/phenology/processed/france_grape_phenology_complete.csv"),
            Path("data/phenology/processed/germany_grape_phenology_complete.csv"),
        ],
        help="Processed phenology table(s) to map.",
    )
    parser.add_argument(
        "--out-dir",
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
        "--dpi",
        type=int,
        default=300,
        help="Output image resolution.",
    )
    return parser.parse_args()


def load_data(paths: list[Path]) -> pd.DataFrame:
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
        "bbch_code",
        "cultivar_group",
    ]
    df = pd.concat(
        [pd.read_csv(path, usecols=columns, low_memory=False) for path in paths],
        ignore_index=True,
    )
    df = df.dropna(subset=["latitude", "longitude"])
    df = df[
        df["latitude"].between(40.0, 56.5)
        & df["longitude"].between(-7.5, 16.5)
    ].copy()
    df["source_label"] = df["source_system"].map(
        {"france_tempo": "France TEMPO", "germany_dwd": "Germany DWD"}
    ).fillna(df["source_system"])
    return df


def site_summary(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby(["source_system", "source_label", "country_name", "site_id"], dropna=False)
        .agg(
            site_name=("site_name", "first"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
            altitude=("altitude", "first"),
            n_observations=("site_id", "size"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            n_years=("year", "nunique"),
            n_stages=("stage_event", "nunique"),
        )
        .reset_index()
    )
    return grouped


def setup_map(ax, ccrs, cfeature, extent: list[float]) -> None:
    ax.set_extent(extent, crs=ccrs.PlateCarree())
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


def save_figure(fig, out_dir: Path, stem: str, dpi: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"{stem}.png", dpi=dpi, bbox_inches="tight")
    fig.savefig(out_dir / f"{stem}.pdf", bbox_inches="tight")


def plot_sites(sites: pd.DataFrame, out_dir: Path, dpi: int) -> None:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    colors = {"france_tempo": "#1f78b4", "germany_dwd": "#d95f02"}
    extent = [-6.5, 16.0, 41.0, 55.5]

    fig = plt.figure(figsize=(11, 9))
    ax = plt.axes(projection=ccrs.PlateCarree())
    setup_map(ax, ccrs, cfeature, extent)

    max_obs = sites["n_observations"].max()
    for source_system, group in sites.groupby("source_system"):
        sizes = 14 + 86 * (group["n_observations"] / max_obs).pow(0.45)
        ax.scatter(
            group["longitude"],
            group["latitude"],
            s=sizes,
            c=colors.get(source_system, "#666666"),
            alpha=0.64,
            edgecolors="white",
            linewidths=0.25,
            transform=ccrs.PlateCarree(),
            label=group["source_label"].iloc[0],
            zorder=3,
        )

    handles = [
        Line2D([0], [0], marker="o", color="none", label="France TEMPO", markerfacecolor=colors["france_tempo"], markersize=8),
        Line2D([0], [0], marker="o", color="none", label="Germany DWD", markerfacecolor=colors["germany_dwd"], markersize=8),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True, framealpha=0.92, fontsize=9)
    ax.text(
        0.01,
        0.01,
        "Point size scales with observations per site",
        transform=ax.transAxes,
        fontsize=8,
        color="#4d4d4d",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 3},
    )
    save_figure(fig, out_dir, "phenology_sites_by_source", dpi)
    plt.close(fig)


def plot_density(df: pd.DataFrame, out_dir: Path, dpi: int) -> None:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt

    extent = [-6.5, 16.0, 41.0, 55.5]
    fig = plt.figure(figsize=(11, 9))
    ax = plt.axes(projection=ccrs.PlateCarree())
    setup_map(ax, ccrs, cfeature, extent)

    hb = ax.hexbin(
        df["longitude"],
        df["latitude"],
        C=None,
        gridsize=75,
        mincnt=1,
        bins="log",
        cmap="viridis",
        linewidths=0,
        alpha=0.82,
        transform=ccrs.PlateCarree(),
        zorder=3,
    )
    cbar = fig.colorbar(hb, ax=ax, shrink=0.72, pad=0.02)
    cbar.set_label("Observation count per hexagon (log scale)")
    save_figure(fig, out_dir, "phenology_observation_density", dpi)
    plt.close(fig)


def plot_stage_panels(df: pd.DataFrame, out_dir: Path, dpi: int) -> None:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt

    preferred = [
        "Germination / sprouting / bud development",
        "Leaf development (main shoot)",
        "Flowering (main shoot)",
        "Development of fruit",
        "Ripening of fruit and seed",
        "Beginning of dormancy, die off of leaves, stem, ...",
    ]
    available = [stage for stage in preferred if stage in set(df["stage_event"].dropna())]
    if len(available) < 6:
        top = df["stage_event"].value_counts().head(6).index.tolist()
        available = list(dict.fromkeys(available + top))[:6]

    extent = [-6.5, 16.0, 41.0, 55.5]
    fig, axes = plt.subplots(
        2,
        3,
        figsize=(15, 10),
        subplot_kw={"projection": ccrs.PlateCarree()},
    )
    for ax, stage in zip(axes.ravel(), available, strict=False):
        setup_map(ax, ccrs, cfeature, extent)
        subset = (
            df[df["stage_event"] == stage]
            .groupby(["source_system", "site_id"], dropna=False)
            .agg(latitude=("latitude", "first"), longitude=("longitude", "first"), n=("site_id", "size"))
            .reset_index()
        )
        sizes = 8 + 50 * (subset["n"] / subset["n"].max()).pow(0.45)
        ax.scatter(
            subset["longitude"],
            subset["latitude"],
            s=sizes,
            c="#7b3294",
            alpha=0.55,
            edgecolors="white",
            linewidths=0.15,
            transform=ccrs.PlateCarree(),
            zorder=3,
        )
        title = stage.replace(" / ", " / \n")
        ax.set_title(f"{title}\n{len(subset):,} sites", fontsize=9)

    for ax in axes.ravel()[len(available):]:
        ax.set_axis_off()
    save_figure(fig, out_dir, "phenology_stage_site_panels", dpi)
    plt.close(fig)


def write_summary(df: pd.DataFrame, sites: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    site_counts = (
        sites.groupby(["source_system", "country_name"], dropna=False)
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
    )
    stage_counts = (
        df.groupby(["source_system", "stage_event"], dropna=False)
        .agg(
            n_observations=("site_id", "size"),
            n_sites=("site_id", "nunique"),
            first_year=("year", "min"),
            last_year=("year", "max"),
        )
        .reset_index()
        .sort_values(["source_system", "n_observations"], ascending=[True, False])
    )
    site_counts.to_csv(out_dir / "map_site_summary.csv", index=False)
    stage_counts.to_csv(out_dir / "map_stage_summary.csv", index=False)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    df = load_data(args.input)
    sites = site_summary(df)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.data_out_dir.mkdir(parents=True, exist_ok=True)
    sites.to_csv(args.data_out_dir / "map_sites.csv", index=False)
    write_summary(df, sites, args.data_out_dir)
    plot_sites(sites, args.out_dir, args.dpi)
    plot_density(df, args.out_dir, args.dpi)
    plot_stage_panels(df, args.out_dir, args.dpi)

    print(f"Input rows: {len(df):,}")
    print(f"Unique sites: {len(sites):,}")
    print(f"Figures written to: {args.out_dir}")
    print(f"Derived CSVs written to: {args.data_out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
