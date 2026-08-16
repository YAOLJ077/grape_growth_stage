#!/usr/bin/env python
"""Print a compact audit of completed DEM and ERA5-Land preprocessing."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    topo = pd.read_csv(ROOT / "data/phenology/derived/descriptive_phenology/site_topography.csv")
    crosswalk = pd.read_csv(ROOT / "data/topography/processed/site_era5_land_grid_crosswalk.csv")
    summary = json.loads((ROOT / "data/weather/processed/qc/weather_model_ready_summary.json").read_text())
    qc = pd.read_csv(ROOT / "data/weather/processed/qc/weather_site_year_qc.csv")

    print("DEM / ERA5-Land preprocessing audit")
    print(f"Sites: {len(topo):,}; site DEM complete: {topo.dem_elevation_m.notna().sum():,}/{len(topo):,}")
    print(f"ERA5-Land grids: {crosswalk.era5_grid_id.nunique():,}; official grid elevation complete: {crosswalk.era5_grid_elevation_m.notna().sum():,}/{len(crosswalk):,}")
    print(f"Source-vs-DEM discrepancy >100 m: {int(topo.source_dem_discrepancy_flag.sum()):,}")
    differences = ", ".join(
        f">{threshold} m={int(crosswalk[f'site_grid_difference_gt_{threshold}m'].sum()):,}"
        for threshold in (100, 200, 300)
    )
    print(f"Site DEM vs official ERA5 grid elevation: {differences}")
    print(f"Weather: {summary['n_daily_rows']:,} rows; {summary['n_site_years']:,} site-years")
    print(f"Full requested period: {summary['n_complete_full_period_site_years']:,}; partial: {summary['n_partial_period_site_years']:,} (all {', '.join(map(str, sorted(qc.loc[~qc.weather_period_complete, 'year'].unique())))})")
    print(f"Observed-event coverage: {summary['n_complete_for_observed_events']:,}/{summary['n_site_years']:,}; physical-QC failures: {summary['n_site_years_failing_daily_physical_qc']:,}")
    print(f"Buffer-filled coastal/island site-years: {summary['n_site_years_with_buffer_fill']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
