"""Recompute plotted results from the packaged locked scoring-error cube.

Saved summary tables serve as regression references. Bootstrap seeds, finite
masks, fixed-model/site/stage weighting and sparse-group rules are unchanged.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from common import DATA,MODELS,STAGES
from group_bootstrap import summarise


def compare(actual,reference,keys,folder):
    saved=pd.read_csv(DATA/reference,dtype={'BBCH':str})
    columns=[c for c in ['value','ci_low','ci_high','ci_status','n_observations','n_sites','n_groups']
             if c in saved and c in actual]
    a=actual.sort_values(keys).reset_index(drop=True)
    b=saved.sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(a[keys+columns],b[keys+columns],check_dtype=False,check_exact=False,rtol=1e-9,atol=1e-9)
    out=folder/reference;out.parent.mkdir(parents=True,exist_ok=True);actual.to_csv(out,index=False)
    return {'table':reference,'rows':len(actual),'matched_columns':keys+columns,'verified':True}


def recompute(folder):
    folder=Path(folder);folder.mkdir(exist_ok=True)
    identities=pd.read_csv(DATA/'predictions/identity.csv.gz',dtype={'site':str,'group_id':str,'BBCH':str})
    cube=np.load(DATA/'predictions/scoring_errors.npz')['errors']
    assert cube.shape==(74618,10,4) and len(identities)==74618
    assert identities.observation_id.is_monotonic_increasing and identities.observation_id.is_unique
    report=[]
    print('Recomputing process/hybrid scoring MAE, RMSE and bias',flush=True)
    expected_pbm=pd.concat([pd.read_csv(DATA/'pbm'/n,dtype={'BBCH':str}) for n in ['stage_metrics.csv','overall_metrics.csv']])
    expected_hybrid=pd.read_csv(DATA/'hybrid/stage_metrics.csv',dtype={'BBCH':str})
    metric_rows=[]
    for j,model in enumerate(MODELS):
        for arm,(temperature,method) in enumerate([('RAW','process'),('RAW','tabm'),('DEM','process'),('DEM','tabm')]):
            for part in ['calibration','test']:
                mask=identities.partition.eq(part).to_numpy()
                d=identities.loc[mask,['site','BBCH']].copy();e=cube[mask,j,arm]
                d['abs']=abs(e);d['mse']=e**2;d['bias']=e
                site=d.groupby(['site','BBCH'])[['abs','mse','bias']].mean()
                stage=site.groupby('BBCH').mean().reindex(STAGES)
                stage.loc['ALL']=stage.mean()
                source=expected_pbm if method=='process' else expected_hybrid
                source=source[source.model.eq(model)&source.temperature.eq(temperature)&source.partition.eq(part)&source.metric_view.eq('scoring')]
                if method=='tabm':source=source[source.method.eq('tabm')]
                for s,r in stage.iterrows():
                    expected=source[source.BBCH.eq(s)]
                    if len(expected)==0 and s=='ALL':continue
                    assert len(expected)==1
                    values=[r['abs'],np.sqrt(r['mse']),r['bias']]
                    np.testing.assert_allclose(values,expected[['mae_days','rmse_days','bias_days']].iloc[0].to_numpy(float),atol=1e-9)
                    metric_rows.append(dict(model=model,temperature=temperature,method=method,partition=part,BBCH=s,
                        mae_days=values[0],rmse_days=values[1],bias_days=values[2]))
    pd.DataFrame(metric_rows).to_csv(folder/'scoring_metrics.csv',index=False)
    report.append({'table':'process/hybrid scoring metrics','rows':len(metric_rows),'verified':True})
    test=identities.partition.eq('test').to_numpy();base=identities[test].reset_index(drop=True);errors=cube[test]
    info=pd.read_csv(DATA/'environment/environmental_zone_sites.csv',usecols=['site','lat','lon'],dtype={'site':str})
    base=base.merge(info,on='site',validate='many_to_one',sort=False)
    print('Recomputing controlled structure contrasts and site/zone summaries',flush=True)
    pairs=pd.read_csv(DATA/'structure/controlled_pairs.csv');summaries=[]
    for family,left,right in [('forcing_response','FL','FB'),('chilling_response','CL','CB'),('interaction','S','P'),('chilling_addition','F','C + F')]:
        pp=pairs[pairs.family.eq(family)]
        li=[MODELS.index(m) for m in pp.left_model];ri=[MODELS.index(m) for m in pp.right_model]
        common=np.isfinite(errors[:,sorted(set(li+ri)),0]).all(1)
        d=base[common].copy();e=errors[common,:,0];columns=[]
        for arm,ii in [('left',li),('right',ri)]:
            for metric,values in [('abs',abs(e[:,ii])),('mse',e[:,ii]**2),('bias',e[:,ii])]:
                col=f'{arm}_{metric}';d[col]=values.mean(1);columns.append(col)
        summaries.append(summarise(d,columns).assign(family=family,left=left,right=right,n_pairs=len(pp)))
    report.append(compare(pd.concat(summaries),'structure/function_performance.csv',['family','BBCH','metric'],folder))
    best=base.copy();best['error']=errors[:,MODELS.index('CB-FL-S'),0]
    best['abs_error']=best.error.abs();best['mse']=best.error**2
    mapped=best.groupby(['site','BBCH','group_id','temperature_zone_id','lat','lon'],dropna=False).agg(
        mae_days=('abs_error','mean'),mse=('mse','mean'),bias_days=('error','mean'),
        n_observations=('observation_id','size'),n_scored=('error','count')).reset_index()
    mapped['rmse_days']=np.sqrt(mapped.mse)
    saved=pd.read_csv(DATA/'structure/cb_fl_s_site_metrics.csv',dtype={'BBCH':str,'group_id':str})
    pd.testing.assert_frame_equal(mapped,saved,check_dtype=False,check_exact=False,atol=1e-9,rtol=1e-9)
    mapped.to_csv(folder/'structure/cb_fl_s_site_metrics.csv',index=False)
    zones=[]
    for zone in sorted(base.temperature_zone_id.unique()):
        d=best[best.temperature_zone_id.eq(zone)&best.error.notna()]
        zones.append(summarise(d,['abs_error','mse','error']).assign(temperature_zone_id=zone))
    report.append(compare(pd.concat(zones),'structure/cb_fl_s_zone_metrics.csv',['temperature_zone_id','BBCH','metric'],folder))
    print('Recomputing paired DEM benefits and terrain/zone intervals',flush=True)
    strata=pd.read_csv(DATA/'dem/site_strata.csv',dtype={'site':str,'group_id':str})
    cuts=json.loads((DATA/'dem/analysis.json').read_text())['terrain_cuts']
    for col,rule in cuts.items():
        bounds=strata.loc[strata.partition.eq('calibration'),col].dropna().quantile([1/3,2/3],interpolation='linear').to_numpy()
        np.testing.assert_allclose(bounds,rule['cutpoints'],atol=1e-9)
        actual=np.where(strata[col].isna(),'missing',np.where(strata[col]<=bounds[0],'low',np.where(strata[col]<=bounds[1],'middle','high')))
        assert (actual==strata[col+'_class']).all()
    extra=[c for c in strata if c.endswith('_class')]
    dem_base=base.merge(strata[['site',*extra]],on='site',validate='many_to_one',sort=False)
    dem_errors=errors[:,:,[0,2]];common=np.isfinite(dem_errors).all((1,2))
    def dem_metrics(b,e):
        d=b.copy()
        for j,arm in enumerate(['raw','dem']):
            d[arm+'_abs']=abs(e[:,:,j]).mean(1);d[arm+'_mse']=(e[:,:,j]**2).mean(1);d[arm+'_bias']=e[:,:,j].mean(1)
        d['benefit']=d.raw_abs-d.dem_abs;d['bias_change']=d.dem_bias-d.raw_bias
        return d
    columns=['raw_abs','dem_abs','raw_mse','dem_mse','raw_bias','dem_bias','benefit','bias_change']
    d=dem_metrics(dem_base[common],dem_errors[common]);model_rows=[]
    for j,m in enumerate(MODELS):
        for cohort,mask in [('common_all_twenty',common),('model_specific_pair',np.isfinite(dem_errors[:,j,:]).all(1))]:
            model_rows.append(summarise(dem_metrics(dem_base[mask],dem_errors[mask,j:j+1]),columns).assign(model=m,cohort=cohort))
    report.append(compare(pd.concat(model_rows),'dem/model_effects.csv',['cohort','model','BBCH','metric'],folder))
    expected=pd.read_csv(DATA/'dem/paired_effects.csv',dtype={'BBCH':str});rows=[]
    for stratum,level in expected[['stratum','level']].drop_duplicates().itertuples(index=False,name=None):
        if stratum=='all':selected=d
        elif stratum.endswith('_by_mismatch'):
            x,y=level.split('|');selected=d[d[stratum[:-len('_by_mismatch')]].eq(x)&d.absolute_elevation_mismatch_m_class.eq(y)]
        else:selected=d[d[stratum].eq(level)]
        rows.append(summarise(selected,columns).assign(analysis='all_models',stratum=stratum,level=level))
    report.append(compare(pd.concat(rows),'dem/paired_effects.csv',['stratum','level','BBCH','metric'],folder))
    print('Recomputing ML and hybrid-DEM gains with 2,000 group-bootstrap draws',flush=True)
    zone_rows=[];model_rows=[];support=[]
    for comparison,indices in [('ML_RAW',[0,1]),('DEM_ML',[1,3])]:
        common=np.isfinite(errors[:,:,indices]).all((1,2));b=base[common].copy();pair=abs(errors[common][:,:,indices])
        d=b.copy();d['baseline_mae']=pair[:,:,0].mean(1);d['hybrid_mae']=pair[:,:,1].mean(1);d['gain']=d.baseline_mae-d.hybrid_mae
        columns=['baseline_mae','hybrid_mae','gain']
        zone_rows.append(summarise(d,columns).assign(comparison=comparison,zone='ALL'))
        for zone in sorted(base.temperature_zone_id.unique()):
            zone_rows.append(summarise(d[d.temperature_zone_id.eq(zone)],columns).assign(comparison=comparison,zone=zone.replace('TZ','EZ')))
        for j,m in enumerate(MODELS):
            single=b.copy();single['baseline_mae']=pair[:,j,0];single['hybrid_mae']=pair[:,j,1];single['gain']=single.baseline_mae-single.hybrid_mae
            model_rows.append(summarise(single,columns).assign(comparison=comparison,model=m))
        for s in STAGES:
            g=d[d.BBCH.eq(s)];ss=g.groupby('site').gain.mean()
            support.append(dict(comparison=comparison,BBCH=s,n_eligible=int(base.BBCH.eq(s).sum()),n_common=len(g),n_sites=g.site.nunique(),n_groups=g.group_id.nunique(),
                n_sites_improved=int(ss.gt(0).sum()),n_sites_worsened=int(ss.lt(0).sum()),n_sites_unchanged=int(ss.eq(0).sum())))
    report.append(compare(pd.concat(zone_rows),'ml/zone_effects.csv',['comparison','zone','BBCH','metric'],folder))
    report.append(compare(pd.concat(model_rows),'ml/model_effects.csv',['comparison','model','BBCH','metric'],folder))
    a=pd.DataFrame(support);b=pd.read_csv(DATA/'ml/support.csv',dtype={'BBCH':str})
    pd.testing.assert_frame_equal(a,b,check_dtype=False);a.to_csv(folder/'ml/support.csv',index=False)
    report.append({'table':'ml/support.csv','rows':len(a),'all_counts_recomputed':True})
    return report
