"""Leakage-safe pilot features, whole-group folds and paired evaluation."""
import numpy as np
import pandas as pd

from model.specification import STAGES

KEYS = ["site", "season", "BBCH"]
TERRAIN = ["dem_elevation_m", "slope_deg", "northness", "eastness", "dem_local_std_m"]
FEATURES = ["pbm_doy", "phase_duration_days", *[
    f"Tmean_{stat}_{window}" for window in (7, 30, 90)
    for stat in ("mean", "std", "min", "max")], "daylength_hours", *TERRAIN]


def make_folds(sites, observations, seed=20260908):
    """Seeded size-balanced group allocation, not temperature-zone clustering."""
    result = sites[["site", "group_id", "partition"]].sort_values("site").copy()
    if result.site.duplicated().any() or result.groupby("group_id").partition.nunique().gt(1).any():
        raise ValueError("Sites and shared location/grid groups must stay in one partition")
    if set(result.partition) != {"calibration", "test"}:
        raise ValueError("Require calibration and test partitions")
    calibration = result.loc[result.partition.eq("calibration")]
    sizes = calibration.groupby("group_id").size()
    if len(sizes) < 4:
        raise ValueError("Need at least four calibration groups")
    rng = np.random.default_rng(seed)
    for _ in range(1000):
        totals = np.zeros(4, dtype=int)
        assignment = {}
        for group in rng.permutation(sizes.index.to_numpy()):
            fold = int(np.argmin(totals))
            assignment[group] = fold
            totals[fold] += sizes[group]
        result["fold"] = result.group_id.map(assignment).fillna(-1).astype(int)
        # Each fold has all stages, thus every ordinary and nested training set does.
        if all(set(observations.loc[observations.site.isin(result.loc[result.fold.eq(f), "site"]),
                                    "BBCH"].astype(str).str.zfill(2)) == set(STAGES) for f in range(4)):
            return result.reset_index(drop=True)
    raise ValueError("Cannot allocate four grouped folds with collective stage coverage")


def crossfit_jobs(folds):
    jobs = []
    for nested in (False, True):
        for f in (range(1, 4) if nested else range(4)):
            excluded = [0, f] if nested else [f]
            jobs.append(dict(name=f"{'nested' if nested else 'oof'}_{f}",
                excluded_folds=excluded,
                train_sites=sorted(folds.loc[folds.fold.ge(0) & ~folds.fold.isin(excluded), "site"]),
                predict_sites=sorted(folds.loc[folds.fold.eq(f), "site"])))
    return jobs


def build_features(predictions, weather, terrain, *, temperature_column="Tmean"):
    """No observation-date argument: all dynamic boundaries are PBM predictions.

    Daylength uses the FAO-56 sunset-angle approximation (365-day solar year),
    https://www.fao.org/4/x0490e/x0490e07.htm, equations 24, 25 and 34.
    Weather windows include their predicted end date; std uses ddof=0.
    """
    result = predictions.copy().reset_index(drop=True)
    result["BBCH"] = result.BBCH.astype(str).str.zfill(2)
    result["predicted_date"] = pd.to_datetime(result.predicted_date)
    if result.duplicated(KEYS).any():
        raise ValueError("Duplicate PBM prediction keys")
    if terrain.site.duplicated().any():
        raise ValueError("Duplicate terrain sites")
    topography = terrain.set_index("site")
    needed = set(result.site)
    if not needed.issubset(topography.index):
        raise ValueError("Missing terrain sites")
    terrain_values = topography.loc[sorted(needed), ["lat", *TERRAIN]].to_numpy(float)
    if np.isinf(terrain_values).any():
        raise ValueError("Infinite terrain predictors")
    weather = weather.loc[weather.site.isin(needed)].copy()
    weather["Date"] = pd.to_datetime(weather.Date)
    if weather.duplicated(["site", "Date"]).any():
        raise ValueError("Duplicate weather dates")
    lookup = {}
    for site, frame in weather.groupby("site", sort=False):
        frame = frame.sort_values("Date")
        if temperature_column not in frame.columns:
            raise ValueError(f"Missing residual feature temperature column: {temperature_column}")
        lookup[site] = (frame.Date.to_numpy(dtype="datetime64[D]"), frame[temperature_column].to_numpy(float))
    dates = result.set_index(KEYS).predicted_date
    values = np.full((len(result), len(FEATURES)), np.nan)
    phase_starts = []
    for row in result.itertuples():
        if pd.isna(row.predicted_date):
            phase_starts.append(pd.NaT)
            continue
        stage_index = STAGES.index(row.BBCH)
        start = (pd.Timestamp(int(row.season), 1, 1) if stage_index == 0 else
                 dates.get((row.site, row.season, STAGES[stage_index - 1]), pd.NaT) + pd.Timedelta(days=1))
        if pd.isna(start) or start > row.predicted_date:
            raise ValueError("Missing or unordered preceding PBM stage")
        phase_starts.append(start)
        doy = (row.predicted_date - pd.Timestamp(int(row.season), 1, 1)).days + 1
        features = [doy, (row.predicted_date - start).days + 1]
        if row.site not in lookup:
            raise ValueError("Missing site weather")
        day_array, temperature = lookup[row.site]
        end = np.datetime64(row.predicted_date, "D")
        for window in (7, 30, 90):
            wanted = np.arange(end - np.timedelta64(window - 1, "D"), end + np.timedelta64(1, "D"))
            indices = np.searchsorted(day_array, wanted)
            if (indices >= len(day_array)).any() or not np.array_equal(day_array[indices], wanted):
                raise ValueError(f"Incomplete weather feature window: {row.site}, {row.BBCH}, {end}")
            t = temperature[indices]
            if not np.isfinite(t).all():
                raise ValueError("Nonfinite weather feature window")
            features.extend((t.mean(), t.std(ddof=0), t.min(), t.max()))
        terrain_row = topography.loc[row.site]
        declination = .409 * np.sin(2 * np.pi * row.predicted_date.dayofyear / 365 - 1.39)
        angle = np.arccos(np.clip(-np.tan(np.deg2rad(terrain_row.lat)) * np.tan(declination), -1, 1))
        # Missing terrain derivatives are retained as NaN and imputed by the
        # learner's training-fold preprocessor; no site-level value is invented.
        terrain_features = terrain_row[TERRAIN].to_numpy(float)
        if np.isinf(terrain_features).any():
            raise ValueError("Infinite terrain predictors")
        features.extend((24 / np.pi * angle, *terrain_features))
        values[row.Index] = features
    result[FEATURES] = values
    result["feature_end_date"] = result.predicted_date
    result["phase_start_date"] = phase_starts
    return result


def correct_dates(predictions, residuals):
    result = predictions.copy().reset_index(drop=True)
    result["predicted_date"] = pd.to_datetime(result.predicted_date)
    corrections = np.asarray(residuals, dtype=float)
    valid = result.predicted_date.notna().to_numpy()
    if corrections.shape != (len(result),) or not np.isfinite(corrections[valid]).all():
        raise ValueError("Require a finite correction for every attained PBM stage")
    if result.duplicated(KEYS).any():
        raise ValueError("Duplicate PBM prediction keys")
    corrections = np.where(valid, corrections, np.nan)
    result["pbm_date"] = result.predicted_date
    result["residual_prediction_days"] = corrections
    # NumPy nearest-even rounding is explicit and reproducible at half-day ties.
    result["unconstrained_date"] = result.predicted_date + pd.to_timedelta(np.nan_to_num(np.rint(corrections)), unit="D")
    result["predicted_date"] = result.unconstrained_date
    for _, part in result.groupby(["site", "season"], sort=False):
        previous = None
        for idx in part.sort_values("BBCH").index:
            date = result.at[idx, "predicted_date"]
            if pd.isna(date):
                continue
            if previous is not None:
                date = max(date, previous + pd.Timedelta(days=1))
            result.at[idx, "predicted_date"] = date
            previous = date
    result["order_adjustment_days"] = (result.predicted_date - result.unconstrained_date).dt.days
    result["outside_target_year"] = result.predicted_date.notna() & result.predicted_date.dt.year.ne(result.season)
    result["predicted_doy"] = (result.predicted_date - pd.to_datetime(result.season.astype(str) + "-01-01")).dt.days + 1
    return result


def site_mean(values, sites):
    work = pd.DataFrame(dict(value=np.asarray(values, float), site=np.asarray(sites)))
    if work.empty or not np.isfinite(work.value).all():
        raise ValueError("Need finite values for site-balanced mean")
    return float(work.groupby("site").value.mean().mean())


def metrics(comparison):
    records = []
    for (partition, method, stage), part in comparison.groupby(["partition", "method", "BBCH"], sort=True):
        finite = part.loc[np.isfinite(part.delta_days)]
        record = dict(partition=partition, method=method, BBCH=stage,
            n_observations=len(part), n_sites=part.site.nunique(), n_attained=len(finite),
            n_unattained=len(part) - len(finite), n_sites_attained=finite.site.nunique(),
            attainment_rate=len(finite) / len(part))
        for label, errors in (("mae", finite.delta_days.abs()), ("rmse", finite.delta_days ** 2),
                              ("bias", finite.delta_days)):
            value = site_mean(errors, finite.site) if len(finite) else np.nan
            record[f"site_balanced_{label}"] = np.sqrt(value) if label == "rmse" else value
        records.append(record)
    return pd.DataFrame(records)


def paired_improvement(comparison, n_bootstrap=2000, seed=20260908):
    if n_bootstrap < 1:
        raise ValueError("n_bootstrap must be positive")
    if comparison.duplicated(["partition", "method", "observation_id"]).any():
        raise ValueError("Duplicate comparison observations")
    records = []
    for (partition, stage), part in comparison.groupby(["partition", "BBCH"], sort=True):
        baseline = part.loc[part.method.eq("pbm")].set_index("observation_id").sort_index()
        for method in sorted(set(part.method) - {"pbm"}):
            candidate = part.loc[part.method.eq(method)].set_index("observation_id").sort_index()
            if (not baseline.index.equals(candidate.index) or
                    not baseline[["site", "group_id"]].equals(candidate[["site", "group_id"]]) or
                    not np.array_equal(np.isfinite(baseline.delta_days), np.isfinite(candidate.delta_days))):
                raise ValueError("Methods require matched observations and identical attainment")
            finite = np.isfinite(baseline.delta_days)
            diff = baseline.loc[finite, ["site", "group_id"]].copy()
            diff["improvement"] = baseline.loc[finite, "delta_days"].abs() - candidate.loc[finite, "delta_days"].abs()
            per_site = diff.groupby(["site", "group_id"]).improvement.mean().reset_index()
            if per_site.empty:
                records.append(dict(partition=partition, method=method, BBCH=stage, n_pairs=0,
                    n_sites=0, n_groups=0, mae_improvement_days=np.nan, ci_low=np.nan, ci_high=np.nan))
                continue
            groups = per_site.groupby("group_id").improvement.agg(["sum", "size"])
            rng = np.random.default_rng(seed)
            draws = rng.integers(0, len(groups), size=(n_bootstrap, len(groups)))
            boot = groups["sum"].to_numpy()[draws].sum(axis=1) / groups["size"].to_numpy()[draws].sum(axis=1)
            records.append(dict(partition=partition, method=method, BBCH=stage,
                n_pairs=int(finite.sum()), n_sites=len(per_site), n_groups=len(groups),
                mae_improvement_days=per_site.improvement.mean(),
                ci_low=np.quantile(boot, .025), ci_high=np.quantile(boot, .975)))
    return pd.DataFrame(records)
