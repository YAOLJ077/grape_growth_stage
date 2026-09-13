import numpy as np
import pandas as pd
import pytest

from model.structure_comparison import fixed_parameters
from model_run.src.median_cutoff import (
    derive_cutoff, scoring_predictions, EarlySearch, maturity_median, evaluation_rows,
)
from test_pooled_calibration import constant_problem, seasons
from model_run.src.pooled_calibration import RateEvaluator
from model.registry import MODEL_NAMES
from model.data import SeasonWeather


def test_cutoff_uses_calibration_maturity_month_day_only():
    frame = pd.DataFrame({'partition': ['calibration'] * 3 + ['test'],
        'BBCH': ['89', '89', '81', '89'],
        'Date': pd.to_datetime(['1970-11-04', '2022-09-29', '2020-12-01', '2023-11-15'])})
    assert derive_cutoff(frame) == '11-04'


def test_cutoff_boundaries_missing_and_same_day_assignment():
    raw = np.array([
        ['2020-04-01', '2020-06-01', '2020-11-03', '2020-11-04'],
        ['2020-04-01', '2020-06-01', '2020-11-04', '2020-11-05'],
        ['2020-04-01', '2020-06-01', '2020-11-05', '2020-12-01'],
        ['2020-04-01', '2020-06-01', 'NaT', 'NaT'],
    ], dtype='datetime64[D]')
    original = raw.copy()
    used, reason, cutoffs = scoring_predictions(raw, [2020] * 4, '11-04')
    np.testing.assert_array_equal(raw, original)
    np.testing.assert_array_equal(used[:, :2], raw[:, :2])
    assert str(used[0, 2]) == '2020-11-03'
    assert reason[0, 3] == ''
    assert reason[1, 2] == ''
    assert reason[1, 3] == 'after_cutoff'
    assert reason[2, 2] == 'after_cutoff'
    assert reason[3, 2] == 'unattained'
    assert np.all(used[2:, 2:] == np.datetime64('2020-11-04'))


def test_early_objective_excludes_maturity_and_enforces_raw_coverage():
    evaluator, frame, parameters = constant_problem()
    search = EarlySearch(evaluator, frame, parameters, '11-04')
    assert 'forcing_requirement_89' not in search.names
    assert search.feasible(search.vector(parameters))
    other = EarlySearch(evaluator, frame.assign(Date=frame.Date.where(
        frame.BBCH.ne('89'), pd.Timestamp('2020-11-04'))), parameters, '11-04')
    assert search.violation(search.vector(parameters)) == other.violation(other.vector(parameters))
    bad = dict(parameters, forcing_requirement_07=3000., forcing_requirement_65=3000.)
    assert not search.covered(search.vector(bad))
    # Complete scoring of stage81 must not conceal raw failure.
    assert search.stats(search.vector(bad))[2, 3] == 1.
    with pytest.raises(ValueError, match='calibration'):
        EarlySearch(evaluator, frame.assign(partition='test'), parameters, '11-04')


def test_median_preserves_earlier_parameters_and_uses_raw_start():
    evaluator, frame, parameters = constant_problem()
    fitted, audit = maturity_median(evaluator, frame, parameters)
    assert fitted == parameters
    assert audit.eligible_requirement.all()
    with pytest.raises(ValueError, match='positive'):
        maturity_median(evaluator, frame.assign(Date=pd.Timestamp('2020-01-01')), parameters)
    with pytest.raises(ValueError, match='calibration'):
        maturity_median(evaluator, frame.assign(partition='test'), parameters)


def test_median_balances_sites_and_audits_invalid_observations():
    evaluator, _, parameters = constant_problem()
    w = evaluator.prepared[0]
    ev = RateEvaluator('FL', tuple(SeasonWeather(site, w.season, w.dates, w.temperature) for site in ['a', 'b', 'c']))
    previous = ev.predict(parameters)[0, 2]
    rows = []
    for site, repetitions, days in [('a', 10, 10), ('b', 1, 20), ('c', 1, 30), ('c', 1, -1)]:
        for _ in range(repetitions):
            rows.append(dict(site=site, season=2020, BBCH='89', partition='calibration',
                Date=pd.Timestamp(previous) + pd.Timedelta(days=days), observation_id=str(len(rows))))
    fitted, audit = maturity_median(ev, pd.DataFrame(rows), parameters)
    assert fitted['forcing_requirement_89'] == 200.
    assert audit.eligible_requirement.sum() == 12
    assert audit.iloc[-1].exclusion_reason == 'observation_not_after_raw_81'
    np.testing.assert_allclose(audit.groupby('site').site_weight.sum(), 1.)


def test_cached_early_scoring_agrees_with_independent_date_evaluation():
    evaluator, frame, parameters = constant_problem()
    search = EarlySearch(evaluator, frame, parameters, '11-04')
    for late in [100., 3000.]:
        p = dict(parameters, forcing_requirement_65=late, forcing_requirement_81=late)
        expected = search.stats(search.vector(p))[:3, :3]
        _, metrics = evaluation_rows(evaluator, frame, evaluator.predict(search.decode(search.vector(p))),
                                    '11-04', 'FL', 'RAW', 'median_cutoff', 'calibration')
        got = metrics[metrics.metric_view.eq('scoring') & metrics.BBCH.ne('89')][['mae_days', 'rmse_days', 'bias_days']]
        np.testing.assert_allclose(expected, got.to_numpy(), equal_nan=True)


@pytest.mark.parametrize('model', MODEL_NAMES)
def test_median_defined_for_all_structures_and_freezes_early_predictions(model):
    evaluator = RateEvaluator(model, seasons())
    p = fixed_parameters(model)
    p.update({f'forcing_requirement_{s}': 5. for s in ['07', '65', '81', '89']})
    if 'chilling_minimum' in p:
        p['chilling_requirement'] = 1.
    raw = evaluator.predict(p)
    records = []
    for i, weather in enumerate(evaluator.prepared):
        records.append(dict(site=weather.site, season=weather.season, BBCH='89',
            Date=pd.Timestamp(raw[i, 2]) + pd.Timedelta(days=30), partition='calibration',
            observation_id=str(i)))
    fitted, audit = maturity_median(evaluator, pd.DataFrame(records), p)
    assert audit.eligible_requirement.any()
    np.testing.assert_array_equal(evaluator.predict(fitted)[:, :3], raw[:, :3])


def test_scoring_does_not_turn_failure_into_attainment_or_drop_late_observations():
    evaluator, frame, parameters = constant_problem()
    frame = frame.copy()
    frame.loc[frame.BBCH.eq('89'), 'Date'] = pd.Timestamp('2020-11-10')
    raw = evaluator.predict(parameters)
    raw[0, 3] = np.datetime64('NaT')
    predictions, metrics = evaluation_rows(evaluator, frame, raw, '11-04', 'FL', 'RAW', 'median_cutoff', 'test')
    row = predictions[predictions.BBCH.eq('89')].iloc[0]
    assert row.scoring_error_days == -6
    assert np.isnan(row.error_days)
    assert not row.raw_attained and not row.attained_by_cutoff and row.cutoff_assigned
    saved = metrics[(metrics.BBCH.eq('89')) & metrics.metric_view.eq('scoring')].iloc[0]
    assert saved.n_scored == 1 and saved.raw_attainment == 0 and saved.cutoff_assignment_fraction == 1
