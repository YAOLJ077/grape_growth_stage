#!/usr/bin/env python3
"""Fit early-stage thresholds, freeze them, and assign a median maturity threshold."""
import argparse
from datetime import datetime, timezone
import fcntl
import importlib.metadata
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('NUMBA_NUM_THREADS', '7')
for variable in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS']:
    os.environ.setdefault(variable, '1')

import numba
import numpy as np
import pandas as pd
from model.data import prepare_weather
from model.registry import MODEL_NAMES
from model_run.src.pooled_calibration import RateEvaluator
from model_run.src.calibrate_pooled_sites import (
    canonical_predictions, check_sources, digest, log,
    optimize, save_json,
)
from model_run.src.median_cutoff import derive_cutoff, EarlySearch, maturity_median, evaluation_rows


def verify_unit(folder):
    marker = json.loads((folder / 'complete.json').read_text())
    if not marker['verified']:
        raise ValueError(f'Unverified unit: {folder}')
    check_sources({str(folder / name): value for name, value in marker['artifacts'].items()})
    return marker


def early_fit(evaluator, calibration, existing, cutoff, seeds, budget, retry):
    search = EarlySearch(evaluator, calibration, existing, cutoff)
    starts = [search.vector(existing)]
    starts = [x for x in starts if search.covered(x)]
    if not starts:
        raise ValueError('No starting candidate satisfies early raw attainment ≥99%')
    starts.sort(key=lambda x: (search.violation(x), search.mae(x)))
    p, feasibility = optimize(search, 'bias_feasibility', starts, seeds, budget, retry)
    history = [dict(phase='early_bias_feasibility', **r) for r in feasibility]
    if search.feasible(search.vector(p)):
        p, optimization = optimize(search, 'low_bias_mae', [search.vector(p)], seeds, budget, retry)
        history.extend(dict(phase='early_mae', **r) for r in optimization)
    x = search.vector(p)
    if not search.covered(x):
        raise ValueError('Selected early fit violates raw attainment floor')
    return p, dict(early_bias_target_met=search.feasible(x), early_coverage_met=search.covered(x),
        early_maximum_bias_excess_days=search.violation(x),
        early_scoring_metrics=search.stats(x)[:3].tolist(),
        early_raw_metrics=search.raw_stats[:3].tolist(), restarts=history,
        early_status='met' if search.feasible(x) else 'bias target not reached within search budget')


def fit_unit(args, folder, evaluator, calibration, existing, cutoff):
    early_path = folder / 'early_fit.json'
    if early_path.exists():
        check_sources({str(early_path): json.loads((folder / 'early_fit.complete.json').read_text())['sha256']})
        saved = json.loads(early_path.read_text())
        parameters, info = saved['parameters'], saved['diagnostics']
    else:
        parameters, info = early_fit(evaluator, calibration, existing, cutoff,
            args.seeds, args.maxiter, args.retry_maxiter)
        save_json(early_path, dict(parameters=parameters, diagnostics=info))
        save_json(folder / 'early_fit.complete.json', dict(sha256=digest(early_path)))
    search = EarlySearch(evaluator, calibration, parameters, cutoff)
    x = search.vector(parameters)
    np.testing.assert_allclose(search.stats(x)[:3], info['early_scoring_metrics'], rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(search.raw_stats[:3], info['early_raw_metrics'], rtol=1e-10, atol=1e-10)
    if not search.covered(x) or search.feasible(x) != info['early_bias_target_met']:
        raise ValueError('Early checkpoint does not satisfy saved target status')
    before = canonical_predictions(evaluator, parameters)
    fitted, audit = maturity_median(evaluator, calibration, parameters)
    after = canonical_predictions(evaluator, fitted)
    np.testing.assert_array_equal(before[:, :3], after[:, :3])
    audit.to_csv(folder / 'median_requirements.csv.gz', index=False, date_format='%Y-%m-%d')
    fit = dict(parameters=fitted, **info, median_threshold_status='met',
        median_unbounded=float(audit.median_unbounded.iloc[0]),
        median_bound_adjusted=bool(audit.bound_adjusted.iloc[0]),
        median_eligible_records=int(audit.eligible_requirement.sum()),
        median_excluded_records=int((~audit.eligible_requirement).sum()),
        cutoff_month_day=cutoff, test_labels_used=False, zone_specific_parameters=False,
        early_predictions_unchanged_after_median=True)
    save_json(folder / 'fit.json', fit)
    save_json(folder / 'calibration_lock.json', dict(
        locked_at=datetime.now(timezone.utc).isoformat(), parameters=fitted,
        fit_sha256=digest(folder / 'fit.json'), calibration_only=True,
        calibration_observations=len(calibration), cutoff_month_day=cutoff))
    return fitted


def runtime_threads(args):
    reservation = 0
    if args.competing_pid:
        try:
            os.kill(args.competing_pid, 0)
            reservation = args.reserved_threads
        except ProcessLookupError:
            pass
    threads = max(1, args.threads - reservation)
    numba.set_num_threads(threads)
    return threads


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', type=Path, default=ROOT / 'model_run/results/pooled_calibration_20260912')
    parser.add_argument('--cohort', type=Path, default=ROOT / 'model_run/results/publication_cohort_20260910')
    parser.add_argument('--output', type=Path, default=ROOT / 'model_run/results/median_cutoff_calibration_20260912')
    parser.add_argument('--models', nargs='+', choices=MODEL_NAMES, default=list(MODEL_NAMES))
    parser.add_argument('--temperatures', nargs='+', choices=['RAW', 'DEM'], default=['RAW', 'DEM'])
    parser.add_argument('--maxiter', type=int, default=300)
    parser.add_argument('--retry-maxiter', type=int, default=600)
    parser.add_argument('--seeds', nargs='+', type=int, default=[20260907, 20260908, 20260909])
    parser.add_argument('--threads', type=int, choices=range(1, 8), default=7)
    parser.add_argument('--competing-pid', type=int)
    parser.add_argument('--reserved-threads', type=int, default=4)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args(argv)
    if not args.smoke and (args.maxiter != 300 or args.retry_maxiter != 600 or args.seeds != [20260907, 20260908, 20260909]):
        parser.error('Altered optimization budget requires --smoke')
    if args.reserved_threads < 0 or args.reserved_threads >= args.threads:
        if args.competing_pid:
            parser.error('Reservation must leave at least one calibration thread')
    if args.output.resolve() == args.source_run.resolve() or args.source_run.resolve() in args.output.resolve().parents:
        parser.error('Use a separate output directory')
    status = json.loads((args.source_run / 'status.json').read_text())
    if not status['complete'] or status.get('smoke', False):
        raise ValueError('Require completed full source calibration before launching')
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output / '.run.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    cal_path = args.source_run / 'calibration_observations.csv.gz'
    test_path = args.source_run / 'test_observations.csv.gz'
    weather_path = args.cohort / 'weather.csv.gz'
    source_paths = [cal_path, test_path, weather_path, Path(__file__),
        Path(__file__).with_name('median_cutoff.py'), Path(__file__).with_name('pooled_calibration.py'),
        Path(__file__).with_name('calibrate_pooled_sites.py'), *sorted((ROOT / 'model').rglob('*.py'))]
    for model in args.models:
        for temperature in args.temperatures:
            folder = args.source_run / model / temperature
            verify_unit(folder)
            source_paths.extend([folder / 'calibration_lock.json', folder / 'complete.json'])
    sources = {str(p.resolve()): digest(p) for p in source_paths}
    calibration = pd.read_csv(cal_path, dtype={'site': str, 'BBCH': str, 'observation_id': str}, parse_dates=['Date'])
    if not calibration.partition.eq('calibration').all() or calibration.observation_id.duplicated().any():
        raise ValueError('Invalid calibration population')
    if len(calibration) != 59472 or calibration.site.nunique() != 2534:
        raise ValueError('Frozen calibration population differs')
    cutoff = derive_cutoff(calibration)
    if cutoff != '11-04':
        raise ValueError('Calibration maximum changed from approved 11-04 cutoff')
    config = dict(sources=sources, models=args.models, temperatures=args.temperatures,
        seeds=args.seeds, maxiter=args.maxiter, retry_maxiter=args.retry_maxiter, popsize=15, tol=.001,
        smoke=args.smoke, cutoff_month_day=cutoff, cutoff_source='latest calibration BBCH89 month-day',
        early_bias_tolerance_days=1., early_raw_attainment_floor=.99,
        maturity_threshold='equal-site weighted median of positive requirements after raw predicted81',
        full_maturity_attainment_constraint=False, test_selection=False)
    run_path = args.output / 'run.json'
    if run_path.exists() and json.loads(run_path.read_text()) != config:
        raise ValueError('Resume configuration or source fingerprint differs')
    save_json(run_path, config)
    save_json(args.output / 'runtime_environment.json', dict(pid=os.getpid(), python=sys.version,
        max_total_thread_budget=args.threads, competing_pid=args.competing_pid,
        reserved_threads=args.reserved_threads if args.competing_pid else 0,
        numba_threads=runtime_threads(args), fit_worker_count=1,
        versions={name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'scipy', 'numba']}))
    completed, failed = [], []
    expected = len(args.models) * len(args.temperatures)
    final_sources_verified = False

    def write_status(active=None):
        save_json(args.output / 'status.json', dict(complete=len(completed) == expected and final_sources_verified,
            finished=len(completed) + len(failed) == expected, completed=completed, failed=failed,
            expected=expected, active=active, smoke=args.smoke, cutoff_month_day=cutoff,
            final_sources_verified=final_sources_verified))

    write_status()
    log(f'Loading weather; cutoff {cutoff}; {len(calibration)} calibration observations')
    weather = pd.read_csv(weather_path, dtype={'site': str}, parse_dates=['Date'])
    test = None
    for temperature in args.temperatures:
        column = 'Tmean' if temperature == 'RAW' else 'Tmean_DEM'
        prepared = prepare_weather(weather, calibration[['site', 'season']].drop_duplicates(), column, None)
        test_prepared = None
        for model in args.models:
            unit = f'{model}/{temperature}'
            folder = args.output / unit
            folder.mkdir(parents=True, exist_ok=True)
            if (folder / 'complete.json').exists():
                verify_unit(folder)
                completed.append(unit)
                write_status()
                continue
            threads = runtime_threads(args)
            write_status(dict(unit=unit, phase='calibration', numba_threads=threads))
            log(f'{unit}: early-stage fitting, {threads} threads')
            evaluator = RateEvaluator(model, prepared)
            source = json.loads((args.source_run / unit / 'calibration_lock.json').read_text())
            existing = source['fits']['existing']['parameters']
            try:
                fitted = fit_unit(args, folder, evaluator, calibration, existing, cutoff)
            except ValueError as error:
                # Scientific infeasibility is visible; unexpected errors still stop the run.
                if not str(error).startswith(('No starting candidate', 'No admissible starting', 'No valid positive')):
                    raise
                if hasattr(error, 'audit'):
                    error.audit.to_csv(folder / 'median_requirements.csv.gz', index=False, date_format='%Y-%m-%d')
                save_json(folder / 'failure.json', dict(reason=str(error), cutoff_month_day=cutoff))
                failed.append(unit)
                write_status()
                continue
            if test is None:
                test = pd.read_csv(test_path, dtype={'site': str, 'BBCH': str, 'observation_id': str}, parse_dates=['Date'])
                if (not test.partition.eq('test').all() or test.observation_id.duplicated().any()
                        or set(test.site) & set(calibration.site) or len(test) != 15146 or test.site.nunique() != 635):
                    raise ValueError('Invalid frozen test population or site overlap')
            if test_prepared is None:
                test_prepared = prepare_weather(weather, test[['site', 'season']].drop_duplicates(), column, None)
            test_evaluator = RateEvaluator(model, test_prepared)
            log(f'{unit}: calibration locked; evaluate test sites')
            write_status(dict(unit=unit, phase='locked_evaluation', numba_threads=threads))
            predictions, metrics = [], []
            for partition, frame, ev in [('calibration', calibration, evaluator), ('test', test, test_evaluator)]:
                for method, params in [('existing', existing), ('median_cutoff', fitted)]:
                    raw = canonical_predictions(ev, params)
                    pred, metric = evaluation_rows(ev, frame, raw, cutoff, model, temperature, method, partition)
                    predictions.append(pred)
                    metrics.append(metric)
            pd.concat(predictions, ignore_index=True).to_csv(folder / 'predictions.csv.gz', index=False, date_format='%Y-%m-%d')
            pd.concat(metrics, ignore_index=True).to_csv(folder / 'metrics.csv', index=False)
            check_sources(sources)
            save_json(folder / 'complete.json', dict(verified=True, canonical_replay=True, independent_metrics=True,
                artifacts={p.name: digest(p) for p in folder.iterdir() if p.is_file()
                           and p.name not in ['complete.json', 'failure.json'] and not p.name.endswith('.tmp')}))
            completed.append(unit)
            write_status()
            from model_run.src.report_median_cutoff import build_report
            build_report(args.output, args.output / 'report')
            del evaluator, test_evaluator
    check_sources(sources)
    final_sources_verified = True
    write_status()
    from model_run.src.report_median_cutoff import build_report
    build_report(args.output, args.output / 'report')
    log(f'Finished: {len(completed)} verified, {len(failed)} unsuccessful configurations')


if __name__ == '__main__':
    main()
