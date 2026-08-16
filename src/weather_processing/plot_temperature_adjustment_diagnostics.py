#!/usr/bin/env python
"""Plot site-level diagnostics for France-Germany elevation adjustment."""

from __future__ import annotations

import argparse
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
DEFAULT_OUTPUT = REPO_ROOT / "fig/weather_processing/france_germany_temperature_adjustment_diagnostics.png"
COUNTRIES = ("France", "Germany")
COUNTRY_COLORS = {"France": "#0072B2", "Germany": "#D55E00"}
RATE_COLUMNS = {
    "4.5": "temperature_adjustment_c_sensitivity_4p5c_km",
    "6.0": "temperature_adjustment_c_sensitivity_6p0c_km",
    "6.5": "temperature_adjustment_c_main_6p5c_km",
}
BAND_EDGES = (-np.inf, 50.0, 100.0, 200.0, 300.0, np.inf)
BAND_LABELS = ("≤50", "50–100", "100–200", "200–300", ">300")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
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
            "axes.titlesize": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "legend.fontsize": 7,
            "axes.linewidth": 0.65,
            "axes.unicode_minus": False,
        }
    )


def validate(data: pd.DataFrame) -> pd.DataFrame:
    required = {
        "country",
        "site_uid",
        "site_minus_grid_elevation_m",
        "abs_site_grid_elevation_difference_m",
        *RATE_COLUMNS.values(),
    }
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Site summary is missing columns: {sorted(missing)}")
    work = data[data["country"].isin(COUNTRIES)].copy()
    if work["site_uid"].duplicated().any():
        raise ValueError("Site summary must contain one row per site_uid")
    if work[list(required - {"country", "site_uid"})].isna().any().any():
        raise ValueError("Temperature-adjustment diagnostics cannot contain missing values")
    work["abs_dz_band"] = pd.cut(
        work["abs_site_grid_elevation_difference_m"],
        BAND_EDGES,
        labels=BAND_LABELS,
        right=True,
        include_lowest=True,
        ordered=True,
    )
    return work


def plot(data: pd.DataFrame, output: Path, dpi: int) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(7.2, 2.75),
        gridspec_kw={"width_ratios": [1.0, 1.42, 1.05], "wspace": 0.39},
    )
    fig.subplots_adjust(left=0.075, right=0.992, bottom=0.255, top=0.975)

    # (a) Site-level elevation mismatch distribution.
    ax = axes[0]
    bins = np.linspace(-500, 500, 51)
    for country in COUNTRIES:
        values = data.loc[data["country"].eq(country), "site_minus_grid_elevation_m"].clip(-500, 500)
        ax.hist(
            values,
            bins=bins,
            density=True,
            histtype="step",
            linewidth=1.25,
            color=COUNTRY_COLORS[country],
            label=country,
        )
    ax.axvline(0, color="#4d4d4d", linewidth=0.7, linestyle="--")
    ax.set_xlabel(r"Site minus grid elevation, $\Delta z$ (m)")
    ax.set_ylabel("Density")
    ax.set_xlim(-500, 500)
    ax.legend(frameon=False, loc="upper right", handlelength=1.8)
    ax.text(0.025, 0.965, "(a)", transform=ax.transAxes, ha="left", va="top", fontweight="bold")

    # (b) Main correction by absolute elevation mismatch band.
    ax = axes[1]
    offsets = {"France": -0.18, "Germany": 0.18}
    rng = np.random.default_rng(20260804)
    for country in COUNTRIES:
        group = data[data["country"].eq(country)]
        for band_index, band in enumerate(BAND_LABELS, start=1):
            values = group.loc[
                group["abs_dz_band"].astype("string").eq(band),
                RATE_COLUMNS["6.5"],
            ].to_numpy(dtype=float)
            if not len(values):
                continue
            x = band_index + offsets[country] + rng.uniform(-0.085, 0.085, len(values))
            ax.scatter(x, values, s=5.2, color=COUNTRY_COLORS[country], alpha=0.22, linewidths=0)
            median = float(np.median(values))
            ax.plot(
                [band_index + offsets[country] - 0.11, band_index + offsets[country] + 0.11],
                [median, median],
                color=COUNTRY_COLORS[country],
                linewidth=1.5,
            )
    ax.axhline(0, color="#4d4d4d", linewidth=0.65, linestyle="--")
    ax.set_xticks(range(1, len(BAND_LABELS) + 1), BAND_LABELS)
    ax.set_xlabel(r"Absolute elevation mismatch, $|\Delta z|$ (m)")
    ax.set_ylabel(r"Temperature adjustment, $\Delta T$ (°C)")
    ax.set_ylim(-5.4, 5.0)
    ax.text(0.025, 0.965, "(b)", transform=ax.transAxes, ha="left", va="top", fontweight="bold")

    # (c) Sensitivity of the site-level adjustment distribution to lapse rate.
    ax = axes[2]
    rate_positions = np.arange(len(RATE_COLUMNS), dtype=float)
    for country in COUNTRIES:
        positions = rate_positions + offsets[country]
        medians, lower, upper = [], [], []
        for column in RATE_COLUMNS.values():
            values = data.loc[data["country"].eq(country), column]
            q05, median, q95 = values.quantile([0.05, 0.5, 0.95])
            lower.append(median - q05)
            medians.append(median)
            upper.append(q95 - median)
        ax.errorbar(
            positions,
            medians,
            yerr=np.vstack([lower, upper]),
            fmt="o",
            markersize=3.6,
            capsize=2.1,
            elinewidth=1.0,
            color=COUNTRY_COLORS[country],
            label=country,
        )
    ax.axhline(0, color="#4d4d4d", linewidth=0.65, linestyle="--")
    ax.set_xticks(rate_positions, RATE_COLUMNS.keys())
    ax.set_xlabel(r"Lapse rate (°C km$^{-1}$)")
    ax.set_ylabel(r"Median and 5–95% $\Delta T$ (°C)")
    ax.text(0.025, 0.965, "(c)", transform=ax.transAxes, ha="left", va="top", fontweight="bold")

    for ax in axes:
        ax.grid(axis="y", color="#bdbdbd", linewidth=0.35, alpha=0.5)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(length=2.5, width=0.55)

    handles = [
        Line2D([0], [0], marker="o", linestyle="none", markersize=4, color=COUNTRY_COLORS[c], label=c)
        for c in COUNTRIES
    ]
    axes[1].legend(handles=handles, frameon=False, loc="lower right", ncol=2, handletextpad=0.35, columnspacing=0.8)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=dpi)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    configure_matplotlib()
    data = validate(pd.read_csv(args.input, low_memory=False))
    plot(data, args.output, args.dpi)
    print(f"Sites: {len(data):,}; output: {args.output.relative_to(REPO_ROOT)}")
    abs_dz = data["abs_site_grid_elevation_difference_m"]
    main_adjustment = data[RATE_COLUMNS["6.5"]]
    print("Temperature-adjustment diagnostic report")
    print("  Country sites: " + ", ".join(
        f"{country}={int(data['country'].eq(country).sum()):,}" for country in COUNTRIES
    ))
    print(
        f"  |delta_z| <= 50 m: {abs_dz.le(50).mean() * 100:.1f}%; "
        f"<= 100 m: {abs_dz.le(100).mean() * 100:.1f}%; > 300 m: {abs_dz.gt(300).mean() * 100:.2f}%"
    )
    q01, q05, q50, q95, q99 = main_adjustment.quantile([0.01, 0.05, 0.50, 0.95, 0.99])
    print(
        "  Main 6.5 degC km-1 delta_T: "
        f"median={q50:+.3f} degC; P05-P95={q05:+.3f} to {q95:+.3f}; "
        f"P01-P99={q01:+.3f} to {q99:+.3f}"
    )
    for rate, column in RATE_COLUMNS.items():
        q05_rate, q50_rate, q95_rate = data[column].quantile([0.05, 0.50, 0.95])
        print(
            f"  {rate} degC km-1: median={q50_rate:+.3f} degC; "
            f"P05-P95={q05_rate:+.3f} to {q95_rate:+.3f}"
        )
    print("  Reliability: 6.5 degC km-1 is literature-fixed, not tuned to phenology; ")
    print("  most sites require modest corrections, and 4.5/6.0 alternatives test rate sensitivity.")
    print("  Boundary: without station temperature, these plots support plausibility and internal consistency, not truth validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
