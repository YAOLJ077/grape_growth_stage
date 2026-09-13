"""Grouped label isolation, canonical median refits and tamper-evident replay."""
import json
import os
os.environ.setdefault('NUMBA_NUM_THREADS', '1')

import numpy as np
import pandas as pd
import pytest

from model.data import SeasonWeather
from model.registry import MODEL_NAMES
from model_run.src import cutoff_ml_crossfit as crossfit


def problem():
    protocol = pd.DataFrame([dict(site=f'FR:tempo:{i:03}', season=2020,
        partition='calibration' if i < 4 else 'test', inner_fold=i if i < 4 else -1,
        group_id=f'physical{i}') for i in range(5)])
    frame = pd.DataFrame([dict(**row, BBCH=stage, Date=pd.Timestamp(date),
        observation_id=f'{row["site"]}-{stage}')
        for row in protocol.iloc[:4].to_dict('records') for stage, date in
        zip(['07', '65', '81', '89'], ['2020-01-01', '2020-01-02', '2020-01-03', '2020-01-20'])])
    dates = pd.date_range('2019-09-01', '2020-12-31').to_numpy()
    weather = tuple(SeasonWeather(s, 2020, dates, np.full(len(dates), 10.)) for s in protocol.site)
    return protocol, frame, weather


def run(tmp_path, frame=None, weather=None):
    protocol, observations, prepared = problem()
    return crossfit.fit_predict_job(crossfit.make_jobs(protocol)[0],
        observations if frame is None else frame, prepared if weather is None else weather,
        'FL', 'RAW', tmp_path, seeds=[7], maxiter=1, retry_maxiter=1)


def test_ten_jobs_have_both_nested_directions_and_no_full_or_test():
    protocol, _, _ = problem()
    jobs = crossfit.make_jobs(protocol)
    assert len(jobs) == 10 and not any(j['name'] == 'full' for j in jobs)
    assert [j['name'] for j in jobs[:4]] == ['oof_0', 'oof_1', 'oof_2', 'oof_3']
    assert sum(len(j['excluded_folds']) for j in jobs[4:]) == 12
    for job in jobs:
        train, target = {s for s, _ in job['train_pairs']}, {s for s, _ in job['predict_pairs']}
        assert not train & target
        assert train | target == set(protocol.loc[protocol.partition.eq('calibration'), 'site'])


def test_protocol_rejects_split_source_sites_physical_groups_and_outer_test_overlap():
    protocol, _, _ = problem()
    bad = pd.concat([protocol, protocol.iloc[[0]].assign(season=2021, inner_fold=1)], ignore_index=True)
    with pytest.raises(ValueError, match='site overlap'):
        crossfit.make_jobs(bad)
    bad = protocol.copy()
    bad.loc[1, 'group_id'] = bad.loc[0, 'group_id']
    with pytest.raises(ValueError, match='group_id overlap'):
        crossfit.make_jobs(bad)
    bad = protocol.copy()
    bad.loc[4, 'site'] = bad.loc[0, 'site']
    bad.loc[4, 'season'] = 2021
    with pytest.raises(ValueError, match='site overlap'):
        crossfit.make_jobs(bad)


@pytest.mark.parametrize('model', MODEL_NAMES)
def test_initialization_is_predeclared_for_every_model(model):
    initial = crossfit._initial(model)
    assert all(initial[f'forcing_requirement_{s}'] == .001 + 1e-9 for s in ['07', '65', '81', '89'])
    if 'chilling_minimum' in initial:
        assert initial['chilling_requirement'] == .001 + 1e-9


def test_real_fit_initialization_isolated_and_median_freezes_early_stages(tmp_path, monkeypatch):
    real = crossfit.early_fit
    calls = []
    def audited(evaluator, calibration, initial, *args):
        assert set(calibration.site) == {'FR:tempo:001', 'FR:tempo:002', 'FR:tempo:003'}
        assert set(w.site for w in evaluator.prepared) == set(calibration.site)
        assert initial == crossfit._initial('FL')
        calls.append(True)
        return real(evaluator, calibration, initial, *args)
    monkeypatch.setattr(crossfit, 'early_fit', audited)
    # A malformed nearby full-fit artifact is not opened or used for initialization.
    (tmp_path / 'full').mkdir()
    (tmp_path / 'full' / 'fit.json').write_text('THIS MUST NEVER BE READ')
    predictions = run(tmp_path / 'oof_0')
    assert calls == [True]
    assert set(predictions.site) == {'FR:tempo:000'}
    assert not predictions.duplicated(['site', 'season', 'BBCH']).any()
    assert predictions.phase_start_date.tolist()[:3] == list(pd.to_datetime(['2020-01-01', '2020-01-02', '2020-01-03']))
    assert predictions.predicted_date.tolist() == list(pd.to_datetime(['2020-01-01', '2020-01-02', '2020-01-03', '2020-01-20']))
    fit = json.loads((tmp_path / 'oof_0' / 'fit.json').read_text())
    early = json.loads((tmp_path / 'oof_0' / 'early_fit.json').read_text())['parameters']
    assert all(fit['parameters'][key] == value for key, value in early.items() if key != 'forcing_requirement_89')
    assert fit['parameters']['forcing_requirement_89'] == 170.
    assert fit['early_predictions_unchanged_after_median']
    metadata = json.loads((tmp_path / 'oof_0' / 'job.json').read_text())
    assert not metadata['full_calibration_parameters_used']
    assert not any('000' in s for s in metadata['observation_ids'])


def test_replay_ignores_excluded_labels_but_rejects_training_weather_and_artifact_changes(tmp_path, monkeypatch):
    first = run(tmp_path)
    monkeypatch.setattr(crossfit, 'early_fit', lambda *a: pytest.fail('resume refit'))
    _, frame, weather = problem()
    frame.loc[frame.inner_fold.eq(0), 'Date'] = pd.Timestamp('2020-12-31')
    pd.testing.assert_frame_equal(first, run(tmp_path, frame=frame))
    frame.loc[frame.inner_fold.eq(1), 'Date'] += pd.Timedelta(days=1)
    with pytest.raises(ValueError, match='provenance'):
        run(tmp_path, frame=frame)
    changed = list(weather)
    w = changed[1]
    changed[1] = SeasonWeather(w.site, w.season, w.dates, w.temperature + .01)
    with pytest.raises(ValueError, match='provenance'):
        run(tmp_path, weather=tuple(changed))
    with (tmp_path / 'predictions.csv.gz').open('ab') as stream:
        stream.write(b'tampered')
    with pytest.raises(ValueError, match='hash differs'):
        run(tmp_path)


def test_early_checkpoint_resume_replays_without_fitting(tmp_path, monkeypatch):
    first = run(tmp_path)
    for name in ['complete.json', 'fit.json', 'predictions.csv.gz', 'median_requirements.csv.gz']:
        (tmp_path / name).unlink()
    monkeypatch.setattr(crossfit, 'early_fit', lambda *a: pytest.fail('early checkpoint refit'))
    pd.testing.assert_frame_equal(first, run(tmp_path))
    (tmp_path / 'complete.json').unlink()
    with (tmp_path / 'early_fit.json').open('a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='checkpoint hash'):
        run(tmp_path)


def test_test_labels_and_bad_fold_or_physical_membership_rejected(tmp_path):
    protocol, frame, weather = problem()
    with pytest.raises(ValueError, match='test records forbidden'):
        run(tmp_path, frame=frame.assign(partition='test'))
    bad = frame.copy()
    bad.loc[bad.inner_fold.eq(1), 'group_id'] = 'physical0'
    with pytest.raises(ValueError, match='group_id overlap'):
        run(tmp_path, frame=bad)
    job = crossfit.make_jobs(protocol)[0]
    bad = frame.copy()
    bad.loc[bad.inner_fold.eq(1), 'inner_fold'] = 0
    with pytest.raises(ValueError, match='excluded folds'):
        run(tmp_path, frame=bad)
    with pytest.raises(ValueError, match='fixed protocol cutoff'):
        crossfit.fit_predict_job(job, frame, weather, 'FL', 'RAW', tmp_path,
            seeds=[7], maxiter=1, retry_maxiter=1, cutoff='10-01')


def test_uncovered_fixed_initialization_fails_without_fallback(tmp_path):
    _, _, weather = problem()
    cold = tuple(SeasonWeather(w.site, w.season, w.dates, np.full_like(w.temperature, -10.)) for w in weather)
    with pytest.raises(ValueError, match='No starting candidate'):
        run(tmp_path, weather=cold)
    assert (tmp_path / 'failure.json').exists()
    assert not (tmp_path / 'complete.json').exists()


def test_raw_prediction_helper_retains_post_cutoff_dates_and_starts():
    _, _, weather = problem()
    parameters = crossfit._initial('FL')
    parameters.update(forcing_requirement_07=100., forcing_requirement_65=100.,
                      forcing_requirement_81=3000., forcing_requirement_89=100.)
    prediction = crossfit.predict_table('FL', parameters, weather[:1], 'RAW', 'frozen_source')
    stage81 = prediction.loc[prediction.BBCH.eq('81')].iloc[0]
    stage89 = prediction.loc[prediction.BBCH.eq('89')].iloc[0]
    assert stage81.predicted_date > pd.Timestamp('2020-11-04')
    assert stage89.phase_start_date == stage81.predicted_date + pd.Timedelta(days=1)
    assert prediction.pbm_fit_id.eq('frozen_source').all()
    assert prediction.raw_attained.all()


def test_replay_detects_inconsistent_prediction_even_if_manifest_is_rehashed(tmp_path):
    run(tmp_path)
    path = tmp_path / 'predictions.csv.gz'
    saved = pd.read_csv(path, dtype={'site': str, 'BBCH': str})
    saved.loc[0, 'phase_start_date'] = '2020-01-02'
    saved.to_csv(path, index=False)
    marker = json.loads((tmp_path / 'complete.json').read_text())
    marker['artifacts']['predictions.csv.gz'] = crossfit._digest(path)
    (tmp_path / 'complete.json').write_text(json.dumps(marker))
    with pytest.raises(AssertionError):
        run(tmp_path)
