import numpy as np
import pandas as pd
import pytest

from model_run.src.run_cutoff_ml import make_protocol, residual_assembly, score_methods, _features_cached
from model_run.factorial.runner import frame_hash
from test_pooled_calibration import constant_problem


def test_protocol_preserves_groups_and_rejects_overlap():
    cal = pd.DataFrame({'site': ['a', 'b', 'c', 'd'], 'season': [2020]*4,
        'partition': ['calibration']*4, 'inner_fold': range(4)})
    test = pd.DataFrame({'site': ['e'], 'season': [2020], 'partition': ['test'], 'inner_fold': [-1]})
    sites = pd.DataFrame({'site': list('abcde'), 'group_id': list('ABCDE')})
    assert len(make_protocol(cal, test, sites)) == 5
    with pytest.raises(ValueError, match='group'):
        make_protocol(cal, test, sites.assign(group_id=['A', 'B', 'C', 'D', 'A']))
    with pytest.raises(ValueError, match='site'):
        make_protocol(cal, test.assign(site='a'), sites)


def test_nested_residual_training_excludes_validation_fold():
    protocol = pd.DataFrame({'site': list('abcd'), 'season': [2020]*4,
        'partition': ['calibration']*4, 'inner_fold': range(4)})
    observations = protocol.assign(BBCH='07', Date=pd.Timestamp('2020-04-10'), observation_id=list('abcd'))
    predictions = {}
    for a in range(4):
        predictions[f'oof_{a}'] = pd.DataFrame({'site': [chr(97+a)], 'season': [2020], 'BBCH': ['07'], 'predicted_date': [pd.Timestamp('2020-04-01')]})
        for b in range(a+1, 4):
            predictions[f'nested_{a}_{b}'] = pd.concat([pd.DataFrame({'site': [chr(97+i)], 'season': [2020], 'BBCH': ['07'], 'predicted_date': [pd.Timestamp('2020-04-01')]}) for i in [a,b]])
    oof, nested = residual_assembly(predictions, observations, protocol)
    assert len(oof) == 4 and oof.residual_days.eq(9).all()
    for held, rows in nested.items():
        assert len(rows) == 3 and chr(97+held) not in set(rows.site)


def test_ml_scoring_keeps_unattained_process_and_cutoff_separate():
    evaluator, observations, params = constant_problem()
    raw = evaluator.predict(params)
    raw[0, 3] = np.datetime64('NaT')
    table = pd.DataFrame({'site': ['a']*4, 'season': [2020]*4, 'BBCH': ['07','65','81','89'],
                          'predicted_date': raw[0]})
    ml = table.copy()
    ml.loc[ml.BBCH.eq('81'), 'predicted_date'] = pd.Timestamp('2020-11-10')
    pred, metrics = score_methods(observations, evaluator.prepared, table, ml, 'FL', 'RAW', 'calibration')
    maturity = pred[pred.method.eq('tabm') & pred.BBCH.eq('89')].iloc[0]
    assert not maturity.pbm_raw_attained and maturity.cutoff_assigned
    assert pd.isna(maturity.raw_predicted_date) and maturity.scoring_date == pd.Timestamp('2020-11-04')
    earlier = pred[pred.method.eq('tabm') & pred.BBCH.eq('81')].iloc[0]
    assert earlier.scoring_date == maturity.scoring_date
    assert len(metrics) == 16


def test_feature_cache_first_run_and_resume_have_identical_hashes(tmp_path):
    from test_factorial_features import fixture
    predictions, weather, terrain = fixture()
    weather['Tmean'] = np.linspace(.125, 21.827364928, len(weather))
    first = _features_cached(tmp_path, predictions, weather, terrain, 'RAW', {})
    resumed = _features_cached(tmp_path, predictions, weather, terrain, 'RAW', {})
    assert frame_hash(first) == frame_hash(resumed)
