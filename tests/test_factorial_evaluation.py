import importlib
import pandas as pd
import pytest


def module():
    try:return importlib.import_module('model_run.factorial.evaluation')
    except ModuleNotFoundError:pytest.fail('Factorial evaluation module missing')


def fixture(n=2):
    sites=pd.DataFrame([dict(site=f's{i}',group_id=f'g{i}',country='FR',site_minus_grid_elevation_m=50+100*i,dem_local_std_m=10.*i,dem_elevation_m=100.*i,slope_deg=i,northness=1.,eastness=0.) for i in range(n)])
    rows=[]
    for i in range(n):
        for obs in range(1+i):
            for model,ml,temp,error in [('FL','none','RAW',4),('FL','none','DEM',2),('FL-ML','tabm','RAW',3),('FL-ML','tabm','DEM',0)]:
                rows.append(dict(observation_id=f'{i}:{obs}',site=f's{i}',group_id=f'g{i}',season=2000,BBCH='07',observed_date='2000-04-01',predicted_date=pd.Timestamp('2000-04-01')+pd.Timedelta(days=error),model_name=model,ml_algorithm=ml,temperature_input=temp,partition='test',experiment='site_holdout'))
    return pd.DataFrame(rows),sites


def test_handchecked_matched_benefits_interaction_and_missing_attainment():
    c,s=fixture();c.loc[(c.observation_id=='1:1')&(c.model_name=='FL')&(c.temperature_input=='DEM'),'predicted_date']=pd.NaT
    result=module().evaluate_comparison(c,s,n_bootstrap=20,terrain_cuts=[5,15])
    paired=result['paired_temperature'].set_index('model_name')
    assert paired.loc['FL','n_observations']==2
    assert paired.loc['FL','benefit_mae_days']==2
    assert paired.loc['FL','descriptive_only']
    assert pd.isna(paired.loc['FL','benefit_ci_low'])
    assert result['interaction'].iloc[0].interaction_days==1
    assert result['interaction'].iloc[0].n_observations==2
    metric=result['metrics'].query("model_name == 'FL' and temperature_input == 'DEM'").iloc[0]
    assert metric.attainment==pytest.approx(2/3)
    assert not result['terrain'].empty


def test_bootstrap_uses_groups_and_equal_site_weights():
    c,s=fixture(10)
    c.loc[(c.site=='s9')&(c.temperature_input=='RAW'),'predicted_date']=pd.Timestamp('2000-04-11')
    result=module().evaluate_comparison(c,s,n_bootstrap=200,terrain_cuts=[20,60])
    row=result['paired_temperature'].query("model_name == 'FL'").iloc[0]
    assert row.benefit_mae_days==pytest.approx(2.6)
    assert row.n_groups==10
    assert not row.descriptive_only
    assert row.benefit_ci_low <= row.benefit_mae_days <= row.benefit_ci_high
    c['group_id']='one';s['group_id']='one'
    row=module().evaluate_comparison(c,s,n_bootstrap=200)['paired_temperature'].iloc[0]
    assert row.n_groups==1 and row.descriptive_only


def test_spatial_bootstrap_can_merge_canonical_groups_but_cannot_split_one():
    c,s=fixture(10)
    c['group_id']='spatial_all'
    row=module().evaluate_comparison(c,s,n_bootstrap=20)['paired_temperature'].iloc[0]
    assert row.n_groups==1
    s['group_id']='canonical_all'
    c['group_id']=c.site
    with pytest.raises(ValueError,match='group'):
        module().evaluate_comparison(c,s)


def test_ml_benefits_have_matched_denominators_and_equal_site_estimate():
    sites = pd.DataFrame([dict(site='s0',group_id='g0'),dict(site='s1',group_id='g1')])
    rows = []
    for site, identifier, errors in [('s0','a',(10,2)),('s1','b',(3,2)),('s1','c',(3,2)),('s1','d',(3,None))]:
        for model, algorithm, error in zip(('FL','FL-ML'),('none','tabm'),errors):
            rows.append(dict(site=site,group_id='g'+site[-1],observation_id=identifier,season=2000,BBCH='07',observed_date='2000-04-01',predicted_date=pd.Timestamp('2000-04-01')+pd.Timedelta(days=error) if error is not None else pd.NaT,model_name=model,ml_algorithm=algorithm,temperature_input='RAW',experiment='site_holdout',partition='test'))
    result = module().evaluate_comparison(pd.DataFrame(rows),sites,n_bootstrap=20)
    assert 'paired_ml' in result
    value = result['paired_ml'].iloc[0]
    assert value.benefit_mae_days == pytest.approx(4.5)
    assert value.observation_benefit_mae_days == pytest.approx(10/3)
    assert value.n_pbm_observations == value.n_tabm_observations == value.n_matched_observations == 4
    assert value.n_pbm_attained == 4
    assert value.n_tabm_attained == value.n_paired_observations == value.n_observations == 3
    assert value.descriptive_only
    assert pd.isna(value.benefit_ci_low)
    assert result['paired_ml'].attrs['metadata']['benefit'] == 'MAE_PBM_minus_MAE_TabM'


def test_ml_bootstrap_respects_groups_and_preserves_existing_temperature_results():
    c,s=fixture(10)
    result=module().evaluate_comparison(c,s,n_bootstrap=100)
    assert 'paired_ml' in result
    ml=result['paired_ml'].set_index('temperature_input')
    assert ml.loc['RAW','benefit_mae_days']==1
    assert ml.loc['DEM','benefit_mae_days']==2
    assert ml.loc['RAW','benefit_ci_low']==ml.loc['RAW','benefit_ci_high']==1
    assert not ml.loc['RAW','descriptive_only']
    assert result['paired_temperature'].set_index('model_name').loc['FL','benefit_mae_days']==2
    assert result['interaction'].iloc[0].interaction_days==1
    c['group_id']='one';s['group_id']='one'
    pooled=module().evaluate_comparison(c,s,n_bootstrap=100)['paired_ml']
    assert pooled.n_groups.eq(1).all()
    assert pooled.descriptive_only.all() and pooled.benefit_ci_low.isna().all()


def test_ml_contrast_reports_unmatched_rows_and_complete_nonattainment():
    c,s=fixture()
    c=c.loc[~(c.observation_id.eq('1:1')&c.ml_algorithm.eq('tabm'))].copy()
    c.loc[c.ml_algorithm.eq('tabm'),'predicted_date']=pd.NaT
    result=module().evaluate_comparison(c,s,n_bootstrap=20)
    assert 'paired_ml' in result
    ml=result['paired_ml']
    assert ml.n_pbm_observations.eq(3).all()
    assert ml.n_tabm_observations.eq(2).all()
    assert ml.n_matched_observations.eq(2).all()
    assert ml.n_pbm_attained.eq(3).all()
    assert ml.n_tabm_attained.eq(0).all()
    assert ml.n_paired_observations.eq(0).all() and ml.n_sites.eq(0).all()
    assert ml.benefit_mae_days.isna().all() and ml.descriptive_only.all()
    assert module().evaluate_comparison(c[c.ml_algorithm.eq('none')],s)['paired_ml'].empty
