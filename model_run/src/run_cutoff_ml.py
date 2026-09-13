#!/usr/bin/env python3
"""Nested, calibration-only TabM residual learning on locked median/cutoff models."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('NUMBA_NUM_THREADS', '7')
for name in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS']:
    os.environ.setdefault(name, '1')

import numba
import numpy as np
import pandas as pd
from model.data import prepare_weather
from model.registry import MODEL_NAMES
from model.residual.data import KEYS, FEATURES, TERRAIN
from model.residual.learner import TabMConfig
from model.residual.storage import digest, json_once, publish, run_lock
from model_run.factorial.features import build_features
from model_run.factorial.runner import (
    residual_rows, select_observations, _pairs, train_stage, make_predictions,
    read_table, frame_hash, _seal_task, _check_task,
)
from model_run.src.calibrate_pooled_sites import check_sources, save_json, log
from model_run.src.median_cutoff import evaluation_rows


def make_protocol(calibration, test, sites):
    fields = ['site', 'season', 'partition', 'inner_fold']
    if set(calibration.site) & set(test.site):
        raise ValueError('Calibration/test site overlap')
    protocol = pd.concat([calibration[fields], test[fields]]).drop_duplicates().reset_index(drop=True)
    if protocol.duplicated(['site', 'season']).any() or protocol.groupby('site').partition.nunique().gt(1).any():
        raise ValueError('Inconsistent frozen site assignments')
    protocol = protocol.merge(sites[['site', 'group_id']], on='site', how='left', validate='many_to_one')
    if protocol.group_id.isna().any() or protocol.groupby('group_id').partition.nunique().gt(1).any():
        raise ValueError('Missing or overlapping independence group')
    cal = protocol[protocol.partition.eq('calibration')]
    if set(cal.inner_fold.astype(int)) != set(range(4)) or cal.groupby('group_id').inner_fold.nunique().gt(1).any():
        raise ValueError('Calibration group crosses folds or a fold is missing')
    return protocol


def residual_assembly(features, calibration, protocol):
    oof = residual_rows(pd.concat([features[f'oof_{fold}'] for fold in range(4)], ignore_index=True), calibration)
    nested = {}
    for held in range(4):
        pieces = []
        for predicted in range(4):
            if predicted == held:
                continue
            name = 'nested_' + '_'.join(map(str, sorted([held, predicted])))
            targets = _pairs(protocol[protocol.partition.eq('calibration') & protocol.inner_fold.eq(predicted)])
            pieces.append(select_observations(features[name], targets))
        nested[held] = residual_rows(pd.concat(pieces, ignore_index=True), calibration)
        if set(nested[held].site) & set(protocol.loc[protocol.inner_fold.eq(held), 'site']):
            raise ValueError('Nested residual training includes validation sites')
    if set(oof.observation_id) != set(calibration.observation_id) or oof.observation_id.duplicated().any():
        raise ValueError('OOF residual population differs from frozen calibration records')
    return oof, nested


def _matrix(predictions, prepared):
    if predictions.duplicated(KEYS).any():
        raise ValueError('Duplicate process/hybrid prediction keys')
    index = pd.MultiIndex.from_tuples([(w.site, w.season, stage) for w in prepared
        for stage in ['07', '65', '81', '89']], names=KEYS)
    ordered = predictions.set_index(KEYS).reindex(index)
    if len(predictions) != len(index) or set(predictions.set_index(KEYS).index) != set(index):
        raise ValueError('Prediction population differs from prepared seasons')
    return pd.to_datetime(ordered.predicted_date).to_numpy(dtype='datetime64[D]').reshape(-1, 4)


def score_methods(observations, prepared, process, hybrid, model, temperature, partition):
    rows, metrics = [], []
    ev = SimpleNamespace(prepared=prepared)
    base = observations[KEYS].merge(process[KEYS + ['predicted_date']], on=KEYS, how='left', validate='many_to_one')
    pbm_dates = pd.to_datetime(base.predicted_date).to_numpy(dtype='datetime64[D]')
    cutoff = np.array([f'{int(y)}-11-04' for y in observations.season], dtype='datetime64[D]')
    for method, table in [('process', process), ('tabm', hybrid)]:
        pred, metric = evaluation_rows(ev, observations, _matrix(table, prepared), '11-04',
                                      model, temperature, method, partition)
        pred['pbm_raw_predicted_date'] = pbm_dates
        pred['pbm_raw_attained'] = ~np.isnat(pbm_dates)
        pred['pbm_attained_by_cutoff'] = (~np.isnat(pbm_dates)) & (pbm_dates <= cutoff)
        pred['model_name'] = model + ('-ML' if method == 'tabm' else '')
        extra = [c for c in table if c in ['unconstrained_date', 'order_adjustment_days', 'residual_prediction_days']
                 or c.startswith('residual_seed_')]
        if extra:
            pred = pred.merge(table[KEYS + extra], on=KEYS, how='left', validate='many_to_one')
        rows.append(pred)
        metrics.append(metric)
    return pd.concat(rows, ignore_index=True), pd.concat(metrics, ignore_index=True)


def _features_cached(folder, predictions, weather, sites, temperature, source_hashes):
    provenance = dict(predictions_hash=frame_hash(predictions), temperature=temperature,
                      source_hashes=source_hashes, feature_columns=FEATURES)
    folder.mkdir(parents=True, exist_ok=True)
    json_once(folder / 'provenance.json', provenance)
    if (folder / 'complete.json').exists():
        _check_task(folder)
        return read_table(folder / 'features.csv.gz')
    result = build_features(predictions, weather, sites, temperature)
    publish(folder / 'features.csv.gz', lambda p: result.to_csv(p, index=False, date_format='%Y-%m-%d', compression={'method': 'gzip', 'mtime': 0}))
    _seal_task(folder)
    # Training hashes and values must be identical on first execution and resume.
    return read_table(folder / 'features.csv.gz')


def smoke_population(calibration, test, sites, count=3):
    """Deterministic small diagnostic population, selected by calibration stage coverage."""
    chosen = []
    for fold in range(4):
        subset = calibration[calibration.inner_fold.eq(fold)]
        coverage = subset.groupby('site').BBCH.nunique()
        candidates = sorted(coverage[coverage.eq(4)].index)
        if len(candidates) < count:
            raise ValueError('Insufficient complete-stage calibration sites for smoke')
        chosen.extend(candidates[:count])
    cal = calibration[calibration.site.isin(chosen)].copy()
    candidates = test.groupby('site').BBCH.nunique()
    held = sorted(candidates[candidates.eq(4)].index)[:2]
    if len(held) < 2:
        raise ValueError('Insufficient smoke test sites')
    return cal, test[test.site.isin(held)].copy()


def run_unit(args, model, temperature, calibration, test, protocol, prepared, weather, sites, config, sources, status):
    from model_run.src.cutoff_ml_crossfit import make_jobs, fit_predict_job, predict_table
    unit = f'{model}/{temperature}'
    folder = args.output / unit
    folder.mkdir(parents=True, exist_ok=True)
    feature_tables = {}
    source_features = {k: v for k, v in sources.items() if Path(k).name in ['weather.csv.gz', 'sites.csv', 'features.py', 'data.py']}
    for job in make_jobs(protocol):
        status(unit, 'process_crossfit', job['name'])
        predicted = fit_predict_job(job, calibration, prepared, model, temperature, folder / 'pbm' / job['name'],
            seeds=args.seeds, maxiter=args.maxiter, retry_maxiter=args.retry_maxiter, cutoff='11-04')
        feature_tables[job['name']] = _features_cached(folder / 'features' / job['name'],
            predicted, weather, sites, temperature, source_features)
    oof, nested = residual_assembly(feature_tables, calibration, protocol)
    if set(oof.site) & set(test.site):
        raise ValueError('Test sites entered residual training')
    for stage in ['07', '65', '81', '89']:
        status(unit, 'tabm_training', f'BBCH{stage}')
        train_stage(stage, nested, oof, protocol, folder / 'stages' / stage, config, args.seeds)
    # Full-source process predictions are used only after ML tuning/training has locked.
    source = args.source_run / unit
    fitted = json.loads((source / 'fit.json').read_text())['parameters']
    full = predict_table(model, fitted, prepared, temperature, fit_id=str(source / 'fit.json'))
    source_predictions = pd.read_csv(source / 'predictions.csv.gz', dtype={'site': str, 'BBCH': str},
        usecols=['site', 'season', 'BBCH', 'method', 'raw_predicted_date'], parse_dates=['raw_predicted_date'])
    source_predictions = source_predictions[source_predictions.method.eq('median_cutoff')].drop_duplicates(KEYS)
    source_predictions = source_predictions.rename(columns={'raw_predicted_date': 'source_raw_predicted_date'})
    matched = full.merge(source_predictions[KEYS + ['source_raw_predicted_date']], on=KEYS, how='inner', validate='one_to_one')
    observed_keys = pd.concat([calibration[KEYS], test[KEYS]]).drop_duplicates()
    if len(matched.merge(observed_keys, on=KEYS)) != len(observed_keys):
        raise ValueError('Missing locked source prediction')
    np.testing.assert_array_equal(matched.predicted_date.to_numpy(dtype='datetime64[D]'),
                                  matched.source_raw_predicted_date.to_numpy(dtype='datetime64[D]'))
    full_features = _features_cached(folder / 'features' / 'full', full, weather, sites, temperature, source_features)
    all_predictions = make_predictions(full_features, folder / 'stages', args.seeds, ['none', 'tabm'])
    process = all_predictions[all_predictions.ml_algorithm.eq('none')].copy()
    hybrid = all_predictions[all_predictions.ml_algorithm.eq('tabm')].copy()
    # A zero-residual process comparator must remain exactly the canonical dates.
    np.testing.assert_array_equal(process.predicted_date.to_numpy(dtype='datetime64[D]'), full.predicted_date.to_numpy(dtype='datetime64[D]'))
    lock_path = folder / 'ml_lock.json'
    locked_at = json.loads(lock_path.read_text())['locked_at'] if lock_path.exists() else datetime.now(timezone.utc).isoformat()
    json_once(lock_path, dict(locked_at=locked_at,
        seeds=args.seeds, source_fit_sha256=digest(source / 'fit.json'), test_labels_used=False,
        checkpoints={str(p.relative_to(folder)): digest(p) for p in (folder / 'stages').rglob('checkpoint.pt')}))
    status(unit, 'locked_evaluation', None)
    predictions, metrics = [], []
    for partition, observations in [('calibration', calibration), ('test', test)]:
        pairs = _pairs(observations)
        keys = set(map(tuple, pairs))
        selected_weather = tuple(w for w in prepared if (w.site, w.season) in keys)
        pred, metric = score_methods(observations, selected_weather, select_observations(process, pairs),
            select_observations(hybrid, pairs), model, temperature, partition)
        predictions.append(pred)
        metrics.append(metric)
    pd.concat(predictions, ignore_index=True).to_csv(folder / 'predictions.csv.gz', index=False, date_format='%Y-%m-%d')
    pd.concat(metrics, ignore_index=True).to_csv(folder / 'metrics.csv', index=False)
    oof.to_csv(folder / 'residual_training.csv.gz', index=False, date_format='%Y-%m-%d')
    save_json(folder / 'provenance.json', dict(model=model, temperature=temperature,
        calibration_observations=len(calibration), test_observations=len(test),
        residual_definition='observed date minus raw fold-specific process date',
        feature_columns=FEATURES, excluded_features=['observed date', 'site', 'country', 'year', 'variety'],
        early_stopping='four nested calibration folds; no outer test tuning',
        seeds=args.seeds, configuration=asdict(config), scoring_cutoff='11-04',
        calibration_metrics='apparent full-fit predictions, not out-of-fold accuracy',
        nonattainment='no residual for unattained PBM; 81/89 retain cutoff scoring',
        prediction_context='retrospective; weather windows end at raw PBM predicted date'))
    check_sources(sources)
    save_json(folder / 'complete.json', dict(verified=True, independent_metrics=True, canonical_replay=True,
        artifacts={str(p.relative_to(folder)): digest(p) for p in folder.rglob('*') if p.is_file()
                   and p != folder / 'complete.json' and not p.name.endswith('.tmp')}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', type=Path, default=ROOT / 'model_run/results/median_cutoff_calibration_20260912')
    parser.add_argument('--population-run', type=Path, default=ROOT / 'model_run/results/pooled_calibration_20260912')
    parser.add_argument('--cohort', type=Path, default=ROOT / 'model_run/results/publication_cohort_20260910')
    parser.add_argument('--output', type=Path, default=ROOT / 'model_run/results/median_cutoff_ml_20260912')
    parser.add_argument('--models', nargs='+', choices=MODEL_NAMES, default=list(MODEL_NAMES))
    parser.add_argument('--temperatures', nargs='+', choices=['RAW', 'DEM'], default=['RAW', 'DEM'])
    parser.add_argument('--threads', type=int, choices=range(1, 8), default=7)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args(argv)
    args.seeds = [7] if args.smoke else [20260907, 20260908, 20260909]
    args.maxiter, args.retry_maxiter = (1, 1) if args.smoke else (300, 600)
    if args.output.resolve() == args.source_run.resolve() or args.source_run.resolve() in args.output.resolve().parents:
        parser.error('Use a separate ML output directory')
    source_status = json.loads((args.source_run / 'status.json').read_text())
    if not source_status['complete'] or source_status.get('smoke') or not source_status['final_sources_verified']:
        raise ValueError('Require verified complete production process calibration')
    args.output.mkdir(parents=True, exist_ok=True)
    with run_lock(args.output):
        cal_path = args.population_run / 'calibration_observations.csv.gz'
        test_path = args.population_run / 'test_observations.csv.gz'
        paths = [cal_path, test_path, args.cohort / 'weather.csv.gz', args.cohort / 'sites.csv',
            Path(__file__), Path(__file__).with_name('cutoff_ml_crossfit.py'),
            Path(__file__).with_name('calibrate_median_cutoff.py'), Path(__file__).with_name('median_cutoff.py'),
            Path(__file__).with_name('calibrate_pooled_sites.py'), Path(__file__).with_name('pooled_calibration.py'),
            *sorted((ROOT / 'model').rglob('*.py')), *sorted((ROOT / 'model_run/factorial').glob('*.py'))]
        for model in args.models:
            for temperature in args.temperatures:
                folder = args.source_run / model / temperature
                marker = json.loads((folder / 'complete.json').read_text())
                if not marker['verified']:
                    raise ValueError('Unverified source unit')
                check_sources({str(folder / name): value for name, value in marker['artifacts'].items()})
                paths.extend([folder / 'fit.json', folder / 'predictions.csv.gz', folder / 'complete.json'])
        sources = {str(p.resolve()): digest(p) for p in paths}
        calibration_sources = json.loads((args.source_run / 'run.json').read_text())['sources']
        for path in [cal_path, test_path, args.cohort / 'weather.csv.gz']:
            expected = calibration_sources.get(str(path.resolve()))
            if expected is None or digest(path) != expected:
                raise ValueError(f'ML input differs from locked process calibration: {path}')
        cal = pd.read_csv(cal_path, dtype={'site': str, 'BBCH': str, 'observation_id': str}, parse_dates=['Date'])
        test = pd.read_csv(test_path, dtype={'site': str, 'BBCH': str, 'observation_id': str}, parse_dates=['Date'])
        sites = pd.read_csv(args.cohort / 'sites.csv', dtype={'site': str, 'group_id': str},
                            usecols=['site', 'group_id', 'lat'] + TERRAIN)
        if len(cal) != 59472 or len(test) != 15146:
            raise ValueError('Frozen observation population changed')
        if args.smoke:
            cal, test = smoke_population(cal, test, sites)
        protocol = make_protocol(cal, test, sites)
        cal = cal.merge(sites[['site', 'group_id']], on='site', validate='many_to_one')
        config = TabMConfig(threads=args.threads) if not args.smoke else TabMConfig(
            n_blocks=1, d_block=8, k=2, n_bins=3, d_embedding=2, max_epochs=2, patience=1, batch_size=32, threads=args.threads)
        configuration = dict(sources=sources, models=args.models, temperatures=args.temperatures,
            seeds=args.seeds, optimizer=dict(maxiter=args.maxiter, retry_maxiter=args.retry_maxiter, popsize=15, tol=.001),
            config=asdict(config), smoke=args.smoke, cutoff='11-04', feature_columns=FEATURES,
            calibration_observations=len(cal), test_observations=len(test), protocol_hash=frame_hash(protocol),
            neural_training='nested group cross-fitting, fixed hyperparameters, fold-local preprocessing',
            cutoff_policy='frozen protocol constant; not recalculated or optimized in inner folds')
        json_once(args.output / 'run.json', configuration)
        numba.set_num_threads(args.threads)
        save_json(args.output / 'runtime_environment.json', dict(pid=os.getpid(), threads=args.threads,
            worker_count=1, numba_threads=numba.get_num_threads(), config=asdict(config), started_at=datetime.now(timezone.utc).isoformat()))
        completed = []
        expected = len(args.models) * len(args.temperatures)
        final_verified = False

        def status(unit=None, phase=None, task=None):
            save_json(args.output / 'status.json', dict(complete=len(completed) == expected and final_verified,
                completed=completed, failed=[], expected=expected, smoke=args.smoke, final_sources_verified=final_verified,
                active=dict(unit=unit, phase=phase, task=task) if unit else None, threads=args.threads))
            if unit:
                log(f'{unit}: {phase}: {task or ""}')

        status()
        log('Loading weather for new process/TabM comparison')
        weather = pd.read_csv(args.cohort / 'weather.csv.gz', dtype={'site': str}, parse_dates=['Date'])
        all_pairs = pd.concat([cal[['site', 'season']], test[['site', 'season']]]).drop_duplicates()
        weather = weather[weather.site.isin(all_pairs.site)].copy()
        for temperature in args.temperatures:
            column = 'Tmean' if temperature == 'RAW' else 'Tmean_DEM'
            prepared = prepare_weather(weather, all_pairs, column, None)
            for model in args.models:
                unit = f'{model}/{temperature}'
                marker_path = args.output / unit / 'complete.json'
                if marker_path.exists():
                    marker = json.loads(marker_path.read_text())
                    if not marker['verified']:
                        raise ValueError('Unverified ML unit')
                    check_sources({str(marker_path.parent / name): value for name, value in marker['artifacts'].items()})
                    from model_run.src.cutoff_ml_crossfit import make_jobs, fit_predict_job
                    for job in make_jobs(protocol):
                        status(unit, 'process_replay', job['name'])
                        fit_predict_job(job, cal, prepared, model, temperature, marker_path.parent / 'pbm' / job['name'],
                            seeds=args.seeds, maxiter=args.maxiter, retry_maxiter=args.retry_maxiter, cutoff='11-04')
                else:
                    run_unit(args, model, temperature, cal, test, protocol, prepared, weather, sites, config, sources, status)
                completed.append(unit)
                status()
                from model_run.src.report_cutoff_ml import build_report
                build_report(args.output)
        check_sources(sources)
        final_verified = True
        status()
        from model_run.src.report_cutoff_ml import build_report
        build_report(args.output)
        log('All new process/TabM configurations verified')


if __name__ == '__main__':
    main()
