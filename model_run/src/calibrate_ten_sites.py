"""Reproducible RAW-temperature pilot: six calibration and four held-out sites."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from model.artifacts import load_fit, read_csv, save_fit, write_csv
from model.calibration import FitSettings, _weather_hash, fit
from model.data import observations as validate_observations, prepare_weather
from model.metrics import evaluate
from model.parameters import default_parameters
from model.registry import list_models
from model.simulation import predict
from model.specification import STAGES
from model_run.src.run_first_site import OBSERVATIONS, WEATHER, observation_identity
from src.weather_processing.site_weather import INVENTORY, file_hash, load_inventory


def independence_groups(inventory):
    """Transitive groups from shared grid cells or coordinates rounded to 4 decimals."""
    parent = {uid: uid for uid in inventory.site_uid}

    def root(uid):
        while parent[uid] != uid:
            parent[uid] = parent[parent[uid]]
            uid = parent[uid]
        return uid

    seen = {}
    for row in inventory.itertuples(index=False):
        if not str(row.era5_grid_id).strip():
            raise ValueError("Missing ERA5 grid identity")
        for key in (("grid", row.era5_grid_id), ("location", round(float(row.lat), 4), round(float(row.lon), 4))):
            if key in seen:
                a, b = root(row.site_uid), root(seen[key])
                parent[max(a, b)] = min(a, b)
            else:
                seen[key] = row.site_uid
    return {uid: root(uid) for uid in parent}


def select_sites(eligible, seed):
    """Seeded sampling, conditioned on collective four-stage coverage in each split."""
    if eligible.empty or eligible.group_id.nunique() < 10:
        raise ValueError("Need at least ten independent weather-complete site groups")
    rng = np.random.default_rng(seed)
    base = eligible.sort_values("site").reset_index(drop=True)
    for _ in range(10000):
        # One site per group; unequal availability is documented, not a country quota.
        chosen = base.iloc[rng.permutation(len(base))].drop_duplicates("group_id").head(10).copy()
        chosen["partition"] = ["calibration"] * 6 + ["test"] * 4
        if all(set("|".join(part.stages).split("|")) == set(STAGES)
               for _, part in chosen.groupby("partition")):
            return chosen.reset_index(drop=True)
    raise ValueError("Unable to select a six/four split with all four stages represented collectively")


def prepare_cohort(inventory=INVENTORY, observations_path=OBSERVATIONS, weather_dir=WEATHER, *, seed=20260907,
                   selector=select_sites):
    inventory, observations_path, weather_dir = Path(inventory), Path(observations_path), Path(weather_dir)
    raw_inventory = pd.read_csv(inventory, dtype=str, keep_default_na=False)
    groups = independence_groups(raw_inventory)
    sites = load_inventory(inventory)
    source_hash = file_hash(observations_path)
    all_obs = validate_observations(read_csv(observations_path))
    all_obs["observation_id"] = np.arange(len(all_obs))
    obs_groups = dict(tuple(all_obs.groupby("site", sort=False)))
    # Freeze availability before scanning: the background downloader is a separate writer.
    available = {p.name for p in weather_dir.glob("*.csv")}
    rows = []
    for site in sites:
        identity = observation_identity(site.uid)
        observed = obs_groups.get(identity)
        row = dict(site=identity, site_uid=site.uid, site_name=site.name, lat=site.lat, lon=site.lon,
                   group_id=groups[site.uid], weather_file=site.filename, eligible=False, reason="",
                   weather_sha256="", stages="", n_observations=0, n_seasons=0)
        try:
            if observed is None:
                raise ValueError("No canonical target observations")
            coordinates = observed[["lat", "lon"]].apply(pd.to_numeric, errors="coerce")
            if (not np.isfinite(coordinates.to_numpy()).all()
                    or (coordinates.lat-site.lat).abs().gt(1e-4).any()
                    or (coordinates.lon-site.lon).abs().gt(1e-4).any()):
                raise ValueError("Observation and inventory coordinates disagree or are missing")
            row.update(stages="|".join(sorted(observed.BBCH.unique())), n_observations=len(observed),
                       n_seasons=int(observed.season.nunique()), country=str(observed.country.iloc[0]),
                       first_year=int(observed.season.min()), last_year=int(observed.season.max()))
            if site.filename not in available:
                raise ValueError("Weather file unavailable in initial snapshot")
            path = weather_dir / site.filename
            before = file_hash(path)
            weather = read_csv(path)
            if weather.columns.tolist() != ["Date", "Tmean"]:
                raise ValueError("Weather requires exactly Date,Tmean in Celsius")
            weather["site"] = identity
            values = pd.to_numeric(weather.Tmean, errors="raise")
            if not np.isfinite(values).all() or not values.between(-100, 70).all():
                raise ValueError("Invalid finite Celsius temperatures")
            prepare_weather(weather, observed[["site", "season"]].drop_duplicates(), "Tmean")
            if before != file_hash(path):
                raise ValueError("Weather changed during eligibility checks")
            row.update(eligible=True, weather_sha256=before)
        except (ValueError, OSError) as exc:
            row["reason"] = str(exc)
        rows.append(row)
    audit = pd.DataFrame(rows)
    selected = selector(audit.loc[audit.eligible], seed)
    weather_parts = []
    for row in selected.itertuples(index=False):
        path = weather_dir / row.weather_file
        if file_hash(path) != row.weather_sha256:
            raise ValueError("Selected weather changed; rerun cohort preparation")
        weather = read_csv(path)
        weather["site"] = row.site
        if file_hash(path) != row.weather_sha256:
            raise ValueError("Selected weather changed while reading")
        weather_parts.append(weather)
    if source_hash != file_hash(observations_path):
        raise ValueError("Observation source changed during cohort preparation")
    return dict(sites=selected, observations=all_obs.loc[all_obs.site.isin(selected.site)].copy(),
                weather=pd.concat(weather_parts, ignore_index=True), eligibility=audit,
                metadata=dict(seed=seed, created_utc=datetime.now(timezone.utc).isoformat(),
                    inventory=str(inventory.resolve()), inventory_sha256=file_hash(inventory),
                    observations=str(observations_path.resolve()), observations_sha256=source_hash,
                    weather_dir=str(weather_dir.resolve()),
                    selection="Seeded site sampling; one site per transitive location/grid group; collective four-stage coverage in both partitions",
                    scope="10-site availability-conditioned pilot, not clustered-temperature-zone European validation"))


def summarize_improvement(comparison):
    """Site-balanced errors on paired finite events, with full-denominator attainment."""
    records = []
    for (name, partition, stage), part in comparison.groupby(["model", "partition", "BBCH"], sort=False):
        keys = ["observation_id", "site"]
        a = part.loc[part.parameter_source.eq("default"), keys+["delta_days"]]
        b = part.loc[part.parameter_source.eq("calibrated"), keys+["delta_days"]]
        joined = a.merge(b, on=keys, how="outer", validate="one_to_one", indicator=True, suffixes=("_default", "_calibrated"))
        if not joined._merge.eq("both").all():
            raise ValueError("Before/after observations do not match")
        valid = joined.dropna(subset=["delta_days_default", "delta_days_calibrated"])
        row = dict(model=name, partition=partition, BBCH=stage, n_observations=len(joined),
                   n_sites=int(joined.site.nunique()), n_paired=len(valid), n_sites_paired=int(valid.site.nunique()),
                   default_attainment_rate=float(joined.delta_days_default.notna().mean()),
                   calibrated_attainment_rate=float(joined.delta_days_calibrated.notna().mean()))
        for label in ("default", "calibrated"):
            error = valid[f"delta_days_{label}"].astype(float)
            per_site = pd.DataFrame(dict(site=valid.site, ae=error.abs(), se=error**2, error=error)).groupby("site").mean()
            row.update({f"paired_{label}_mae": per_site.ae.mean(),
                        f"paired_{label}_rmse": np.sqrt(per_site.se.mean()),
                        f"paired_{label}_bias": per_site.error.mean()})
        row["mae_improvement_days"] = row["paired_default_mae"] - row["paired_calibrated_mae"]
        row["rmse_improvement_days"] = row["paired_default_rmse"] - row["paired_calibrated_rmse"]
        records.append(row)
    return pd.DataFrame(records)


def run_model(name, cohort, settings, output, *, baseline_parameters=None):
    directory = Path(output) / name
    directory.mkdir(parents=True, exist_ok=False)
    defaults = default_parameters(name) if baseline_parameters is None else dict(baseline_parameters)
    with (directory / "default_parameters.json").open("x") as stream:
        json.dump(defaults, stream, indent=2, allow_nan=False)
    observed, weather, sites = cohort["observations"], cohort["weather"], cohort["sites"]
    calibration_ids = sites.loc[sites.partition.eq("calibration"), "site"]
    calibration = observed.loc[observed.site.isin(calibration_ids)].copy()
    calibration_weather = weather.loc[weather.site.isin(calibration_ids)].copy()
    start = time.monotonic()
    print(f"{name}: fitting {len(calibration)} observations at {calibration.site.nunique()} calibration sites", flush=True)
    fitted = fit(name, calibration, calibration_weather, settings)
    save_fit(fitted, directory / "fit.json")
    comparisons, predictions, metrics = [], [], []
    for partition in ("calibration", "test"):
        ids = sites.loc[sites.partition.eq(partition), "site"]
        obs = observed.loc[observed.site.isin(ids)]
        forcing = weather.loc[weather.site.isin(ids)]
        seasons = obs[["site", "season"]].drop_duplicates().sort_values(["site", "season"])
        for source, parameters in (("default", defaults), ("calibrated", fitted.parameters)):
            predicted = predict(name, parameters, forcing, seasons, temperature_column="Tmean", temperature_input="RAW")
            comparison = obs.rename(columns={"Date": "observed_date"}).merge(
                predicted, on=["site", "season", "BBCH"], how="left", validate="many_to_one")
            comparison["delta_days"] = (comparison.predicted_date-comparison.observed_date).dt.days
            comparison["absolute_error_days"] = comparison.delta_days.abs()
            metric = evaluate(obs, predicted)
            for frame in (predicted, comparison, metric):
                frame.insert(0, "model", name)
                frame["partition"], frame["parameter_source"] = partition, source
            comparisons.append(comparison)
            predictions.append(predicted)
            metrics.append(metric)
    result = dict(comparison=pd.concat(comparisons, ignore_index=True),
                  predictions=pd.concat(predictions, ignore_index=True), metrics=pd.concat(metrics, ignore_index=True))
    result["improvement"] = summarize_improvement(result["comparison"])
    for key, frame in result.items():
        write_csv(frame, directory / f"{key}.csv")
    result["diagnostics"] = dict(model=name, objective_value=fitted.objective_value,
                                  optimizer_converged=fitted.optimizer_converged,
                                  boundary_hits="|".join(fitted.diagnostics["boundary_hits"]),
                                  elapsed_seconds=time.monotonic()-start)
    print(f"{name}: finished in {result['diagnostics']['elapsed_seconds']:.1f}s; calibration objective={fitted.objective_value:.3f}; converged={fitted.optimizer_converged}", flush=True)
    return result


def overall_summary(improvement):
    """Equal-stage mean of paired site-balanced metrics; never silently omit a stage."""
    records = []
    for (name, partition), part in improvement.groupby(["model", "partition"], sort=False):
        if len(part) != 4 or set(part.BBCH) != set(STAGES):
            raise ValueError("Overall summaries require exactly four stage rows")
        row = dict(model=name, partition=partition, n_observations=int(part.n_observations.sum()),
                   n_paired=int(part.n_paired.sum()), minimum_sites_per_stage=int(part.n_sites_paired.min()))
        for source in ("default", "calibrated"):
            row[f"{source}_attainment_rate"] = float(np.average(
                part[f"{source}_attainment_rate"], weights=part.n_observations))
            for metric in ("mae", "rmse", "bias"):
                row[f"mean_stage_{source}_{metric}"] = part[f"paired_{source}_{metric}"].mean(skipna=False)
        row["mae_improvement_days"] = row["mean_stage_default_mae"]-row["mean_stage_calibrated_mae"]
        row["mae_improvement_percent"] = (100 * row["mae_improvement_days"] / row["mean_stage_default_mae"]
                                          if row["mean_stage_default_mae"] > 0 else np.nan)
        row["rmse_improvement_days"] = row["mean_stage_default_rmse"]-row["mean_stage_calibrated_rmse"]
        records.append(row)
    return pd.DataFrame(records)


def save_cohort(cohort, output):
    output.mkdir(parents=True, exist_ok=False)
    for key in ("sites", "observations", "weather", "eligibility"):
        write_csv(cohort[key], output / f"{key}.csv")
    metadata = {**cohort["metadata"], "snapshot_sha256": {
        key: file_hash(output / f"{key}.csv") for key in ("sites", "observations", "weather", "eligibility")}}
    with (output / "cohort.json").open("x") as stream:
        json.dump(metadata, stream, indent=2, allow_nan=False)


def load_cohort(directory):
    directory = Path(directory)
    metadata = json.loads((directory / "cohort.json").read_text())
    result = {"metadata": metadata}
    for key, digest in metadata["snapshot_sha256"].items():
        path = directory / f"{key}.csv"
        if file_hash(path) != digest:
            raise ValueError(f"Cohort snapshot checksum mismatch: {key}")
        result[key] = read_csv(path)
    result["observations"] = validate_observations(result["observations"])
    return result


def verify_run(directory, *, names=None, expected_site_counts=(6, 4)):
    """Recreate saved predictions and metrics without refitting or changing files."""
    directory = Path(directory)
    cohort = load_cohort(directory)
    sites, observed, weather = cohort["sites"], cohort["observations"], cohort["weather"]
    counts = sites.groupby("partition").size().to_dict()
    assert set(counts) == {"calibration", "test"}
    assert sites.site.is_unique
    assert sites.groupby("group_id").partition.nunique().eq(1).all()
    if expected_site_counts is not None:
        assert counts == dict(zip(("calibration", "test"), expected_site_counts))
        assert sites.site.nunique() == sites.group_id.nunique() == sum(expected_site_counts)
    assert set(observed.site) == set(sites.site)
    calibration_ids = sites.loc[sites.partition.eq("calibration"), "site"]
    calibration = validate_observations(observed.loc[observed.site.isin(calibration_ids)])
    calibration_hash = hashlib.sha256(calibration.to_csv(index=False, date_format="%Y-%m-%d").encode()).hexdigest()
    full_run = names is None
    names = list(list_models()) if full_run else list(names)
    for name in names:
        folder = directory / name
        fitted = load_fit(folder / "fit.json")
        assert fitted.calibration_hash == calibration_hash
        earliest = math.ceil(fitted.bounds["start_doy"][0]) if "start_doy" in fitted.bounds else None
        calibration_weather = weather.loc[weather.site.isin(calibration_ids)]
        prepared = prepare_weather(calibration_weather, calibration[["site", "season"]].drop_duplicates(),
                                   "Tmean", earliest)
        assert fitted.weather_hash == _weather_hash(prepared)
        assert fitted.diagnostics["n_sites"] == counts["calibration"]
        assert fitted.temperature_input == "RAW"
        defaults = json.loads((folder / "default_parameters.json").read_text())
        if cohort["metadata"].get("response_profile") == "literature_fixed_responses_v1":
            from model.structure_comparison import fixed_parameters
            assert all(fitted.parameters[key] == value and defaults[key] == value
                       for key, value in fixed_parameters(name).items())
        saved_predictions = pd.read_csv(folder / "predictions.csv", dtype={"BBCH": str})
        saved_comparison = pd.read_csv(folder / "comparison.csv", dtype={"BBCH": str}, keep_default_na=False)
        saved_metrics = pd.read_csv(folder / "metrics.csv", dtype={"BBCH": str})
        for partition in ("calibration", "test"):
            ids = sites.loc[sites.partition.eq(partition), "site"]
            obs = observed.loc[observed.site.isin(ids)]
            assert set(obs.BBCH) == set(STAGES)
            seasons = obs[["site", "season"]].drop_duplicates().sort_values(["site", "season"])
            forcing = weather.loc[weather.site.isin(ids)]
            for source, parameters in (("default", defaults), ("calibrated", fitted.parameters)):
                predicted = predict(name, parameters, forcing, seasons, temperature_column="Tmean")
                stored = saved_predictions.loc[lambda x: x.partition.eq(partition) & x.parameter_source.eq(source)].copy()
                keys = ["site", "season", "BBCH"]
                expected = predicted.sort_values(keys).reset_index(drop=True)
                stored = stored.sort_values(keys).reset_index(drop=True)
                assert stored.model.eq(name).all()
                pd.testing.assert_frame_equal(expected[keys+["status"]], stored[keys+["status"]])
                assert pd.to_datetime(stored.predicted_date).equals(expected.predicted_date)
                joined = obs.merge(predicted, on=keys, how="left", validate="many_to_one").sort_values("observation_id")
                actual = saved_comparison.loc[lambda x: x.partition.eq(partition) & x.parameter_source.eq(source)].sort_values("observation_id")
                assert actual.observation_id.tolist() == joined.observation_id.tolist()
                assert actual.variety.tolist() == joined.variety.tolist()
                assert actual.site.tolist() == joined.site.tolist()
                assert pd.to_datetime(actual.observed_date).tolist() == joined.Date.tolist()
                pd.testing.assert_series_equal(pd.to_datetime(actual.predicted_date).reset_index(drop=True),
                                               joined.predicted_date.reset_index(drop=True))
                assert actual.status.tolist() == joined.status.tolist()
                np.testing.assert_allclose(pd.to_numeric(actual.delta_days.replace("", np.nan)),
                                           (joined.predicted_date-joined.Date).dt.days, equal_nan=True)
                np.testing.assert_allclose(pd.to_numeric(actual.absolute_error_days.replace("", np.nan)),
                                           (joined.predicted_date-joined.Date).dt.days.abs(), equal_nan=True)
                recomputed = evaluate(obs, predicted).sort_values("BBCH").reset_index(drop=True)
                metric = saved_metrics.loc[lambda x: x.partition.eq(partition) & x.parameter_source.eq(source)].sort_values("BBCH").reset_index(drop=True)
                pd.testing.assert_frame_equal(recomputed, metric[recomputed.columns], check_dtype=False)
        normalized_comparison = saved_comparison.copy()
        normalized_comparison["delta_days"] = pd.to_numeric(normalized_comparison.delta_days.replace("", np.nan))
        recomputed = summarize_improvement(normalized_comparison).sort_values(["partition", "BBCH"]).reset_index(drop=True)
        stored = pd.read_csv(folder / "improvement.csv", dtype={"BBCH": str}).sort_values(["partition", "BBCH"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(recomputed, stored, check_dtype=False)
    if full_run:
        for key in ("comparison", "predictions", "metrics", "improvement"):
            expected = pd.concat([pd.read_csv(directory / name / f"{key}.csv", dtype={"BBCH": str})
                                  for name in names], ignore_index=True)
            stored = pd.read_csv(directory / f"{key}.csv", dtype={"BBCH": str})
            pd.testing.assert_frame_equal(expected, stored, check_dtype=False)
        expected = overall_summary(pd.read_csv(directory / "improvement.csv", dtype={"BBCH": str}))
        pd.testing.assert_frame_equal(expected, pd.read_csv(directory / "summary.csv"), check_dtype=False)
    return dict(calibration_sites=counts["calibration"], test_sites=counts["test"], observations=len(observed), verified_models=names,
                checks="Frozen checksums, split independence, calibration-only observation/weather hashes, regenerated predictions, preserved observed records, errors and metrics",
                combined_tables_checked=full_run,
                verified_utc=datetime.now(timezone.utc).isoformat())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--observations", type=Path, default=OBSERVATIONS)
    parser.add_argument("--weather-dir", type=Path, default=WEATHER)
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--cohort", type=Path, help="Reuse a frozen, checksum-verified cohort")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true", help="Read-only verification of an existing --output run")
    parser.add_argument("--output", type=Path, required=True, help="New directory; never overwritten")
    parser.add_argument("--maxiter", type=int, default=300)
    parser.add_argument("--popsize", type=int, default=15)
    parser.add_argument("--seeds", type=int, nargs="+", default=[20260907, 20260908, 20260909])
    parser.add_argument("--workers", type=int, default=1, help="Concurrent models; each fit uses one optimizer worker")
    args = parser.parse_args(argv)
    if args.verify_only:
        print(json.dumps(verify_run(args.output), indent=2))
        return 0
    if args.output.exists():
        parser.error("Output exists; choose a new directory")
    if args.workers < 1:
        parser.error("workers must be positive")
    settings = FitSettings(seeds=tuple(args.seeds), maxiter=args.maxiter, popsize=args.popsize, temperature_column="Tmean")
    settings.validate()
    cohort = load_cohort(args.cohort) if args.cohort else prepare_cohort(
        args.inventory, args.observations, args.weather_dir, seed=args.seed)
    save_cohort(cohort, args.output)
    print(cohort["sites"][["site", "partition", "stages", "n_observations", "n_seasons"]].to_string(index=False), flush=True)
    if args.prepare_only:
        return 0
    with (args.output / "settings.json").open("x") as stream:
        json.dump(asdict(settings), stream, indent=2)
    with (args.output / "source_sha256.json").open("x") as stream:
        json.dump({str(path.relative_to(ROOT)): file_hash(path) for path in
                   [Path(__file__).resolve(), *sorted((ROOT / "model").rglob("*.py"))]}, stream, indent=2)
    names = list(list_models())
    if args.workers == 1:
        results = [run_model(name, cohort, settings, args.output) for name in names]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(run_model, name, cohort, settings, args.output) for name in names]
            results = [future.result() for future in futures]
    for key in ("comparison", "predictions", "metrics", "improvement"):
        write_csv(pd.concat([result[key] for result in results], ignore_index=True), args.output / f"{key}.csv")
    write_csv(pd.DataFrame([result["diagnostics"] for result in results]), args.output / "diagnostics.csv")
    write_csv(overall_summary(pd.concat([result["improvement"] for result in results])), args.output / "summary.csv")
    with (args.output / "verification.json").open("x") as stream:
        json.dump(verify_run(args.output), stream, indent=2)
    print(f"Completed all {len(results)} models: {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
