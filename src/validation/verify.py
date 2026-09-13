#!/usr/bin/env python3
"""Verify final model evidence, dates and equal-site metrics without refitting."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MODELS = ['FL', 'FB', 'CL-FL-S', 'CL-FL-P', 'CB-FL-S', 'CB-FL-P',
          'CL-FB-S', 'CL-FB-P', 'CB-FB-S', 'CB-FB-P']
UNITS = [f'{model}/{temperature}' for model in MODELS for temperature in ['RAW', 'DEM']]
STAGES = ['07', '65', '81', '89']
FINAL = ['median_cutoff_calibration_20260912', 'median_cutoff_ml_20260912']


def resolve_source(raw: str, root: Path = ROOT) -> Path:
    """Map a recorded absolute repository suffix onto this checkout only."""
    path, root = Path(raw), root.resolve()
    if '..' in path.parts:
        raise ValueError(f'Parent traversal in source path: {raw}')
    if not path.is_absolute():
        candidate = root / path
    elif path.is_relative_to(root):
        candidate = path
    else:
        anchors = {'model', 'model_run', 'data', 'src', 'tests', 'paper', 'fig'}
        matches = [root.joinpath(*path.parts[i:]) for i, part in enumerate(path.parts)
                   if part in anchors and root.joinpath(*path.parts[i:]).is_file()]
        if len(matches) != 1:
            raise ValueError(f'Cannot uniquely relocate source: {raw}')
        candidate = matches[0]
    candidate = candidate.resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError(f'Missing source or path outside checkout: {raw}')
    return candidate


def check_hash(path: Path, expected: str, cache: dict) -> None:
    stat = path.stat()
    signature = (stat.st_size, stat.st_mtime_ns)
    cached = cache.get(path)
    if cached is None or cached[:2] != signature:
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        cache[path] = (*signature, actual)
    if cache[path][2] != expected:
        raise ValueError(f'SHA-256 mismatch: {path}')


def verify_marker(marker: Path, cache: dict) -> int:
    document = json.loads(marker.read_text())
    if document.get('verified') is False or not document.get('artifacts'):
        raise ValueError(f'Unverified or empty marker: {marker}')
    count = 0
    for name, expected in document['artifacts'].items():
        path = (marker.parent / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(marker.parent.resolve()):
            raise ValueError(f'Artifact leaves its unit: {marker}/{name}')
        check_hash(path, expected, cache)
        count += 1
    return count


def metric_values(frame: pd.DataFrame, view: str) -> dict:
    errors = frame[f'{view}_error_days'].astype(float)
    values = pd.DataFrame({'site': frame.site, 'absolute': errors.abs(),
                           'square': errors ** 2, 'signed': errors})
    means = values.groupby('site')[['absolute', 'square', 'signed']].mean().mean()
    rates = frame.groupby('site')[['raw_attained', 'attained_by_cutoff', 'cutoff_assigned']].mean().mean()
    return dict(n_observations=len(frame), n_sites=frame.site.nunique(),
        n_scored=int(np.isfinite(errors).sum()), mae_days=means.absolute,
        rmse_days=np.sqrt(means.square), bias_days=means.signed,
        raw_attainment=frame.raw_attained.mean(), raw_site_attainment=rates.raw_attained,
        cutoff_attainment=frame.attained_by_cutoff.mean(), cutoff_site_attainment=rates.attained_by_cutoff,
        cutoff_assignment_fraction=frame.cutoff_assigned.mean(),
        cutoff_assignment_site_fraction=rates.cutoff_assigned)


def verify_predictions(folder: Path) -> dict:
    frame = pd.read_csv(folder / 'predictions.csv.gz', low_memory=False,
                        dtype={'site': str, 'BBCH': str, 'observation_id': str})
    key = ['method', 'partition', 'observation_id']
    if frame.duplicated(key).any():
        raise ValueError(f'Duplicate observation predictions: {folder}')
    observed = pd.to_datetime(frame.Date, errors='raise')
    raw = pd.to_datetime(frame.raw_predicted_date, errors='raise')
    scoring = pd.to_datetime(frame.scoring_date, errors='raise')
    cutoff = pd.to_datetime(frame.season.astype(str) + '-11-04', errors='raise')
    for view, dates in [('raw', raw), ('scoring', scoring)]:
        errors = (dates - observed).dt.days.to_numpy(dtype=float)
        np.testing.assert_allclose(frame[f'{view}_error_days'], errors, atol=1e-10, rtol=0, equal_nan=True)
    np.testing.assert_allclose(frame.error_days, frame.raw_error_days, atol=1e-10, rtol=0, equal_nan=True)
    np.testing.assert_array_equal(pd.to_datetime(frame.predicted_date).to_numpy(), raw.to_numpy())
    np.testing.assert_array_equal(frame.raw_attained, raw.notna())
    np.testing.assert_array_equal(frame.attained_by_cutoff, raw.notna() & raw.le(cutoff))
    assigned = frame.BBCH.isin(['81', '89']) & (raw.isna() | raw.gt(cutoff))
    expected_scoring = raw.mask(assigned, cutoff)
    np.testing.assert_array_equal(scoring.to_numpy(), expected_scoring.to_numpy())
    np.testing.assert_array_equal(frame.cutoff_assigned, assigned)
    np.testing.assert_array_equal(pd.to_datetime(frame.cutoff_date).to_numpy(), cutoff.to_numpy())
    np.testing.assert_array_equal(frame.assignment_reason.fillna('').ne(''), assigned)
    if 'pbm_raw_predicted_date' in frame:
        pbm = pd.to_datetime(frame.pbm_raw_predicted_date, errors='raise')
        np.testing.assert_array_equal(frame.pbm_raw_attained, pbm.notna())
        np.testing.assert_array_equal(frame.pbm_attained_by_cutoff, pbm.notna() & pbm.le(cutoff))
    metrics = pd.read_csv(folder / 'metrics.csv', dtype={'BBCH': str})
    metric_keys = ['method', 'partition', 'BBCH', 'metric_view']
    methods = set(frame.method)
    expected_keys = set(itertools.product(methods, ['calibration', 'test'], STAGES, ['raw', 'scoring']))
    if (metrics.duplicated(metric_keys).any() or
            set(metrics[metric_keys].itertuples(index=False, name=None)) != expected_keys):
        raise ValueError(f'Incomplete or duplicate metric catalogue: {folder}')
    indexed = metrics.set_index(metric_keys)
    for group_key, subset in frame.groupby(['method', 'partition', 'BBCH'], sort=False):
        for view in ['raw', 'scoring']:
            actual = indexed.loc[(*group_key, view)]
            values = metric_values(subset, view)
            for name, value in values.items():
                np.testing.assert_allclose(actual[name], value, atol=1e-9, rtol=1e-10, equal_nan=True,
                                           err_msg=f'{folder}: {group_key}/{view}/{name}')
    for partition, count, sites in [('calibration', 59472, 2534), ('test', 15146, 635)]:
        subset = frame[frame.partition.eq(partition)]
        for method in methods:
            selected = subset[subset.method.eq(method)]
            if len(selected) != count or selected.site.nunique() != sites:
                raise ValueError(f'Frozen population changed: {folder}/{partition}/{method}')
    return dict(prediction_rows=len(frame), metric_rows=len(metrics))


def verify_population(results: Path) -> dict:
    folder = results / 'pooled_calibration_20260912'
    frames = [pd.read_csv(folder / f'{p}_observations.csv.gz', dtype={'site': str, 'BBCH': str})
              for p in ['calibration', 'test']]
    sites = pd.read_csv(results / 'publication_cohort_20260910/sites.csv', dtype={'site': str, 'group_id': str})
    population = pd.concat(frames, ignore_index=True)
    if population.observation_id.duplicated().any():
        raise ValueError('Duplicate canonical observation identities')
    population = population.merge(sites[['site', 'group_id']], on='site', how='left', validate='many_to_one')
    if population.group_id.isna().any() or population.groupby('group_id').partition.nunique().gt(1).any():
        raise ValueError('Missing or overlapping independence group')
    calibration = population[population.partition.eq('calibration')]
    if (set(calibration.inner_fold.astype(int)) != {0, 1, 2, 3} or
            calibration.groupby('group_id').inner_fold.nunique().gt(1).any()):
        raise ValueError('Calibration groups cross folds')
    return dict(observations=len(population), sites=population.site.nunique(), groups=population.group_id.nunique())


def replay_process(results: Path, threads: int) -> int:
    """Canonically simulate saved full process parameters; never optimize them."""
    import os
    os.environ.setdefault('NUMBA_NUM_THREADS', str(threads))
    sys.path.insert(0, str(results.parents[1]))
    import numba
    from model.data import prepare_weather
    from model_run.src.pooled_calibration import RateEvaluator
    from model_run.src.calibrate_pooled_sites import canonical_predictions

    numba.set_num_threads(threads)
    weather = pd.read_csv(results / 'publication_cohort_20260910/weather.csv.gz',
                          dtype={'site': str}, parse_dates=['Date'])
    population = pd.concat([pd.read_csv(results / 'pooled_calibration_20260912' /
        f'{partition}_observations.csv.gz', dtype={'site': str, 'BBCH': str})
        for partition in ['calibration', 'test']], ignore_index=True)
    pairs = population[['site', 'season']].drop_duplicates()
    for temperature in ['RAW', 'DEM']:
        prepared = prepare_weather(weather, pairs, 'Tmean' if temperature == 'RAW' else 'Tmean_DEM', None)
        for model in MODELS:
            folder = results / FINAL[0] / model / temperature
            parameters = json.loads((folder / 'fit.json').read_text())['parameters']
            dates = canonical_predictions(RateEvaluator(model, prepared), parameters)
            index = pd.MultiIndex.from_tuples([(w.site, w.season, stage) for w in prepared for stage in STAGES],
                                              names=['site', 'season', 'BBCH'])
            simulated = pd.Series(dates.ravel(), index=index)
            saved = pd.read_csv(folder / 'predictions.csv.gz', dtype={'site': str, 'BBCH': str})
            saved = saved[saved.method.eq('median_cutoff')]
            expected = simulated.reindex(pd.MultiIndex.from_frame(saved[['site', 'season', 'BBCH']]))
            np.testing.assert_array_equal(expected.to_numpy(dtype='datetime64[D]'),
                pd.to_datetime(saved.raw_predicted_date).to_numpy(dtype='datetime64[D]'))
            print(f'Canonical process replay: {model}/{temperature}', flush=True)
    return 20


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Checkout root for portable historical source mapping')
    parser.add_argument('--hashes-only', action='store_true', help='Skip independent date and metric arithmetic')
    parser.add_argument('--replay-process', action='store_true', help='Also simulate all saved full process fits (slow)')
    parser.add_argument('--threads', type=int, choices=range(1, 8), default=7)
    parser.add_argument('--output', type=Path, help='Write new JSON evidence; existing files are refused')
    args = parser.parse_args(argv)
    if args.output and args.output.exists():
        raise FileExistsError(args.output)
    root, cache, checks = args.root.resolve(), {}, {}
    results = root / 'model_run/results'
    for name in FINAL:
        folder = results / name
        status = json.loads((folder / 'status.json').read_text())
        config = json.loads((folder / 'run.json').read_text())
        if not (status.get('complete') is True and status.get('final_sources_verified') is True
                and status.get('smoke') is False and not status.get('failed') and not status.get('active')
                and status.get('expected') == 20 and len(status.get('completed', [])) == 20
                and set(status['completed']) == set(UNITS) and config.get('smoke') is False
                and config.get('models') == MODELS and set(config.get('temperatures', [])) == {'RAW', 'DEM'}):
            raise ValueError(f'Final production completion not established: {folder}')
        for raw, expected in config['sources'].items():
            check_hash(resolve_source(raw, root), expected, cache)
        checks[name] = {}
        for unit in UNITS:
            unit_folder = folder / unit
            verify_marker(unit_folder / 'complete.json', cache)
            checks[name][unit] = {} if args.hashes_only else verify_predictions(unit_folder)
            print(f'Verified: {name}/{unit}', flush=True)
    # Upstream initializers are computational inputs; obsolete historical ML
    # assembly comparisons are not followed through documentary manifests.
    pooled = results / 'pooled_calibration_20260912'
    for raw, expected in json.loads((pooled / 'run.json').read_text())['sources'].items():
        check_hash(resolve_source(raw, root), expected, cache)
    for unit in UNITS:
        verify_marker(pooled / unit / 'complete.json', cache)
        verify_marker(results / 'publication_factorial_20260911_v3/experiments/site_holdout' /
                      unit / 'pbm/full/complete.json', cache)
    result = dict(verified=True, distinct_hashed_files=len(cache), process_units=20, hybrid_units=20,
                  population=verify_population(results), metric_arithmetic=not args.hashes_only,
                  canonical_process_replay_units=replay_process(results, args.threads) if args.replay_process else 0,
                  checks=checks)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'checks'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
