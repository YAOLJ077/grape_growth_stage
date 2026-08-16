#!/usr/bin/env python
"""Audit and conservatively rebuild France-Germany BBCH81 site-year events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OBSERVATIONS = (
    REPO_ROOT
    / "data/phenology/derived/standardized_bbch/six_country_phenology_bbch_standardized.csv"
)
DEFAULT_EVENT_INDEX = (
    REPO_ROOT
    / "data/phenology/derived/modeling/france_germany_four_stage/validation/modeling_event_index.csv"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "results/france_germany_four_stage/bbch81_audit"
DEFAULT_MAX_DOY_RANGE_DAYS = 21.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--event-index", type=Path, default=DEFAULT_EVENT_INDEX)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--max-doy-range-days",
        type=float,
        default=DEFAULT_MAX_DOY_RANGE_DAYS,
        help="Exclude exact-BBCH81 site-year events with an internal DOY range above this value.",
    )
    return parser.parse_args()


def date_from_year_doy(year: int, doy: float) -> str:
    return (pd.Timestamp(year, 1, 1) + pd.to_timedelta(int(round(doy)) - 1, unit="D")).strftime(
        "%Y-%m-%d"
    )


def join_unique(values: pd.Series) -> str:
    clean = sorted({str(value) for value in values.dropna() if str(value).strip()})
    return ";".join(clean)


def audit_records(
    observation_path: Path,
    event_index_path: Path,
    max_doy_range_days: float = DEFAULT_MAX_DOY_RANGE_DAYS,
) -> pd.DataFrame:
    observations = pd.read_csv(observation_path, low_memory=False)
    observations = observations.loc[
        observations["country_name"].isin(["France", "Germany"])
        & pd.to_numeric(observations["bbch_standard"], errors="coerce").eq(81)
    ].copy()
    observations["site_id"] = observations["site_id"].astype(str)
    observations["year"] = pd.to_numeric(observations["year"], errors="raise").astype(int)
    observations["doy"] = pd.to_numeric(observations["doy"], errors="coerce")
    qb = pd.to_numeric(observations["date_quality_flag"], errors="coerce")
    observations["source_quality_eligible"] = ~(
        observations["country_name"].eq("Germany") & qb.isin([5, 8])
    )

    events = pd.read_csv(event_index_path, low_memory=False)
    events["site_id"] = events["site_id"].astype(str)
    veraison = events.loc[events["target_stage"].eq("veraison")].copy()
    lookup = events.pivot_table(
        index="weather_id", columns="target_stage", values="event_doy", aggfunc="first"
    )

    records: list[dict[str, object]] = []
    grouped = {
        key: group
        for key, group in observations.groupby(
            ["country_name", "source_system", "site_id", "year"], sort=False
        )
    }
    for event in veraison.itertuples(index=False):
        key = (str(event.country), str(event.source), str(event.site_id), int(event.year))
        group = grouped.get(key, observations.iloc[0:0]).copy()
        eligible = group.loc[group["source_quality_eligible"] & group["doy"].notna()].copy()
        has_eligible = not eligible.empty
        audited_doy = float(eligible["doy"].min()) if has_eligible else np.nan
        audited_doy_range = (
            float(eligible["doy"].max() - eligible["doy"].min()) if has_eligible else np.nan
        )
        range_valid = bool(has_eligible and audited_doy_range <= max_doy_range_days)
        stage_dates = lookup.loc[str(event.weather_id)] if str(event.weather_id) in lookup.index else pd.Series(dtype=float)
        flowering = pd.to_numeric(stage_dates.get("flowering"), errors="coerce")
        maturity = pd.to_numeric(stage_dates.get("maturity_or_harvest"), errors="coerce")
        chronology_valid = bool(
            has_eligible
            and (pd.isna(flowering) or float(flowering) < audited_doy)
            and (pd.isna(maturity) or audited_doy < float(maturity))
        )
        use = bool(has_eligible and chronology_valid and range_valid)
        if not has_eligible:
            reason = "no BBCH81 observation remains after excluding DWD QB 5/8"
        elif not range_valid:
            reason = f"audited BBCH81 internal DOY range exceeds {max_doy_range_days:g} days"
        elif not chronology_valid:
            reason = "audited BBCH81 violates observed flowering/veraison/maturity order"
        else:
            reason = "eligible exact-BBCH81 site-level onset retained"
        records.append(
            {
                "record_id": str(event.record_id),
                "weather_id": str(event.weather_id),
                "country": str(event.country),
                "source": str(event.source),
                "site_id": str(event.site_id),
                "year": int(event.year),
                "original_event_doy": float(event.event_doy),
                "raw_n_obs": int(len(group)),
                "excluded_doubtful_or_incorrect_obs": int((~group["source_quality_eligible"]).sum()),
                "audited_n_obs": int(len(eligible)),
                "audited_event_doy": audited_doy,
                "audited_event_date": date_from_year_doy(int(event.year), audited_doy)
                if has_eligible
                else pd.NA,
                "audited_doy_min": float(eligible["doy"].min()) if has_eligible else np.nan,
                "audited_doy_median": float(eligible["doy"].median()) if has_eligible else np.nan,
                "audited_doy_max": float(eligible["doy"].max()) if has_eligible else np.nan,
                "audited_doy_range": audited_doy_range,
                "audited_doy_range_within_primary_limit": range_valid,
                "audited_reporter_types": join_unique(eligible["reporter_type"]),
                "audited_cultivar_groups": join_unique(eligible["cultivar_group"]),
                "audited_stage_descriptions": join_unique(eligible["stage_description"]),
                "audited_chronology_valid": chronology_valid,
                "bbch81_use_in_primary": use,
                "audit_reason": reason,
                "event_doy_changed": bool(
                    has_eligible and not np.isclose(float(event.event_doy), audited_doy)
                ),
            }
        )
    return pd.DataFrame.from_records(records)


def definition_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "country": "France",
                "source": "TEMPO",
                "source_phase": "BBCH 81 / début de la maturation",
                "operational_definition": (
                    "berries begin to lighten and/or change colour; beginning of fruit ripening"
                ),
                "harmonized_target": "site-level onset of BBCH81 veraison",
                "compatibility": "compatible onset definition; no explicit percentage in source text",
            },
            {
                "country": "Germany",
                "source": "DWD",
                "source_phase": "Phase 42 / Reife Beginn Weinrebe / BBCH 81",
                "operational_definition": (
                    "about 25% of grapes/berries begin to become soft and light"
                ),
                "harmonized_target": "site-level onset of BBCH81 veraison",
                "compatibility": "compatible BBCH81 mapping; DWD uses an explicit circa-25% rule",
            },
        ]
    )


def main() -> int:
    args = parse_args()
    audit = audit_records(args.observations, args.event_index, args.max_doy_range_days)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.output_dir / "audited_bbch81_event_overrides.csv", index=False)
    definition_table().to_csv(args.output_dir / "bbch81_definition_harmonization.csv", index=False)
    summary = (
        audit.groupby("country")
        .agg(
            event_records=("record_id", "size"),
            retained_events=("bbch81_use_in_primary", "sum"),
            excluded_events=("bbch81_use_in_primary", lambda value: int((~value).sum())),
            changed_event_dates=("event_doy_changed", "sum"),
            excluded_source_observations=("excluded_doubtful_or_incorrect_obs", "sum"),
            excluded_extreme_doy_range_events=(
                "audit_reason",
                lambda value: int(value.str.contains("internal DOY range exceeds", regex=False).sum()),
            ),
            multi_observation_events=("audited_n_obs", lambda value: int((value > 1).sum())),
            median_within_event_range_days=("audited_doy_range", "median"),
            maximum_within_event_range_days=("audited_doy_range", "max"),
        )
        .reset_index()
    )
    summary.to_csv(args.output_dir / "bbch81_audit_summary.csv", index=False)
    metadata = {
        "aggregation_target": "earliest eligible exact-BBCH81 observation at each site-year",
        "germany_quality_rule": "exclude Eintrittsdatum_QB 5 (doubtful) and 8 (incorrect); retain 0/1/2/3",
        "france_quality_rule": "retain exact source BBCH81; no equivalent observation quality byte is available",
        "chronology_rule": "flowering < audited BBCH81 < maturity/harvest whenever adjacent stages exist",
        "extreme_target_noise_rule": f"exclude audited BBCH81 events with internal DOY range > {args.max_doy_range_days:g} days",
        "spatial_folds_changed": False,
        "records": int(len(audit)),
        "retained": int(audit["bbch81_use_in_primary"].sum()),
    }
    (args.output_dir / "bbch81_audit_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nBBCH81 audit completed")
    print(summary.to_string(index=False))
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
