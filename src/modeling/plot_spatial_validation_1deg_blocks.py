#!/usr/bin/env python
"""Plot ERA5-Land-centered 1-degree spatial validation blocks."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VALIDATION_DIR = (
    REPO_ROOT
    / "data/phenology/derived/modeling/france_germany_four_stage/validation"
)
DEFAULT_EVENTS = DEFAULT_VALIDATION_DIR / "modeling_event_index.csv"
DEFAULT_BLOCK_FOLDS = DEFAULT_VALIDATION_DIR / "outer_spatial_block_folds.csv"
DEFAULT_BOUNDARIES = REPO_ROOT / "data/topography/metadata/countries.geojson"
DEFAULT_FIG_DIR = REPO_ROOT / "fig/spatial_validation"
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/spatial_validation_1deg_blocks"
)
DEFAULT_STEM = "france_germany_era5_centered_1deg_validation_blocks"
DOUBLE_COLUMN_WIDTH_IN = 7.00
DOUBLE_COLUMN_HEIGHT_IN = 5.35
AXIS_LABEL_SIZE = 10
TICK_LABEL_SIZE = 10
LEGEND_FONT_SIZE = 8
SUMMARY_FONT_SIZE = 8
COUNTRY_ISO2 = {"France": "FR", "Germany": "DE"}
FOLD_COLORS = {
    1: "#1b9e77",
    2: "#d95f02",
    3: "#7570b3",
    4: "#e7298a",
    5: "#66a61e",
}
BLOCK_PATTERN = re.compile(r"lat(?P<lat>[+-]\d+(?:\.\d+)?)_lon(?P<lon>[+-]\d+(?:\.\d+)?)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--block-folds", type=Path, default=DEFAULT_BLOCK_FOLDS)
    parser.add_argument("--country-boundaries", type=Path, default=DEFAULT_BOUNDARIES)
    parser.add_argument("--fig-dir", type=Path, default=DEFAULT_FIG_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--stem", default=DEFAULT_STEM)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--label-blocks", action="store_true")
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


def parse_block_lower_left(block_id: str) -> tuple[float, float]:
    match = BLOCK_PATTERN.search(block_id)
    if not match:
        raise ValueError(f"Cannot parse 1-degree block id: {block_id}")
    return float(match.group("lat")), float(match.group("lon"))


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


def geometry_intersects_extent(geometry: object, extent: tuple[float, float, float, float]) -> bool:
    lon_min, lon_max, lat_min, lat_max = extent
    min_x, min_y, max_x, max_y = geometry.bounds
    return not (max_x < lon_min or min_x > lon_max or max_y < lat_min or min_y > lat_max)


def iter_polygons(geometry: object):
    if geometry.geom_type == "Polygon":
        yield geometry
    elif geometry.geom_type == "MultiPolygon":
        yield from geometry.geoms
    elif geometry.geom_type == "GeometryCollection":
        for part in geometry.geoms:
            yield from iter_polygons(part)


def draw_geometry(ax, geometry: object, extent: tuple[float, float, float, float]) -> None:
    for polygon in iter_polygons(geometry):
        if not geometry_intersects_extent(polygon, extent):
            continue
        x, y = polygon.exterior.xy
        ax.fill(x, y, facecolor="#f7f5ef", edgecolor="#555555", linewidth=0.75, zorder=1)
        for interior in polygon.interiors:
            hole_x, hole_y = interior.xy
            ax.fill(hole_x, hole_y, facecolor="white", edgecolor="#777777", linewidth=0.25, zorder=1)


def build_block_summary(events: pd.DataFrame, folds: pd.DataFrame) -> pd.DataFrame:
    work = events.copy()
    grouped = (
        work.groupby("validation_block_1deg_id", as_index=False)
        .agg(
            events=("record_id", "size"),
            sites=("site_uid", "nunique"),
            site_years=("weather_id", "nunique"),
            era5_grids=("era5_grid_id", "nunique"),
            countries=("country", lambda values: ";".join(sorted(set(values)))),
            stages=("target_stage", lambda values: ";".join(sorted(set(values)))),
            first_year=("year", "min"),
            last_year=("year", "max"),
            median_lat=("lat", "median"),
            median_lon=("lon", "median"),
            median_era5_grid_lat=("era5_grid_lat", "median"),
            median_era5_grid_lon=("era5_grid_lon", "median"),
            median_elevation_m=("dem_elevation_m", "median"),
        )
    )
    grouped = grouped.merge(folds, on="validation_block_1deg_id", how="left", validate="one_to_one")
    if grouped["outer_spatial_fold"].isna().any():
        missing = grouped.loc[grouped["outer_spatial_fold"].isna(), "validation_block_1deg_id"].tolist()
        raise ValueError(f"Missing outer folds for blocks: {missing[:5]}")
    coordinates = grouped["validation_block_1deg_id"].map(parse_block_lower_left)
    grouped["block_lat_lower"] = [lat for lat, _ in coordinates]
    grouped["block_lon_lower"] = [lon for _, lon in coordinates]
    grouped["block_lat_center"] = grouped["block_lat_lower"] + 0.5
    grouped["block_lon_center"] = grouped["block_lon_lower"] + 0.5
    grouped["outer_spatial_fold"] = grouped["outer_spatial_fold"].astype(int)
    return grouped.sort_values(["outer_spatial_fold", "block_lat_lower", "block_lon_lower"]).reset_index(drop=True)


def plot_blocks(
    blocks: pd.DataFrame,
    events: pd.DataFrame,
    geometries: dict[str, object],
    fig_dir: Path,
    stem: str,
    dpi: int,
    label_blocks: bool,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Rectangle

    lon_min = float(blocks["block_lon_lower"].min() - 0.6)
    lon_max = float(blocks["block_lon_lower"].max() + 1.6)
    lat_min = float(blocks["block_lat_lower"].min() - 0.6)
    lat_max = float(blocks["block_lat_lower"].max() + 1.6)
    extent = (lon_min, lon_max, lat_min, lat_max)

    fig, ax = plt.subplots(
        figsize=(DOUBLE_COLUMN_WIDTH_IN, DOUBLE_COLUMN_HEIGHT_IN),
        constrained_layout=True,
    )
    ax.set_facecolor("#e9f0f5")
    for iso2 in COUNTRY_ISO2.values():
        draw_geometry(ax, geometries[iso2], extent)

    for lon in np.arange(np.floor(lon_min), np.ceil(lon_max) + 0.1, 1.0):
        ax.axvline(lon, color="#b8b8b8", linewidth=0.35, alpha=0.48, zorder=0)
    for lat in np.arange(np.floor(lat_min), np.ceil(lat_max) + 0.1, 1.0):
        ax.axhline(lat, color="#b8b8b8", linewidth=0.35, alpha=0.48, zorder=0)

    for row in blocks.itertuples(index=False):
        color = FOLD_COLORS[int(row.outer_spatial_fold)]
        rectangle = Rectangle(
            (row.block_lon_lower, row.block_lat_lower),
            1.0,
            1.0,
            facecolor=color,
            edgecolor=color,
            linewidth=0.9,
            alpha=0.34,
            zorder=2,
        )
        ax.add_patch(rectangle)
        if label_blocks:
            ax.text(
                row.block_lon_center,
                row.block_lat_center,
                str(int(row.outer_spatial_fold)),
                ha="center",
                va="center",
                fontsize=6.5,
                color="#222222",
                zorder=5,
            )

    point_sample = events.drop_duplicates("site_uid")
    ax.scatter(
        point_sample["lon"],
        point_sample["lat"],
        s=5,
        facecolor="#111111",
        edgecolor="none",
        alpha=0.16,
        zorder=3,
    )

    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Longitude", fontsize=AXIS_LABEL_SIZE)
    ax.set_ylabel("Latitude", fontsize=AXIS_LABEL_SIZE)
    ax.tick_params(axis="both", labelsize=TICK_LABEL_SIZE)

    fold_handles = [
        Patch(facecolor=color, edgecolor=color, alpha=0.34, label=f"Fold {fold}")
        for fold, color in FOLD_COLORS.items()
    ]
    site_handle = Line2D(
        [0],
        [0],
        marker="o",
        color="none",
        label="Sites",
        markerfacecolor="#111111",
        markeredgecolor="none",
        markersize=4,
        alpha=0.42,
    )
    ax.legend(
        handles=fold_handles + [site_handle],
        loc="lower left",
        frameon=True,
        framealpha=0.94,
        fontsize=LEGEND_FONT_SIZE,
        ncol=3,
        borderpad=0.45,
        handlelength=1.35,
        handleheight=0.82,
        handletextpad=0.45,
        columnspacing=0.85,
        labelspacing=0.45,
    )
    summary_text = (
        f"{len(blocks):,} active 1° blocks\n"
        f"{len(point_sample):,} sites\n"
        f"{int(events['era5_grid_id'].nunique()):,} ERA5-Land grids\n"
        f"{len(events):,} event records"
    )
    ax.text(
        0.805,
        0.018,
        summary_text,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        multialignment="left",
        fontsize=SUMMARY_FONT_SIZE,
        color="#333333",
        bbox={"facecolor": "white", "edgecolor": "#cccccc", "alpha": 0.88, "pad": 5.0},
        zorder=6,
    )

    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / f"{stem}.png", dpi=dpi)
    fig.savefig(fig_dir / f"{stem}.pdf")
    plt.close(fig)


def write_outputs(blocks: pd.DataFrame, events: pd.DataFrame, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    blocks.to_csv(output_dir / "block_distribution_summary.csv", index=False)
    by_fold_country = (
        events.groupby(["outer_spatial_fold", "country"], as_index=False)
        .agg(
            events=("record_id", "size"),
            sites=("site_uid", "nunique"),
            site_years=("weather_id", "nunique"),
            era5_grids=("era5_grid_id", "nunique"),
            one_degree_blocks=("validation_block_1deg_id", "nunique"),
        )
        .sort_values(["outer_spatial_fold", "country"])
    )
    by_fold_country.to_csv(output_dir / "block_distribution_by_fold_country.csv", index=False)
    by_fold = (
        blocks.groupby("outer_spatial_fold", as_index=False)
        .agg(
            one_degree_blocks=("validation_block_1deg_id", "nunique"),
            events=("events", "sum"),
            sites=("sites", "sum"),
            site_years=("site_years", "sum"),
            era5_grids=("era5_grids", "sum"),
            median_events_per_block=("events", "median"),
            max_events_in_block=("events", "max"),
        )
        .sort_values("outer_spatial_fold")
    )
    by_fold.to_csv(output_dir / "block_distribution_by_fold.csv", index=False)
    summary = {
        "n_active_1deg_blocks": int(blocks["validation_block_1deg_id"].nunique()),
        "n_event_records": int(len(events)),
        "n_sites": int(events["site_uid"].nunique()),
        "n_site_years": int(events["weather_id"].nunique()),
        "n_era5_land_grids": int(events["era5_grid_id"].nunique()),
        "n_outer_folds": int(blocks["outer_spatial_fold"].nunique()),
        "block_count_by_fold": {
            str(int(row.outer_spatial_fold)): int(row.one_degree_blocks)
            for row in by_fold.itertuples(index=False)
        },
        "event_count_by_fold": {
            str(int(row.outer_spatial_fold)): int(row.events)
            for row in by_fold.itertuples(index=False)
        },
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    events = pd.read_csv(args.events, dtype={"site_id": "string"}, low_memory=False)
    folds = pd.read_csv(args.block_folds)
    required = {
        "record_id",
        "weather_id",
        "site_uid",
        "country",
        "year",
        "target_stage",
        "lat",
        "lon",
        "era5_grid_id",
        "era5_grid_lat",
        "era5_grid_lon",
        "validation_block_1deg_id",
        "outer_spatial_fold",
        "dem_elevation_m",
    }
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"Event index is missing columns: {sorted(missing)}")
    blocks = build_block_summary(events, folds)
    geometries = load_country_geometries(args.country_boundaries)
    plot_blocks(blocks, events, geometries, args.fig_dir, args.stem, args.dpi, args.label_blocks)
    summary = write_outputs(blocks, events, args.output_dir)

    print("ERA5-Land-centered 1-degree validation blocks")
    print(f"Active 1° blocks: {summary['n_active_1deg_blocks']:,}")
    print(f"Event records: {summary['n_event_records']:,}")
    print(f"Sites: {summary['n_sites']:,}")
    print(f"ERA5-Land grids: {summary['n_era5_land_grids']:,}")
    print(f"Block count by outer fold: {summary['block_count_by_fold']}")
    print(f"Figure: {(args.fig_dir / f'{args.stem}.png').relative_to(REPO_ROOT)}")
    print(f"Summary: {(args.output_dir / 'block_distribution_summary.csv').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
