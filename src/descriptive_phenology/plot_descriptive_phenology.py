#!/usr/bin/env python
"""Create descriptive overview figures for grape phenology observations."""

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
AXIS_LABEL_SIZE = 14
TICK_LABEL_SIZE = 12
SUBTITLE_SIZE = 15
LEGEND_SIZE = 12
COUNT_LABEL_SIZE = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        default=COUNTRY_TABLES,
        help="Processed country phenology table(s).",
    )
    parser.add_argument(
        "--fig-dir",
        type=Path,
        default=Path("fig/descriptive_phenology"),
        help="Directory for PNG/PDF figures.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/phenology_grape/derived/descriptive_phenology"),
        help="Directory for derived summary CSVs.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Output image resolution.")
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
        "region",
        "federal_state",
        "cultivar",
        "cultivar_group",
        "bbch_code",
        "stage_event",
        "stage_description",
        "year",
        "doy",
        "date",
    ]
    df = pd.concat(
        [pd.read_csv(path, usecols=columns, low_memory=False) for path in paths],
        ignore_index=True,
    )
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["doy"] = pd.to_numeric(df["doy"], errors="coerce")
    df = df.dropna(subset=["country_name", "site_id", "year", "doy"]).copy()
    df["year"] = df["year"].astype(int)
    df["doy"] = df["doy"].astype(float)
    df = df[df["doy"].between(1, 366)].copy()
    df["bbch_norm"] = df["bbch_code"].map(normalize_bbch)
    df["area"] = df["region"].where(df["country_name"].eq("France"), df["federal_state"])
    df["area"] = df["area"].fillna("Unknown")
    df["cultivar_display"] = df["cultivar"].fillna(df["cultivar_group"]).fillna("Unknown")
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
    phase = phase.mask(bbch.eq("81") | event.str.contains("reife beginn|ripening", regex=True) | desc.str.contains("début de la maturation|beginning of ripening", regex=True), "veraison")
    phase = phase.mask(bbch.eq("89") | event.str.contains("lese|harvest", regex=True) | desc.str.contains("vendange|grapes.*harvest", regex=True), "maturity_or_harvest")
    return phase


def save_figure(fig, fig_dir: Path, stem: str, dpi: int) -> None:
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / f"{stem}.png", dpi=dpi, bbox_inches="tight")
    fig.savefig(fig_dir / f"{stem}.pdf", bbox_inches="tight")


def write_summary_tables(df: pd.DataFrame, interval_long: pd.DataFrame, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)

    coverage = (
        df.groupby(["country_name", "year"], dropna=False)
        .agg(
            n_observations=("site_id", "size"),
            n_sites=("site_id", "nunique"),
            n_bbch=("bbch_norm", lambda value: value[value.ne("")].nunique()),
            n_phenophases=("phenophase", "nunique"),
        )
        .reset_index()
    )
    coverage.to_csv(data_dir / "coverage_by_country_year.csv", index=False)

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

    trend = (
        df.dropna(subset=["phenophase"])
        .groupby(["country_name", "phenophase", "decade"], dropna=False)
        .agg(n_observations=("doy", "size"), n_sites=("site_id", "nunique"), median_doy=("doy", "median"))
        .reset_index()
        .sort_values(["country_name", "phenophase", "decade"])
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


def plot_coverage_overview(df: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    countries = ["France", "Germany"]
    colors = {"France": "#2f6f9f", "Germany": "#b45f06"}

    ax = axes[0, 0]
    yearly = df.groupby(["country_name", "year"]).size().reset_index(name="n")
    for country in countries:
        group = yearly[yearly["country_name"].eq(country)]
        ax.plot(group["year"], group["n"], color=colors[country], linewidth=1.5, label=country)
    ax.set_title("Observation records by year")
    ax.set_xlabel("Year")
    ax.set_ylabel("Records")
    ax.legend(frameon=False)

    ax = axes[0, 1]
    stage = df["stage_event"].fillna("Unknown").value_counts().head(12).sort_values()
    ax.barh(stage.index, stage.values, color="#4c78a8")
    ax.set_title("Most frequent stage labels")
    ax.set_xlabel("Records")

    ax = axes[1, 0]
    area_rows = []
    for country in countries:
        top = (
            df[df["country_name"].eq(country)]
            .groupby("area")
            .size()
            .sort_values(ascending=False)
            .head(8)
            .reset_index(name="n")
        )
        top["label"] = top["area"] + " (" + country + ")"
        area_rows.append(top)
    area = pd.concat(area_rows, ignore_index=True).sort_values("n")
    ax.barh(area["label"], area["n"], color="#59a14f")
    ax.set_title("Top regions / federal states")
    ax.set_xlabel("Records")

    ax = axes[1, 1]
    cultivar = df["cultivar_display"].replace("", "Unknown").value_counts().head(12).sort_values()
    ax.barh(cultivar.index, cultivar.values, color="#9c755f")
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
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    colors = {"France": "#2f6f9f", "Germany": "#b45f06"}

    for ax, country in zip(axes, ["France", "Germany"], strict=False):
        country_df = plot_df[plot_df["country_name"].eq(country)]
        data = [country_df.loc[country_df["bbch_norm"].eq(code), "doy"].dropna().to_numpy() for code in KEY_BBCH]
        positions = np.arange(len(KEY_BBCH)) + 1
        box = ax.boxplot(data, positions=positions, widths=0.6, patch_artist=True, showfliers=False)
        for patch in box["boxes"]:
            patch.set_facecolor(colors[country])
            patch.set_alpha(0.55)
        ax.set_ylabel("DOY")
        ax.set_title(country)
        ax.grid(axis="y", color="#dddddd", linewidth=0.5)
        counts = [len(values) for values in data]
        top_limit = ax.get_ylim()[1]
        bottom_limit = ax.get_ylim()[0]
        whiskers = box["whiskers"]
        for i, (pos, count) in enumerate(zip(positions, counts, strict=False)):
            if count:
                lower_whisker = float(np.nanmin(whiskers[2 * i].get_ydata()))
                upper_whisker = float(np.nanmax(whiskers[2 * i + 1].get_ydata()))
                above_y = upper_whisker + 7
                below_y = lower_whisker - 7
                label_above = above_y <= top_limit - 20 or below_y < bottom_limit + 5
                label_y = above_y if label_above else below_y
                ax.text(
                    pos,
                    label_y,
                    f"n={count:,}",
                    ha="center",
                    va="bottom" if label_above else "top",
                    fontsize=COUNT_LABEL_SIZE,
                    rotation=0,
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 0.4},
                )

    axes[-1].set_xticks(np.arange(len(KEY_BBCH)) + 1)
    axes[-1].set_xticklabels(KEY_BBCH)
    axes[-1].set_xlabel("BBCH code")
    fig.tight_layout()
    save_figure(fig, fig_dir, "descriptive_bbch_doy_boxplots", dpi)
    plt.close(fig)


def plot_longterm_trends(df: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt

    trend = (
        df.dropna(subset=["phenophase"])
        .groupby(["country_name", "phenophase", "decade"])
        .agg(n=("doy", "size"), median_doy=("doy", "median"))
        .reset_index()
    )
    trend = trend[trend["n"].ge(30)]

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=False)
    colors = {"France": "#2f6f9f", "Germany": "#b45f06"}
    for ax, phase in zip(axes.flat, PHENOPHASE_ORDER, strict=False):
        for country in ["France", "Germany"]:
            group = trend[(trend["country_name"].eq(country)) & (trend["phenophase"].eq(phase))]
            if group.empty:
                continue
            ax.plot(group["decade"], group["median_doy"], marker="o", linewidth=1.6, color=colors[country], label=country)
            if len(group) >= 3:
                fit = np.polyfit(group["decade"], group["median_doy"], 1)
                ax.plot(group["decade"], np.polyval(fit, group["decade"]), color=colors[country], linestyle="--", linewidth=1.0)
        ax.set_title(PHENOPHASE_LABELS[phase])
        ax.set_xlabel("Decade")
        ax.set_ylabel("Median DOY")
        ax.grid(color="#dddddd", linewidth=0.5)
    axes[0, 0].legend(frameon=False)
    fig.tight_layout()
    save_figure(fig, fig_dir, "descriptive_longterm_phenophase_trends", dpi)
    plt.close(fig)


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
    value_cols = [column for column in INTERVAL_ORDER if column in wide.columns]
    interval_long = wide.melt(
        id_vars=["country_name", "site_id", "year"],
        value_vars=value_cols,
        var_name="interval",
        value_name="interval_days",
    )
    interval_long = interval_long.dropna(subset=["interval_days"])
    interval_long = interval_long[interval_long["interval_days"].between(1, 260)].copy()
    interval_long["decade"] = (interval_long["year"] // 10) * 10
    return interval_long


def plot_interval_lengths(interval_long: pd.DataFrame, fig_dir: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    colors = {"France": "#2f6f9f", "Germany": "#b45f06"}

    ax = axes[0]
    positions = []
    data = []
    facecolors = []
    tick_positions = []
    tick_labels = []
    pos = 1
    for interval in INTERVAL_ORDER:
        interval_positions = []
        for country in ["France", "Germany"]:
            values = interval_long[
                interval_long["interval"].eq(interval) & interval_long["country_name"].eq(country)
            ]["interval_days"].to_numpy()
            data.append(values)
            positions.append(pos)
            interval_positions.append(pos)
            facecolors.append(colors[country])
            pos += 1
        tick_positions.append(float(np.mean(interval_positions)))
        tick_labels.append(INTERVAL_LABELS[interval])
        pos += 0.7
    box = ax.boxplot(data, positions=positions, widths=0.55, patch_artist=True, showfliers=False)
    for patch, color in zip(box["boxes"], facecolors, strict=False):
        patch.set_facecolor(color)
        patch.set_alpha(0.55)
    ax.set_ylabel("Interval length (days)")
    ax.set_title("Site-year interval distributions")
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right")
    ax.grid(axis="y", color="#dddddd", linewidth=0.5)
    from matplotlib.patches import Patch

    ax.legend(
        handles=[
            Patch(facecolor=colors["France"], alpha=0.55, edgecolor="black", label="France"),
            Patch(facecolor=colors["Germany"], alpha=0.55, edgecolor="black", label="Germany"),
        ],
        frameon=False,
        loc="upper left",
    )

    ax = axes[1]
    trend = (
        interval_long.groupby(["country_name", "interval", "decade"])
        .agg(n=("interval_days", "size"), median_days=("interval_days", "median"))
        .reset_index()
    )
    trend = trend[trend["n"].ge(20)]
    for interval in INTERVAL_ORDER:
        for country in ["France", "Germany"]:
            group = trend[trend["interval"].eq(interval) & trend["country_name"].eq(country)]
            if group.empty:
                continue
            label = f"{INTERVAL_LABELS[interval]} - {country}"
            linestyle = "-" if country == "France" else "--"
            ax.plot(group["decade"], group["median_days"], marker="o", linewidth=1.2, linestyle=linestyle, label=label)
    ax.set_title("Median interval length by decade")
    ax.set_xlabel("Decade")
    ax.set_ylabel("Median interval length (days)")
    ax.grid(color="#dddddd", linewidth=0.5)
    ax.legend(
        frameon=True,
        facecolor="white",
        edgecolor="none",
        framealpha=0.82,
        fontsize=10,
        ncol=1,
        loc="center right",
        bbox_to_anchor=(0.98, 0.52),
    )

    fig.tight_layout()
    save_figure(fig, fig_dir, "descriptive_phenophase_intervals", dpi)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    args.fig_dir.mkdir(parents=True, exist_ok=True)
    args.data_dir.mkdir(parents=True, exist_ok=True)

    df = load_data(args.input)
    interval_long = build_intervals(df)
    write_summary_tables(df, interval_long, args.data_dir)

    plot_coverage_overview(df, args.fig_dir, args.dpi)
    plot_bbch_doy_boxplots(df, args.fig_dir, args.dpi)
    plot_longterm_trends(df, args.fig_dir, args.dpi)
    plot_interval_lengths(interval_long, args.fig_dir, args.dpi)

    print(f"Input records used: {len(df):,}")
    print(f"Interval site-years used: {len(interval_long):,}")
    print(f"Figures written to: {args.fig_dir}")
    print(f"Derived CSVs written to: {args.data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
