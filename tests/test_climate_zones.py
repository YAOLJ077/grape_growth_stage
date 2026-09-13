"""Temperature-only strata and independent-group validation invariants."""
import importlib
import json

import numpy as np
import pandas as pd
import pytest

MONTHS = [f'tmean_month_{month:02d}_c' for month in range(1, 13)]


def module():
    try:
        return importlib.import_module('model_run.factorial.climate_zones')
    except ModuleNotFoundError:
        pytest.fail('Temperature-zone validation module missing')


def fixture(n=50):
    sites = pd.DataFrame([dict(site=f's{i:03}', group_id=f'g{i:03}',
                               era5_grid_id=f'grid{i:03}') for i in range(n)])
    profiles = pd.DataFrame([dict(era5_grid_id=f'grid{i:03}', **{
        col: float((i // 10) * 10 + i % 10 / 20 + np.sin(m / 12 * 2 * np.pi))
        for m, col in enumerate(MONTHS)}) for i in range(n)])
    obs = pd.DataFrame([dict(site=s, BBCH=b, Date='2000-06-01')
                        for s in sites.site for b in ('07', '65', '81', '89')])
    return sites, profiles, obs


def test_climate_fit_is_invariant_to_source_site_multiplicity_and_row_order():
    sites, profiles, _ = fixture()
    zones, metadata = module().cluster_temperature_zones(sites, profiles)
    duplicates = pd.concat([sites.iloc[[0]].assign(site=f'alias{i}') for i in range(50)])
    repeated, repeated_metadata = module().cluster_temperature_zones(
        pd.concat([sites, duplicates]).sample(frac=1, random_state=4),
        profiles.sample(frac=1, random_state=5))
    assert metadata['cluster_centers_standardized'] == repeated_metadata['cluster_centers_standardized']
    assert metadata['scaler_mean_c'] == repeated_metadata['scaler_mean_c']
    assert metadata['n_clusters'] == 5
    expected = zones.set_index('site').temperature_zone_id
    pd.testing.assert_series_equal(expected, repeated.set_index('site').loc[expected.index].temperature_zone_id)
    assert repeated.loc[repeated.group_id.eq('g000'), 'temperature_zone_id'].nunique() == 1
    centers = np.array(metadata['cluster_centers_c'])
    assert np.all(np.diff(centers.mean(axis=1)) >= 0)
    json.dumps(metadata, allow_nan=False)


def test_spanning_groups_receive_one_zone_and_sparse_clusters_reduce():
    sites, profiles, _ = fixture(20)
    sites.loc[sites.site.eq('s019'), 'group_id'] = 'g000'
    zones, metadata = module().cluster_temperature_zones(sites, profiles)
    assert zones.groupby('group_id').temperature_zone_id.nunique().max() == 1
    assert zones.groupby('temperature_zone_id').group_id.nunique().min() >= 5
    assert metadata['n_clusters'] < 5
    assert metadata['group_profile_weight_unit'] == 'unique_era5_grid'


def test_outer_split_and_folds_keep_groups_and_all_four_stages():
    sites, profiles, obs = fixture()
    sites = pd.concat([sites, sites.iloc[[0]].assign(site='alias')], ignore_index=True)
    obs = pd.concat([obs, obs.loc[obs.site.eq('s000')].assign(site='alias')], ignore_index=True)
    zones, _ = module().cluster_temperature_zones(sites, profiles)
    test = module().split_temperature_groups(zones, obs)
    assert test == module().split_temperature_groups(zones.sample(frac=1, random_state=4), obs)
    train = zones.loc[~zones.group_id.isin(test)]
    assert 0.15 <= zones.group_id.isin(test).mean() <= 0.25
    for _, zone in zones.groupby('temperature_zone_id'):
        assert zone.group_id.isin(test).any()
        assert zone.loc[~zone.group_id.isin(test)].group_id.nunique() >= 4
    mapping = module().assign_temperature_folds(train, obs)
    assert set(mapping) == set(train.group_id)
    assert mapping == module().assign_temperature_folds(train.sample(frac=1, random_state=2), obs)
    for _, zone in train.groupby('temperature_zone_id'):
        assert set(zone.group_id.map(mapping)) == {0, 1, 2, 3}
    for fold in range(4):
        fold_sites = set(train.loc[train.group_id.map(mapping).eq(fold), 'site'])
        assert set(obs.loc[obs.site.isin(fold_sites), 'BBCH']) == {'07', '65', '81', '89'}
    assert test == module().split_temperature_groups(zones, obs.assign(Date='1900-01-01', country='XX'))
    assert mapping == module().assign_temperature_folds(train, obs.assign(Date='1900-01-01'))


def test_sparse_stage_support_is_distributed_without_using_dates():
    sites, profiles, obs = fixture(30)
    zones, _ = module().cluster_temperature_zones(sites, profiles)
    obs = obs.loc[obs.BBCH.ne('89') | obs.site.isin([f's{i:03}' for i in range(5)])]
    test = module().split_temperature_groups(zones, obs)
    assert len(test.intersection({f'g{i:03}' for i in range(5)})) == 1
    train = zones.loc[~zones.group_id.isin(test)]
    folds = module().assign_temperature_folds(train, obs)
    assert {folds[f'g{i:03}'] for i in range(5) if f'g{i:03}' not in test} == {0, 1, 2, 3}


def test_impossible_sparse_inputs_fail_explicitly():
    sites, profiles, obs = fixture(4)
    with pytest.raises(ValueError, match='five|5'):
        module().cluster_temperature_zones(sites, profiles)
    sites, profiles, obs = fixture(20)
    zones, _ = module().cluster_temperature_zones(sites, profiles)
    sparse = obs.loc[obs.BBCH.ne('89') | obs.site.isin(['s000', 's001', 's002'])]
    with pytest.raises(ValueError, match='stage|BBCH'):
        module().split_temperature_groups(zones, sparse)
    with pytest.raises(ValueError, match='stage|BBCH'):
        module().assign_temperature_folds(zones, sparse)


@pytest.mark.parametrize('bad_kind', ['missing_grid', 'nonfinite', 'duplicate_grid', 'split_grid'])
def test_invalid_profiles_or_independence_fail(bad_kind):
    sites, profiles, _ = fixture()
    if bad_kind == 'missing_grid':
        profiles = profiles.iloc[1:]
    elif bad_kind == 'nonfinite':
        profiles.loc[0, MONTHS[2]] = np.nan
    elif bad_kind == 'duplicate_grid':
        profiles = pd.concat([profiles, profiles.iloc[[0]]])
    else:
        sites.loc[1, 'era5_grid_id'] = sites.loc[0, 'era5_grid_id']
    with pytest.raises(ValueError):
        module().cluster_temperature_zones(sites, profiles)
