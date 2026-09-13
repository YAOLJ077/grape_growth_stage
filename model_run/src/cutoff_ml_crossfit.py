"""Leakage-free grouped PBM refits for the November 4 median-cutoff protocol.

Full-calibration parameters are deliberately absent from this module's API.
Prediction artifacts contain raw simulator dates, never administrative dates.
"""
import hashlib
import itertools
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from model.calibration import _weather_hash
from model.data import SeasonWeather
from model.fast_thresholds import _predict_frame
from model.registry import get_model
from model.specification import STAGES
from model.structure_comparison import fixed_parameters
from model_run.src.calibrate_median_cutoff import early_fit
from model_run.src.calibrate_pooled_sites import canonical_predictions
from model_run.src.median_cutoff import EarlySearch, maturity_median
from model_run.src.pooled_calibration import RateEvaluator

_KEYS = ['site', 'season']
_ARTIFACTS = ['job.json', 'early_fit.json', 'early_fit.complete.json', 'fit.json',
              'median_requirements.csv.gz', 'predictions.csv.gz']


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path, value):
    temporary = path.with_name('.' + path.name + '.tmp')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    os.replace(temporary, path)


def _table(path, frame):
    temporary = path.with_name('.' + path.name + '.tmp')
    frame.to_csv(temporary, index=False, date_format='%Y-%m-%d', compression='gzip')
    os.replace(temporary, path)


def _read(path):
    return json.loads(path.read_text())


def _pairs(frame):
    return [[str(s), int(y)] for s, y in frame[_KEYS].drop_duplicates().sort_values(_KEYS).itertuples(index=False, name=None)]


def _check_groups(train, target):
    for column in ['site', 'group_id', 'physical_site_id']:
        if column in train and column in target:
            if train[column].isna().any() or target[column].isna().any():
                raise ValueError(f'Missing grouping identifier: {column}')
            if set(train[column]) & set(target[column]):
                raise ValueError(f'Train/predict {column} overlap; whole physical/source sites must remain grouped')


def make_jobs(protocol: pd.DataFrame):
    """Four OOF jobs and six pair-exclusion jobs, with no full-fit job."""
    required = {'site', 'season', 'partition', 'inner_fold'}
    if not required.issubset(protocol) or protocol.duplicated(_KEYS).any():
        raise ValueError('Require unique protocol site-season rows and fold/partition fields')
    if not protocol.partition.isin(['calibration', 'test']).all():
        raise ValueError('Unrecognized protocol partition')
    calibration = protocol.loc[protocol.partition.eq('calibration')]
    _check_groups(calibration, protocol.loc[protocol.partition.eq('test')])
    if set(calibration.inner_fold) != set(range(4)):
        raise ValueError('Require all four calibration folds')
    jobs = []
    for excluded in [*((i,) for i in range(4)), *itertools.combinations(range(4), 2)]:
        train = calibration.loc[~calibration.inner_fold.isin(excluded)]
        target = calibration.loc[calibration.inner_fold.isin(excluded)]
        _check_groups(train, target)
        name = 'oof_' + str(excluded[0]) if len(excluded) == 1 else 'nested_' + '_'.join(map(str, excluded))
        jobs.append(dict(name=name, excluded_folds=list(excluded), train_pairs=_pairs(train), predict_pairs=_pairs(target)))
    return jobs


def _select(frame, pairs):
    keys = pd.DataFrame(pairs, columns=_KEYS)
    if keys.empty or keys.duplicated().any():
        raise ValueError('Require nonempty unique site-season pairs')
    selected = frame.merge(keys, on=_KEYS, how='inner', validate='many_to_one')
    if set(map(tuple, _pairs(selected))) != set(map(tuple, pairs)):
        raise ValueError('Requested pair is absent from calibration observations')
    return selected


def _prepared_subset(prepared, pairs):
    lookup = {(w.site, int(w.season)): w for w in prepared}
    if len(lookup) != len(prepared):
        raise ValueError('Duplicate prepared weather site-season')
    try:
        return tuple(lookup[(s, int(y))] for s, y in pairs)
    except KeyError as error:
        raise ValueError('Missing requested prepared weather') from error


def _initial(model):
    parameters = dict(fixed_parameters(model))
    # SciPy's affine bound transform rounds exact 0.001 slightly below zero.
    # This fixed interior epsilon is numerical only and never label-derived.
    small = .001 + 1e-9
    parameters.update({f'forcing_requirement_{s}': small for s in STAGES})
    if get_model(model).chilling != 'none':
        parameters['chilling_requirement'] = small
    return parameters


def predict_table(model, parameters, prepared, temperature, fit_id=""):
    """Canonical raw predictions and accumulation starts for prepared weather."""
    if get_model(model).interaction == 'none':
        # The canonical batch starts at index zero; forcing-only starts Jan 1.
        trimmed = []
        for w in prepared:
            start = np.searchsorted(w.dates, np.datetime64(f'{w.season}-01-01'))
            trimmed.append(SeasonWeather(w.site, w.season, w.dates[start:], w.temperature[start:]))
        prepared = tuple(trimmed)
    result = _predict_frame(model, parameters, prepared, temperature)
    result['raw_predicted_date'] = result.predicted_date
    result['raw_attained'] = result.predicted_date.notna()
    result['pbm_fit_id'] = fit_id
    if result.duplicated([*_KEYS, 'BBCH']).any():
        raise ValueError('Duplicate prediction keys')
    return result


def _source_hashes():
    root = Path(__file__).resolve().parents[2]
    paths = [Path(__file__), *sorted((root / 'model').glob('*.py')),
             *[Path(__file__).with_name(n) for n in ['calibrate_median_cutoff.py',
               'calibrate_pooled_sites.py', 'median_cutoff.py', 'pooled_calibration.py']]]
    return {str(p.relative_to(root)): _digest(p) for p in paths}


def _verify_artifacts(directory):
    marker = _read(directory / 'complete.json')
    if marker.get('verified') is not True or set(marker.get('artifacts', {})) != set(_ARTIFACTS):
        raise ValueError('Incomplete cross-fit artifact manifest')
    for name, value in marker['artifacts'].items():
        if not (directory / name).is_file() or _digest(directory / name) != value:
            raise ValueError(f'Cross-fit artifact hash differs: {name}')


def fit_predict_job(job, calibration: pd.DataFrame, prepared: tuple, model: str,
                    temperature: str, directory: Path, *, seeds: list[int],
                    maxiter: int, retry_maxiter: int, cutoff='11-04') -> pd.DataFrame:
    """Fit only job training labels and predict only its held-fold site-seasons.

    Non-default budgets are supported for the caller's explicitly marked smoke
    run. Production orchestration owns the required three seeds and 300/600 limit.
    """
    if cutoff != '11-04':
        raise ValueError('The fixed protocol cutoff is November 4 (11-04)')
    if temperature not in {'RAW', 'DEM'} or not seeds or maxiter < 1 or retry_maxiter < maxiter:
        raise ValueError('Invalid temperature or optimizer settings')
    if not calibration.partition.eq('calibration').all():
        raise ValueError('Only calibration records may enter cross-fitting; test records forbidden')
    if calibration.observation_id.duplicated().any():
        raise ValueError('Duplicate calibration observation IDs')
    excluded = job['excluded_folds']
    if len(excluded) not in (1, 2):
        raise ValueError('Require an OOF or nested exclusion job, never a full fit')
    expected_name = ('oof_' + str(excluded[0]) if len(excluded) == 1 else
                     'nested_' + '_'.join(map(str, excluded)))
    if len(excluded) not in (1, 2) or sorted(set(excluded)) != excluded or not set(excluded) <= set(range(4)) or job['name'] != expected_name:
        raise ValueError('Require an OOF or nested exclusion job, never a full fit')
    train = _select(calibration, job['train_pairs'])
    # Only keys/group identifiers from held observations enter validation/provenance.
    grouping = [c for c in ['site', 'season', 'group_id', 'physical_site_id', 'inner_fold'] if c in calibration]
    target = _select(calibration[grouping].drop_duplicates(), job['predict_pairs'])
    _check_groups(train, target)
    if 'inner_fold' in calibration:
        if train.inner_fold.isin(excluded).any() or not target.inner_fold.isin(excluded).all():
            raise ValueError('Job pair membership disagrees with excluded folds')
    training_weather = _prepared_subset(prepared, job['train_pairs'])
    prediction_weather = _prepared_subset(prepared, job['predict_pairs'])
    initial = _initial(model)
    provenance = dict(**job, model=model, temperature_input=temperature,
        observation_ids=train.observation_id.astype(str).tolist(),
        input_frame_sha256=hashlib.sha256(train.to_csv(index=False, date_format='%Y-%m-%d').encode()).hexdigest(),
        training_weather_sha256=_weather_hash(training_weather),
        prediction_weather_sha256=_weather_hash(prediction_weather),
        cutoff_month_day=cutoff, cutoff_source='fixed approved protocol, not rederived within folds',
        initialization=initial, initialization_source='predeclared fixed responses and 0.001 + 1e-9 thresholds (SciPy bound-roundoff guard)',
        full_calibration_parameters_used=False, test_labels_used=False,
        seeds=list(seeds), maxiter=maxiter, retry_maxiter=retry_maxiter, source_sha256=_source_hashes())
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    job_path = directory / 'job.json'
    complete = (directory / 'complete.json').exists()
    if complete:
        _verify_artifacts(directory)
    if job_path.exists():
        if _read(job_path) != provenance:
            raise ValueError('Cross-fit training provenance differs on resume')
    else:
        _json(job_path, provenance)
    evaluator = RateEvaluator(model, training_weather)
    early_path = directory / 'early_fit.json'
    early_marker = directory / 'early_fit.complete.json'
    if early_path.exists():
        if not early_marker.exists() or _read(early_marker) != dict(sha256=_digest(early_path), job_sha256=_digest(job_path)):
            raise ValueError('Early checkpoint hash/provenance differs')
        checkpoint = _read(early_path)
        early, diagnostics = checkpoint['parameters'], checkpoint['diagnostics']
    else:
        try:
            early, diagnostics = early_fit(evaluator, train, initial, cutoff, seeds, maxiter, retry_maxiter)
        except ValueError as error:
            _json(directory / 'failure.json', dict(reason=str(error), job_sha256=_digest(job_path)))
            raise
        _json(early_path, dict(parameters=early, diagnostics=diagnostics))
        _json(early_marker, dict(sha256=_digest(early_path), job_sha256=_digest(job_path)))
    search = EarlySearch(evaluator, train, early, cutoff)
    vector = search.vector(early)
    np.testing.assert_allclose(search.stats(vector)[:3], diagnostics['early_scoring_metrics'], rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(search.raw_stats[:3], diagnostics['early_raw_metrics'], rtol=1e-10, atol=1e-10)
    if not search.covered(vector) or search.feasible(vector) != diagnostics['early_bias_target_met']:
        raise ValueError('Early checkpoint raw coverage/bias status differs')
    before = canonical_predictions(evaluator, early)
    try:
        parameters, audit = maturity_median(evaluator, train, early)
    except ValueError as error:
        if hasattr(error, 'audit'):
            _table(directory / 'median_requirements.csv.gz', error.audit)
        _json(directory / 'failure.json', dict(reason=str(error), job_sha256=_digest(job_path)))
        raise
    if any(parameters[k] != v for k, v in early.items() if k != 'forcing_requirement_89'):
        raise ValueError('Maturity fitting changed frozen early parameters')
    after = canonical_predictions(evaluator, parameters)
    np.testing.assert_array_equal(before[:, :3], after[:, :3])
    fit = dict(parameters=parameters, **diagnostics, job_sha256=_digest(job_path),
        cutoff_month_day=cutoff, early_predictions_unchanged_after_median=True,
        median_threshold_status='met', median_eligible_records=int(audit.eligible_requirement.sum()),
        median_excluded_records=int((~audit.eligible_requirement).sum()),
        median_unbounded=float(audit.median_unbounded.iloc[0]),
        median_bound_adjusted=bool(audit.bound_adjusted.iloc[0]), test_labels_used=False)
    predictions = predict_table(model, parameters, prediction_weather, temperature, job['name'])
    if complete:
        if _read(directory / 'fit.json') != fit:
            raise ValueError('Cached fit differs from replayed median/calibration diagnostics')
        saved = pd.read_csv(directory / 'predictions.csv.gz', dtype={'site': str, 'BBCH': str},
                            parse_dates=['predicted_date', 'phase_start_date', 'raw_predicted_date'])
        columns = [*_KEYS, 'BBCH', 'model_name', 'temperature_input', 'pbm_fit_id',
                   'predicted_date', 'phase_start_date', 'raw_predicted_date', 'raw_attained']
        pd.testing.assert_frame_equal(saved[columns], predictions[columns], check_dtype=False)
        return predictions
    _json(directory / 'fit.json', fit)
    _table(directory / 'median_requirements.csv.gz', audit)
    _table(directory / 'predictions.csv.gz', predictions)
    _json(directory / 'complete.json', dict(verified=True, canonical_replay=True,
        artifacts={name: _digest(directory / name) for name in _ARTIFACTS}))
    return predictions
