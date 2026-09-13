"""Matched temperature/ML benefits and interactions with equal-site group bootstrap.

Error is predicted minus observed calendar days. Benefits are RAW absolute
error minus DEM absolute error. Positive interaction means residual ML
increases the DEM benefit, on the four-arm attained-event intersection.
"""
import json

import numpy as np
import pandas as pd

FACTORS = ['experiment','partition','BBCH','model_name','ml_algorithm']
CONTINUOUS = ['site_minus_grid_elevation_m','abs_elevation_difference_m','dem_elevation_m',
              'slope_deg','northness','eastness','dem_local_std_m']


def _counts(frame):
    countries = frame[['site','country']].drop_duplicates().groupby('country').size().to_dict() if 'country' in frame else {}
    return dict(n_observations=len(frame),n_sites=frame.site.nunique(),n_groups=frame.group_id.nunique(),
                n_countries=len(countries),country_site_counts=json.dumps({str(k):int(v) for k,v in countries.items()},sort_keys=True))


def _bootstrap(site_values, column, n_bootstrap, rng, is_test):
    n_groups = site_values.group_id.nunique()
    out = dict(descriptive_only=(n_groups < 10 or not is_test), benefit_ci_low=np.nan,benefit_ci_high=np.nan)
    if out['descriptive_only'] or n_bootstrap <= 0:
        return out
    group = site_values.groupby('group_id')[column].agg(['sum','count'])
    sums, counts = group['sum'].to_numpy(),group['count'].to_numpy()
    draws = []
    # Sample entire independent groups. Repeated draws multiply all their sites;
    # denominators preserve equal-site weighting even for unequal group sizes.
    for start in range(0,n_bootstrap,128):
        weights = rng.multinomial(n_groups,np.full(n_groups,1/n_groups),size=min(128,n_bootstrap-start))
        draws.append((weights @ sums)/(weights @ counts))
    out['benefit_ci_low'],out['benefit_ci_high'] = np.quantile(np.concatenate(draws),[.025,.975]).tolist()
    return out


def _contrast(frame, column, n_bootstrap, rng, is_test):
    site = frame.groupby(['site','group_id'],as_index=False)[column].mean()
    return {**_counts(frame),'benefit_mae_days':float(site[column].mean()),
            'observation_benefit_mae_days':float(frame[column].mean()),
            **_bootstrap(site,column,n_bootstrap,rng,is_test)}


def _paired_ml(comparison, n_bootstrap, seed):
    """PBM minus TabM absolute error, retaining all arm and matched denominators."""
    comparison = comparison.assign(process_model=comparison.model_name.str.replace(r'-ML$','',regex=True))
    factors = ['experiment','partition','BBCH','process_model','temperature_input']
    rng = np.random.default_rng(seed)
    rows = []
    for key, frame in comparison.groupby(factors,sort=True,dropna=False):
        pbm = frame.loc[frame.ml_algorithm.eq('none')]
        ml = frame.loc[frame.ml_algorithm.eq('tabm')]
        if pbm.empty or ml.empty:
            continue
        matched = pbm.rename(columns={'error':'pbm_error'}).merge(
            ml[['observation_id','error']].rename(columns={'error':'tabm_error'}),
            on='observation_id',validate='one_to_one')
        paired = matched.loc[np.isfinite(matched.pbm_error)&np.isfinite(matched.tabm_error)].copy()
        paired['benefit'] = paired.pbm_error.abs()-paired.tabm_error.abs()
        n_pbm_attained, n_tabm_attained = int(np.isfinite(pbm.error).sum()), int(np.isfinite(ml.error).sum())
        rows.append({**dict(zip(factors,key)),
            'benefit_definition':'MAE_PBM_minus_MAE_TabM',
            'n_pbm_observations':len(pbm),'n_tabm_observations':len(ml),
            'n_pbm_attained':n_pbm_attained,'n_tabm_attained':n_tabm_attained,
            'n_pbm_unattained':len(pbm)-n_pbm_attained,'n_tabm_unattained':len(ml)-n_tabm_attained,
            'n_matched_observations':len(matched),'n_paired_observations':len(paired),
            **_contrast(paired,'benefit',n_bootstrap,rng,key[1]=='test')})
    return pd.DataFrame(rows)


def _terrain_rows(frame, factors, terrain_cuts, n_bootstrap, rng):
    result = []
    strata = [('abs_elevation_difference',frame.abs_elevation_difference_m.pipe(
        lambda s:pd.cut(s,[0,100,200,300,np.inf],right=False,labels=['0–<100','100–<200','200–<300','≥300'])).astype('string').fillna('missing'))]
    if terrain_cuts is not None:
        cuts = np.asarray(terrain_cuts,dtype=float)
        if cuts.shape != (2,) or not np.isfinite(cuts).all() or cuts[0] > cuts[1]:
            raise ValueError('terrain_cuts must be two ordered finite calibration tertiles')
        variability = pd.Series(np.where(frame.dem_local_std_m.le(cuts[0]),'low',
                    np.where(frame.dem_local_std_m.le(cuts[1]),'middle','high')),index=frame.index)
        variability = variability.where(frame.dem_local_std_m.notna(),'missing')
        strata += [('local_elevation_variability',variability),
                   ('elevation_difference_x_variability',strata[0][1]+' / '+variability)]
    is_test = factors['partition'] == 'test'
    for variable, labels in strata:
        for label, subset in frame.groupby(labels,sort=True):
            result.append({**factors,'analysis':'stratum','terrain_variable':variable,'terrain_stratum':str(label),
                           **_contrast(subset,'benefit',n_bootstrap,rng,is_test)})
    # Correlations use one paired mean benefit per site; no p-values or causal claims.
    site = frame.groupby(['site','group_id'],as_index=False).agg(
        benefit=('benefit','mean'),**{c:(c,'first') for c in CONTINUOUS})
    for variable in CONTINUOUS:
        finite = site.loc[np.isfinite(site[variable]) & np.isfinite(site.benefit)]
        x,y = finite[variable].to_numpy(),finite.benefit.to_numpy()
        valid = len(x) >= 3 and np.ptp(x) > 0 and np.ptp(y) > 0
        pearson = float(np.corrcoef(x,y)[0,1]) if valid else np.nan
        spearman = float(finite[[variable,'benefit']].rank().corr().iloc[0,1]) if valid else np.nan
        slope = float(np.sum((x-x.mean())*(y-y.mean()))/np.sum((x-x.mean())**2)) if valid else np.nan
        result.append({**factors,'analysis':'continuous_descriptive_association','terrain_variable':variable,
                       'terrain_stratum':'all','n_sites':len(finite),'n_groups':finite.group_id.nunique(),
                       'descriptive_only':True,'pearson_r':pearson,'spearman_r':spearman,'slope_days_per_unit':slope})
    return result


def evaluate_comparison(comparison, sites, *, n_bootstrap=2000, seed=20260909, terrain_cuts=None):
    """Evaluate observation and site-balanced errors without dropping nonattainments.

    Error metrics use attained events; attainment retains every supplied event
    as denominator. Paired contrasts use finite matched events only. Confidence
    intervals use 2.5/97.5 percentiles of independent-group resampling and are
    omitted below ten groups. Terrain tertiles must come from calibration sites.
    """
    if n_bootstrap < 0:
        raise ValueError('n_bootstrap must be nonnegative')
    c = comparison.copy()
    required = {'observation_id','site','season','BBCH','observed_date','predicted_date',
                'model_name','temperature_input','ml_algorithm','partition','group_id','experiment'}
    missing = required - set(c.columns)
    if missing:
        raise ValueError(f'Missing comparison fields: {sorted(missing)}')
    if sites.site.duplicated().any():
        raise ValueError('Duplicate terrain sites')
    c['BBCH'] = c.BBCH.astype(str).str.zfill(2)
    keys = ['experiment','partition','observation_id','model_name','temperature_input','ml_algorithm']
    if c.duplicated(keys).any():
        raise ValueError('Duplicate model-arm observation keys')
    if not set(c.temperature_input).issubset({'RAW','DEM'}) or not set(c.ml_algorithm).issubset({'none','tabm'}):
        raise ValueError('Unknown temperature or ML arm')
    if not set(c.site).issubset(set(sites.site)):
        raise ValueError('Missing site terrain')
    if 'group_id' in sites:
        canonical = c.site.map(sites.set_index('site').group_id)
        grouping = c[['experiment','site','group_id']].assign(canonical_group=canonical)
        if grouping.groupby(['experiment','canonical_group']).group_id.nunique().gt(1).any():
            raise ValueError('Comparison group splits a canonical independence group')
    invariant = ['site','season','BBCH','observed_date']
    if c.groupby('observation_id')[invariant].nunique(dropna=False).gt(1).any().any():
        raise ValueError('Observation identity differs between arms')
    if c.groupby(['experiment','observation_id']).group_id.nunique(dropna=False).gt(1).any():
        raise ValueError('Observation group identity differs between arms')
    c['observed_date'] = pd.to_datetime(c.observed_date,errors='raise')
    c['predicted_date'] = pd.to_datetime(c.predicted_date,errors='coerce')
    if c.observed_date.isna().any():
        raise ValueError('Missing observed date')
    c['error'] = (c.predicted_date-c.observed_date).dt.total_seconds()/86400
    terrain_columns = ['country',*CONTINUOUS]
    terrain = sites.copy()
    if 'site_minus_grid_elevation_m' not in terrain:
        terrain['site_minus_grid_elevation_m'] = np.nan
    terrain['abs_elevation_difference_m'] = terrain.site_minus_grid_elevation_m.abs()
    for column in terrain_columns:
        if column not in terrain:
            terrain[column] = 'unknown' if column == 'country' else np.nan
    c = c.drop(columns=[col for col in terrain_columns if col in c]).merge(terrain[['site',*terrain_columns]],on='site',validate='many_to_one')
    rng = np.random.default_rng(seed)
    metrics, paired_rows, terrain_rows, interactions = [],[],[],[]
    for key,frame in c.groupby([*FACTORS,'temperature_input'],sort=True,dropna=False):
        factors = dict(zip([*FACTORS,'temperature_input'],key))
        finite = frame.loc[np.isfinite(frame.error)].copy()
        finite['absolute_error'],finite['squared_error'] = finite.error.abs(),finite.error**2
        site = finite.groupby('site')[['error','absolute_error','squared_error']].mean()
        attainment_site = frame.assign(attained=np.isfinite(frame.error)).groupby('site').attained.mean()
        metrics.append({**factors,**_counts(frame),'n_attained':len(finite),'n_attained_sites':len(site),
            'attainment':float(len(finite)/len(frame)),'site_attainment':float(attainment_site.mean()),
            'mae_days':float(finite.absolute_error.mean()),'rmse_days':float(np.sqrt(finite.squared_error.mean())),
            'bias_days':float(finite.error.mean()),'site_mae_days':float(site.absolute_error.mean()),
            'site_rmse_days':float(np.sqrt(site.squared_error.mean())),'site_bias_days':float(site.error.mean())})
    paired_frames = []
    for key,frame in c.groupby(FACTORS,sort=True,dropna=False):
        factors = dict(zip(FACTORS,key))
        raw = frame.loc[frame.temperature_input.eq('RAW')].drop(columns='temperature_input')
        dem = frame.loc[frame.temperature_input.eq('DEM'),['observation_id','error']].rename(columns={'error':'dem_error'})
        pair = raw.rename(columns={'error':'raw_error'}).merge(dem,on='observation_id',validate='one_to_one')
        pair = pair.loc[np.isfinite(pair.raw_error)&np.isfinite(pair.dem_error)].copy()
        if pair.empty:
            paired_rows.append({**factors,**_counts(pair),'benefit_mae_days':np.nan,
                'observation_benefit_mae_days':np.nan,'benefit_ci_low':np.nan,'benefit_ci_high':np.nan,'descriptive_only':True})
            continue
        pair['benefit'] = pair.raw_error.abs()-pair.dem_error.abs()
        paired_frames.append(pair)
        paired_rows.append({**factors,**_contrast(pair,'benefit',n_bootstrap,rng,factors['partition']=='test')})
        terrain_rows.extend(_terrain_rows(pair,factors,terrain_cuts,n_bootstrap,rng))
    # Interactions always match all four arms; model_name suffix is distinct from T.
    if paired_frames:
        all_pairs = pd.concat(paired_frames,ignore_index=True)
        all_pairs['process_model'] = all_pairs.model_name.str.replace(r'-ML$','',regex=True)
        by = ['experiment','partition','BBCH','process_model']
        for key,frame in all_pairs.groupby(by,sort=True):
            factors = dict(zip(by,key))
            pbm = frame.loc[frame.ml_algorithm.eq('none')]
            ml = frame.loc[frame.ml_algorithm.eq('tabm'),['observation_id','benefit']].rename(columns={'benefit':'ml_benefit'})
            four = pbm.merge(ml,on='observation_id',validate='one_to_one')
            if four.empty:
                continue
            four['interaction'] = four.ml_benefit-four.benefit
            contrast = _contrast(four,'interaction',n_bootstrap,rng,factors['partition']=='test')
            contrast['interaction_days'] = contrast.pop('benefit_mae_days')
            contrast['observation_interaction_days'] = contrast.pop('observation_benefit_mae_days')
            contrast['interaction_ci_low'] = contrast.pop('benefit_ci_low')
            contrast['interaction_ci_high'] = contrast.pop('benefit_ci_high')
            interactions.append({**factors,**contrast})
    result = dict(metrics=pd.DataFrame(metrics),paired_temperature=pd.DataFrame(paired_rows),
                  terrain=pd.DataFrame(terrain_rows),interaction=pd.DataFrame(interactions),
                  paired_ml=_paired_ml(c,n_bootstrap,seed))
    for frame in result.values():
        frame.attrs['metadata'] = dict(error='predicted_minus_observed_days',benefit='MAE_RAW_minus_MAE_DEM',
          interaction='DEM_benefit_with_ML_minus_DEM_benefit_without_ML',bootstrap_unit='independent_group',
          n_bootstrap=n_bootstrap,seed=seed,terrain_cuts=list(terrain_cuts) if terrain_cuts is not None else None)
    result['paired_ml'].attrs['metadata']['benefit'] = 'MAE_PBM_minus_MAE_TabM'
    return result
