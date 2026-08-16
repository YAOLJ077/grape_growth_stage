#!/usr/bin/env python
"""Plot nested spatial validation as five stacked fold layers."""

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
VALIDATION_DIR = REPO_ROOT / "data/phenology/derived/modeling/france_germany_four_stage/validation"
DEFAULT_EVENTS = VALIDATION_DIR / "modeling_event_index.csv"
DEFAULT_OUTER_FOLDS = VALIDATION_DIR / "outer_spatial_block_folds.csv"
DEFAULT_INNER_FOLDS = VALIDATION_DIR / "inner_spatial_block_folds.csv"
DEFAULT_BOUNDARIES = REPO_ROOT / "data/topography/metadata/countries.geojson"
DEFAULT_FIG_DIR = REPO_ROOT / "fig/spatial_validation"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "results/france_germany_four_stage/spatial_validation_1deg_blocks"
DEFAULT_STEM = "france_germany_era5_centered_1deg_nested_validation_layers"
COUNTRY_ISO2 = {"France": "FR", "Germany": "DE"}
BLOCK_PATTERN = re.compile(r"lat(?P<lat>[+-]\d+(?:\.\d+)?)_lon(?P<lon>[+-]\d+(?:\.\d+)?)$")

ROLE_STYLES = {
    "Inner training": {"color": "#9ecae1", "alpha": 0.42},
    "Inner validation": {"color": "#f0b35a", "alpha": 0.78},
    "Outer test": {"color": "#c0392b", "alpha": 0.86},
}
SITE_COLOR = "#222222"
BOUNDARY_COLOR = "#4c4c4c"
PANEL_LABEL_FONT_SIZE = 11.0
LEGEND_FONT_SIZE = 10.0
LEGEND_SITE_SIZE = 12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--outer-folds", type=Path, default=DEFAULT_OUTER_FOLDS)
    parser.add_argument("--inner-folds", type=Path, default=DEFAULT_INNER_FOLDS)
    parser.add_argument("--country-boundaries", type=Path, default=DEFAULT_BOUNDARIES)
    parser.add_argument("--fig-dir", type=Path, default=DEFAULT_FIG_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--stem", default=DEFAULT_STEM)
    parser.add_argument("--shown-inner-fold", type=int, default=1)
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


def iter_polygons(geometry: object):
    if geometry.geom_type == "Polygon":
        yield geometry
    elif geometry.geom_type == "MultiPolygon":
        yield from geometry.geoms
    elif geometry.geom_type == "GeometryCollection":
        for part in geometry.geoms:
            yield from iter_polygons(part)


def geometry_intersects_extent(geometry: object, extent: tuple[float, float, float, float]) -> bool:
    lon_min, lon_max, lat_min, lat_max = extent
    min_x, min_y, max_x, max_y = geometry.bounds
    return not (max_x < lon_min or min_x > lon_max or max_y < lat_min or min_y > lat_max)


def build_block_table(
    events: pd.DataFrame,
    outer_folds: pd.DataFrame,
    inner_folds: pd.DataFrame,
    shown_inner_fold: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    block_stats = (
        events.groupby("validation_block_1deg_id", as_index=False)
        .agg(
            events=("record_id", "size"),
            sites=("site_uid", "nunique"),
            site_years=("weather_id", "nunique"),
            era5_grids=("era5_grid_id", "nunique"),
        )
    )
    blocks = block_stats.merge(
        outer_folds,
        on="validation_block_1deg_id",
        how="left",
        validate="one_to_one",
    )
    if blocks["outer_spatial_fold"].isna().any():
        missing = blocks.loc[blocks["outer_spatial_fold"].isna(), "validation_block_1deg_id"].tolist()
        raise ValueError(f"Missing outer fold assignment for blocks: {missing[:5]}")
    coordinates = blocks["validation_block_1deg_id"].map(parse_block_lower_left)
    blocks["block_lat_lower"] = [lat for lat, _ in coordinates]
    blocks["block_lon_lower"] = [lon for _, lon in coordinates]
    blocks["outer_spatial_fold"] = blocks["outer_spatial_fold"].astype(int)

    layer_records: list[dict[str, object]] = []
    for outer_fold in sorted(blocks["outer_spatial_fold"].unique()):
        inner_for_outer = inner_folds.loc[inner_folds["outer_test_fold"].eq(outer_fold)].copy()
        inner_for_outer["inner_spatial_fold"] = inner_for_outer["inner_spatial_fold"].astype(int)
        inner_map = dict(
            zip(inner_for_outer["validation_block_1deg_id"], inner_for_outer["inner_spatial_fold"])
        )
        for row in blocks.itertuples(index=False):
            if int(row.outer_spatial_fold) == int(outer_fold):
                role = "Outer test"
                inner_fold = np.nan
            else:
                inner_fold = inner_map.get(row.validation_block_1deg_id)
                if inner_fold is None:
                    raise ValueError(
                        "Missing inner fold assignment for "
                        f"outer fold {outer_fold}, block {row.validation_block_1deg_id}"
                    )
                role = "Inner validation" if int(inner_fold) == shown_inner_fold else "Inner training"
            layer_records.append(
                {
                    "outer_test_fold": int(outer_fold),
                    "validation_block_1deg_id": row.validation_block_1deg_id,
                    "displayed_role": role,
                    "inner_spatial_fold": inner_fold,
                    "outer_spatial_fold": int(row.outer_spatial_fold),
                    "events": int(row.events),
                    "sites": int(row.sites),
                    "site_years": int(row.site_years),
                    "era5_grids": int(row.era5_grids),
                    "block_lat_lower": float(row.block_lat_lower),
                    "block_lon_lower": float(row.block_lon_lower),
                }
            )
    layer_table = pd.DataFrame(layer_records)
    return blocks, layer_table


def add_plane(ax, lon_min: float, lon_max: float, lat_min: float, lat_max: float, z_value: float) -> None:
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    vertices = [
        (lon_min, lat_min, z_value),
        (lon_max, lat_min, z_value),
        (lon_max, lat_max, z_value),
        (lon_min, lat_max, z_value),
    ]
    plane = Poly3DCollection(
        [vertices],
        facecolor="#eef3f6",
        edgecolor="#b8bec2",
        linewidth=0.45,
        alpha=0.30,
        zorder=0,
    )
    ax.add_collection3d(plane)


def add_grid(ax, lon_min: float, lon_max: float, lat_min: float, lat_max: float, z_value: float) -> None:
    for lon in np.arange(np.floor(lon_min), np.ceil(lon_max) + 0.1, 2.0):
        ax.plot(
            [lon, lon],
            [lat_min, lat_max],
            [z_value, z_value],
            color="#b7b7b7",
            linewidth=0.25,
            alpha=0.45,
            zorder=1,
        )
    for lat in np.arange(np.floor(lat_min), np.ceil(lat_max) + 0.1, 2.0):
        ax.plot(
            [lon_min, lon_max],
            [lat, lat],
            [z_value, z_value],
            color="#b7b7b7",
            linewidth=0.25,
            alpha=0.45,
            zorder=1,
        )


def add_country_boundaries(
    ax,
    geometries: dict[str, object],
    extent: tuple[float, float, float, float],
    z_value: float,
) -> None:
    for geometry in geometries.values():
        for polygon in iter_polygons(geometry):
            if not geometry_intersects_extent(polygon, extent):
                continue
            x, y = polygon.exterior.xy
            ax.plot(
                x,
                y,
                zs=z_value + 0.018,
                zdir="z",
                color=BOUNDARY_COLOR,
                linewidth=0.55,
                alpha=0.92,
                zorder=3,
            )
            for interior in polygon.interiors:
                hole_x, hole_y = interior.xy
                ax.plot(
                    hole_x,
                    hole_y,
                    zs=z_value + 0.018,
                    zdir="z",
                    color=BOUNDARY_COLOR,
                    linewidth=0.25,
                    alpha=0.65,
                    zorder=3,
                )


def add_blocks(ax, layer_blocks: pd.DataFrame, z_value: float) -> None:
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    for role, style in ROLE_STYLES.items():
        role_blocks = layer_blocks.loc[layer_blocks["displayed_role"].eq(role)]
        vertices = []
        for row in role_blocks.itertuples(index=False):
            lon = float(row.block_lon_lower)
            lat = float(row.block_lat_lower)
            vertices.append(
                [
                    (lon, lat, z_value + 0.035),
                    (lon + 1.0, lat, z_value + 0.035),
                    (lon + 1.0, lat + 1.0, z_value + 0.035),
                    (lon, lat + 1.0, z_value + 0.035),
                ]
            )
        if not vertices:
            continue
        collection = Poly3DCollection(
            vertices,
            facecolor=style["color"],
            edgecolor=style["color"],
            linewidth=0.45,
            alpha=style["alpha"],
            zorder=2,
        )
        ax.add_collection3d(collection)


def add_sites(ax, sites: pd.DataFrame, z_value: float) -> None:
    ax.scatter(
        sites["lon"].to_numpy(),
        sites["lat"].to_numpy(),
        zs=z_value + 0.08,
        zdir="z",
        s=1.0,
        c=SITE_COLOR,
        alpha=0.055,
        linewidths=0,
        depthshade=False,
        zorder=4,
    )


def add_layer_labels(ax, z_values: dict[int, float], lon_max: float, lat_max: float) -> None:
    for outer_fold, z_value in z_values.items():
        ax.text(
            lon_max + 0.35,
            lat_max - 0.35,
            z_value + 0.04,
            f"Outer group {outer_fold}",
            ha="left",
            va="center",
            fontsize=8.2,
            color="#222222",
            zorder=10,
        )


def plot_nested_layers(
    layer_table: pd.DataFrame,
    events: pd.DataFrame,
    geometries: dict[str, object],
    fig_dir: Path,
    stem: str,
    shown_inner_fold: int,
    dpi: int,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Polygon, Rectangle

    lon_min = float(layer_table["block_lon_lower"].min() - 0.6)
    lon_max = float(layer_table["block_lon_lower"].max() + 1.6)
    lat_min = float(layer_table["block_lat_lower"].min() - 0.6)
    lat_max = float(layer_table["block_lat_lower"].max() + 1.6)
    extent = (lon_min, lon_max, lat_min, lat_max)
    panel_labels = {1: "(a)", 2: "(b)", 3: "(c)", 4: "(d)", 5: "(e)"}

    fig = plt.figure(figsize=(7.0, 4.35))
    grid_spec = fig.add_gridspec(10, 2)
    axes = np.empty((3, 2), dtype=object)
    axes[0, 0] = fig.add_subplot(grid_spec[0:3, 0])
    axes[1, 0] = fig.add_subplot(grid_spec[3:6, 0])
    axes[2, 0] = fig.add_subplot(grid_spec[6:9, 0])
    axes[0, 1] = fig.add_subplot(grid_spec[3:6, 1])
    axes[1, 1] = fig.add_subplot(grid_spec[6:9, 1])
    axes[2, 1] = fig.add_subplot(grid_spec[0:3, 1])
    sites = events.drop_duplicates("site_uid")[["lon", "lat"]].copy()

    def draw_panel(ax, outer_fold: int) -> None:
        shear = 0.36
        y_scale = 0.47
        depth_x = 0.42
        depth_y = -0.24

        def project(x_values, y_values):
            x_array = np.asarray(x_values, dtype=float)
            y_array = np.asarray(y_values, dtype=float)
            projected_x = x_array - lon_min + shear * (y_array - lat_min)
            projected_y = y_scale * (y_array - lat_min)
            return projected_x, projected_y

        corner_x, corner_y = project(
            [lon_min, lon_max, lon_max, lon_min],
            [lat_min, lat_min, lat_max, lat_max],
        )
        plane = list(zip(corner_x, corner_y))
        back_plane = [(x + depth_x, y + depth_y) for x, y in plane]
        ax.add_patch(
            Polygon(
                back_plane,
                closed=True,
                facecolor="#dbe6ec",
                edgecolor="#b4bec4",
                linewidth=0.42,
                alpha=0.44,
                zorder=0,
            )
        )
        for i, j in ((0, 1), (1, 2), (2, 3), (3, 0)):
            ax.plot(
                [plane[i][0], back_plane[i][0], back_plane[j][0], plane[j][0]],
                [plane[i][1], back_plane[i][1], back_plane[j][1], plane[j][1]],
                color="#bdc7cc",
                linewidth=0.32,
                alpha=0.40,
                zorder=0.5,
            )
        ax.add_patch(
            Polygon(
                plane,
                closed=True,
                facecolor="#edf3f6",
                edgecolor="#aeb8be",
                linewidth=0.58,
                alpha=0.92,
                zorder=1,
            )
        )
        for iso2 in COUNTRY_ISO2.values():
            for polygon in iter_polygons(geometries[iso2]):
                if not geometry_intersects_extent(polygon, extent):
                    continue
                x, y = polygon.exterior.xy
                x_plot, y_plot = project(x, y)
                ax.fill(
                    x_plot,
                    y_plot,
                    facecolor="#f7f5ef",
                    edgecolor=BOUNDARY_COLOR,
                    linewidth=0.44,
                    alpha=0.96,
                    zorder=2,
                )
                for interior in polygon.interiors:
                    hole_x, hole_y = interior.xy
                    hole_x_plot, hole_y_plot = project(hole_x, hole_y)
                    ax.fill(
                        hole_x_plot,
                        hole_y_plot,
                        facecolor="white",
                        edgecolor="#777777",
                        linewidth=0.16,
                        zorder=2,
                    )

        for lon in np.arange(np.floor(lon_min), np.ceil(lon_max) + 0.1, 2.0):
            x_grid, y_grid = project([lon, lon], [lat_min, lat_max])
            ax.plot(x_grid, y_grid, color="#c4c4c4", linewidth=0.24, alpha=0.40, zorder=1.5)
        for lat in np.arange(np.floor(lat_min), np.ceil(lat_max) + 0.1, 2.0):
            x_grid, y_grid = project([lon_min, lon_max], [lat, lat])
            ax.plot(x_grid, y_grid, color="#c4c4c4", linewidth=0.24, alpha=0.40, zorder=1.5)

        layer_blocks = layer_table.loc[layer_table["outer_test_fold"].eq(outer_fold)]
        for role in ["Inner training", "Inner validation", "Outer test"]:
            style = ROLE_STYLES[role]
            role_blocks = layer_blocks.loc[layer_blocks["displayed_role"].eq(role)]
            for row in role_blocks.itertuples(index=False):
                x_block, y_block = project(
                    [
                        row.block_lon_lower,
                        row.block_lon_lower + 1.0,
                        row.block_lon_lower + 1.0,
                        row.block_lon_lower,
                    ],
                    [
                        row.block_lat_lower,
                        row.block_lat_lower,
                        row.block_lat_lower + 1.0,
                        row.block_lat_lower + 1.0,
                    ],
                )
                ax.add_patch(
                    Polygon(
                        list(zip(x_block, y_block)),
                        closed=True,
                        facecolor=style["color"],
                        edgecolor=style["color"],
                        linewidth=0.32 if role == "Inner training" else 0.46,
                        alpha=style["alpha"],
                        zorder=3 if role == "Inner training" else 4,
                    )
                )

        site_x, site_y = project(sites["lon"], sites["lat"])
        ax.scatter(
            site_x,
            site_y,
            s=0.9,
            c=SITE_COLOR,
            alpha=0.07,
            linewidths=0,
            zorder=5,
        )
        ax.text(
            0.018,
            0.955,
            f"{panel_labels[outer_fold]} Outer group {outer_fold}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=PANEL_LABEL_FONT_SIZE,
            color="#111111",
            bbox={"facecolor": "white", "edgecolor": "#bbbbbb", "alpha": 0.84, "pad": 1.4},
            zorder=10,
        )
        all_x = np.array([*corner_x, *(np.array(corner_x) + depth_x)])
        all_y = np.array([*corner_y, *(np.array(corner_y) + depth_y)])
        ax.set_xlim(all_x.min() - 0.25, all_x.max() + 0.25)
        ax.set_ylim(all_y.min() - 0.25, all_y.max() + 0.25)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

    for outer_fold in range(1, 6):
        row = outer_fold - 1 if outer_fold <= 3 else outer_fold - 4
        col = 0 if outer_fold <= 3 else 1
        draw_panel(axes[row, col], outer_fold)

    axes[2, 1].axis("off")

    legend_ax = fig.add_axes([0.505, 0.748, 0.465, 0.142])
    legend_ax.set_xlim(0, 1)
    legend_ax.set_ylim(0, 1)
    legend_ax.axis("off")
    legend_ax.add_patch(
        Rectangle(
            (0.0, 0.0),
            1.0,
            1.0,
            facecolor="white",
            edgecolor="#b5b5b5",
            linewidth=0.9,
            alpha=0.96,
            transform=legend_ax.transAxes,
            clip_on=False,
        )
    )

    def legend_patch(x: float, y: float, style: dict[str, object]) -> None:
        legend_ax.add_patch(
            Rectangle(
                (x, y - 0.100),
                0.060,
                0.155,
                facecolor=str(style["color"]),
                edgecolor=str(style["color"]),
                linewidth=0.8,
                alpha=float(style["alpha"]),
                transform=legend_ax.transAxes,
            )
        )

    legend_patch(0.035, 0.710, ROLE_STYLES["Inner training"])
    legend_ax.text(
        0.115,
        0.710,
        "Inner training set (3 inner folds)",
        transform=legend_ax.transAxes,
        ha="left",
        va="center",
        fontsize=LEGEND_FONT_SIZE,
        color="#111111",
    )
    legend_patch(0.035, 0.300, ROLE_STYLES["Inner validation"])
    legend_ax.text(
        0.115,
        0.300,
        "Inner validation set",
        transform=legend_ax.transAxes,
        ha="left",
        va="center",
        fontsize=LEGEND_FONT_SIZE,
        color="#111111",
    )
    legend_patch(0.505, 0.300, ROLE_STYLES["Outer test"])
    legend_ax.text(
        0.585,
        0.300,
        "Outer test set",
        transform=legend_ax.transAxes,
        ha="left",
        va="center",
        fontsize=LEGEND_FONT_SIZE,
        color="#111111",
    )
    legend_ax.scatter([0.825], [0.300], s=LEGEND_SITE_SIZE, c=SITE_COLOR, alpha=0.35, linewidths=0)
    legend_ax.text(
        0.875,
        0.300,
        "Sites",
        transform=legend_ax.transAxes,
        ha="left",
        va="center",
        fontsize=LEGEND_FONT_SIZE,
        color="#111111",
    )
    fig.subplots_adjust(left=0.025, right=0.985, top=0.985, bottom=0.025, wspace=0.075, hspace=0.00)

    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / f"{stem}.png", dpi=dpi)
    plt.close(fig)

def write_outputs(layer_table: pd.DataFrame, output_dir: Path, shown_inner_fold: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    layer_table.to_csv(output_dir / "nested_layer_block_categories.csv", index=False)
    summary = (
        layer_table.groupby(["outer_test_fold", "displayed_role"], as_index=False)
        .agg(
            one_degree_blocks=("validation_block_1deg_id", "nunique"),
            events=("events", "sum"),
            sites=("sites", "sum"),
            site_years=("site_years", "sum"),
            era5_grids=("era5_grids", "sum"),
        )
        .sort_values(["outer_test_fold", "displayed_role"])
    )
    summary.to_csv(output_dir / "nested_layer_role_summary.csv", index=False)
    metadata = {
        "shown_inner_fold": shown_inner_fold,
        "interpretation": (
            "Each layer corresponds to one outer spatial test fold. Inner validation "
            "shows one representative split from the 4-fold inner CV; inner model "
            "selection rotates over all 4 inner folds in the actual analysis."
        ),
    }
    (output_dir / "nested_layer_plot_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    events = pd.read_csv(args.events, dtype={"site_id": "string"}, low_memory=False)
    outer_folds = pd.read_csv(args.outer_folds)
    inner_folds = pd.read_csv(args.inner_folds)
    required_events = {
        "record_id",
        "weather_id",
        "site_uid",
        "lon",
        "lat",
        "validation_block_1deg_id",
        "era5_grid_id",
    }
    missing_events = required_events.difference(events.columns)
    if missing_events:
        raise ValueError(f"Event index missing columns: {sorted(missing_events)}")
    required_inner = {"outer_test_fold", "validation_block_1deg_id", "inner_spatial_fold"}
    missing_inner = required_inner.difference(inner_folds.columns)
    if missing_inner:
        raise ValueError(f"Inner fold table missing columns: {sorted(missing_inner)}")
    if args.shown_inner_fold not in {1, 2, 3, 4}:
        raise ValueError("--shown-inner-fold must be one of 1, 2, 3, or 4")

    _, layer_table = build_block_table(
        events,
        outer_folds,
        inner_folds,
        shown_inner_fold=args.shown_inner_fold,
    )
    geometries = load_country_geometries(args.country_boundaries)
    plot_nested_layers(
        layer_table=layer_table,
        events=events,
        geometries=geometries,
        fig_dir=args.fig_dir,
        stem=args.stem,
        shown_inner_fold=args.shown_inner_fold,
        dpi=args.dpi,
    )
    write_outputs(layer_table, args.output_dir, args.shown_inner_fold)

    print("Nested spatial validation layers")
    print(f"Shown inner fold: {args.shown_inner_fold}/4")
    print(f"Layers: {layer_table['outer_test_fold'].nunique()}")
    print(f"Blocks per layer: {layer_table.groupby('outer_test_fold')['validation_block_1deg_id'].nunique().iloc[0]}")
    print(f"Figure: {(args.fig_dir / f'{args.stem}.png').relative_to(REPO_ROOT)}")
    print(f"Role table: {(args.output_dir / 'nested_layer_role_summary.csv').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
