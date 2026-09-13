import numpy as np
import pandas as pd
import pytest

from model.data import SeasonWeather
from model.registry import MODEL_NAMES
from model.simulation import simulate_season
from model.structure_comparison import fixed_parameters
from model_run.src.pooled_calibration import RateEvaluator, Metrics, weighted_median, select_partitions
from model_run.src.calibrate_pooled_sites import Search, median_thresholds, canonical_predictions, optimize


def seasons():
    dates = pd.date_range('2019-09-01', '2020-12-31').to_numpy()
    return tuple(SeasonWeather(str(i), 2020, dates,
        12 + 15 * np.sin(np.arange(len(dates)) / 58 + i)) for i in range(3))


@pytest.mark.parametrize('name', MODEL_NAMES)
def test_cached_crossings_match_reference(name):
    prepared = seasons()
    evaluator = RateEvaluator(name, prepared)
    rng = np.random.default_rng(193)
    for _ in range(12):
        p = fixed_parameters(name)
        p.update({f'forcing_requirement_{s}': float(rng.uniform(.01, 1800 if 'forcing_base_07' in p else 180))
                  for s in ['07', '65', '81', '89']})
        if 'chilling_minimum' in p:
            p['chilling_requirement'] = float(rng.uniform(.01, 200))
        got = evaluator.predict(p)
        expected = np.array([simulate_season(name, p, w)[0] for w in prepared], dtype='datetime64[D]')
        np.testing.assert_array_equal(got, expected)


def test_metrics_balance_sites_and_preserve_missing_denominator():
    frame = pd.DataFrame([(site, stage) for stage in ['07','65','81','89']
                          for site in ['a','a','b']], columns=['site','BBCH'])
    m = Metrics(frame)
    got = m(np.tile([0., 2., 10.], 4))
    np.testing.assert_allclose(got[:,0], 5.5)
    np.testing.assert_allclose(got[:,1], np.sqrt(51))
    np.testing.assert_allclose(got[:,2], 5.5)
    missing = m(np.tile([0., np.nan, 10.], 4))
    np.testing.assert_allclose(missing[:,0], 5.)
    np.testing.assert_allclose(missing[:,3], 2/3)
    np.testing.assert_allclose(missing[:,4], .75)
    np.testing.assert_allclose(missing[:,5], np.sqrt(250050))


def test_median_is_weighted_and_ignores_nonfinite_values():
    assert weighted_median(np.array([1., 2., 100., np.nan]), np.array([1., 1., 3., 9.])) == 100
    assert weighted_median(np.array([1.,3.]), np.array([1.,1.])) == 1.
    with pytest.raises(ValueError):
        weighted_median(np.array([np.nan]), np.array([1.]))


def test_partition_selection_is_exact_and_disjoint():
    obs = pd.DataFrame({'site':['a','b'], 'Date':['2020-02-29','2020-03-01'], 'BBCH':['07','07']})
    protocol = pd.DataFrame({'site':['a','b'], 'season':[2020,2020],
                             'partition':['calibration','test'], 'temperature_zone_id':['TZ01','TZ02']})
    train, test = select_partitions(obs, protocol)
    assert train.site.tolist() == ['a']
    assert test.site.tolist() == ['b']
    assert train.Date.iloc[0] == pd.Timestamp('2020-02-29')
    with pytest.raises(ValueError):
        select_partitions(obs, protocol.iloc[:1])


def constant_problem():
    dates = pd.date_range('2019-09-01','2020-12-31').to_numpy()
    evaluator = RateEvaluator('FL',(SeasonWeather('a',2020,dates,np.full(len(dates),10.)),))
    parameters = {**fixed_parameters('FL'), **dict(zip(
        [f'forcing_requirement_{s}' for s in ['07','65','81','89']], [600.,320.,300.,300.]))}
    frame = pd.DataFrame({'site':['a']*4,'season':[2020]*4,'BBCH':['07','65','81','89'],
        'Date':pd.to_datetime(['2020-02-29','2020-04-01','2020-05-01','2020-05-31']),
        'partition':['calibration']*4,'observation_id':['one','two','three','four']})
    return evaluator,frame,parameters


def test_median_thresholds_use_next_day_restart_and_leap_day():
    evaluator, frame, parameters = constant_problem()
    search = Search(evaluator,frame,parameters)
    fitted, audit = median_thresholds(search,parameters)
    assert fitted == parameters
    assert len(audit) == len(frame)
    assert all(row['eligible_requirement'] for row in audit)
    np.testing.assert_array_equal(canonical_predictions(evaluator,fitted),frame.Date.to_numpy(dtype='datetime64[D]')[None,:])


def test_search_rejects_test_records_and_coverage_loss():
    evaluator, frame, parameters = constant_problem()
    with pytest.raises(ValueError,match='Only calibration'):
        Search(evaluator,frame.assign(partition='test'),parameters)
    search = Search(evaluator,frame,parameters)
    assert search.feasible(search.vector(parameters))
    bad = dict(parameters,forcing_requirement_07=3000.,forcing_requirement_65=3000.)
    assert not search.covered(search.vector(bad))
    fitted, history = optimize(search,'low_bias_mae',[search.vector(parameters)],[7],1,1)
    assert search.feasible(search.vector(fitted))
    assert search.mae(search.vector(fitted)) == 0
    assert history


@pytest.mark.parametrize('name',MODEL_NAMES)
def test_zero_forcing_never_becomes_a_date(name):
    dates = pd.date_range('2019-09-01','2020-12-31').to_numpy()
    prepared = (SeasonWeather('a',2020,dates,np.full(len(dates),-20.)),)
    p = fixed_parameters(name)
    p.update({f'forcing_requirement_{s}':.001 for s in ['07','65','81','89']})
    if 'chilling_minimum' in p:
        p['chilling_requirement'] = .001
    evaluator = RateEvaluator(name,prepared)
    assert np.isnat(evaluator.predict(p)).all()
    assert np.isnat(canonical_predictions(evaluator,p)).all()
