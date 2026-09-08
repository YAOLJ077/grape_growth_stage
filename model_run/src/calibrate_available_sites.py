"""Interim RAW, threshold-only calibration on every weather-complete inventory site.

Seeded 80/20 grouped holdout, NOT temperature-zone-stratified European validation.
The frozen cohort does not change when background weather downloads progress.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from model.artifacts import write_csv
from model.parameters import default_parameters
from model.registry import list_models
from model.specification import STAGES
from model.structure_comparison import PROFILE, fixed_parameters, threshold_only_settings
from model_run.src.calibrate_ten_sites import (
    prepare_cohort, save_cohort, load_cohort, run_model, verify_run, overall_summary,
)
from model_run.src.run_first_site import OBSERVATIONS, WEATHER, observation_identity
from src.weather_processing.site_weather import INVENTORY, file_hash, load_inventory


def split_available(eligible, seed):
    """Keep every eligible site; randomize whole groups, targeting 20% of sites."""
    if eligible.empty or eligible.group_id.nunique() < 5:
        raise ValueError("Need at least five independent weather-complete groups")
    base = eligible.sort_values("site").reset_index(drop=True).copy()
    sizes = base.groupby("group_id", sort=True).size()
    rng = np.random.default_rng(seed)
    for attempt in range(10000):
        order = rng.permutation(sizes.index.to_numpy())
        cumulative = sizes.loc[order].cumsum().to_numpy()
        n_test = int(np.argmin(np.abs(cumulative[:-1] - .2 * len(base)))) + 1
        test_groups = set(order[:n_test])
        chosen = base.assign(partition=np.where(base.group_id.isin(test_groups), "test", "calibration"))
        if all(set("|".join(part.stages).split("|")) == set(STAGES)
               for _, part in chosen.groupby("partition")):
            chosen["split_attempt"] = attempt + 1
            return chosen
    raise ValueError("No grouped split with collective four-stage coverage in both partitions")


def prepare_available(inventory=INVENTORY, observations_path=OBSERVATIONS, weather_dir=WEATHER, *, seed=20260907):
    cohort = prepare_cohort(inventory, observations_path, weather_dir, seed=seed, selector=split_available)
    canonical = pd.read_csv(observations_path, dtype=str, keep_default_na=False)
    mapped = {observation_identity(site.uid) for site in load_inventory(inventory)}
    outside = canonical.loc[~canonical.site.isin(mapped)]
    cohort["metadata"].update(
        scope="Interim availability-conditioned grouped site holdout; not full-European validation",
        selection="All weather-complete sites; seeded whole-group allocation targeting 80/20 sites; collective four-stage coverage",
        temperature_zone_stratified=False, response_profile=PROFILE,
        canonical_sites=int(canonical.site.nunique()), canonical_observations=len(canonical),
        canonical_sites_outside_inventory=int(outside.site.nunique()),
        canonical_observations_outside_inventory=len(outside),
        exclusion_unit="Whole site if any observed season lacks September 1 prior year through December 31 weather",
        baseline="Illustrative uncalibrated thresholds with the same fixed response parameters as calibrated models",
        temperature_input="RAW", residual_ml=False)
    return cohort


def baseline_parameters(name):
    return {**default_parameters(name), **fixed_parameters(name)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--observations", type=Path, default=OBSERVATIONS)
    parser.add_argument("--weather-dir", type=Path, default=WEATHER)
    parser.add_argument("--cohort", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--seeds", type=int, nargs="+", default=[20260907, 20260908, 20260909])
    parser.add_argument("--maxiter", type=int, default=300)
    parser.add_argument("--popsize", type=int, default=15)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_only:
        print(json.dumps(verify_run(args.output, expected_site_counts=None), indent=2))
        return 0
    if args.output.exists():
        parser.error("Output exists; choose a new directory")
    if args.workers < 1:
        parser.error("workers must be positive")
    names = list(list_models())
    settings = {name: threshold_only_settings(name, seeds=tuple(args.seeds), maxiter=args.maxiter,
                    popsize=args.popsize, temperature_column="Tmean") for name in names}
    for item in settings.values():
        item.validate()
    cohort = load_cohort(args.cohort) if args.cohort else prepare_available(
        args.inventory, args.observations, args.weather_dir, seed=args.seed)
    if cohort["metadata"].get("response_profile") != PROFILE:
        raise ValueError("Require a frozen all-available fixed-response cohort, not the historical pilot")
    save_cohort(cohort, args.output)
    print(cohort["sites"].groupby(["country", "partition"]).agg(
        sites=("site", "size"), observations=("n_observations", "sum"), seasons=("n_seasons", "sum")).to_string(), flush=True)
    if args.prepare_only:
        return 0
    with (args.output / "settings.json").open("x") as stream:
        json.dump({name: asdict(item) for name, item in settings.items()}, stream, indent=2)
    sources = [Path(__file__).resolve(), ROOT / "model_run/src/calibrate_ten_sites.py",
               ROOT / "model_run/src/run_first_site.py", ROOT / "src/weather_processing/site_weather.py",
               *sorted((ROOT / "model").rglob("*.py"))]
    with (args.output / "source_sha256.json").open("x") as stream:
        json.dump({str(path.relative_to(ROOT)): file_hash(path) for path in sources}, stream, indent=2)
    if args.workers == 1:
        results = [run_model(name, cohort, settings[name], args.output,
                            baseline_parameters=baseline_parameters(name)) for name in names]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(run_model, name, cohort, settings[name], args.output,
                                   baseline_parameters=baseline_parameters(name)) for name in names]
            results = [future.result() for future in futures]
    for key in ("comparison", "predictions", "metrics", "improvement"):
        write_csv(pd.concat([result[key] for result in results], ignore_index=True), args.output / f"{key}.csv")
    write_csv(pd.DataFrame([result["diagnostics"] for result in results]), args.output / "diagnostics.csv")
    write_csv(overall_summary(pd.concat([result["improvement"] for result in results])), args.output / "summary.csv")
    with (args.output / "verification.json").open("x") as stream:
        json.dump(verify_run(args.output, expected_site_counts=None), stream, indent=2)
    print(f"Completed and verified all {len(names)} models: {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
