#!/usr/bin/env python
"""Create descriptive figures for the six-country grape phenology dataset."""

from __future__ import annotations

import argparse
import math
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_INPUTS = [
    Path("data/phenology/derived/standardized_bbch/six_country_phenology_bbch_standardized.csv"),
]
COUNTRY_ORDER = ["France", "Germany", "Austria", "Switzerland", "Slovakia", "Spain"]
COUNTRY_COLORS = {
    "France": "#0072B2",
    "Germany": "#CC79A7",
    "Austria": "#00BFC4",
    "Switzerland": "#7570B3",
    "Slovakia": "#E7298A",
    "Spain": "#E66100",
}
EXTENT = [-7.5, 23.5, 37.2, 55.5]
KEY_BBCH = ["07", "09", "11", "15", "19", "55", "61", "65", "69", "75", "79", "81", "89"]
MAP_BBCH = ["07", "61", "81", "89"]
PHENOPHASE_ORDER = ["budburst", "flowering", "veraison", "maturity_or_harvest"]
PHENOPHASE_LABELS = {
    "budburst": "Budburst",
    "flowering": "Flowering",
    "veraison": "Veraison",
    "maturity_or_harvest": "Maturity / harvest",
}
INTERVAL_ORDER = [
    "budburst_to_flowering",
    "flowering_to_veraison",
    "veraison_to_maturity_or_harvest",
    "budburst_to_maturity_or_harvest",
]
INTERVAL_LABELS = {
    "budburst_to_flowering": "Budburst to flowering",
    "flowering_to_veraison": "Flowering to veraison",
    "veraison_to_maturity_or_harvest": "Veraison to maturity/harvest",
    "budburst_to_maturity_or_harvest": "Budburst to maturity/harvest",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", default=DEFAULT_INPUTS)
    parser.add_argument("--fig-dir", type=Path, default=Path("fig/descriptive_phenology/six_countries"))
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/phenology/derived/descriptive_phenology/six_countries"),
    )
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
            "axes.labelsize": 12,
            "axes.titlesize": 13,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
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


def read_standardized(paths: list[Path]) -> pd.DataFrame:
    columns = [
        "source_system",
        "country_name",
        "site_id",
        "site_name",
        "latitude",
        "longitude",
        "altitude",
        "region",
        "federal_state",
        "cultivar",
        "cultivar_group",
        "bbch_code",
        "bbch_standard",
        "bbch_major",
        "bbch_mapping_confidence",
        "phenophase_standard",
        "phenophase_order",
        "stage_event",
        "stage_description",
        "year",
        "doy",
        "date",
    ]
    frames = []
    for path in paths:
        header = pd.read_csv(path, nrows=0)
        usecols = [column for column in columns if column in header.columns]
        frame = pd.read_csv(path, usecols=usecols, low_memory=False)
        for column in columns:
            if column not in frame.columns:
                frame[column] = pd.NA
        frames.append(frame[columns])
    df = pd.concat(frames, ignore_index=True)
    df = df[df["country_name"].isin(COUNTRY_ORDER)].copy()
    for column in ["year", "doy", "latitude", "longitude", "altitude"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["country_name", "site_id", "year", "doy", "latitude", "longitude"])
    df["year"] = df["year"].astype(int)
    df = df[df["doy"].between(1, 366)].copy()
    if df["bbch_standard"].notna().any():
        df["bbch_norm"] = df["bbch_standard"].fillna("").map(normalize_bbch)
    else:
        df["bbch_norm"] = df["bbch_code"].map(normalize_bbch)
    df["area"] = df["region"].where(df["country_name"].eq("France"), df["federal_state"])
    df["area"] = df["area"].fillna("Unknown").replace("", "Unknown")
    df["cultivar_display"] = df["cultivar"].fillna(df["cultivar_group"]).fillna("Unknown").replace("", "Unknown")
    if df["phenophase_standard"].notna().any():
        df["phenophase"] = df["phenophase_standard"].replace("", pd.NA)
    else:
        df["phenophase"] = assign_phenophase(df)
    df["decade"] = (df["year"] // 10) * 10
    return df


def assign_phenophase(df: pd.DataFrame) -> pd.Series:
    event = df["stage_event"].fillna("").str.lower()
    desc = df["stage_description"].fillna("").str.lower()
    bbch = df["bbch_code"].map(normalize_bbch)
    phase = pd.Series(pd.NA, index=df.index, dtype="string")
    phase = phase.mask(bbch.eq("07") | event.str.contains("austrieb|bud development|sprouting", regex=True), "budburst")
    phase = phase.mask(bbch.isin(["61", "65"]) | event.str.contains("blüte beginn|vollblüte|flowering", regex=True), "flowering")
    phase = phase.mask(
        bbch.eq("81")
        | event.str.contains("reife beginn|ripening", regex=True)
        | desc.str.contains("début de la maturation|beginning of ripening", regex=True),
        "veraison",
    )
    phase = phase.mask(
        bbch.eq("89")
        | event.str.contains("lese|harvest", regex=True)
        | desc.str.contains("vendange|grapes.*harvest", regex=True),
        "maturity_or_harvest",
    )
    return phase


def ordered_countries(df: pd.DataFrame) -> list[str]:
    present = set(df["country_name"].dropna())
    return [country for country in COUNTRY_ORDER if country in present]


def save_figure(fig, fig_dir: Path, stem: str, dpi: int) -> None:
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / f"{stem}.png", dpi=dpi, bbox_inches="tight")
    fig.savefig(fig_dir / f"{stem}.pdf", bbox_inches="tight")


def build_intervals(df: pd.DataFrame) -> pd.DataFrame:
    phase_df = df.dropna(subset=["phenophase"]).copy()
    phase_df = phase_df[phase_df["phenophase"].isin(PHENOPHASE_ORDER)]
    first_phase = (
        phase_df.groupby(["country_name", "site_id", "year", "phenophase"], dropna=False)
        .agg(doy=("doy", "median"))
        .reset_index()
    )
    wide = first_phase.pivot_table(
        index=["country_name", "site_id", "year"],
        columns="phenophase",
        values="doy",
        aggfunc="median",
    ).reset_index()
    wide["budburst_to_flowering"] = wide.get("flowering") - wide.get("budburst")
    wide["flowering_to_veraison"] = wide.get("veraison") - wide.get("flowering")
    wide["veraison_to_maturity_or_harvest"] = wide.get("maturity_or_harvest") - wide.get("veraison")
    wide["budburst_to_maturity_or_harvest"] = wide.get("maturity_or_harvest") - wide.get("budburst")
    interval_long = wide.melt(
        id_vars=["country_name", "site_id", "year"],
        value_vars=[column for column in INTERVAL_ORDER if column in wide.columns],
        var_name="interval",
        value_name="interval_days",
    )
    interval_long = interval_long.dropna(subset=["interval_days"])
    interval_long = interval_long[interval_long["interval_days"].between(1, 260)].copy()
    interval_long["decade"] = (interval_long["year"] // 10) * 10
    return interval_long


def build_summary_tables(df: pd.DataFrame, interval_long: pd.DataFrame, data_dir: Path) -> dict[str, pd.DataFrame]:
    data_dir.mkdir(parents=True, exist_ok=True)
    country_summary = (
        df.groupby("country_name")
        .agg(
            n_observations=("site_id", "size"),
            n_sites=("site_id", "nunique"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            n_bbch=("bbch_norm", lambda value: value[value.ne("")].nunique()),
            n_phenophases=("phenophase", "nunique"),
        )
        .reindex(COUNTRY_ORDER)
        .dropna(how="all")
        .reset_index()
    )
    country_summary.to_csv(data_dir / "country_summary.csv", index=False)

    coverage = (
        df.groupby(["country_name", "year"], dropna=False)
        .agg(n_observations=("site_id", "size"), n_sites=("site_id", "nunique"))
        .reset_index()
    )
    coverage.to_csv(data_dir / "coverage_by_country_year.csv", index=False)

    coverage_bbch = (
        df[df["bbch_norm"].isin(KEY_BBCH)]
        .groupby(["country_name", "year", "bbch_norm"], dropna=False)
        .agg(n_observations=("doy", "size"), n_sites=("site_id", "nunique"))
        .reset_index()
    )
    coverage_bbch.to_csv(data_dir / "coverage_year_by_bbch.csv", index=False)

    site_span = (
        df.groupby(["country_name", "source_system", "site_id"], dropna=False)
        .agg(
            site_name=("site_name", "first"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
            altitude=("altitude", "median"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            n_years=("year", "nunique"),
            n_observations=("doy", "size"),
            n_bbch=("bbch_norm", lambda value: value[value.ne("")].nunique()),
        )
        .reset_index()
    )
    site_span.to_csv(data_dir / "site_observation_span.csv", index=False)

    bbch_summary = (
        df[df["bbch_norm"].isin(KEY_BBCH)]
        .groupby(["country_name", "bbch_norm"], dropna=False)
        .agg(
            n_observations=("doy", "size"),
            n_sites=("site_id", "nunique"),
            median_doy=("doy", "median"),
            q25_doy=("doy", lambda value: value.quantile(0.25)),
            q75_doy=("doy", lambda value: value.quantile(0.75)),
        )
        .reset_index()
    )
    bbch_summary.to_csv(data_dir / "bbch_doy_summary.csv", index=False)

    site_bbch = (
        df[df["bbch_norm"].isin(MAP_BBCH)]
        .groupby(["country_name", "source_system", "site_id", "bbch_norm"], dropna=False)
        .agg(
            site_name=("site_name", "first"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
            altitude=("altitude", "median"),
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
    )
    altitude_bins = (
        gradient_base.groupby(["country_name", "bbch_norm", "altitude_bin"], dropna=False)
        .agg(n_sites=("site_id", "nunique"), median_doy=("median_doy", "median"))
        .reset_index()
    )
    latitude_bins.to_csv(data_dir / "latitude_bbch_median_doy_bins.csv", index=False)
    altitude_bins.to_csv(data_dir / "altitude_bbch_median_doy_bins.csv", index=False)

    trend = (
        df.dropna(subset=["phenophase"])
        .groupby(["country_name", "phenophase", "decade"], dropna=False)
        .agg(n_observations=("doy", "size"), n_sites=("site_id", "nunique"), median_doy=("doy", "median"))
        .reset_index()
    )
    trend.to_csv(data_dir / "phenophase_decade_median_doy.csv", index=False)

    interval_summary = (
        interval_long.groupby(["country_name", "interval"], dropna=False)
        .agg(
            n_site_years=("interval_days", "size"),
            median_days=("interval_days", "median"),
            q25_days=("interval_days", lambda value: value.quantile(0.25)),
            q75_days=("interval_days", lambda value: value.quantile(0.75)),
        )
        .reset_index()
    )
    interval_summary.to_csv(data_dir / "phenophase_interval_summary.csv", index=False)
    interval_long.to_csv(data_dir / "phenophase_intervals_site_year.csv", index=False)

    return {
        "country_summary": country_summary,
        "coverage": coverage,
        "coverage_bbch": coverage_bbch,
        "site_span": site_span,
        "bbch_summary": bbch_summary,
        "site_bbch": site_bbch,
        "latitude_bins": latitude_bins,
        "altitude_bins": altitude_bins,
        "trend": trend,
        "interval_summary": interval_summary,
    }


def plot_coverage_overview(df: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt

    countries = ordered_countries(df)
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))

    yearly = df.groupby(["country_name", "year"]).size().reset_index(name="n")
    ax = axes[0, 0]
    for country in countries:
        group = yearly[yearly["country_name"].eq(country)]
        ax.plot(group["year"], group["n"], color=COUNTRY_COLORS[country], linewidth=1.4, label=country)
    ax.set_title("Observation records by year")
    ax.set_xlabel("Year")
    ax.set_ylabel("Records")
    ax.legend(frameon=False, ncol=2)

    ax = axes[0, 1]
    site_counts = df.groupby("country_name")["site_id"].nunique().reindex(countries)
    ax.bar(site_counts.index, site_counts.values, color=[COUNTRY_COLORS[country] for country in site_counts.index])
    ax.set_title("Unique sites by country")
    ax.set_ylabel("Sites")
    ax.tick_params(axis="x", rotation=35)

    ax = axes[1, 0]
    stage = df["stage_event"].fillna("Unknown").value_counts().head(12).sort_values()
    ax.barh(stage.index, stage.values, color="#4C78A8")
    ax.set_title("Most frequent stage labels")
    ax.set_xlabel("Records")

    ax = axes[1, 1]
    cultivar = df["cultivar_display"].replace("", "Unknown").value_counts().head(12).sort_values()
    ax.barh(cultivar.index, cultivar.values, color="#9C755F")
    ax.set_title("Most frequent cultivar groups / cultivars")
    ax.set_xlabel("Records")

    for axis in axes.flat:
        axis.grid(axis="x", color="#dddddd", linewidth=0.5)
    fig.tight_layout()
    save_figure(fig, fig_dir, "descriptive_coverage_overview", dpi)
    plt.close(fig)


def plot_bbch_doy_boxplots(df: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt

    plot_df = df[df["bbch_norm"].isin(KEY_BBCH)].copy()
    countries = ordered_countries(plot_df)
    ncols = 2
    nrows = math.ceil(len(countries) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(15, 4.2 * nrows), sharex=True, sharey=True)
    axes = np.atleast_1d(axes).ravel()
    positions = np.arange(len(KEY_BBCH)) + 1
    for ax, country in zip(axes, countries, strict=False):
        country_df = plot_df[plot_df["country_name"].eq(country)]
        data = [country_df.loc[country_df["bbch_norm"].eq(code), "doy"].dropna().to_numpy() for code in KEY_BBCH]
        box = ax.boxplot(data, positions=positions, widths=0.6, patch_artist=True, showfliers=False)
        for patch in box["boxes"]:
            patch.set_facecolor(COUNTRY_COLORS[country])
            patch.set_alpha(0.56)
        ax.set_title(country)
        ax.set_ylabel("DOY")
        ax.grid(axis="y", color="#dddddd", linewidth=0.5)
        top_limit = ax.get_ylim()[1]
        whiskers = box["whiskers"]
        for i, (pos, values) in enumerate(zip(positions, data, strict=False)):
            if len(values):
                upper_whisker = float(np.nanmax(whiskers[2 * i + 1].get_ydata()))
                ax.text(pos, min(upper_whisker + 7, top_limit - 4), f"n={len(values):,}", ha="center", fontsize=7)
    for ax in axes[len(countries) :]:
        ax.set_axis_off()
    for ax in axes[-ncols:]:
        ax.set_xticks(positions)
        ax.set_xticklabels(KEY_BBCH)
        ax.set_xlabel("BBCH code")
    fig.tight_layout()
    save_figure(fig, fig_dir, "descriptive_bbch_doy_boxplots", dpi)
    plt.close(fig)


def plot_longterm_trends(tables: dict[str, pd.DataFrame], fig_dir: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt

    trend = tables["trend"]
    trend = trend[trend["n_observations"].ge(20)]
    countries = ordered_countries(trend)
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), sharex=False)
    for ax, phase in zip(axes.flat, PHENOPHASE_ORDER, strict=False):
        phase_handles = []
        phase_labels = []
        for country in countries:
            group = trend[(trend["country_name"].eq(country)) & (trend["phenophase"].eq(phase))]
            if group.empty:
                continue
            line = ax.plot(
                group["decade"],
                group["median_doy"],
                marker="o",
                linewidth=1.4,
                color=COUNTRY_COLORS[country],
                label=country,
            )[0]
            phase_handles.append(line)
            phase_labels.append(country)
            if len(group) >= 3:
                fit = np.polyfit(group["decade"], group["median_doy"], 1)
                ax.plot(
                    group["decade"],
                    np.polyval(fit, group["decade"]),
                    color=COUNTRY_COLORS[country],
                    linestyle="--",
                    linewidth=1.0,
                    alpha=0.85,
                )
        ax.set_title(PHENOPHASE_LABELS[phase])
        ax.set_xlabel("Decade")
        ax.set_ylabel("Median DOY")
        ax.grid(color="#dddddd", linewidth=0.5)
        if phase_handles:
            ax.legend(phase_handles, phase_labels, frameon=False, ncol=2, loc="best")
    fig.tight_layout()
    save_figure(fig, fig_dir, "descriptive_longterm_phenophase_trends", dpi)
    plt.close(fig)


def plot_interval_lengths(interval_long: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    countries = ordered_countries(interval_long)
    fig, axes = plt.subplots(1, 2, figsize=(17, 6.5))

    ax = axes[0]
    positions = []
    data = []
    facecolors = []
    tick_positions = []
    tick_labels = []
    pos = 1
    for interval in INTERVAL_ORDER:
        interval_positions = []
        for country in countries:
            values = interval_long[
                interval_long["interval"].eq(interval) & interval_long["country_name"].eq(country)
            ]["interval_days"].to_numpy()
            data.append(values)
            positions.append(pos)
            interval_positions.append(pos)
            facecolors.append(COUNTRY_COLORS[country])
            pos += 1
        tick_positions.append(float(np.mean(interval_positions)))
        tick_labels.append(INTERVAL_LABELS[interval])
        pos += 0.8
    box = ax.boxplot(data, positions=positions, widths=0.55, patch_artist=True, showfliers=False)
    for patch, color in zip(box["boxes"], facecolors, strict=False):
        patch.set_facecolor(color)
        patch.set_alpha(0.55)
    ax.set_ylabel("Interval length (days)")
    ax.set_title("Site-year interval distributions")
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=35, ha="right")
    ax.grid(axis="y", color="#dddddd", linewidth=0.5)
    ax.legend(
        handles=[Patch(facecolor=COUNTRY_COLORS[country], alpha=0.55, edgecolor="black", label=country) for country in countries],
        frameon=False,
        ncol=2,
        loc="upper left",
    )

    ax = axes[1]
    trend = (
        interval_long.groupby(["country_name", "interval", "decade"])
        .agg(n=("interval_days", "size"), median_days=("interval_days", "median"))
        .reset_index()
    )
    trend = trend[trend["n"].ge(10)]
    linestyles = {
        "budburst_to_flowering": "-",
        "flowering_to_veraison": "--",
        "veraison_to_maturity_or_harvest": ":",
        "budburst_to_maturity_or_harvest": "-.",
    }
    for interval in INTERVAL_ORDER:
        for country in countries:
            group = trend[trend["interval"].eq(interval) & trend["country_name"].eq(country)]
            if group.empty:
                continue
            ax.plot(
                group["decade"],
                group["median_days"],
                marker="o",
                linewidth=1.1,
                linestyle=linestyles[interval],
                color=COUNTRY_COLORS[country],
                alpha=0.9,
            )
    ax.set_title("Median interval length by decade")
    ax.set_xlabel("Decade")
    ax.set_ylabel("Median interval length (days)")
    ax.grid(color="#dddddd", linewidth=0.5)
    ax.text(
        0.02,
        0.98,
        "Line colors indicate country; line styles indicate interval",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 3},
    )

    fig.tight_layout()
    save_figure(fig, fig_dir, "descriptive_phenophase_intervals", dpi)
    plt.close(fig)


def plot_coverage_heatmap(tables: dict[str, pd.DataFrame], fig_dir: Path, dpi: int) -> None:
    import matplotlib.colors as colors
    import matplotlib.pyplot as plt

    coverage = tables["coverage_bbch"]
    countries = ordered_countries(coverage)
    fig, axes = plt.subplots(len(countries), 1, figsize=(16, 2.35 * len(countries)), sharey=True)
    axes = np.atleast_1d(axes)
    image = None
    for ax, country in zip(axes, countries, strict=False):
        subset = coverage[coverage["country_name"].eq(country)]
        years = np.arange(int(subset["year"].min()), int(subset["year"].max()) + 1)
        matrix = (
            subset.pivot_table(index="bbch_norm", columns="year", values="n_observations", aggfunc="sum")
            .reindex(index=KEY_BBCH, columns=years)
            .to_numpy(dtype=float)
        )
        masked = np.ma.masked_invalid(matrix)
        masked = np.ma.masked_where(masked <= 0, masked)
        image = ax.imshow(masked, aspect="auto", interpolation="nearest", cmap="YlGnBu", norm=colors.LogNorm(vmin=1))
        ax.set_title(country)
        ax.set_ylabel("BBCH")
        ax.set_yticks(np.arange(len(KEY_BBCH)))
        ax.set_yticklabels(KEY_BBCH)
        tick_idx = np.linspace(0, len(years) - 1, min(10, len(years))).round().astype(int)
        ax.set_xticks(tick_idx)
        ax.set_xticklabels(years[tick_idx])
        ax.set_xlabel("Year")
    if image is not None:
        cbar = fig.colorbar(image, ax=axes.tolist(), pad=0.01, shrink=0.7)
        cbar.set_label("Observation count")
    save_figure(fig, fig_dir, "bbch_year_coverage_heatmap", dpi)
    plt.close(fig)


def setup_map(ax, ccrs, cfeature) -> None:
    ax.set_extent(EXTENT, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor="#e9f0f5", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor="#f7f5ef", zorder=0)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), edgecolor="#3f464b", linewidth=0.55)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor="#2f2f2f", linewidth=0.75)
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

    fig, axes = plt.subplots(1, 2, figsize=(16, 7), subplot_kw={"projection": ccrs.PlateCarree()})
    for ax, field in zip(axes, ["first_year", "last_year"], strict=False):
        setup_map(ax, ccrs, cfeature)
        sc = ax.scatter(
            site_span["longitude"],
            site_span["latitude"],
            c=site_span[field],
            s=11 + 42 * np.sqrt(site_span["n_observations"] / site_span["n_observations"].max()),
            cmap="viridis",
            alpha=0.74,
            edgecolors="white",
            linewidths=0.12,
            transform=ccrs.PlateCarree(),
            zorder=3,
        )
        ax.set_title(field.replace("_", " ").title())
        cbar = fig.colorbar(sc, ax=ax, shrink=0.72, pad=0.02)
        cbar.set_label("Year")
    fig.tight_layout()
    save_figure(fig, fig_dir, "site_first_last_year_maps", dpi)
    plt.close(fig)


def plot_bbch_median_doy_maps(site_bbch: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(15, 10), subplot_kw={"projection": ccrs.PlateCarree()})
    for ax, bbch in zip(axes.ravel(), MAP_BBCH, strict=False):
        subset = site_bbch[site_bbch["bbch_norm"].eq(bbch)]
        setup_map(ax, ccrs, cfeature)
        if subset.empty:
            ax.set_axis_off()
            continue
        sc = ax.scatter(
            subset["longitude"],
            subset["latitude"],
            c=subset["median_doy"],
            s=12 + 32 * np.sqrt(subset["n_observations"] / subset["n_observations"].max()),
            cmap="magma",
            alpha=0.74,
            edgecolors="white",
            linewidths=0.1,
            transform=ccrs.PlateCarree(),
            zorder=3,
        )
        ax.set_title(f"BBCH {bbch} median DOY")
        cbar = fig.colorbar(sc, ax=ax, shrink=0.72, pad=0.02)
        cbar.set_label("Median DOY")
    fig.tight_layout()
    save_figure(fig, fig_dir, "site_bbch_median_doy_maps", dpi)
    plt.close(fig)


def plot_geographic_gradients(tables: dict[str, pd.DataFrame], fig_dir: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt

    countries = ordered_countries(tables["latitude_bins"])
    fig, axes = plt.subplots(2, len(MAP_BBCH), figsize=(17, 8), sharey=False)
    for col, bbch in enumerate(MAP_BBCH):
        lat_ax = axes[0, col]
        alt_ax = axes[1, col]
        for country in countries:
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
                lat_ax.plot(lat["latitude_bin"], lat["median_doy"], marker="o", linewidth=1.4, color=COUNTRY_COLORS[country], label=country)
            if not alt.empty:
                alt_ax.plot(alt["altitude_bin"], alt["median_doy"], marker="o", linewidth=1.4, color=COUNTRY_COLORS[country], label=country)
        lat_ax.set_title(f"BBCH {bbch}")
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

    df = read_standardized(args.input)
    interval_long = build_intervals(df)
    tables = build_summary_tables(df, interval_long, args.data_dir)

    plot_coverage_overview(df, args.fig_dir, args.dpi)
    plot_bbch_doy_boxplots(df, args.fig_dir, args.dpi)
    plot_longterm_trends(tables, args.fig_dir, args.dpi)
    plot_interval_lengths(interval_long, args.fig_dir, args.dpi)
    plot_coverage_heatmap(tables, args.fig_dir, args.dpi)
    plot_site_span_maps(tables["site_span"], args.fig_dir, args.dpi)
    plot_bbch_median_doy_maps(tables["site_bbch"], args.fig_dir, args.dpi)
    plot_geographic_gradients(tables, args.fig_dir, args.dpi)

    print(f"Input records used: {len(df):,}")
    print(f"Countries: {', '.join(ordered_countries(df))}")
    print(f"Unique sites: {df.groupby('country_name')['site_id'].nunique().sum():,}")
    print(f"Interval site-years used: {len(interval_long):,}")
    print(f"Figures written to: {args.fig_dir}")
    print(f"Derived CSVs written to: {args.data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
