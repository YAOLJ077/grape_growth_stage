#!/usr/bin/env python
"""Freeze nested spatial validation folds and the four-stage modeling index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVENTS = (
    REPO_ROOT
    / "data/phenology/derived/modeling/france_germany_four_stage/phenology_events_long.csv"
)
DEFAULT_WIDE = (
    REPO_ROOT
    / "data/phenology/derived/modeling/france_germany_four_stage/phenology_site_year_wide.csv"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "data/phenology/derived/modeling/france_germany_four_stage/validation"
)
COUNTRIES = ("France", "Germany")
STAGES = ("budburst", "flowering", "veraison", "maturity_or_harvest")
PREVIOUS_STAGE = {
    "budburst": None,
    "flowering": "budburst",
    "veraison": "flowering",
    "maturity_or_harvest": "veraison",
}
STAGE_DOY_COLUMN = {
    "budburst": "budburst_doy_bbch07",
    "flowering": "flowering_doy_bbch65",
    "veraison": "veraison_doy_bbch81",
    "maturity_or_harvest": "maturity_or_harvest_doy_bbch89",
}
OUTER_GROUP_COLUMN = "validation_block_1deg_id"
INNER_GROUP_COLUMN = "validation_block_1deg_id"
N_OUTER_FOLDS = 5
N_INNER_FOLDS = 4
RANDOM_SEED = 20260804


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--wide", type=Path, default=DEFAULT_WIDE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--outer-folds", type=int, default=N_OUTER_FOLDS)
    parser.add_argument("--inner-folds", type=int, default=N_INNER_FOLDS)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    return parser.parse_args()


def validate_events(events: pd.DataFrame) -> None:
    required = {
        "record_id", "weather_id", "site_uid", "country", "year", "event_doy",
        "target_stage", "model_tier", "analysis_role", "era5_grid_id",
        "era5_grid_lat", "era5_grid_lon", "spatial_block_1deg_id", "spatial_block_2deg_id",
        "validation_block_1deg_id", "validation_block_2deg_id", "dem_elevation_m",
    }
    missing = required.difference(events.columns)
    if missing:
        raise ValueError(f"Event table is missing columns: {sorted(missing)}")
    if events["record_id"].duplicated().any():
        raise ValueError("record_id must be unique")
    if not events["country"].isin(COUNTRIES).all():
        raise ValueError("Validation design contains countries outside France and Germany")
    if not events["target_stage"].isin(STAGES).all():
        raise ValueError("Validation design contains an unexpected target stage")
    key_columns = [
        "site_uid", "era5_grid_id", "validation_block_1deg_id", "validation_block_2deg_id",
        "event_doy", "dem_elevation_m",
    ]
    if events[key_columns].isna().any().any():
        raise ValueError("Validation design contains missing spatial or target fields")
    site_groups = events.groupby("site_uid")[
        ["era5_grid_id", "validation_block_1deg_id", "validation_block_2deg_id"]
    ].nunique()
    if site_groups.gt(1).any().any():
        raise ValueError("A site maps to multiple grids or spatial blocks")


def add_validation_weather_blocks(events: pd.DataFrame) -> pd.DataFrame:
    """Anchor validation blocks to ERA5 grid centers so one grid cannot cross blocks."""
    work = events.copy()
    for size in (1.0, 2.0):
        lat_lower = np.floor(pd.to_numeric(work["era5_grid_lat"], errors="raise") / size) * size
        lon_lower = np.floor(pd.to_numeric(work["era5_grid_lon"], errors="raise") / size) * size
        label = str(int(size))
        work[f"validation_block_{label}deg_id"] = [
            f"weather_block_{label}_lat{lat:+.1f}_lon{lon:+.1f}"
            for lat, lon in zip(lat_lower, lon_lower)
        ]
    return work


def block_scale_audit(events: pd.DataFrame) -> pd.DataFrame:
    outputs: list[pd.DataFrame] = []
    for scale, column in (("ERA5 grid", "era5_grid_id"), ("1 degree", "validation_block_1deg_id"), ("2 degree", "validation_block_2deg_id")):
        grouped = (
            events.groupby(["country", "target_stage", column], dropna=False)
            .agg(events=("record_id", "size"), sites=("site_uid", "nunique"))
            .reset_index()
        )
        totals = grouped.groupby(["country", "target_stage"])["events"].transform("sum")
        grouped["event_share_pct"] = grouped["events"].div(totals).mul(100)
        summary = (
            grouped.groupby(["country", "target_stage"], as_index=False)
            .agg(
                n_groups=(column, "nunique"),
                total_events=("events", "sum"),
                total_sites=("sites", "sum"),
                median_events_per_group=("events", "median"),
                max_events_in_group=("events", "max"),
                max_single_group_share_pct=("event_share_pct", "max"),
            )
        )
        summary.insert(0, "candidate_scale", scale)
        summary["group_column"] = column
        outputs.append(summary)
    result = pd.concat(outputs, ignore_index=True)
    result["selected_for_primary_nested_cv"] = result["candidate_scale"].eq("1 degree")
    result["selection_note"] = np.where(
        result["candidate_scale"].eq("1 degree"),
        "Selected: adequate spatial separation with materially better fold balance than 2-degree blocks.",
        np.where(
            result["candidate_scale"].eq("2 degree"),
            "Rejected for five-fold CV: one German block contains about half of several stage records.",
            "Retained as the no-identical-weather-series constraint, not the primary regional block.",
        ),
    )
    numeric = result.select_dtypes(include="number").columns
    result[numeric] = result[numeric].round(3)
    return result.sort_values(["candidate_scale", "country", "target_stage"]).reset_index(drop=True)


def group_profile(events: pd.DataFrame, group_column: str) -> tuple[pd.DataFrame, list[str]]:
    event_counts = pd.crosstab(
        events[group_column], [events["country"], events["target_stage"]]
    )
    event_counts.columns = [f"events__{country}__{stage}" for country, stage in event_counts.columns]
    site_rows = events.drop_duplicates([group_column, "country", "target_stage", "site_uid"])
    site_counts = pd.crosstab(
        site_rows[group_column], [site_rows["country"], site_rows["target_stage"]]
    )
    site_counts.columns = [f"sites__{country}__{stage}" for country, stage in site_counts.columns]
    profile = event_counts.join(site_counts, how="outer").fillna(0.0).sort_index()
    profile["n_groups"] = 1.0
    features = [column for column in profile.columns if column != "n_groups"]
    return profile.astype(float), features


def assignment_objective(
    fold_sums: np.ndarray,
    fold_group_counts: np.ndarray,
    targets: np.ndarray,
    target_groups: float,
) -> float:
    scaled = (fold_sums - targets) / np.maximum(targets, 1.0)
    group_scaled = (fold_group_counts - target_groups) / max(target_groups, 1.0)
    return float(np.mean(scaled**2) + 0.05 * np.mean(group_scaled**2))


def balanced_group_assignment(
    events: pd.DataFrame,
    group_column: str,
    n_folds: int,
    seed: int,
    n_restarts: int = 300,
) -> tuple[pd.DataFrame, float]:
    """Assign intact spatial groups while balancing country-stage events and sites."""
    profile, features = group_profile(events, group_column)
    if len(profile) < n_folds:
        raise ValueError(f"Only {len(profile)} {group_column} groups for {n_folds} folds")
    values = profile[features].to_numpy(dtype=float)
    targets = values.sum(axis=0) / n_folds
    target_groups = len(profile) / n_folds
    normalized_size = (values / np.maximum(targets, 1.0)).max(axis=1)
    rng = np.random.default_rng(seed)
    best_assignment: np.ndarray | None = None
    best_score = np.inf

    for restart in range(n_restarts):
        jitter = rng.uniform(0.0, 0.08, len(profile)) if restart else np.zeros(len(profile))
        order = np.argsort(-(normalized_size + jitter), kind="stable")
        fold_sums = np.zeros((n_folds, len(features)), dtype=float)
        fold_counts = np.zeros(n_folds, dtype=float)
        assignment = np.full(len(profile), -1, dtype=int)
        for position, group_index in enumerate(order):
            candidate_folds = [position] if position < n_folds else list(rng.permutation(n_folds))
            best_fold = None
            best_fold_key = None
            for fold in candidate_folds:
                candidate_sums = fold_sums.copy()
                candidate_counts = fold_counts.copy()
                candidate_sums[fold] += values[group_index]
                candidate_counts[fold] += 1
                score = assignment_objective(candidate_sums, candidate_counts, targets, target_groups)
                key = (score, fold_counts[fold], fold)
                if best_fold_key is None or key < best_fold_key:
                    best_fold_key = key
                    best_fold = int(fold)
            assert best_fold is not None
            assignment[group_index] = best_fold
            fold_sums[best_fold] += values[group_index]
            fold_counts[best_fold] += 1
        score = assignment_objective(fold_sums, fold_counts, targets, target_groups)
        if score < best_score:
            best_score = score
            best_assignment = assignment.copy()

    if best_assignment is None:
        raise RuntimeError("No spatial group assignment was generated")
    raw = pd.DataFrame({group_column: profile.index.astype(str), "fold_zero_based": best_assignment})
    # Canonicalize arbitrary fold labels by their lexicographically first group identifier.
    fold_order = (
        raw.groupby("fold_zero_based")[group_column].min().sort_values().index.tolist()
    )
    remap = {old: new for new, old in enumerate(fold_order, start=1)}
    raw["fold"] = raw["fold_zero_based"].map(remap).astype(int)
    return raw.drop(columns="fold_zero_based").sort_values(group_column).reset_index(drop=True), best_score


def add_sequence_fields(events: pd.DataFrame, wide: pd.DataFrame) -> pd.DataFrame:
    wide_fields = ["site_uid", "year", "chronology_valid", *STAGE_DOY_COLUMN.values()]
    missing = set(wide_fields).difference(wide.columns)
    if missing:
        raise ValueError(f"Wide event table is missing columns: {sorted(missing)}")
    work = events.merge(
        wide[wide_fields], on=["site_uid", "year"], how="left", validate="many_to_one"
    )
    if work["chronology_valid"].isna().any():
        raise ValueError("Some event records have no chronology audit")
    work["previous_target_stage"] = work["target_stage"].map(PREVIOUS_STAGE).astype("string")
    work["previous_stage_doy"] = np.nan
    for stage, previous in PREVIOUS_STAGE.items():
        if previous is None:
            continue
        mask = work["target_stage"].eq(stage)
        work.loc[mask, "previous_stage_doy"] = work.loc[mask, STAGE_DOY_COLUMN[previous]]
    work["previous_stage_observed"] = work["previous_stage_doy"].notna()
    work["sequential_observed_start_eligible"] = (
        work["previous_stage_observed"] & work["chronology_valid"].astype(bool)
    )
    work["independent_stage_weather_eligible"] = (
        work["all_weather_complete_for_observed_events"].astype(bool)
        & work["all_daily_physical_qc_pass"].astype(bool)
    )
    work["temperature_branch_raw_available"] = work["independent_stage_weather_eligible"]
    work["temperature_branch_adjusted_6p5_available"] = (
        work["independent_stage_weather_eligible"]
        & work["era5_grid_elevation_m"].notna()
        & ~work["coordinate_instability_flag"].astype(bool)
    )
    return work


def fold_balance(
    events: pd.DataFrame,
    fold_column: str,
    group_column: str,
    prefix_columns: list[str] | None = None,
    strata_columns: list[str] | None = None,
    expected_folds: int = 5,
) -> pd.DataFrame:
    prefix_columns = prefix_columns or []
    strata_columns = strata_columns or ["country", "target_stage", "model_tier"]
    output: list[pd.DataFrame] = []
    prefix_iterator = [((), events)] if not prefix_columns else events.groupby(prefix_columns, dropna=False)
    for prefix_values, subset in prefix_iterator:
        if not isinstance(prefix_values, tuple):
            prefix_values = (prefix_values,)
        keys = [fold_column, *strata_columns]
        observed = (
            subset.groupby(keys, dropna=False)
            .agg(
                event_records=("record_id", "size"),
                sites=("site_uid", "nunique"),
                site_years=("weather_id", "nunique"),
                spatial_groups=(group_column, "nunique"),
                era5_grids=("era5_grid_id", "nunique"),
                first_year=("year", "min"),
                last_year=("year", "max"),
                median_elevation_m=("dem_elevation_m", "median"),
            )
            .reset_index()
        )
        strata = subset[strata_columns].drop_duplicates().copy()
        folds = pd.DataFrame({fold_column: range(1, expected_folds + 1)})
        complete = folds.merge(strata, how="cross").merge(observed, on=keys, how="left")
        count_columns = ["event_records", "sites", "site_years", "spatial_groups", "era5_grids"]
        complete[count_columns] = complete[count_columns].fillna(0).astype(int)
        for column, value in zip(prefix_columns, prefix_values):
            complete[column] = value
        output.append(complete)
    grouped = pd.concat(output, ignore_index=True)
    total_keys = [*prefix_columns, *strata_columns]
    totals = grouped.groupby(total_keys)["event_records"].transform("sum")
    grouped["event_share_pct"] = grouped["event_records"].div(totals).mul(100)
    grouped["equal_share_target_pct"] = 100.0 / expected_folds
    grouped["event_share_deviation_pct_points"] = (
        grouped["event_share_pct"] - grouped["equal_share_target_pct"]
    )
    numeric = grouped.select_dtypes(include="number").columns
    grouped[numeric] = grouped[numeric].round(3)
    sort_keys = [*prefix_columns, fold_column, *strata_columns]
    return grouped.sort_values(sort_keys).reset_index(drop=True)


def build_modeling_index(
    events: pd.DataFrame,
    wide: pd.DataFrame,
    outer_blocks: pd.DataFrame,
) -> pd.DataFrame:
    work = add_sequence_fields(events, wide)
    work = work.merge(
        outer_blocks.rename(columns={"fold": "outer_spatial_fold"}),
        on=OUTER_GROUP_COLUMN,
        how="left",
        validate="many_to_one",
    )
    if work["outer_spatial_fold"].isna().any():
        raise ValueError("Some event records have no outer spatial fold")
    work["outer_spatial_fold"] = work["outer_spatial_fold"].astype(int)
    preferred = [
        "record_id", "weather_id", "site_uid", "country", "source", "site_id", "site_name",
        "lat", "lon", "year", "event_date", "event_doy", "bbch", "target_stage",
        "target_stage_order", "model_tier", "analysis_role", "bbch_confidence",
        "independent_stage_weather_eligible", "temperature_branch_raw_available",
        "temperature_branch_adjusted_6p5_available", "previous_target_stage",
        "previous_stage_observed", "previous_stage_doy", "chronology_valid",
        "sequential_observed_start_eligible", "dem_elevation_m", "era5_grid_id",
        "era5_grid_elevation_m", "site_minus_grid_elevation_m",
        "abs_site_grid_elevation_difference_m", "spatial_block_1deg_id",
        "spatial_block_2deg_id", "validation_block_1deg_id", "validation_block_2deg_id",
        "outer_spatial_fold",
    ]
    remaining = [column for column in work.columns if column not in preferred and column not in STAGE_DOY_COLUMN.values()]
    return work[preferred + remaining].sort_values(
        ["outer_spatial_fold", "country", "target_stage_order", "site_uid", "year"]
    ).reset_index(drop=True)


def write_readme(path: Path) -> None:
    path.write_text(
        """# Frozen spatial validation design

Generated by `src/modeling/build_spatial_validation_design.py`.

- `modeling_event_index.csv`: four-stage event index with one fixed outer spatial fold per ERA5-grid-anchored 1-degree block.
- `outer_spatial_block_folds.csv`: reusable weather-block-to-outer-fold mapping.
- `inner_spatial_block_folds.csv`: outer-fold-specific weather-block-to-inner-fold mapping for outer training data.
- `outer_fold_balance.csv` and `inner_fold_balance.csv`: country-stage-tier balance audits, including zero-count strata.
- `outer_fold_balance_by_stage_country.csv` and `inner_fold_balance_by_stage_country.csv`: primary country-stage balance audits.
- `block_scale_feasibility_audit.csv`: ERA5-grid, 1-degree and 2-degree concentration audit.
- `spatial_block_inventory.csv`: site/event coverage of every 1-degree block.
- `validation_design_summary.json`: compact reproducibility metadata and leakage checks.

Validation blocks are derived from ERA5 grid-center coordinates rather than station coordinates. Therefore an ERA5 grid cannot straddle a block boundary. All years from a site, every site sharing a weather block, and every ERA5 grid nested in that block remain intact within a fold. Fold construction uses coordinates and sample counts, never event DOY. Outer test records are excluded before each inner-fold assignment.
""",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    events = pd.read_csv(args.events, dtype={"site_id": "string"}, low_memory=False)
    wide = pd.read_csv(args.wide, dtype={"site_id": "string"}, low_memory=False)
    events = add_validation_weather_blocks(events)
    validate_events(events)
    scale_audit = block_scale_audit(events)

    outer_blocks, outer_score = balanced_group_assignment(
        events, OUTER_GROUP_COLUMN, args.outer_folds, args.seed
    )
    event_outer = events.merge(
        outer_blocks.rename(columns={"fold": "outer_spatial_fold"}),
        on=OUTER_GROUP_COLUMN,
        how="left",
        validate="many_to_one",
    )
    inner_parts: list[pd.DataFrame] = []
    inner_event_parts: list[pd.DataFrame] = []
    inner_scores: dict[str, float] = {}
    for outer_fold in range(1, args.outer_folds + 1):
        training = event_outer[event_outer["outer_spatial_fold"].ne(outer_fold)].copy()
        inner_blocks, inner_score = balanced_group_assignment(
            training,
            INNER_GROUP_COLUMN,
            args.inner_folds,
            args.seed + outer_fold,
        )
        inner_blocks.insert(0, "outer_test_fold", outer_fold)
        inner_parts.append(inner_blocks)
        inner_scores[str(outer_fold)] = inner_score
        training = training.merge(
            inner_blocks.drop(columns="outer_test_fold").rename(columns={"fold": "inner_spatial_fold"}),
            on=INNER_GROUP_COLUMN,
            how="left",
            validate="many_to_one",
        )
        training["outer_test_fold"] = outer_fold
        inner_event_parts.append(training)
    inner_blocks_all = pd.concat(inner_parts, ignore_index=True)
    inner_events = pd.concat(inner_event_parts, ignore_index=True)

    modeling_index = build_modeling_index(events, wide, outer_blocks)
    outer_balance = fold_balance(
        modeling_index, "outer_spatial_fold", OUTER_GROUP_COLUMN,
        expected_folds=args.outer_folds,
    )
    inner_balance = fold_balance(
        inner_events, "inner_spatial_fold", INNER_GROUP_COLUMN, ["outer_test_fold"],
        expected_folds=args.inner_folds,
    )
    outer_balance_stage = fold_balance(
        modeling_index, "outer_spatial_fold", OUTER_GROUP_COLUMN,
        strata_columns=["country", "target_stage"], expected_folds=args.outer_folds,
    )
    inner_balance_stage = fold_balance(
        inner_events, "inner_spatial_fold", INNER_GROUP_COLUMN, ["outer_test_fold"],
        strata_columns=["country", "target_stage"], expected_folds=args.inner_folds,
    )
    block_inventory = (
        events.groupby([OUTER_GROUP_COLUMN, "country"], as_index=False)
        .agg(
            events=("record_id", "size"), sites=("site_uid", "nunique"),
            site_years=("weather_id", "nunique"), era5_grids=("era5_grid_id", "nunique"),
            first_year=("year", "min"), last_year=("year", "max"),
            min_elevation_m=("dem_elevation_m", "min"),
            median_elevation_m=("dem_elevation_m", "median"),
            max_elevation_m=("dem_elevation_m", "max"),
        )
        .merge(outer_blocks.rename(columns={"fold": "outer_spatial_fold"}), on=OUTER_GROUP_COLUMN, how="left")
        .sort_values(["outer_spatial_fold", OUTER_GROUP_COLUMN, "country"])
    )
    site_fold_count = modeling_index.groupby("site_uid")["outer_spatial_fold"].nunique()
    grid_fold_count = modeling_index.groupby("era5_grid_id")["outer_spatial_fold"].nunique()
    block_fold_count = modeling_index.groupby(OUTER_GROUP_COLUMN)["outer_spatial_fold"].nunique()
    inner_site_fold_count = inner_events.groupby(["outer_test_fold", "site_uid"])["inner_spatial_fold"].nunique()
    inner_grid_fold_count = inner_events.groupby(["outer_test_fold", "era5_grid_id"])["inner_spatial_fold"].nunique()
    inner_block_fold_count = inner_events.groupby(["outer_test_fold", INNER_GROUP_COLUMN])["inner_spatial_fold"].nunique()
    summary = {
        "study_scope": "France and Germany, 1951+, BBCH 07/65/81/89",
        "outer_group_column": OUTER_GROUP_COLUMN,
        "inner_group_column": INNER_GROUP_COLUMN,
        "n_outer_folds": args.outer_folds,
        "n_inner_folds": args.inner_folds,
        "random_seed": args.seed,
        "n_events": int(len(modeling_index)),
        "n_sites": int(modeling_index["site_uid"].nunique()),
        "n_site_years": int(modeling_index["weather_id"].nunique()),
        "n_era5_grids": int(modeling_index["era5_grid_id"].nunique()),
        "n_outer_spatial_blocks": int(modeling_index[OUTER_GROUP_COLUMN].nunique()),
        "outer_assignment_objective": round(float(outer_score), 8),
        "inner_assignment_objectives": {key: round(float(value), 8) for key, value in inner_scores.items()},
        "max_outer_country_stage_event_share_deviation_pct_points": round(
            float(outer_balance_stage["event_share_deviation_pct_points"].abs().max()), 3
        ),
        "max_inner_country_stage_event_share_deviation_pct_points": round(
            float(inner_balance_stage["event_share_deviation_pct_points"].abs().max()), 3
        ),
        "max_outer_country_stage_tier_event_share_deviation_pct_points": round(
            float(outer_balance["event_share_deviation_pct_points"].abs().max()), 3
        ),
        "max_inner_country_stage_tier_event_share_deviation_pct_points": round(
            float(inner_balance["event_share_deviation_pct_points"].abs().max()), 3
        ),
        "leakage_checks": {
            "sites_in_multiple_outer_folds": int(site_fold_count.gt(1).sum()),
            "era5_grids_in_multiple_outer_folds": int(grid_fold_count.gt(1).sum()),
            "one_degree_blocks_in_multiple_outer_folds": int(block_fold_count.gt(1).sum()),
            "sites_in_multiple_inner_folds_within_outer_training_set": int(inner_site_fold_count.gt(1).sum()),
            "era5_grids_in_multiple_inner_folds_within_outer_training_set": int(inner_grid_fold_count.gt(1).sum()),
            "one_degree_blocks_in_multiple_inner_folds_within_outer_training_set": int(inner_block_fold_count.gt(1).sum()),
            "outer_test_blocks_present_in_corresponding_inner_map": int(sum(
                bool(set(outer_blocks.loc[outer_blocks["fold"].eq(outer_fold), OUTER_GROUP_COLUMN])
                     & set(inner_blocks_all.loc[inner_blocks_all["outer_test_fold"].eq(outer_fold), INNER_GROUP_COLUMN]))
                for outer_fold in range(1, args.outer_folds + 1)
            )),
        },
        "scale_decision": {
            "selected": "1 degree",
            "rejected_as_primary": "2 degree",
            "reason": "The largest German 2-degree block contains roughly half of each stage; 1-degree blocks materially improve five-fold balance while preserving regional separation.",
        },
        "balance_note": "Country-stage counts are balanced without splitting spatial groups. Sparse, geographically concentrated model tiers are audited but not forced to equal shares.",
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    modeling_index.to_csv(args.output_dir / "modeling_event_index.csv", index=False)
    outer_blocks.rename(columns={"fold": "outer_spatial_fold"}).to_csv(
        args.output_dir / "outer_spatial_block_folds.csv", index=False
    )
    inner_blocks_all.rename(columns={"fold": "inner_spatial_fold"}).to_csv(
        args.output_dir / "inner_spatial_block_folds.csv", index=False
    )
    outer_balance.to_csv(args.output_dir / "outer_fold_balance.csv", index=False)
    inner_balance.to_csv(args.output_dir / "inner_fold_balance.csv", index=False)
    outer_balance_stage.to_csv(
        args.output_dir / "outer_fold_balance_by_stage_country.csv", index=False
    )
    inner_balance_stage.to_csv(
        args.output_dir / "inner_fold_balance_by_stage_country.csv", index=False
    )
    scale_audit.to_csv(args.output_dir / "block_scale_feasibility_audit.csv", index=False)
    block_inventory.to_csv(args.output_dir / "spatial_block_inventory.csv", index=False)
    (args.output_dir / "validation_design_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_readme(args.output_dir / "README.md")

    print("Frozen nested spatial validation design")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nOuter fold event totals")
    print(modeling_index.groupby("outer_spatial_fold").size().to_string())
    try:
        display_output = args.output_dir.relative_to(REPO_ROOT)
    except ValueError:
        display_output = args.output_dir
    print(f"\nOutput: {display_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
