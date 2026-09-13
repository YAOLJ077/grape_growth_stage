"""Independent numerical checks for final process/DEM/ML analysis."""
import json
import numpy as np
import pandas as pd
import pytest

from model_run.src.analyze_final_cutoff import (
    paired_statistics, match_predictions, terrain_strata, validate_final_run,
)


def paired_fixture():
    # Two source sites share one original independence group. Site weights differ
    # deliberately from observation weights and independence-group weights.
    rows = []
    for site, group, errors in [('a', 'G1', [10., 10., 10.]), ('b', 'G1', [2.]), ('c', 'G2', [0.])]:
        for stage in ['07', '65', '81', '89']:
            for i, value in enumerate(errors):
                rows.append(dict(site=site, group_id=group, BBCH=stage,
                    observation_id=f'{site}-{stage}-{i}', baseline_error=value,
                    candidate_error=value / 2))
    return pd.DataFrame(rows)


def test_paired_errors_are_site_balanced_and_small_groups_have_no_ci():
    data = paired_fixture()
    result = paired_statistics(data, n_bootstrap=50, seed=17)
    stage = result[result.BBCH.eq('07')].set_index('metric')
    assert stage.loc['mae_days', 'baseline'] == pytest.approx(4.)
    assert stage.loc['mae_days', 'candidate'] == pytest.approx(2.)
    assert stage.loc['mae_days', 'benefit'] == pytest.approx(2.)
    assert stage.loc['rmse_days', 'baseline'] == pytest.approx(np.sqrt(104 / 3))
    assert stage.n_groups.eq(2).all()
    assert stage.ci_low.isna().all()
    assert result[result.BBCH.eq('ALL')].n_stages.eq(4).all()


def test_common_finite_population_and_no_missing_stage_renormalization():
    data = paired_fixture()
    data.loc[data.site.eq('a'), 'candidate_error'] = np.nan
    data = data[~data.BBCH.eq('89')]
    result = paired_statistics(data, n_bootstrap=50, seed=17)
    row = result[result.BBCH.eq('07') & result.metric.eq('mae_days')].iloc[0]
    assert row.n_observations == 5 and row.n_paired == 2 and row.n_baseline_finite == 5
    assert row.baseline == 1 and row.candidate == .5
    assert row.paired_fraction == .4
    assert result[result.BBCH.eq('ALL')].benefit.isna().all()


def test_cluster_bootstrap_reproducible_and_direction_of_bias_defined():
    data = pd.concat([paired_fixture().assign(site=lambda d: d.site + str(i),
        group_id=f'group-{i}') for i in range(12)], ignore_index=True)
    # All 12 groups have identical site composition, so every resample agrees.
    a = paired_statistics(data, n_bootstrap=60, seed=42)
    b = paired_statistics(data, n_bootstrap=60, seed=42)
    pd.testing.assert_frame_equal(a, b)
    row = a[a.BBCH.eq('ALL') & a.metric.eq('mae_days')].iloc[0]
    assert row.ci_low == pytest.approx(2) and row.ci_high == pytest.approx(2)
    bias = a[a.BBCH.eq('07') & a.metric.eq('bias_days')].iloc[0]
    assert bias.change == -2 and np.isnan(bias.benefit)


def test_observation_id_matching_rejects_population_or_identity_changes():
    a = pd.DataFrame(dict(observation_id=['x', 'y'], site=['a','b'], BBCH=['07','65'],
        Date=pd.to_datetime(['2020-04-01','2020-06-01']), partition=['test']*2,
        group_id=['g1','g2'], temperature_zone_id=['1','2'], country=['FR','DE'],
        scoring_error_days=[3.,4.]))
    b = a.iloc[::-1].copy(); b['scoring_error_days'] = [2.,1.]
    paired = match_predictions(a, b)
    assert paired.candidate_error.tolist() == [1.,2.]
    with pytest.raises(ValueError, match='population'):
        match_predictions(a, b.iloc[:1])
    b.loc[b.observation_id.eq('x'), 'site'] = 'changed'
    with pytest.raises(ValueError, match='identity'):
        match_predictions(a,b)


def test_terrain_cuts_ignore_test_extremes_and_preserve_na():
    sites = pd.DataFrame(dict(site=list('abcdef'), partition=['calibration']*3+['test']*3,
        dem_local_std_m=[0.,3.,6.,10000.,np.nan,2.],
        site_minus_grid_elevation_m=[-30.,0.,30.,100000.,np.nan,-1.]))
    assigned, cuts = terrain_strata(sites)
    assert cuts['dem_local_std_m']['cutpoints'] == pytest.approx([2.,4.])
    assert assigned.set_index('site').loc['e','terrain_complexity'] == 'NA'
    assert assigned.set_index('site').loc['d','terrain_complexity'] == 'high'
    assert cuts['absolute_elevation_mismatch_m']['cutpoints'] == pytest.approx([20.,30.])


def test_publication_rejects_empty_partial_or_smoke_runs(tmp_path):
    (tmp_path/'status.json').write_text(json.dumps(dict(complete=False,completed=[],expected=20,smoke=False)))
    with pytest.raises(ValueError, match='complete'):
        validate_final_run(tmp_path)
    (tmp_path/'status.json').write_text(json.dumps(dict(complete=True,completed=[],expected=20,smoke=True)))
    with pytest.raises(ValueError, match='smoke'):
        validate_final_run(tmp_path)


def test_overall_ci_requires_ten_groups_in_every_stage():
    data = pd.concat([paired_fixture().assign(site=lambda d: d.site + str(i),
        group_id=f'group-{i}') for i in range(12)], ignore_index=True)
    data = data[~(data.BBCH.eq('89') & data.group_id.isin([f'group-{i}' for i in range(4)]))]
    result = paired_statistics(data, n_bootstrap=60, seed=42)
    overall = result[result.BBCH.eq('ALL')]
    assert overall.n_stages.eq(4).all() and overall.n_groups.eq(12).all()
    assert overall.ci_low.isna().all() and overall.ci_status.eq('insufficient_groups').all()
    assert result[result.BBCH.eq('07')].ci_low.notna().all()
