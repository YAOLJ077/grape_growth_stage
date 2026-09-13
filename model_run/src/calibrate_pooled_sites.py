#!/usr/bin/env python3
"""Pooled calibration-only threshold comparisons, isolated from frozen runs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault('NUMBA_NUM_THREADS', '2')

import numpy as np
import pandas as pd
from scipy.optimize import NonlinearConstraint, differential_evolution

from model.data import prepare_weather, SeasonWeather
from model.fast_thresholds import _predict_arrays
from model.parameters import validate_parameters
from model.registry import MODEL_NAMES
from model.specification import STAGES
from model.structure_comparison import fixed_parameters, threshold_only_settings
from model_run.src.pooled_calibration import RateEvaluator, Metrics, weighted_median, select_partitions

DEFAULT_RUN = ROOT/'model_run/results/publication_factorial_20260911_v3'
DEFAULT_COHORT = ROOT/'model_run/results/publication_cohort_20260910'
DEFAULT_OBS = ROOT/'model_run/results/cleaned_reevaluation_20260912/observations.csv'
METRIC_NAMES = ['mae_days','rmse_days','bias_days','attainment','site_attainment','penalized_rmse_days']


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def log(message):
    print(datetime.now(timezone.utc).isoformat(timespec='seconds'), message, flush=True)


def save_json(path, value):
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


def check_sources(sources):
    for path, expected in sources.items():
        if digest(path) != expected:
            raise ValueError(f'Source changed: {path}')


class Search:
    def __init__(self, evaluator, frame, parameters):
        if not frame.partition.eq('calibration').all():
            raise ValueError('Only calibration observations can enter threshold fitting')
        self.evaluator, self.frame = evaluator, frame
        self.metrics = Metrics(frame)
        settings = threshold_only_settings(evaluator.name)
        self.names = [k for k,(lo,hi) in settings.bounds.items() if hi > lo]
        self.bounds = [settings.bounds[k] for k in self.names]
        self.fixed = fixed_parameters(evaluator.name)
        lookup = {(w.site,w.season):i for i,w in enumerate(evaluator.prepared)}
        self.rows = np.array([lookup[k] for k in frame[['site','season']].itertuples(index=False,name=None)])
        self.cols = frame.BBCH.map({s:i for i,s in enumerate(STAGES)}).to_numpy()
        self.observed = frame.Date.to_numpy(dtype='datetime64[D]').astype(np.int64)
        self.last_x = None
        self.last_stats = None
        self.baseline = self.stats(self.vector(parameters)).copy()
        self.coverage = self.baseline[:,3:5].copy()
        self.calls = 0

    def vector(self, p):
        return np.array([p[k] for k in self.names], dtype=float)

    def decode(self, x):
        return {**self.fixed, **{k:float(v) for k,v in zip(self.names,x)}}

    def errors(self, p):
        positions = self.evaluator.positions(p)[self.rows,self.cols]
        valid = positions >= 0
        errors = np.full(len(positions), np.nan)
        errors[valid] = self.evaluator.date_numbers[self.rows[valid],positions[valid]] - self.observed[valid]
        return errors

    def stats(self, x):
        if self.last_x is None or not np.array_equal(x, self.last_x):
            self.last_stats = self.metrics(self.errors(self.decode(x)))
            self.last_x = np.array(x).copy()
            self.calls = getattr(self, 'calls', 0) + 1
        return self.last_stats

    def coverage_margin(self, x):
        return (self.stats(x)[:,3:5] - self.coverage + 1e-12).ravel()

    def bias_margin(self, x):
        bias = self.stats(x)[:,2]
        return np.where(np.isfinite(bias), 1.0 - np.abs(bias), -1e9)

    def violation(self, x):
        bias = self.stats(x)[:,2]
        return float(max(0., np.max(np.abs(bias))-1.)) if np.isfinite(bias).all() else 1e9

    def mae(self, x):
        value = self.stats(x)[:,0].mean()
        return float(value) if np.isfinite(value) else 1e9

    def covered(self, x):
        return bool(np.all(self.coverage_margin(x) >= 0))

    def feasible(self, x):
        return self.covered(x) and self.violation(x) <= 1e-10


def initial_population(search, candidates, seed):
    rng = np.random.default_rng(seed)
    bounds = np.array(search.bounds)
    low, high = bounds[:,0], bounds[:,1]
    population = rng.uniform(low, high, size=(15*len(low),len(low)))
    for i in range(len(population)//2):
        center = candidates[i % len(candidates)]
        population[i] = np.clip(center + rng.normal(0, .08*(high-low)), low, high)
    for i, x in enumerate(candidates[:len(population)]):
        population[i] = x
    return population


def optimize(search, kind, starting, seeds, maxiter, retry_maxiter):
    constraints = ()
    if kind != 'original_objective':
        constraints = (NonlinearConstraint(search.coverage_margin, 0., np.inf),)
    if kind == 'low_bias_mae':
        constraints += (NonlinearConstraint(search.bias_margin, 0., np.inf),)
    objective = (lambda x: float(search.stats(x)[:,5].mean())) if kind == 'original_objective' else (
        search.violation if kind == 'bias_feasibility' else search.mae)
    candidates = [np.array(x).copy() for x in starting]
    records = []
    for budget in [maxiter, retry_maxiter] if retry_maxiter > maxiter else [maxiter]:
        failures = False
        for seed in seeds:
            before = time.monotonic()
            log(f'{search.evaluator.name}: {kind}, seed {seed}, budget {budget}')
            result = differential_evolution(objective, search.bounds, seed=seed, maxiter=budget,
                popsize=15, tol=.001, polish=False, workers=1, constraints=constraints,
                init=initial_population(search,candidates,seed), x0=candidates[0])
            x = result.x
            valid = kind == 'original_objective' or (search.covered(x) and (
                kind == 'bias_feasibility' or search.feasible(x)))
            records.append(dict(seed=int(seed), maxiter=int(budget), converged=bool(result.success),
                feasible=bool(valid), objective=float(objective(x)), nit=int(result.nit), nfev=int(result.nfev),
                elapsed_seconds=time.monotonic()-before, message=str(result.message), parameters=search.decode(x)))
            if valid:
                candidates.append(x.copy())
                candidates.sort(key=lambda v:(objective(v),search.mae(v)))
                candidates = candidates[:8]
            failures |= not result.success
            log(f'{kind}: objective {objective(x):.5f}; bias {np.round(search.stats(x)[:,2],3).tolist()}; '
                f'{time.monotonic()-before:.1f}s')
        if kind == 'bias_feasibility' and any(search.feasible(x) for x in candidates):
            break
        if not failures and (kind != 'bias_feasibility' or any(search.feasible(x) for x in candidates)):
            break
    usable = [x for x in candidates if kind == 'original_objective' or (search.covered(x) and (
        kind == 'bias_feasibility' or search.feasible(x)))]
    if not usable:
        raise ValueError(f'No admissible starting or optimized candidate for {kind}')
    best = min(usable, key=lambda x:(objective(x),search.mae(x)))
    return search.decode(best), records


def median_thresholds(search, existing):
    if search.evaluator.name not in {'FL','FB'}:
        raise ValueError('Median baseline is defined only for forcing-only models')
    p, records = dict(existing), []
    evaluator = search.evaluator
    for s, stage in enumerate(STAGES):
        positions = evaluator.positions(p)
        index = np.flatnonzero(search.cols == s)
        rows = search.rows[index]
        starts = evaluator.january[rows] if s == 0 else positions[rows,s-1] + 1
        ends = search.observed[index] - evaluator.date_numbers[rows,0]
        valid = (starts >= 0) & (ends >= starts) & (ends < evaluator.lengths[rows])
        if s:
            valid &= positions[rows,s-1] >= 0
        values = np.full(len(index), np.nan)
        values[valid] = evaluator.f[rows[valid],ends[valid]+1] - evaluator.f[rows[valid],starts[valid]]
        valid &= np.isfinite(values) & (values > 0)
        subset = search.frame.iloc[index]
        if not valid.any():
            raise ValueError(f'No positive thermal requirements for median {stage}')
        counts = subset.loc[valid,'site'].value_counts()
        weights = subset.site.map(counts).rdiv(1.).to_numpy()
        weights[~valid] = 0
        value = weighted_median(values, weights)
        bounds = threshold_only_settings(evaluator.name).bounds[f'forcing_requirement_{stage}']
        p[f'forcing_requirement_{stage}'] = float(np.clip(value, *bounds))
        for j, ix in enumerate(index):
            records.append(dict(observation_id=search.frame.observation_id.iloc[ix], BBCH=stage,
                eligible_requirement=bool(valid[j]), thermal_requirement=float(values[j]) if np.isfinite(values[j]) else None,
                median_unbounded=value, threshold=p[f'forcing_requirement_{stage}']))
    return p, records


def independent_metrics(frame, errors):
    d = frame[['site','BBCH']].copy()
    d['error'] = errors
    d['abs'] = np.abs(errors)
    d['sq'] = errors**2
    d['attained'] = np.isfinite(errors).astype(float)
    d['penalized_sq'] = np.where(np.isfinite(errors), errors**2, 1e6)
    sites = d.groupby(['BBCH','site']).agg(mae=('abs','mean'),mse=('sq','mean'),bias=('error','mean'),
        attainment=('attained','mean'),penalized_mse=('penalized_sq','mean'))
    result = []
    for stage in STAGES:
        group = sites.loc[stage]
        result.append([group.mae.mean(), np.sqrt(group.mse.mean()), group.bias.mean(),
            d.loc[d.BBCH.eq(stage),'attained'].mean(), group.attainment.mean(), np.sqrt(group.penalized_mse.mean())])
    return np.array(result)


def canonical_predictions(evaluator, p):
    prepared = evaluator.prepared
    if evaluator.interaction == 0:
        prepared = tuple(SeasonWeather(w.site,w.season,w.dates[j:],w.temperature[j:])
            for w,j in zip(prepared,evaluator.january))
    positions, _, _, _, dates = _predict_arrays(evaluator.name,p,prepared)
    expected = np.full(positions.shape, np.iinfo(np.int64).min,dtype=np.int64)
    rows, cols = np.nonzero(positions >= 0)
    expected[rows,cols] = dates[rows,positions[rows,cols]]
    predicted = evaluator.predict(p)
    np.testing.assert_array_equal(predicted, expected.astype('datetime64[D]'))
    return predicted


def observation_errors(frame, prepared, predicted):
    lookup = {(w.site,w.season):i for i,w in enumerate(prepared)}
    rows = np.array([lookup[k] for k in frame[['site','season']].itertuples(index=False,name=None)])
    cols = frame.BBCH.map({s:i for i,s in enumerate(STAGES)}).to_numpy()
    dates = predicted[rows,cols]
    errors = (dates - frame.Date.to_numpy(dtype='datetime64[D]')).astype(float)
    errors[np.isnat(dates)] = np.nan
    return dates, errors


def saved_prediction_check(run, name, temperature, frame, dates):
    path = run/f'experiments/site_holdout/{name}/{temperature}/pbm/full/predictions.csv'
    saved = pd.read_csv(path, dtype={'site':str,'BBCH':str},keep_default_na=False)
    saved.BBCH = saved.BBCH.str.zfill(2)
    joined = frame[['site','season','BBCH']].merge(saved[['site','season','BBCH','predicted_date']],
        on=['site','season','BBCH'],how='left',validate='many_to_one',indicator=True)
    if not joined._merge.eq('both').all():
        raise ValueError('Missing saved baseline prediction')
    expected = pd.to_datetime(joined.predicted_date.replace('',None)).to_numpy(dtype='datetime64[D]')
    np.testing.assert_array_equal(dates,expected)


def fit_unit(args, directory, evaluator, calibration, existing):
    search = Search(evaluator,calibration,existing)
    baseline_dates = canonical_predictions(evaluator,existing)
    dates, baseline_errors = observation_errors(calibration,evaluator.prepared,baseline_dates)
    saved_prediction_check(args.run,evaluator.name,args.current_temperature,calibration,dates)
    np.testing.assert_allclose(search.baseline,independent_metrics(calibration,baseline_errors),rtol=1e-11,atol=1e-11)
    fitted = {'existing': dict(parameters=existing,calibration_metrics=search.baseline.tolist(),restarts=[])}
    starts = [search.vector(existing)]
    if evaluator.name in {'FL','FB'}:
        median, audit = median_thresholds(search,existing)
        fitted['median_threshold'] = dict(parameters=median,
            calibration_metrics=search.stats(search.vector(median)).tolist(),restarts=[])
        pd.DataFrame(audit).to_csv(directory/'median_requirements.csv.gz',index=False)
        starts.append(search.vector(median))
    for method in ['original_objective','low_bias_mae']:
        path = directory/f'{method}.json'
        if path.exists():
            fitted[method] = json.loads(path.read_text())
            np.testing.assert_allclose(search.stats(search.vector(fitted[method]['parameters'])),
                fitted[method]['calibration_metrics'],rtol=1e-11,atol=1e-11)
            continue
        if method == 'original_objective':
            p, restarts = optimize(search,method,starts,args.seeds,args.maxiter,args.retry_maxiter)
        else:
            initial = [x for x in starts + [search.vector(fitted['original_objective']['parameters'])] if search.covered(x)]
            initial.sort(key=lambda x:(search.violation(x),search.mae(x)))
            p, feasibility = optimize(search,'bias_feasibility',initial,args.seeds,args.maxiter,args.retry_maxiter)
            restarts = []
            if search.feasible(search.vector(p)):
                p, restarts = optimize(search,method,[search.vector(p)],args.seeds,args.maxiter,args.retry_maxiter)
            restarts = [dict(phase='feasibility',**r) for r in feasibility] + [dict(phase='mae',**r) for r in restarts]
        x = search.vector(p)
        validate_parameters(evaluator.name,p)
        fitted[method] = dict(parameters=p,calibration_metrics=search.stats(x).tolist(),restarts=restarts,
            coverage_preserved=search.covered(x),bias_target_met=search.feasible(x),
            maximum_bias_excess_days=search.violation(x),
            target_status='met' if search.feasible(x) else 'bias target not reached within the search budget',
            threshold_bounds={k:list(b) for k,b in zip(search.names,search.bounds)},
            boundary_hits=[k for k,b,v in zip(search.names,search.bounds,x)
                if min(v-b[0],b[1]-v) <= (b[1]-b[0])*1e-4])
        if method == 'low_bias_mae' and not search.covered(x):
            raise ValueError('Selected fit reduces calibration coverage')
        canonical_predictions(evaluator,p)
        save_json(path,fitted[method])
    save_json(directory/'calibration_lock.json',dict(
        model=evaluator.name,temperature=args.current_temperature,
        n_observations=len(calibration),n_sites=calibration.site.nunique(),
        observation_ids_hash=hashlib.sha256('\n'.join(calibration.observation_id).encode()).hexdigest(),
        test_labels_used=False,zone_specific_parameters=False,
        fits=fitted,locked_at=datetime.now(timezone.utc).isoformat()))
    return fitted


def evaluate_unit(args, directory, fitted, calibration, test, cal_evaluator, test_evaluator):
    output, metric_rows, changes, paired = [], [], [], []
    for partition, frame, evaluator in [('calibration',calibration,cal_evaluator),('test',test,test_evaluator)]:
        metric = Metrics(frame)
        baseline = None
        for method, fit in fitted.items():
            predicted = canonical_predictions(evaluator,fit['parameters'])
            dates, errors = observation_errors(frame,evaluator.prepared,predicted)
            if method == 'existing':
                saved_prediction_check(args.run,evaluator.name,args.current_temperature,frame,dates)
                baseline = errors.copy()
            values = metric(errors)
            np.testing.assert_allclose(values, independent_metrics(frame,errors), rtol=1e-11,atol=1e-11)
            for i, stage in enumerate(STAGES):
                subset = frame.BBCH.eq(stage).to_numpy()
                metric_rows.append(dict(model=evaluator.name,temperature=args.current_temperature,method=method,
                    partition=partition,BBCH=stage,n_observations=int(subset.sum()),n_sites=int(frame.loc[subset,'site'].nunique()),
                    n_attained=int(np.isfinite(errors[subset]).sum()),**dict(zip(METRIC_NAMES,values[i]))))
                common = subset & np.isfinite(errors) & np.isfinite(baseline)
                if common.any():
                    for label, err in [('existing',baseline),('candidate',errors)]:
                        temp = frame.loc[common,['site']].copy()
                        temp['error'] = err[common]
                        temp['absolute'] = temp.error.abs()
                        temp['square'] = temp.error**2
                        site = temp.groupby('site')[['error','absolute','square']].mean()
                        paired.append(dict(model=evaluator.name,temperature=args.current_temperature,method=method,
                            partition=partition,BBCH=stage,arm=label,n_observations=int(common.sum()),n_sites=len(site),
                            mae_days=site.absolute.mean(),bias_days=site.error.mean(),rmse_days=np.sqrt(site.square.mean())))
            result = frame.copy()
            result['predicted_date'] = dates
            result['error_days'] = errors
            result['model'] = evaluator.name
            result['temperature'] = args.current_temperature
            result['method'] = method
            output.append(result)
            changed = np.isfinite(errors) != np.isfinite(baseline)
            for i in np.flatnonzero(changed):
                changes.append(dict(model=evaluator.name,temperature=args.current_temperature,method=method,
                    partition=partition,observation_id=frame.observation_id.iloc[i],BBCH=frame.BBCH.iloc[i],
                    previously_attained=bool(np.isfinite(baseline[i])),now_attained=bool(np.isfinite(errors[i]))))
    pd.concat(output,ignore_index=True).to_csv(directory/'predictions.csv.gz',index=False,date_format='%Y-%m-%d')
    pd.DataFrame(metric_rows).to_csv(directory/'metrics.csv',index=False)
    pd.DataFrame(paired).to_csv(directory/'matched_metrics.csv',index=False)
    pd.DataFrame(changes,columns=['model','temperature','method','partition','observation_id','BBCH',
        'previously_attained','now_attained']).to_csv(directory/'coverage_changes.csv',index=False)
    save_json(directory/'complete.json',dict(verified=True,canonical_replay=True,independent_metrics=True,
        artifacts={p.name:digest(p) for p in directory.iterdir() if p.is_file() and p.name!='complete.json'}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,default=DEFAULT_RUN)
    parser.add_argument('--cohort',type=Path,default=DEFAULT_COHORT)
    parser.add_argument('--observations',type=Path,default=DEFAULT_OBS)
    parser.add_argument('--output',type=Path,default=ROOT/'model_run/results/pooled_calibration_20260912')
    parser.add_argument('--models',nargs='+',choices=MODEL_NAMES,default=list(MODEL_NAMES))
    parser.add_argument('--temperatures',nargs='+',choices=['RAW','DEM'],default=['RAW','DEM'])
    parser.add_argument('--seeds',nargs='+',type=int,default=[20260907,20260908,20260909])
    parser.add_argument('--maxiter',type=int,default=300)
    parser.add_argument('--retry-maxiter',type=int,default=600)
    parser.add_argument('--smoke',action='store_true')
    args = parser.parse_args(argv)
    if not args.smoke and (args.maxiter!=300 or args.retry_maxiter!=600 or args.seeds!=[20260907,20260908,20260909]):
        parser.error('Reduced or altered budgets require --smoke')
    args.output.mkdir(parents=True,exist_ok=True)
    import fcntl
    lock = (args.output/'.run.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    source_paths = [args.observations,args.cohort/'weather.csv.gz',args.run/'protocols.csv',
        Path(__file__),Path(__file__).with_name('pooled_calibration.py'),*sorted((ROOT/'model').rglob('*.py'))]
    for model in args.models:
        for temperature in args.temperatures:
            folder = args.run/f'experiments/site_holdout/{model}/{temperature}/pbm/full'
            marker = json.loads((folder/'complete.json').read_text())
            for filename, expected in marker['artifacts'].items():
                if digest(folder/filename) != expected:
                    raise ValueError(f'Unsealed source artifact: {folder/filename}')
            source_paths += [folder/'fit.json',folder/'predictions.csv',folder/'complete.json']
    sources = {str(p.resolve()):digest(p) for p in source_paths}
    configuration = dict(sources=sources,models=args.models,temperatures=args.temperatures,seeds=args.seeds,
        maxiter=args.maxiter,retry_maxiter=args.retry_maxiter,popsize=15,tol=.001,smoke=args.smoke,
        bias_tolerance_days=1.,coverage='preserve existing record and equal-site calibration attainment',
        fit_population='frozen primary calibration sites; cleaned observations',test_selection=False)
    run_path = args.output/'run.json'
    if run_path.exists():
        if json.loads(run_path.read_text()) != configuration:
            raise ValueError('Resume configuration or input/source fingerprints differ')
    else:
        save_json(run_path,configuration)
    observations = pd.read_csv(args.observations,dtype=str,keep_default_na=False)
    observations['observation_id'] = [hashlib.sha256(json.dumps(list(row),ensure_ascii=False,
        separators=(',',':')).encode()).hexdigest() for row in observations.itertuples(index=False,name=None)]
    if observations.observation_id.duplicated().any():
        raise ValueError('Duplicate canonical observations')
    protocols = pd.read_csv(args.run/'protocols.csv',dtype={'site':str})
    protocols = protocols[protocols.experiment.eq('site_holdout')].drop(columns='experiment')
    calibration, test = select_partitions(observations,protocols)
    if not args.smoke and (len(calibration)!=59472 or len(test)!=15146 or calibration.site.nunique()!=2534 or test.site.nunique()!=635):
        raise ValueError('Cleaned population differs from the approved snapshot')
    pd.concat([calibration,test]).groupby(['partition','BBCH']).agg(n_observations=('site','size'),
        n_sites=('site','nunique')).to_csv(args.output/'population.csv')
    calibration.to_csv(args.output/'calibration_observations.csv.gz',index=False,date_format='%Y-%m-%d')
    test.to_csv(args.output/'test_observations.csv.gz',index=False,date_format='%Y-%m-%d')
    log(f'Loading weather; {len(calibration)} calibration observations, {len(test)} held-out observations')
    weather = pd.read_csv(args.cohort/'weather.csv.gz',dtype={'site':str},parse_dates=['Date'])
    done = []
    for temperature in args.temperatures:
        args.current_temperature = temperature
        column = 'Tmean' if temperature=='RAW' else 'Tmean_DEM'
        log(f'Preparing calibration weather: {temperature}')
        prepared = prepare_weather(weather,calibration[['site','season']].drop_duplicates(),column,None)
        test_prepared = None
        for model in args.models:
            directory = args.output/model/temperature
            directory.mkdir(parents=True,exist_ok=True)
            if (directory/'complete.json').exists():
                marker = json.loads((directory/'complete.json').read_text())
                check_sources({str(directory/k):v for k,v in marker['artifacts'].items()})
                done.append(f'{model}/{temperature}')
                continue
            log(f'{model}/{temperature}: build fixed response cache')
            evaluator = RateEvaluator(model,prepared)
            existing = json.loads((args.run/f'experiments/site_holdout/{model}/{temperature}/pbm/full/fit.json').read_text())['parameters']
            fitted = fit_unit(args,directory,evaluator,calibration,existing)
            log(f'{model}/{temperature}: calibration locked; evaluate test sites')
            if test_prepared is None:
                test_prepared = prepare_weather(weather,test[['site','season']].drop_duplicates(),column,None)
            test_evaluator = RateEvaluator(model,test_prepared)
            evaluate_unit(args,directory,fitted,calibration,test,evaluator,test_evaluator)
            del evaluator,test_evaluator
            done.append(f'{model}/{temperature}')
            save_json(args.output/'status.json',dict(complete=False,completed=done,expected=len(args.models)*len(args.temperatures)))
    for filename in ['metrics.csv','matched_metrics.csv','coverage_changes.csv']:
        pd.concat([pd.read_csv(args.output/model/temperature/filename,dtype={'BBCH':str})
            for model in args.models for temperature in args.temperatures],ignore_index=True).to_csv(args.output/filename,index=False)
    check_sources(sources)
    save_json(args.output/'status.json',dict(complete=True,completed=done,expected=len(done),smoke=args.smoke,
        original_sources_unchanged=True))
    log('All requested calibration comparisons and independent checks completed')


if __name__ == '__main__':
    main()
