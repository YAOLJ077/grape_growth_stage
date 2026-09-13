import importlib
import numpy as np
import pandas as pd
import pytest


def module():
    try:return importlib.import_module('model_run.factorial.validation')
    except ModuleNotFoundError:pytest.fail('Factorial validation module missing')


def fixture():
    sites=pd.DataFrame([dict(site=f's{i}',group_id=f'g{i//2}',era5_grid_id=f'grid{i//2}',lat=30.+i//2,lon=5.,country='FR') for i in range(60)])
    obs=pd.DataFrame([dict(site=s,season=y,BBCH=b,Date=f'{y}-06-01') for s in sites.site for y in [2000,2020,2025] for b in ['07','65','81','89']])
    climate=pd.DataFrame([dict(era5_grid_id=f'grid{i}',year=y,tmean_apr_sep_c=i+float(y==2025)*10) for i in range(30) for y in range(1951,2026)])
    return dict(sites=sites,observations=obs),climate


def test_split_group_integrity_and_all_inner_stage_coverage():
    c,_=fixture(); p=module().make_protocols(c)
    assert set(p.experiment)=={'site_holdout',*[f'spatial_{i}' for i in range(5)]}
    joined=p.merge(c['sites'][['site','group_id']],on='site')
    assert joined.groupby(['experiment','group_id']).partition.nunique().max()==1
    assert joined.query("partition == 'calibration'").groupby(['experiment','group_id']).inner_fold.nunique().max()==1
    for _,a in p.groupby('experiment'):
        assert set(a.query("partition == 'calibration'").inner_fold)=={0,1,2,3}
    pd.testing.assert_frame_equal(p,module().make_protocols(c))


def test_climate_holdouts_use_climate_only_and_annual_grid_equal_weights():
    c,climate=fixture();p=module().make_protocols(c,climate)
    warm=p.query("experiment == 'warm_year' and partition == 'test'")
    assert set(warm.season)=={2025}
    assert p.query("experiment == 'warm_site' and partition == 'test'").site.nunique()==12
    changed={**c,'observations':c['observations'].assign(Date='1900-01-01')}
    pd.testing.assert_frame_equal(p,module().make_protocols(changed,climate))
    assert 'warm_year' in p.attrs['metadata']
    with pytest.raises(ValueError,match='climate|reference'):
        module().make_protocols(c,climate.query('year != 1991'))


def test_warm_anomaly_is_equal_grid_and_spatial_blocks_remain_together():
    c,climate=fixture()
    climate.loc[climate.year.eq(2025),'tmean_apr_sep_c']-=10
    climate.loc[climate.year.eq(2025)&climate.era5_grid_id.eq('grid0'),'tmean_apr_sep_c']+=90
    p=module().make_protocols(c,climate)
    assert p.attrs['metadata']['warm_year']['annual_anomaly_c']['2025']==3
    # Two distinct grid groups in one degree block must have one spatial fold.
    c['sites'].loc[c['sites'].site.isin(['s2','s3']),'lat']=30.9
    p=module().make_protocols(c)
    for _,a in p[p.experiment.str.startswith('spatial_')].groupby('experiment'):
        selected=a.loc[a.site.isin(['s0','s1','s2','s3'])]
        assert selected.partition.nunique()==1
        assert selected.inner_fold.nunique()==1


def normals_fixture(tmp_path):
    import json
    c, climate = fixture()
    normals = pd.DataFrame([dict(era5_grid_id=f'grid{i}', **{
        f'tmean_month_{m:02d}_c': float(i + m) for m in range(1,13)}) for i in range(30)])
    path = tmp_path/'monthly_normals.csv'
    normals.to_csv(path,index=False)
    request = dict(normal_period=[1991,2020],temperature_input='RAW',units='degrees Celsius',
        collection='ECMWF/ERA5_LAND/MONTHLY_AGGR',band='temperature_2m')
    (tmp_path/'request.json').write_text(json.dumps(request))
    return c, climate, path


def test_monthly_normals_primary_and_unstratified_sensitivity_are_frozen(tmp_path):
    import json
    from model_run.factorial.cohort import file_hash
    c, climate, path = normals_fixture(tmp_path)
    legacy = module().make_protocols(c, climate)
    p = module().make_protocols(c, climate, monthly_normals=path)
    metadata = p.attrs['metadata']
    assert metadata['stratification'] == 'clustered_temperature_zones'
    assert metadata['publication_primary_design'] is True
    assert metadata['temperature_zones']['normal_period'] == [1991,2020]
    assert metadata['normal_input_hashes'][str(path.resolve())] == file_hash(path)
    assert metadata['normal_input_hashes'][str((tmp_path/'request.json').resolve())] == file_hash(tmp_path/'request.json')
    assert 'unstratified_site_holdout' in set(p.experiment)
    assert p.groupby('site').temperature_zone_id.nunique().max() == 1
    sensitivity = p[p.experiment.eq('unstratified_site_holdout')].drop(columns='temperature_zone_id')
    expected = legacy[legacy.experiment.eq('site_holdout')].assign(experiment='unstratified_site_holdout')
    pd.testing.assert_frame_equal(sensitivity.reset_index(drop=True), expected.reset_index(drop=True))
    primary = p[p.experiment.eq('site_holdout')].merge(c['sites'][['site','group_id']],on='site')
    for _, zone in primary.groupby('temperature_zone_id'):
        assert set(zone.partition) == {'calibration','test'}
        assert set(zone.loc[zone.partition.eq('calibration'),'inner_fold']) == {0,1,2,3}
    pd.testing.assert_frame_equal(p,module().make_protocols(c,climate,monthly_normals=path))
    assert json.loads(json.dumps(metadata)) == metadata
    assert legacy.attrs['metadata']['publication_primary_design'] is False


@pytest.mark.parametrize('key,value', [('normal_period',[1981,2010]),('temperature_input','DEM'),('units','kelvin')])
def test_monthly_normal_provenance_is_required_and_checked(tmp_path,key,value):
    import json
    c, _, path = normals_fixture(tmp_path)
    request_path = tmp_path/'request.json'
    request = json.loads(request_path.read_text())
    request[key] = value
    request_path.write_text(json.dumps(request))
    with pytest.raises(ValueError,match='normal|RAW|Celsius'):
        module().make_protocols(c,monthly_normals=path)
    request_path.unlink()
    with pytest.raises(ValueError,match='metadata|provenance'):
        module().make_protocols(c,monthly_normals=path)
