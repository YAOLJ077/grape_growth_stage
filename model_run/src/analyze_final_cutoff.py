#!/usr/bin/env python3
"""Verified final PBM → DEM terrain effects → TabM analysis of a complete run.

Usage: python model_run/src/analyze_final_cutoff.py RUN_DIR --sites COHORT/sites.csv
Publication output is refused for incomplete or smoke runs. Fitted inputs are read only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import Normalize, TwoSlopeNorm
import numpy as np
import pandas as pd

from model_run.src.report_cutoff_ml import MODELS, STAGES, METHODS, PANELS, collect, require, sha256

IDENTITY = ['site', 'BBCH', 'Date', 'partition', 'group_id', 'temperature_zone_id', 'country']
TERRAIN = ['dem_local_std_m', 'site_minus_grid_elevation_m']
STRATA = ['terrain_complexity', 'elevation_mismatch', 'temperature_zone_id', 'country']
METRICS = ['mae_days', 'rmse_days', 'bias_days']
CONTRASTS = {
    'DEM_process': (('RAW', 'process'), ('DEM', 'process')),
    'DEM_tabm': (('RAW', 'tabm'), ('DEM', 'tabm')),
    'ML_RAW': (('RAW', 'process'), ('RAW', 'tabm')),
    'ML_DEM': (('DEM', 'process'), ('DEM', 'tabm')),
}


def validate_final_run(run: Path):
    """Publication gating is separate from fixture-level numerical functions."""
    status_bytes = (run / 'status.json').read_bytes()
    status = json.loads(status_bytes)
    require(status.get('smoke') is False, 'Publication refuses smoke or unspecified-smoke runs')
    require(status.get('complete') is True, 'Publication requires a complete run')
    expected = {f'{m}/{t}' for m, t in itertools.product(MODELS, ['RAW', 'DEM'])}
    units = status.get('completed', [])
    require(status.get('expected') == 20 and len(units) == 20 and set(units) == expected,
            'Publication requires all 20 model/temperature units')
    require(status.get('final_sources_verified') is True, 'Final source verification is required')
    require(not status.get('failed') and not status.get('active'), 'Final run is failed or still active')
    run_bytes = (run / 'run.json').read_bytes()
    config = json.loads(run_bytes)
    require(config.get('smoke') is False and set(config.get('models', [])) == set(MODELS)
            and set(config.get('temperatures', [])) == {'RAW', 'DEM'}, 'Run catalogue is not final production')
    require(len(config['models']) == 10 and len(config['temperatures']) == 2,
            'Duplicate production catalogue entries')
    return status, config, {'status.json': hashlib.sha256(status_bytes).hexdigest(),
                            'run.json': hashlib.sha256(run_bytes).hexdigest()}


def terrain_strata(site_population: pd.DataFrame):
    """Freeze global empirical tertiles on distinct calibration sites only."""
    require(not site_population.site.duplicated().any(), 'Terrain population must contain one row per site')
    result = site_population.copy()
    for col in TERRAIN:
        result[col] = pd.to_numeric(result[col], errors='raise')
        require(not np.isinf(result[col]).any(), f'Infinite terrain value: {col}')
    require(result.dem_local_std_m.dropna().ge(0).all(), 'Negative local terrain variability')
    result['absolute_elevation_mismatch_m'] = result.site_minus_grid_elevation_m.abs()
    definitions = {}
    for source, target in [('dem_local_std_m', 'terrain_complexity'),
                           ('absolute_elevation_mismatch_m', 'elevation_mismatch')]:
        values = result.loc[result.partition.eq('calibration'), source].dropna()
        bounds = np.quantile(values, [1/3, 2/3], method='linear') if len(values) else np.array([np.nan, np.nan])
        labels = np.full(len(result), 'NA', dtype=object)
        finite = result[source].notna().to_numpy()
        if len(values):
            labels[finite] = np.where(result.loc[finite, source].to_numpy() <= bounds[0], 'low',
                                     np.where(result.loc[finite, source].to_numpy() <= bounds[1], 'middle', 'high'))
        result[target] = labels
        definitions[source] = dict(output_column=target, cutpoints=bounds.tolist(), units='m',
            calibration_sites=int(len(values)), missing_calibration_sites=int(
                (result.partition.eq('calibration') & result[source].isna()).sum()),
            quantile_method='linear', quantiles=[1/3, 2/3],
            definition='low: x <= q1; middle: q1 < x <= q2; high: x > q2; NA: missing x or unavailable calibration cutpoints',
            repeated_boundaries='Retained exactly; tied cutpoints can yield an empty middle stratum',
            population='One equally weighted record per distinct calibration site; common cutpoints for all partitions and regions')
    return result, definitions


def match_predictions(baseline: pd.DataFrame, candidate: pd.DataFrame):
    """Require exact observation identity before creating a common finite pair."""
    for frame in [baseline, candidate]:
        require(not frame.observation_id.duplicated().any(), 'Duplicate observation identity in comparison')
        require(frame.observation_id.notna().all(), 'Missing observation identity')
    require(set(baseline.observation_id) == set(candidate.observation_id), 'Comparison population differs')
    left = baseline.set_index('observation_id')
    right = candidate.set_index('observation_id').reindex(left.index)
    for column in IDENTITY:
        require(left[column].eq(right[column]).fillna(False).all()
                or (left[column].eq(right[column]) | (left[column].isna() & right[column].isna())).all(),
                f'Observation identity differs: {column}')
    result = left.reset_index().copy()
    result['baseline_error'] = left.scoring_error_days.to_numpy(dtype=float)
    result['candidate_error'] = right.scoring_error_days.to_numpy(dtype=float)
    return result


def _metric_values(sums, counts):
    """Last dimensions are stage × [baseline/candidate abs,square,signed]."""
    means = np.divide(sums, counts[..., None], out=np.full_like(sums, np.nan), where=counts[..., None] > 0)
    means[..., [1, 4]] = np.sqrt(np.maximum(0., means[..., [1, 4]]))
    return means


def paired_statistics(frame: pd.DataFrame, *, n_bootstrap=2000, seed=20260912, min_groups=10):
    """Site-balanced paired metrics and original-group percentile bootstrap.

    Groups are drawn with replacement. Every site retains equal weight within
    each replicate, multiplied by its original group's draw multiplicity.
    ALL gives each of the four stages weight 1/4 and is missing if any is absent.
    """
    require(n_bootstrap >= 1 and min_groups >= 2, 'Invalid bootstrap configuration')
    require(frame.site.notna().all() and frame.group_id.notna().all(), 'Missing site or original independence group')
    require(not frame.groupby('site').group_id.nunique().gt(1).any(), 'Site changes independence group')
    a = frame.baseline_error.to_numpy(dtype=float)
    b = frame.candidate_error.to_numpy(dtype=float)
    common = np.isfinite(a) & np.isfinite(b)
    paired = frame.loc[common, ['site', 'group_id', 'BBCH']].copy()
    for column, values in zip(['a_abs','a_square','a_signed','b_abs','b_square','b_signed'],
                             [abs(a),a*a,a,abs(b),b*b,b]):
        paired[column] = values[common]
    values_cols = ['a_abs','a_square','a_signed','b_abs','b_square','b_signed']
    site = paired.groupby(['group_id','site','BBCH'], sort=True)[values_cols].mean().reset_index()
    groups = sorted(site.group_id.unique())
    group_index = {g:i for i,g in enumerate(groups)}
    sums = np.zeros((len(groups),4,6), dtype=float)
    counts = np.zeros((len(groups),4), dtype=float)
    for stage_index, stage in enumerate(STAGES):
        selected = site[site.BBCH.eq(stage)]
        grouped = selected.groupby('group_id')[values_cols].sum()
        group_counts = selected.groupby('group_id').size()
        indices = [group_index[g] for g in grouped.index]
        sums[indices,stage_index,:] = grouped.to_numpy()
        counts[indices,stage_index] = group_counts.to_numpy()
    point = _metric_values(sums.sum(axis=0), counts.sum(axis=0))
    stage_groups = (counts > 0).sum(axis=0)
    boot = None
    if len(groups) >= min_groups:
        # Cluster sufficient statistics avoid expanding observation records.
        rng = np.random.default_rng(seed)
        multiplicity = rng.multinomial(len(groups), np.full(len(groups),1/len(groups)), size=n_bootstrap)
        boot_sums = np.einsum('bg,gsk->bsk', multiplicity, sums, optimize=False)
        boot_counts = np.einsum('bg,gs->bs', multiplicity, counts, optimize=False)
        boot = _metric_values(boot_sums, boot_counts)
    rows = []
    for i, stage in enumerate(STAGES + ['ALL']):
        selected = frame if stage == 'ALL' else frame[frame.BBCH.eq(stage)]
        av = selected.baseline_error.to_numpy(dtype=float)
        bv = selected.candidate_error.to_numpy(dtype=float)
        mask = np.isfinite(av) & np.isfinite(bv)
        matched = selected.loc[mask]
        n_stages = int(np.isfinite(point[:,0]).sum()) if stage == 'ALL' else int(len(matched) > 0)
        if stage == 'ALL':
            value = np.mean(point, axis=0)
            # RMSE pools stage mean squared errors with equal stage weights.
            value[[1,4]] = np.sqrt(np.mean(point[:,[1,4]]**2,axis=0))
            resamples = np.mean(boot, axis=1) if boot is not None else None
            if resamples is not None:
                resamples[:,[1,4]] = np.sqrt(np.mean(boot[:,:,[1,4]]**2,axis=1))
            supported = n_stages == 4 and (stage_groups >= min_groups).all()
        else:
            value = point[i]
            resamples = boot[:,i,:] if boot is not None else None
            supported = stage_groups[i] >= min_groups
        for metric_index, metric in enumerate(METRICS):
            base, cand = float(value[metric_index]), float(value[metric_index+3])
            change = cand - base
            effect = change if metric == 'bias_days' else -change
            distribution = None if resamples is None else (
                resamples[:,metric_index+3] - resamples[:,metric_index]) * (1 if metric == 'bias_days' else -1)
            valid = np.array([]) if distribution is None else distribution[np.isfinite(distribution)]
            enough = supported and len(valid) >= .95 * n_bootstrap
            bounds = np.quantile(valid, [.025,.975]) if enough else [np.nan,np.nan]
            ci_status = ('available' if enough else 'missing_stage' if stage == 'ALL' and n_stages < 4
                         else 'insufficient_groups' if not supported else 'insufficient_valid_resamples')
            rows.append(dict(BBCH=stage, metric=metric, baseline=base, candidate=cand, change=change,
                benefit=-change if metric != 'bias_days' else np.nan, ci_low=bounds[0], ci_high=bounds[1],
                ci_estimand='change' if metric == 'bias_days' else 'benefit', ci_status=ci_status,
                n_observations=len(selected), n_paired=int(mask.sum()), n_sites=matched.site.nunique(),
                n_groups=matched.group_id.nunique(), n_baseline_finite=int(np.isfinite(av).sum()),
                n_candidate_finite=int(np.isfinite(bv).sum()),
                paired_fraction=float(mask.mean()) if len(mask) else np.nan,
                n_stages=n_stages, n_bootstrap_valid=int(len(valid)) if supported else 0,
                n_bootstrap=n_bootstrap, min_groups=min_groups))
    return pd.DataFrame(rows)


def recompute_metrics(frame):
    """Return stage and equal-stage overall metrics from actual saved dates."""
    rows = []
    for (method,partition), data in frame.groupby(['method','partition'], sort=True):
        for view in ['raw','scoring']:
            error_column = f'{view}_error_days'
            staged = []
            for stage in STAGES:
                observations = data[data.BBCH.eq(stage)]
                finite = observations[np.isfinite(observations[error_column])].copy()
                finite['abs_error'] = finite[error_column].abs()
                finite['square_error'] = finite[error_column]**2
                per_site = finite.groupby('site')[['abs_error','square_error',error_column]].mean()
                rates = observations.groupby('site')[['pbm_raw_attained','pbm_attained_by_cutoff',
                    'raw_attained','attained_by_cutoff','cutoff_assigned']].mean()
                row = dict(method=method, partition=partition, BBCH=stage, metric_view=view,
                    n_observations=len(observations), n_sites=observations.site.nunique(), n_scored=len(finite), n_stages=int(len(finite)>0),
                    mae_days=per_site.abs_error.mean(), rmse_days=np.sqrt(per_site.square_error.mean()),
                    bias_days=per_site[error_column].mean(),
                    pbm_raw_site_attainment=rates.pbm_raw_attained.mean(),
                    pbm_cutoff_site_attainment=rates.pbm_attained_by_cutoff.mean(),
                    raw_date_site_availability=rates.raw_attained.mean(),
                    cutoff_date_site_availability=rates.attained_by_cutoff.mean(),
                    cutoff_assignment_site_fraction=rates.cutoff_assigned.mean())
                rows.append(row); staged.append(row)
            stage_frame = pd.DataFrame(staged)
            overall = dict(method=method,partition=partition,BBCH='ALL',metric_view=view,
                n_observations=len(data),n_sites=data.site.nunique(),
                n_scored=int(np.isfinite(data[error_column]).sum()), n_stages=int(stage_frame.mae_days.notna().sum()))
            for column in METRICS + ['pbm_raw_site_attainment','pbm_cutoff_site_attainment',
                                    'raw_date_site_availability','cutoff_date_site_availability','cutoff_assignment_site_fraction']:
                numbers = stage_frame[column].to_numpy()
                overall[column] = (float(np.sqrt(np.mean(numbers**2))) if column == 'rmse_days'
                                   else float(np.mean(numbers)))
            rows.append(overall)
    return pd.DataFrame(rows)


def _parse_bool(series, column):
    values = series.astype(str).str.lower().map({'true':True,'false':False,'1':True,'0':False})
    require(values.notna().all(), f'Invalid Boolean prediction column: {column}')
    return values.astype(bool)


def load_predictions(path, model, temperature, sites, expected_ids=None):
    header = pd.read_csv(path,nrows=0).columns.tolist()
    columns = ['observation_id','site','BBCH','Date','partition','temperature_zone_id','country',
               'model','temperature','method','raw_predicted_date','scoring_date','cutoff_date',
               'raw_error_days','scoring_error_days','pbm_raw_predicted_date','pbm_raw_attained',
               'pbm_attained_by_cutoff','raw_attained','attained_by_cutoff','cutoff_assigned']
    require(set(columns) <= set(header), f'Incomplete prediction schema: {path}')
    frame = pd.read_csv(path,usecols=columns,dtype={c:str for c in columns if not c.endswith('_days')})
    require(frame.model.eq(model).all() and frame.temperature.eq(temperature).all(), 'Prediction unit identity mismatch')
    require(set(frame.method) == set(METHODS) and set(frame.partition) == {'calibration','test'}, 'Invalid prediction factors')
    require(set(frame.BBCH) <= set(STAGES), 'Unknown stage in predictions')
    require(not frame.duplicated(['method','observation_id']).any(), 'Duplicate predictions for observation')
    for col in ['Date','raw_predicted_date','scoring_date','cutoff_date','pbm_raw_predicted_date']:
        frame[col] = pd.to_datetime(frame[col],errors='raise')
    require(frame.Date.notna().all(), 'Missing observed date')
    require(frame.cutoff_date.notna().all() and frame.cutoff_date.dt.strftime('%m-%d').eq('11-04').all()
            and frame.cutoff_date.dt.year.eq(frame.Date.dt.year).all(), 'Invalid fixed November cutoff date')
    for prefix in ['raw','scoring']:
        date_col = 'raw_predicted_date' if prefix == 'raw' else 'scoring_date'
        calculated = (frame[date_col] - frame.Date).dt.total_seconds() / 86400
        np.testing.assert_allclose(frame[f'{prefix}_error_days'],calculated,rtol=1e-10,atol=1e-9,equal_nan=True,
                                   err_msg=f'Saved {prefix} error differs from dates: {path}')
        frame[f'{prefix}_error_days'] = calculated
    flags = {'raw_attained':frame.raw_predicted_date.notna(),
             'attained_by_cutoff':frame.raw_predicted_date.le(frame.cutoff_date),
             'pbm_raw_attained':frame.pbm_raw_predicted_date.notna(),
             'pbm_attained_by_cutoff':frame.pbm_raw_predicted_date.le(frame.cutoff_date)}
    for col in list(flags) + ['cutoff_assigned']:
        frame[col] = _parse_bool(frame[col],col)
        if col in flags:
            require(frame[col].eq(flags[col]).all(), f'Prediction date/flag mismatch: {col}')
    late = frame.BBCH.isin(['81','89'])
    assigned = late & (~frame.raw_attained | frame.raw_predicted_date.gt(frame.cutoff_date))
    require(frame.cutoff_assigned.eq(assigned).all(), 'Cutoff assignment differs from raw-date rule')
    expected_score = frame.raw_predicted_date.where(~assigned,frame.cutoff_date)
    require((frame.scoring_date.eq(expected_score) | (frame.scoring_date.isna() & expected_score.isna())).all(),
            'Scoring date differs from final raw-date cutoff rule')
    process = frame[frame.method.eq('process')]
    require((process.raw_predicted_date.eq(process.pbm_raw_predicted_date)
             | (process.raw_predicted_date.isna() & process.pbm_raw_predicted_date.isna())).all(),
            'Process raw prediction differs from saved PBM date')
    require(not (frame.method.eq('tabm') & ~frame.pbm_raw_attained & frame.raw_attained).any(),
            'Unattained PBM unexpectedly has a finite hybrid date')
    for method in METHODS:
        ids = set(frame.loc[frame.method.eq(method),'observation_id'])
        if expected_ids is None:
            expected_ids = ids
        require(ids == expected_ids,'Prediction observation population differs across units/methods')
    require(frame.site.isin(sites.site).all(), 'Prediction sites missing from terrain cohort')
    joined = frame.merge(sites[['site','group_id'] + TERRAIN],on='site',how='left',validate='many_to_one')
    require(joined.group_id.notna().all(), 'Missing original independence group')
    return joined, expected_ids


def _records(frame):
    return json.loads(frame.to_json(orient='records',date_format='iso',double_precision=15))


def _safe_json(value):
    if isinstance(value,dict): return {str(k):_safe_json(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_safe_json(v) for v in value]
    if isinstance(value,(np.floating,float)) and not np.isfinite(value): return None
    if isinstance(value,np.generic): return value.item()
    return value


def _save_figure(fig,output,stem,pdfs,paths):
    for suffix in ['png','pdf']:
        path=output/f'{stem}.{suffix}';fig.savefig(path,dpi=300);paths.append(path)
    for pdf in pdfs: pdf.savefig(fig)
    plt.close(fig)


def _paper_style():
    from matplotlib import font_manager
    font=Path('/System/Library/Fonts/Helvetica.ttc')
    require(font.is_file(), 'The shared paper font Helvetica is unavailable')
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':'Helvetica','font.size':8,'axes.labelsize':8,
        'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8,'pdf.fonttype':42,
        'text.color':'#182630','axes.unicode_minus':True,'savefig.bbox':None})


def _heatmap(ax,values,labels,columns,cmap,norm,signed=False):
    im=ax.imshow(np.ma.masked_invalid(values),cmap=cmap,norm=norm,aspect='auto')
    ax.set_xticks(range(len(columns)),columns)
    display_labels=[str(label).replace('TZ','EZ',1) if str(label).startswith('TZ') else label for label in labels]
    ax.set_yticks(range(len(labels)),display_labels)
    ax.xaxis.tick_top();ax.tick_params(length=0,labelsize=8)
    ax.set_xticks(np.arange(-.5,len(columns)),minor=True);ax.set_yticks(np.arange(-.5,len(labels)),minor=True)
    ax.grid(which='minor',color='white',linewidth=.6);ax.tick_params(which='minor',length=0)
    for (i,j),v in np.ndenumerate(values):
        light=np.dot(cmap(norm(v))[:3],[.2126,.7152,.0722]) if np.isfinite(v) else 1
        ax.text(j,i,('n/a' if not np.isfinite(v) else f'{v:+.1f}' if signed else f'{v:.1f}'),
                ha='center',va='center',fontsize=8,color='white' if light<.48 else '#182630')
    for spine in ax.spines.values():spine.set_visible(False)
    return im


def _panel(ax,letter,y=1.15):
    ax.text(0,y,f'({letter})',transform=ax.transAxes,ha='left',va='bottom',fontsize=9,fontweight='bold')


def render_publication(stage_metrics,effects,output):
    """Native 180-mm paper figures: Helvetica 8 pt, panel letters only."""
    _paper_style()
    paths=[];width=180/25.4
    book_names=['supporting_results.pdf','supporting_pbm.pdf','supporting_dem.pdf','supporting_ml.pdf']
    with PdfPages(output/book_names[0]) as pdf, PdfPages(output/book_names[1]) as pbm_pdf, \
            PdfPages(output/book_names[2]) as dem_pdf, PdfPages(output/book_names[3]) as ml_pdf:
        for method,number in [('process','01'),('tabm','03')]:
            if method=='tabm':
                demo=effects[effects.comparison.eq('DEM_process') & effects.BBCH.eq('ALL') & effects.metric.eq('mae_days')]
                for kind in STRATA:
                    selected=demo[demo.stratum.eq(kind)]
                    levels=(['low','middle','high','NA'] if kind in ['terrain_complexity','elevation_mismatch']
                            else sorted(selected.level.unique(),key=str))
                    vals=selected.benefit.dropna().abs()
                    limit=max(1.,float(np.ceil(vals.max()))) if len(vals) else 1.
                    cmap=plt.get_cmap('PuOr_r').copy();cmap.set_bad('#e5e7e9')
                    norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit)
                    height=max(100., 12.*len(levels)+35.)/25.4
                    fig,axes=plt.subplots(2,1,figsize=(width,height))
                    fig.subplots_adjust(left=.13,right=.88,top=.90,bottom=.07,hspace=.56)
                    for ax,partition,letter in zip(axes,['calibration','test'],'ab'):
                        matrix=selected[selected.partition.eq(partition)].pivot(index='level',columns='model',values='benefit').reindex(index=levels,columns=MODELS)
                        im=_heatmap(ax,matrix.to_numpy(float),levels,MODELS,cmap,norm,True)
                        _panel(ax,letter,y=1.19)
                        names={'terrain_complexity':'Terrain variability', 'elevation_mismatch':'Elevation mismatch',
                               'temperature_zone_id':'Environmental zone','country':'Country'}
                        ax.set_ylabel(names[kind],fontsize=8)
                    fig.colorbar(im,cax=fig.add_axes([.92,.25,.02,.48]),label='MAE benefit (d)')
                    _save_figure(fig,output,f'02_dem_{kind}',[pdf,dem_pdf],paths)
            for metric,short in [('mae_days','mae'),('bias_days','bias')]:
                signed=metric=='bias_days';low,high=(-10.,10.) if signed else (8.,20.)
                norm=TwoSlopeNorm(vmin=low,vcenter=0,vmax=high) if signed else Normalize(low,high)
                cmap=plt.get_cmap('PuOr_r' if signed else 'YlOrBr').copy();cmap.set_bad('#e5e7e9')
                selected=stage_metrics[stage_metrics.method.eq(method)&stage_metrics.metric_view.eq('scoring')]
                fig,axes=plt.subplots(1,4,figsize=(width,90/25.4))
                fig.subplots_adjust(left=.115,right=.875,top=.84,bottom=.08,wspace=.16)
                for i,(temperature,partition) in enumerate(PANELS):
                    matrix=selected[selected.temperature.eq(temperature)&selected.partition.eq(partition)].pivot(index='model',columns='BBCH',values=metric).reindex(index=MODELS,columns=STAGES)
                    im=_heatmap(axes[i],matrix.to_numpy(float),MODELS if i==0 else ['']*10,STAGES,cmap,norm,signed)
                    _panel(axes[i],'abcd'[i],y=1.11)
                values=selected[metric].dropna();below=values.lt(low).any();above=values.gt(high).any()
                extension='both' if below and above else 'min' if below else 'max' if above else 'neither'
                fig.colorbar(im,cax=fig.add_axes([.91,.16,.02,.60]),label=('Bias (d)' if signed else 'MAE (d)'),extend=extension)
                _save_figure(fig,output,f'{number}_{"pbm" if method=="process" else "ml"}_{short}',[pdf,pbm_pdf if method=='process' else ml_pdf],paths)
        selected=effects[effects.comparison.isin(['ML_RAW','ML_DEM'])&effects.stratum.eq('overall')
                         &effects.BBCH.eq('ALL')&effects.metric.eq('mae_days')]
        numbers=selected[['benefit','ci_low','ci_high']].to_numpy(float)
        maximum=np.nanmax(abs(numbers)) if np.isfinite(numbers).any() else 1.
        limit=max(1.,float(np.ceil(maximum)))
        fig,axes=plt.subplots(1,2,figsize=(width,105/25.4))
        fig.subplots_adjust(left=.13,right=.98,top=.84,bottom=.15,wspace=.28)
        for i,(ax,partition) in enumerate(zip(axes,['calibration','test'])):
            for temperature,offset,colour in [('RAW',-.13,'#5a3a7d'),('DEM',.13,'#b26a18')]:
                rows=selected[selected.comparison.eq('ML_'+temperature)&selected.partition.eq(partition)].set_index('model').reindex(MODELS)
                y=np.arange(10)+offset
                for j,row in enumerate(rows.itertuples()):
                    if np.isfinite(row.ci_low) and np.isfinite(row.ci_high):
                        ax.plot([row.ci_low,row.ci_high],[y[j],y[j]],color=colour,lw=.9,zorder=1)
                ax.scatter(rows.benefit,y,s=13,color=colour,label=temperature,zorder=2)
            ax.axvline(0,color='#83888d',lw=.6);ax.set_xlim(-limit,limit)
            ax.set_yticks(range(10),MODELS if i==0 else ['']*10);ax.invert_yaxis()
            ax.set_xlabel('MAE benefit (d)',fontsize=8);ax.tick_params(labelsize=8)
            for spine in ['top','right']:ax.spines[spine].set_visible(False)
            _panel(ax,'ab'[i],y=1.10)
        axes[1].legend(loc='lower right',frameon=False,fontsize=8)
        _save_figure(fig,output,'03_ml_mae_effects',[pdf,ml_pdf],paths)
    paths.extend(output/name for name in book_names)
    paths += render_main_figures(stage_metrics,effects,output)
    return paths


def region_stage_summary(effects):
    selected=effects[effects.comparison.eq('DEM_process') & effects.stratum.isin(['temperature_zone_id','country'])
                     & effects.BBCH.isin(STAGES) & effects.metric.eq('mae_days')]
    rows=[]
    for keys,table in selected.groupby(['partition','stratum','level','BBCH'],sort=True):
        row=dict(zip(['partition','stratum','level','BBCH'],keys))
        finite=table[table.benefit.notna()]
        row.update(n_models=len(finite),mean_benefit=finite.benefit.mean() if len(finite)==10 else np.nan,
                   min_benefit=finite.benefit.min(),max_benefit=finite.benefit.max(),
                   min_paired_observations=finite.n_paired.min(),min_sites=finite.n_sites.min(),
                   min_groups=finite.n_groups.min(),weighting='equal ten fixed structures within stage; no missing-model renormalization')
        rows.append(row)
    return pd.DataFrame(rows)


def render_main_figures(stage_metrics,effects,output):
    """Three single-page publication figures; the supporting plots retain detail."""
    _paper_style();paths=[];width=180/25.4
    with PdfPages(output/'final_results.pdf') as combined:
        for method,stem in [('process','pbm_mae_bias'),('tabm','ml_mae_bias_effects')]:
            hybrid=method=='tabm'
            fig=plt.figure(figsize=(width,(208 if hybrid else 156)/25.4))
            grid=fig.add_gridspec(3 if hybrid else 2,4,left=.115,right=.875,bottom=.075,top=.90,
                                  wspace=.16,hspace=.48,height_ratios=[1,1,.85] if hybrid else [1,1])
            for row,(metric,signed) in enumerate([('mae_days',False),('bias_days',True)]):
                low,high=(-10.,10.) if signed else (8.,20.)
                norm=TwoSlopeNorm(vmin=low,vcenter=0,vmax=high) if signed else Normalize(low,high)
                cmap=plt.get_cmap('PuOr_r' if signed else 'YlOrBr').copy();cmap.set_bad('#e5e7e9')
                selected=stage_metrics[stage_metrics.method.eq(method)&stage_metrics.metric_view.eq('scoring')]
                for col,(temperature,partition) in enumerate(PANELS):
                    ax=fig.add_subplot(grid[row,col])
                    matrix=selected[selected.temperature.eq(temperature)&selected.partition.eq(partition)].pivot(index='model',columns='BBCH',values=metric).reindex(index=MODELS,columns=STAGES)
                    im=_heatmap(ax,matrix.to_numpy(float),MODELS if col==0 else ['']*10,STAGES,cmap,norm,signed)
                    _panel(ax,'abcdefgh'[row*4+col],y=1.13)
                box=ax.get_position();values=selected[metric].dropna()
                below=values.lt(low).any();above=values.gt(high).any()
                extension='both' if below and above else 'min' if below else 'max' if above else 'neither'
                fig.colorbar(im,cax=fig.add_axes([.91,box.y0+.025,.02,box.height-.05]),
                             label='Bias (d)' if signed else 'MAE (d)',extend=extension)
            if hybrid:
                selected=effects[effects.comparison.isin(['ML_RAW','ML_DEM'])&effects.stratum.eq('overall')
                                 &effects.BBCH.eq('ALL')&effects.metric.eq('mae_days')]
                values=selected[['benefit','ci_low','ci_high']].to_numpy(float)
                limit=max(1.,float(np.ceil(np.nanmax(abs(values))))) if np.isfinite(values).any() else 1.
                for col,partition in enumerate(['calibration','test']):
                    ax=fig.add_subplot(grid[2,col*2:col*2+2])
                    box=ax.get_position()
                    ax.set_position([box.x0,box.y0,box.width-.014,box.height])
                    for temperature,offset,colour in [('RAW',-.14,'#5a3a7d'),('DEM',.14,'#b26a18')]:
                        table=selected[selected.partition.eq(partition)&selected.comparison.eq('ML_'+temperature)].set_index('model').reindex(MODELS)
                        y=np.arange(10)+offset
                        for j,row in enumerate(table.itertuples()):
                            if np.isfinite(row.ci_low) and np.isfinite(row.ci_high):
                                ax.plot([row.ci_low,row.ci_high],[y[j],y[j]],color=colour,lw=.8)
                        ax.scatter(table.benefit,y,s=10,color=colour,label=temperature)
                    ax.axvline(0,color='#83888d',lw=.6);ax.set_xlim(-limit,limit)
                    ax.set_yticks(range(10),MODELS if col==0 else ['']*10);ax.invert_yaxis()
                    ax.set_xlabel('MAE benefit (d)');_panel(ax,'ij'[col],y=1.06)
                    for spine in ['top','right']:ax.spines[spine].set_visible(False)
                    if col==1:ax.legend(frameon=False,loc='upper center',bbox_to_anchor=(.5,-.21),ncol=2,
                                        borderaxespad=0,handletextpad=.3,columnspacing=.8)
            # DEM is placed between process and ML in the final three-page PDF.
            _save_figure(fig,output,stem,[combined],paths)
            if method=='process':
                demo=effects[effects.comparison.eq('DEM_process')&effects.partition.eq('test')
                             &effects.BBCH.eq('ALL')&effects.metric.eq('mae_days')]
                regions=region_stage_summary(effects)
                regions=regions[regions.partition.eq('test')]
                matrices=[];row_labels=[];column_labels=[]
                for kind in STRATA:
                    if kind in ['terrain_complexity','elevation_mismatch']:
                        matrix=demo[demo.stratum.eq(kind)].pivot(index='model',columns='level',values='benefit').reindex(index=MODELS,columns=['low','middle','high','NA'])
                    else:
                        part=regions[regions.stratum.eq(kind)]
                        matrix=part.pivot(index='level',columns='BBCH',values='mean_benefit').reindex(columns=STAGES)
                    matrices.append(matrix.to_numpy(float));row_labels.append(list(matrix.index));column_labels.append(list(matrix.columns))
                numeric=np.concatenate([m.ravel() for m in matrices]);limit=max(1.,float(np.ceil(np.nanmax(abs(numeric))))) if np.isfinite(numeric).any() else 1.
                cmap=plt.get_cmap('PuOr_r').copy();cmap.set_bad('#e5e7e9');norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit)
                fig,axes=plt.subplots(2,2,figsize=(width,172/25.4))
                fig.subplots_adjust(left=.135,right=.87,top=.90,bottom=.055,wspace=.52,hspace=.32)
                for i,ax in enumerate(axes.flat):
                    im=_heatmap(ax,matrices[i],row_labels[i],column_labels[i],cmap,norm,True)
                    _panel(ax,'abcd'[i],y=1.13)
                fig.colorbar(im,cax=fig.add_axes([.91,.20,.02,.61]),label='MAE benefit (d)')
                _save_figure(fig,output,'dem_terrain_effects',[combined],paths)
    paths.append(output/'final_results.pdf')
    return paths


def build_analysis(run: Path, sites_path: Path, output: Path|None=None, *, n_bootstrap=2000, seed=20260912):
    run=Path(run).resolve();sites_path=Path(sites_path).resolve()
    output=(Path(output) if output else run/'final_analysis').resolve()
    require(output != run and output not in run.parents,'Output overlaps run root')
    for model,temperature in itertools.product(MODELS,['RAW','DEM']):
        folder=(run/model/temperature).resolve()
        require(output!=folder and folder not in output.parents and output not in folder.parents,'Output overlaps fitted unit')
    require(not output.exists() or not any(output.iterdir()),'Output must be new or empty to preserve prior final artifacts')
    require(n_bootstrap>=2000,'Publication requires at least 2000 bootstrap replicates')
    status,config,hashes=validate_final_run(run)
    source_metrics,unit_hashes=collect(run,status['completed']);hashes.update(unit_hashes)
    expected_site_hash=config.get('sources',{}).get(str(sites_path))
    require(expected_site_hash is not None and sha256(sites_path)==expected_site_hash,'Terrain cohort differs from locked ML input')
    hashes[str(sites_path)]=expected_site_hash
    header=pd.read_csv(sites_path,nrows=0).columns
    require({'site','group_id','country',*TERRAIN}<=set(header),'Incomplete site metadata')
    sites=pd.read_csv(sites_path,usecols=['site','group_id','country']+TERRAIN,dtype={'site':str,'group_id':str,'country':str})
    require(not sites.site.duplicated().any(),'Duplicate terrain site records')
    expected_ids=None;population=None;site_strata=None;cuts=None;metric_frames=[];effect_frames=[]
    for model in MODELS:
        temperatures={}
        for temperature in ['RAW','DEM']:
            path=run/model/temperature/'predictions.csv.gz'
            require(f'{model}/{temperature}/predictions.csv.gz' in hashes,'Predictions are not sealed artifacts')
            frame,expected_ids=load_predictions(path,model,temperature,sites,expected_ids)
            require(sha256(path)==hashes[f'{model}/{temperature}/predictions.csv.gz'],'Predictions changed during analysis')
            base=frame[frame.method.eq('process')].copy()
            identity=base[['observation_id']+IDENTITY].sort_values('observation_id').reset_index(drop=True)
            if population is None:
                population=identity
                site_population=base[['site','partition','group_id','temperature_zone_id','country']+TERRAIN].drop_duplicates()
                require(not site_population.site.duplicated().any(),'Site has changing partition, zone or terrain')
                require(not site_population.groupby('group_id').partition.nunique().gt(1).any(),'Original independence group crosses partitions')
                require(site_population.country.eq(site_population.site.map(sites.set_index('site').country)).fillna(False).all(),
                        'Prediction country differs from cohort metadata')
                site_strata,cuts=terrain_strata(site_population)
                for col in ['country','temperature_zone_id']:
                    site_strata[col]=site_strata[col].fillna('NA').astype(str)
            else:
                pd.testing.assert_frame_equal(identity,population,check_dtype=False,obj='Frozen observation identity')
            frame=frame.drop(columns=['country','temperature_zone_id']).merge(site_strata[['site']+STRATA],on='site',how='left',validate='many_to_one')
            recalculated=recompute_metrics(frame).assign(model=model,temperature=temperature)
            for row in recalculated[recalculated.BBCH.ne('ALL')].itertuples(index=False):
                match=source_metrics[(source_metrics.model==model)&(source_metrics.temperature==temperature)
                    &(source_metrics.method==row.method)&(source_metrics.partition==row.partition)
                    &(source_metrics.BBCH==row.BBCH)&(source_metrics.metric_view==row.metric_view)]
                require(len(match)==1,'Missing unique source metric row')
                np.testing.assert_allclose([getattr(row,c) for c in METRICS],match[METRICS].iloc[0].to_numpy(float),
                                           rtol=1e-9,atol=1e-8,equal_nan=True,err_msg='Independent metric recomputation disagrees')
                require(all(getattr(row,c)==int(match[c].iloc[0]) for c in ['n_observations','n_sites','n_scored']),
                        'Independent metric denominators disagree')
            metric_frames.append(recalculated);temperatures[temperature]=frame
        for comparison,(baseline_key,candidate_key) in CONTRASTS.items():
            baseline=temperatures[baseline_key[0]][temperatures[baseline_key[0]].method.eq(baseline_key[1])]
            candidate=temperatures[candidate_key[0]][temperatures[candidate_key[0]].method.eq(candidate_key[1])]
            paired=match_predictions(baseline,candidate)
            for partition in ['calibration','test']:
                partition_data=paired[paired.partition.eq(partition)]
                selections=[('overall','all',partition_data)]
                for stratum in STRATA:
                    levels=(['low','middle','high','NA'] if stratum in ['terrain_complexity','elevation_mismatch']
                            else sorted(site_strata[stratum].unique(),key=str))
                    selections.extend((stratum,str(level),partition_data[partition_data[stratum].eq(level)]) for level in levels)
                for stratum,level,records in selections:
                    tag=f'{seed}/{model}/{comparison}/{partition}/{stratum}/{level}'
                    local_seed=int.from_bytes(hashlib.sha256(tag.encode()).digest()[:8],'big')
                    table=paired_statistics(records,n_bootstrap=n_bootstrap,seed=local_seed)
                    effect_frames.append(table.assign(comparison=comparison,model=model,partition=partition,
                                                      stratum=stratum,level=level))
        print(f'Analyzed {model}: paired DEM/ML effects and original-group bootstrap',flush=True)
    all_metrics=pd.concat(metric_frames,ignore_index=True)
    stage_metrics=all_metrics[all_metrics.BBCH.ne('ALL')].copy()
    overall_metrics=all_metrics[all_metrics.BBCH.eq('ALL')].copy()
    overall_metrics['weighting']='equal_four_stage; site_balanced_within_stage; RMSE=sqrt(mean(stage_RMSE^2))'
    effects=pd.concat(effect_frames,ignore_index=True)
    pbm=stage_metrics[stage_metrics.method.eq('process')&stage_metrics.metric_view.eq('scoring')]
    summary=[]
    for keys,table in pbm.groupby(['partition','temperature','BBCH'],sort=True):
        row=dict(zip(['partition','temperature','BBCH'],keys));row['n_models']=len(table)
        for metric in METRICS:
            for name in ['min','max','mean']:row[f'{metric}_{name}']=getattr(table[metric],name)()
        summary.append(row)
    require(sha256(sites_path)==expected_site_hash,'Site metadata changed during analysis')
    require(sha256(run/'run.json')==hashes['run.json'] and sha256(run/'status.json')==hashes['status.json'],
            'Final run configuration/status changed during analysis')
    output.mkdir(parents=True,exist_ok=True)
    tables={'stage_metrics.csv':stage_metrics,'overall_metrics.csv':overall_metrics,
            'paired_effects.csv':effects,'pbm_stage_summary.csv':pd.DataFrame(summary),
            'site_strata.csv':site_strata,'dem_region_stage_summary.csv':region_stage_summary(effects)}
    paths=[]
    for name,table in tables.items():table.to_csv(output/name,index=False);paths.append(output/name)
    payload=dict(schema_version=1,run_dir=str(run),run_complete=True,smoke=False,
        snapshot_utc=datetime.now(timezone.utc).isoformat(),result_order=['process_performance','dem_terrain_effects','ml_performance'],
        primary_partition='test',calibration_interpretation='apparent final-fit training performance, not OOF generalization',
        model_order=MODELS,stage_order=STAGES,temperature_order=['RAW','DEM'],
        figure_style=dict(width_mm=180,font='Helvetica',text_pt=8,panel_label_pt=9,panel_label_weight='bold',titles=False),
        figure_captions=dict(pbm_mae_bias='Process-model site-balanced scoring MAE (a–d) and signed bias (e–h). Within each row: RAW apparent calibration, RAW held-out test, DEM apparent calibration, DEM held-out test. Columns are BBCH07,65,81,89; rows follow the ten-structure catalogue.',
            dem_terrain_effects='Held-out paired DEM MAE benefit, MAE(RAW) minus MAE(DEM), without residual ML. (a) Calibration-defined local terrain variability tertiles and (b) absolute elevation-mismatch tertiles show the ten model structures in rows and equally weighted four-stage benefits. (c) Frozen environmental zones and (d) countries show BBCH07,65,81,89 in columns and descriptive means across all ten fixed model structures within each stage. No missing-stage or missing-model renormalization. Grey n/a denotes unavailable support. Regional means have no aggregate CI; individual-model original-group intervals and support are in paired_effects.csv.',
            ml_mae_bias_effects='Hybrid scoring MAE (a–d) and signed bias (e–h); within each row: RAW apparent calibration, RAW held-out test, DEM apparent calibration, DEM held-out test. (i) Apparent calibration and (j) held-out test show paired process MAE minus hybrid MAE, equally averaged across four stages, with original-group pointwise 95% bootstrap intervals when supported. RAW/DEM colours follow the legend. Intervals are absent with insufficient groups.'),
        stage_metrics=_records(stage_metrics),overall_metrics=_records(overall_metrics),
        paired_effects=_records(effects),pbm_stage_summary=summary,terrain_cuts=cuts,
        dem_region_stage_summary=_records(region_stage_summary(effects)),
        uncertainty=dict(method='original group_id cluster percentile bootstrap; equal site weights within each draw',
            n_bootstrap=n_bootstrap,seed=seed,min_groups=10,confidence=.95,
            requirement='At least 10 original groups per contributing stage and >=95% finite replicates; otherwise no CI',
            multiplicity='Descriptive pointwise intervals, no adjustment for multiple comparisons'),
        definitions=dict(change='candidate minus baseline',benefit='baseline minus candidate for MAE/RMSE; undefined for signed bias',
            ci_estimand='benefit for MAE/RMSE, signed change for bias',
            overall='Each of four stages has weight 1/4; RMSE=sqrt(mean stage MSE); missing stages are not renormalized',
            pairing='Exact observation_id and unchanged site/stage/date/partition/group/zone/country; common finite scoring population',
            cutoff='Final chronological hybrid correction precedes 4 November scoring cap for BBCH81/89',
            attainment='PBM thermal attainment is separate from finite raw hybrid-date availability and assigned scoring dates',
            causal_scope='Predictive associations; no causal terrain claims',
            forecast_scope='Retrospective weather through PBM-predicted dates; not operational forecast validation'),
        source_sha256=hashes,script_sha256=sha256(Path(__file__)))
    (output/'analysis.json').write_text(json.dumps(_safe_json(payload),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    paths.append(output/'analysis.json')
    paths+=render_publication(stage_metrics,effects,output)
    readme='''# Final process, terrain and residual-learning results

The result order is process-model MAE and signed bias, paired DEM effects across terrain and regions, and TabM residual-hybrid MAE and signed bias. `final_results.pdf` contains the three single-page main figures in this order; `supporting_results.pdf` retains the nine detailed figures; numbered PNG/PDF pairs retain the same sequence. Held-out test results are primary; calibration results are apparent fitted-model performance.

All figures have native width 180 mm, Helvetica 8 pt ordinary text and bold 9 pt parenthesized panel letters, with no titles. The single-page main PDFs are `pbm_mae_bias.pdf`, `dem_terrain_effects.pdf` and `ml_mae_bias_effects.pdf`. Main performance panels (a)–(d) show MAE and (e)–(h) show bias, each in RAW calibration, RAW test, DEM calibration, DEM test order. Main ML-effect panels (i)–(j) are calibration and test. Main DEM panels are held-out terrain variability, elevation mismatch, environmental zones and countries; the last two show stagewise descriptive means across ten structures. `dem_region_stage_summary.csv` retains these regional summaries and minimum support across structures. Exact figure captions are retained in `analysis.json`.

`stage_metrics.csv` contains independently recomputed site-balanced raw/scoring metrics by model, temperature, method, partition and BBCH. `overall_metrics.csv` gives every target stage weight 1/4; overall RMSE is the square root of mean stage MSE. Missing stages remain missing rather than being reweighted. `pbm_stage_summary.csv` reports min/max/mean across the ten fixed process structures for each stage, temperature and partition. These descriptive model summaries are not uncertainty intervals.

`paired_effects.csv` compares DEM versus RAW without and with TabM, and TabM versus its process model at each temperature. Observation identities must match exactly. Both errors use the same finite scoring-date population within each comparison, stage and stratum. Baseline and candidate metrics first average within site; sites then receive equal weights. `change` is candidate minus baseline; `benefit` is baseline minus candidate for MAE/RMSE. Signed bias has a change but no scalar improvement definition. Coverage and observation/site/original-group support accompany every estimate. A site's absence from the paired finite sample is explicit in coverage, not converted into zero error.

Original `group_id` clusters are sampled with replacement for 2,000 or more bootstrap replicates. Each replicate preserves cluster membership and gives sites equal weight multiplied by their cluster's resampling count. Percentile 95% intervals require at least ten original groups in every contributing stage and at least 95% finite replicates. Insufficient support has no interval. Intervals are pointwise and unadjusted for multiple comparisons. Terrain effects are predictive associations, not causal effects.

`site_strata.csv` retains original group, partition, country, frozen environmental zone, terrain variables and assigned strata. Global terrain tertiles use one observation per distinct calibration site only; exact linear-quantile boundaries, interval closure and missing-value rules are in `analysis.json`. Test sites and region-specific observations do not modify these cutpoints. NA groups and empty tied-quantile bins remain explicit.

PBM raw attainment, PBM attainment by the cutoff, raw hybrid-date availability and cutoff assignment remain separate. A finite hybrid date is not evidence of thermal attainment. Chronologically corrected final hybrid dates precede the 4 November scoring cap for BBCH81/89. Unattained PBM dates receive no learned residual; November scoring dates can nevertheless be assigned to these late stages. Weather features through PBM dates make this retrospective prediction evaluation, not operational forecast validation.

`analysis.json` embeds the metric/effect tables and method definitions for deterministic manuscript generation. `manifest.json` records output hashes. Every completed unit's declared artifact is SHA-256 verified; the terrain source must match the frozen ML input. Prediction date errors and flags are independently checked and source metrics reconciled. The publication gate requires all 20 configurations, final source verification and a nonsmoke completed run. Fitted source artifacts are unchanged.
'''
    (output/'README.md').write_text(readme,encoding='utf-8');paths.append(output/'README.md')
    manifest=dict(schema_version=1,run_dir=str(run),source_sha256=hashes,script_sha256=sha256(Path(__file__)),
                  result_order=payload['result_order'],output_sha256={p.name:sha256(p) for p in paths})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'Exported final verified analysis to {output}',flush=True)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir',type=Path)
    parser.add_argument('--sites',type=Path,default=ROOT/'model_run/results/publication_cohort_20260910/sites.csv')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--bootstrap',type=int,default=2000)
    parser.add_argument('--seed',type=int,default=20260912)
    args=parser.parse_args()
    build_analysis(args.run_dir,args.sites,args.output,n_bootstrap=args.bootstrap,seed=args.seed)


if __name__=='__main__':main()
