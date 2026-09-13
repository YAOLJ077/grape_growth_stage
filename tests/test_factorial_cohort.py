import importlib
import json
import hashlib
import numpy as np
import pandas as pd
import pytest


def module():
    try:
        return importlib.import_module('model_run.factorial.cohort')
    except ModuleNotFoundError:
        pytest.fail('Factorial cohort module missing')


def inputs(tmp_path):
    obs = pd.DataFrame([['A','v','FR','45','5',d,'07'] for d in ['2025-04-01','2025-04-02','2026-04-01']], columns=['site','variety','country','lat','lon','Date','BBCH'])
    obs.to_csv(tmp_path/'obs.csv', index=False)
    terrain = pd.DataFrame(dict(site=['A'],weather_uid=['A'],filename=['A.csv'],lat=[45.],lon=[5.],era5_grid_id=['g1'],dem_elevation_m=[200.],era5_grid_elevation_m=[100.],site_minus_grid_elevation_m=[100.],slope_deg=[1.],northness=[1.],eastness=[0.],dem_local_std_m=[10.],terrain_status=['complete']))
    terrain.to_csv(tmp_path/'terrain.csv',index=False)
    (tmp_path/'weather').mkdir()
    pd.DataFrame(dict(Date=pd.date_range('2024-06-04','2025-12-31'),Tmean=10.,Tmean_DEM=9.35)).to_csv(tmp_path/'weather/A.csv',index=False)
    return obs,terrain


def test_only_incomplete_season_excluded_repetitions_hashes_preserved(tmp_path):
    obs,_ = inputs(tmp_path)
    c = module().prepare_cohort(tmp_path/'obs.csv',tmp_path/'weather',tmp_path/'terrain.csv')
    assert len(c['observations']) == 2
    assert c['observations'].season.tolist() == [2025,2025]
    literal = hashlib.sha256(json.dumps(obs.iloc[0].tolist(),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    assert c['observations'].observation_id.iloc[0] == literal
    audit=c['eligibility'].set_index('season')
    assert audit.loc[2025,'eligible']
    assert not audit.loc[2026,'eligible']
    assert 'weather' in audit.loc[2026,'reason']
    module().save_cohort(c,tmp_path/'saved')
    loaded=module().load_cohort(tmp_path/'saved')
    pd.testing.assert_frame_equal(c['observations'],loaded['observations'])
    with (tmp_path/'saved/sites.csv').open('a') as f: f.write('\n')
    with pytest.raises(ValueError,match='hash'):
        module().load_cohort(tmp_path/'saved')


def test_coordinate_mismatch_and_dem_equation_have_explicit_exclusions(tmp_path):
    _,terrain=inputs(tmp_path)
    terrain['lat']=46.
    terrain.to_csv(tmp_path/'terrain.csv',index=False)
    c=module().prepare_cohort(tmp_path/'obs.csv',tmp_path/'weather',tmp_path/'terrain.csv')
    assert c['observations'].empty
    assert c['eligibility'].reason.str.contains('coordinate').all()
    terrain['lat']=45.
    terrain.to_csv(tmp_path/'terrain.csv',index=False)
    w=pd.read_csv(tmp_path/'weather/A.csv'); w['Tmean_DEM']=10.;w.to_csv(tmp_path/'weather/A.csv',index=False)
    c=module().prepare_cohort(tmp_path/'obs.csv',tmp_path/'weather',tmp_path/'terrain.csv')
    assert c['eligibility'].reason.str.contains('dem_equation').all()


def test_transitive_independence_groups():
    sites=pd.DataFrame(dict(site=list('ABCD'),lat=[45,45.00001,46,47],lon=[5,5.00001,6,7],era5_grid_id=['g1','g2','g2','g3']))
    grouped=module().assign_groups(sites)
    assert grouped.group_id.iloc[:3].nunique()==1
    assert grouped.group_id.nunique()==2


def test_missing_terrain_site_is_audited_without_dropping_others(tmp_path):
    obs,_=inputs(tmp_path)
    extra=obs.iloc[[0]].assign(site='missing',variety='')
    pd.concat([obs,extra]).to_csv(tmp_path/'obs.csv',index=False)
    c=module().prepare_cohort(tmp_path/'obs.csv',tmp_path/'weather',tmp_path/'terrain.csv')
    assert c['eligibility'].query("site == 'missing'").reason.tolist()==['missing_terrain']
    assert c['observations'].site.tolist()==['A','A']


def test_exact_coordinate_parser_preserves_source_precision_and_frozen_values(tmp_path):
    obs, terrain = inputs(tmp_path)
    coordinate = '0.30000000000000004'
    obs['lon'] = coordinate
    terrain['lon'] = coordinate
    obs.to_csv(tmp_path/'obs.csv',index=False)
    terrain.to_csv(tmp_path/'terrain.csv',index=False)
    c = module().prepare_cohort(tmp_path/'obs.csv',tmp_path/'weather',tmp_path/'terrain.csv')
    assert len(c['observations']) == 2
    assert c['observations'].lon.tolist() == [coordinate,coordinate]
    assert c['sites'].lon.iloc[0] == float(coordinate)
    assert c['sites'].lon_source.iloc[0] == coordinate
    assert c['sites'].lat_source.iloc[0] == '45.0'
    module().save_cohort(c,tmp_path/'saved')
    restored = module().load_cohort(tmp_path/'saved')
    pd.testing.assert_frame_equal(c['sites'],restored['sites'],check_exact=True)


def test_distinct_python_float_coordinates_never_match_via_parser_rounding(tmp_path):
    obs, terrain = inputs(tmp_path)
    obs['lon'] = '0.30000000000000004'
    terrain['lon'] = '0.3'
    obs.to_csv(tmp_path/'obs.csv',index=False)
    terrain.to_csv(tmp_path/'terrain.csv',index=False)
    c = module().prepare_cohort(tmp_path/'obs.csv',tmp_path/'weather',tmp_path/'terrain.csv')
    assert c['observations'].empty
    assert c['eligibility'].reason.eq('coordinate_mismatch').all()


def test_invalid_coordinate_is_audited_with_python_float_parser(tmp_path):
    obs, _ = inputs(tmp_path)
    obs['lat'] = 'invalid'
    obs.to_csv(tmp_path/'obs.csv',index=False)
    c = module().prepare_cohort(tmp_path/'obs.csv',tmp_path/'weather',tmp_path/'terrain.csv')
    assert c['observations'].empty
    assert c['eligibility'].reason.eq('coordinate_mismatch').all()
