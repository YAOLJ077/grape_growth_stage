#!/usr/bin/env python3
"""Render verified pooled-calibration comparisons without fitting or selection."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import Normalize, TwoSlopeNorm
import numpy as np
import pandas as pd

STAGES = ['07','65','81','89']
METHODS = ['existing','original_objective','low_bias_mae']
LABELS = {'existing':'Existing thresholds','original_objective':'Recalibrated: original loss',
          'low_bias_mae':'Recalibrated: low bias + MAE','median_threshold':'Median thresholds'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def scale(values, metric):
    finite = np.asarray(values,dtype=float)
    finite = finite[np.isfinite(finite)]
    maximum = max(1.,float(np.max(np.abs(finite))))
    if metric == 'bias_days':
        return plt.get_cmap('PuOr_r').copy(), TwoSlopeNorm(0.,-maximum,maximum)
    if metric == 'attainment':
        return plt.get_cmap('YlGnBu').copy(), Normalize(min(.98,float(finite.min())),1.)
    return plt.get_cmap('YlOrRd').copy(), Normalize(0.,maximum)


def heatmap(ax, values, row_labels, columns, cmap, norm, metric, fontsize=7):
    cmap.set_bad('#e8e8e8')
    im = ax.imshow(values,aspect='auto',cmap=cmap,norm=norm)
    ax.set_xticks(range(len(columns)),columns)
    ax.set_yticks(range(len(row_labels)),row_labels)
    ax.tick_params(length=0,labelsize=8)
    ax.xaxis.tick_top()
    for r in range(len(row_labels)):
        for c in range(len(columns)):
            v = values[r,c]
            if np.isfinite(v):
                color = cmap(norm(v))
                luminance = .2126*color[0] + .7152*color[1] + .0722*color[2]
                label = f'{v*100:.1f}' if metric=='attainment' else f'{v:.1f}'
                ax.text(c,r,label,ha='center',va='center',fontsize=fontsize,
                        color='white' if luminance < .5 else '#162a35')
            else:
                ax.text(c,r,'—',ha='center',va='center',fontsize=fontsize,color='#666')
    for spine in ax.spines.values():
        spine.set_visible(False)
    return im


def render_comparisons(metrics, output, book, methods=METHODS, prefix='', smoke=False):
    order = list(dict.fromkeys(zip(metrics.model,metrics.temperature)))
    labels = [f'{m}  {t}' for m,t in order]
    for metric,title in [('bias_days','Signed error (days)'),('mae_days','MAE (days)'),
                         ('rmse_days','RMSE (days)'),('attainment','Stage attainment (%)')]:
        selected = metrics[metrics.method.isin(methods)]
        cmap,norm = scale(selected[metric],metric)
        height = max(7.,len(order)*.48+3.)
        fig, axes = plt.subplots(2,len(methods),figsize=(15,height),squeeze=False)
        row_height = (height-3.2)/2
        fig.subplots_adjust(left=.13,right=.92,bottom=.65/height,top=1-1.7/height,
                            wspace=.50,hspace=.85/row_height)
        for row,partition in enumerate(['calibration','test']):
            for col,method in enumerate(methods):
                subset = selected[selected.partition.eq(partition)&selected.method.eq(method)]
                matrix = subset.pivot(index=['model','temperature'],columns='BBCH',values=metric).reindex(
                    index=pd.MultiIndex.from_tuples(order),columns=STAGES).to_numpy()
                im = heatmap(axes[row,col],matrix,labels,STAGES,cmap,norm,metric)
                axes[row,col].set_title(f'{partition.capitalize()} sites\n{LABELS[method]}',fontsize=11,pad=26)
        fig.suptitle(f'Pooled process calibration: {title}',x=.13,ha='left',fontsize=20,fontweight='bold',y=1-.12/height)
        fig.text(.13,1-.65/height,'One fit across calibration sites · original test sites excluded from fitting',fontsize=11)
        fig.text(.13,.36/height,'BBCH07 budburst · 65 flowering · 81 veraison · 89 maturity/harvest',fontsize=10)
        fig.text(.13,.14/height,'Equal-site errors on finite predictions; attainment includes every observation. Point estimates; no confidence intervals.',fontsize=9)
        cax = fig.add_axes([.947,.25,.014,.48])
        fig.colorbar(im,cax=cax)
        if smoke:
            fig.text(.995,.002,'SMOKE CHECK — REDUCED BUDGET',ha='right',fontsize=7,color='#a12828')
        name = prefix+metric.replace('_days','')
        fig.savefig(output/f'{name}.png',dpi=160)
        fig.savefig(output/f'{name}.pdf')
        book.savefig(fig)
        plt.close(fig)


def summarize_zones(directory, model, temperature):
    d = pd.read_csv(directory/'predictions.csv.gz',dtype={'site':str,'BBCH':str},keep_default_na=False,low_memory=False)
    d['predicted_date'] = pd.to_datetime(d.predicted_date.replace('',None))
    d['Date'] = pd.to_datetime(d.Date)
    d['error'] = (d.predicted_date-d.Date).dt.days
    d['absolute'] = d.error.abs()
    d['square'] = d.error**2
    d['attained'] = d.error.notna()
    rows = []
    for keys,group in d.groupby(['partition','method','BBCH','temperature_zone_id']):
        partition,method,stage,zone = keys
        sites = group.groupby('site').agg(mae=('absolute','mean'),mse=('square','mean'),
            bias=('error','mean'),attainment=('attained','mean'))
        rows.append(dict(model=model,temperature=temperature,partition=partition,method=method,BBCH=stage,
            temperature_zone_id=zone,environmental_zone=zone.replace('TZ','EZ'),n_observations=len(group),
            n_sites=len(sites),n_attained=int(group.attained.sum()),mae_days=sites.mae.mean(),
            rmse_days=np.sqrt(sites.mse.mean()),bias_days=sites.bias.mean(),
            attainment=group.attained.mean(),site_attainment=sites.attainment.mean()))
    return rows


def render_zones(zones, output, book, smoke=False):
    models = list(dict.fromkeys(zones.model))
    temperatures = list(dict.fromkeys(zones.temperature))
    for metric,title in [('mae_days','MAE (days)'),('bias_days','Signed error (days)')]:
        d = zones[zones.partition.eq('test')&zones.method.eq('low_bias_mae')]
        cmap,norm = scale(d[metric],metric)
        height = max(6.,len(temperatures)*(len(models)*.36+.8)+1.9)
        row_height = (height-2.35-.85*(len(temperatures)-1))/len(temperatures)
        fig,axes = plt.subplots(len(temperatures),4,figsize=(17,height),squeeze=False)
        fig.subplots_adjust(left=.12,right=.93,top=1-1.7/height,bottom=.65/height,
                            wspace=.5,hspace=.85/row_height)
        for r,temp in enumerate(temperatures):
            for c,stage in enumerate(STAGES):
                group = d[d.temperature.eq(temp)&d.BBCH.eq(stage)]
                matrix = group.pivot(index='model',columns='environmental_zone',values=metric).reindex(
                    index=models,columns=[f'EZ0{i}' for i in range(1,6)]).to_numpy()
                im = heatmap(axes[r,c],matrix,models,[f'EZ0{i}' for i in range(1,6)],cmap,norm,metric)
                axes[r,c].set_title(f'{temp} · BBCH{stage}',pad=25,fontsize=11)
        fig.suptitle(f'Original test sites by environmental zone: {title}',x=.12,ha='left',fontsize=18,y=1-.12/height,fontweight='bold')
        fig.text(.12,1-.65/height,'Low-bias MAE calibration · shared parameters across zones',fontsize=11)
        fig.text(.12,.16/height,'Equal-site errors; grey cells have no finite prediction pairs. Zone sample sizes are in zone_metrics.csv. No confidence intervals.',fontsize=10)
        fig.colorbar(im,cax=fig.add_axes([.951,.26,.012,.43]))
        if smoke:
            fig.text(.995,.002,'SMOKE CHECK — REDUCED BUDGET',ha='right',fontsize=7,color='#a12828')
        name = f'test_{metric.replace("_days","")}_by_environmental_zone'
        fig.savefig(output/f'{name}.png',dpi=160)
        fig.savefig(output/f'{name}.pdf')
        book.savefig(fig)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--allow-smoke',action='store_true')
    args = parser.parse_args()
    output = args.output
    status = json.loads((output/'status.json').read_text())
    run = json.loads((output/'run.json').read_text())
    if not status['complete'] or (run['smoke'] and not args.allow_smoke):
        raise ValueError('Require a complete verified run; smoke reports need explicit permission')
    zone_rows, fit_rows = [], []
    for model in run['models']:
        for temperature in run['temperatures']:
            directory = output/model/temperature
            marker = json.loads((directory/'complete.json').read_text())
            for name,expected in marker['artifacts'].items():
                if digest(directory/name) != expected:
                    raise ValueError(f'Artifact mismatch: {directory/name}')
            zone_rows.extend(summarize_zones(directory,model,temperature))
            fit = json.loads((directory/'low_bias_mae.json').read_text())
            fit_rows.append(dict(model=model,temperature=temperature,coverage_preserved=fit['coverage_preserved'],
                bias_target_met=fit['bias_target_met'],maximum_bias_excess_days=fit['maximum_bias_excess_days'],
                target_status=fit['target_status'],boundary_hits='|'.join(fit['boundary_hits'])))
    zones, fits = pd.DataFrame(zone_rows),pd.DataFrame(fit_rows)
    zones.to_csv(output/'zone_metrics.csv',index=False)
    fits.to_csv(output/'fit_status.csv',index=False)
    metrics = pd.read_csv(output/'metrics.csv',dtype={'BBCH':str})
    keys = ['model','temperature','partition','BBCH']
    baseline = metrics[metrics.method.eq('existing')].set_index(keys)
    change_rows = []
    for row in metrics[~metrics.method.eq('existing')].to_dict('records'):
        old = baseline.loc[tuple(row[k] for k in keys)]
        change_rows.append({**{k:row[k] for k in keys},'method':row['method'],
            **{f'delta_{m}':row[m]-old[m] for m in ['mae_days','rmse_days','bias_days','attainment','site_attainment']}})
    changes = pd.DataFrame(change_rows)
    changes.to_csv(output/'metric_changes.csv',index=False)
    with PdfPages(output/'pooled_calibration_comparison.pdf') as book:
        render_comparisons(metrics,output,book,smoke=run['smoke'])
        median = metrics[metrics.model.isin(['FL','FB'])]
        if not median.empty:
            render_comparisons(median,output,book,['existing','median_threshold','low_bias_mae'],'median_',smoke=run['smoke'])
        render_zones(zones,output,book,smoke=run['smoke'])
        figure_pages = book.get_pagecount()
    test_changes = changes[changes.method.eq('low_bias_mae')&changes.partition.eq('test')]
    excerpts = []
    for model in ['FL','FB']:
        for stage in STAGES:
            selected = metrics[metrics.model.eq(model)&metrics.temperature.eq('RAW')&metrics.BBCH.eq(stage)]
            if selected.empty:
                continue
            values = selected.set_index(['partition','method'])
            a,b,c,e = [values.loc[key] for key in [('calibration','existing'),('calibration','low_bias_mae'),
                ('test','existing'),('test','low_bias_mae')]]
            excerpts.append(f'| {model} | {stage} | {a.bias_days:.2f} → {b.bias_days:.2f} | '
                f'{a.mae_days:.2f} → {b.mae_days:.2f} | {c.mae_days:.2f} → {e.mae_days:.2f} |')
    population = pd.read_csv(output/'population.csv',dtype={'BBCH':str})
    cal_n = int(population.loc[population.partition.eq('calibration'),'n_observations'].sum())
    test_n = int(population.loc[population.partition.eq('test'),'n_observations'].sum())
    bound_text = ''
    certificate = output/'coverage_feasibility_bound.json'
    if certificate.exists():
        bound = json.loads(certificate.read_text())
        values = [r for r in bound['results'] if r['one_day_bias_target_impossible_under_full_attainment']]
        if values:
            descriptions = '; '.join(f"{r['model']} RAW: at most {r['site_weighted_bias_upper_bound_days']:.2f} days" for r in values)
            bound_text = f'''## Coverage constraint and maturity bias

For RAW forcing-only models, maintaining 100% maturity attainment limits the sum of the four thresholds to the lowest annual forcing among the calibration maturity site-years. Even an optimistic bound allowing three maximum daily forcing overshoots gives these upper bounds on equal-site mean maturity bias: **{descriptions}**. Consequently, the one-day bias target is incompatible with complete maturity attainment for these configurations under the fixed response functions and January 1 start, independently of optimizer convergence. This does not establish that the limiting observation is erroneous.

The [calibration-only feasibility certificate](coverage_feasibility_bound.json) records the derivation, source hashes, limiting site-year and prediction checks. [FL bounds](FL_RAW_coverage_bound.csv) and [FB bounds](FB_RAW_coverage_bound.csv) retain observation-level evidence.

'''
    text = f'''# Pooled process calibration on the preserved site split

The comparison uses {cal_n:,} cleaned calibration observations and {test_n:,} observations at the original test sites. Each model–temperature configuration has one shared parameter set across environmental zones. Test outcomes do not enter the new fitting objective or parameter selection. The method revision follows inspection of the existing experiment, so the test comparison is a post hoc reevaluation of that split.

**{int(fits.bias_target_met.sum())} of {len(fits)} configurations reach absolute equal-site mean calibration bias within one day at all four stages.** Calibration observation-weighted and site-weighted attainment are preserved in {int(fits.coverage_preserved.sum())} of {len(fits)} configurations. Unmet bias targets are recorded explicitly; optimizer failure to find a feasible solution is not proof of mathematical infeasibility.

Low-bias MAE fits reduce test MAE in {int((test_changes.delta_mae_days < -1e-10).sum())} of {len(test_changes)} model–temperature–stage comparisons. Test MAE changes range from {test_changes.delta_mae_days.min():+.2f} to {test_changes.delta_mae_days.max():+.2f} days. These are descriptive paired comparisons, not independent significance tests.

| RAW model | BBCH | Calibration bias, existing → new | Calibration MAE, existing → new | Test MAE, existing → new |
|---|---|---:|---:|---:|
{chr(10).join(excerpts)}

![Calibration and test signed error](bias.png)

![Calibration and test MAE](mae.png)

{bound_text}
## Methods and interpretation

The three main arms retain existing thresholds, recalibrate thresholds with the original mean-stage site-balanced RMSE objective (including its 1,000-day non-attainment error), or seek absolute stage bias ≤1 day and then minimize mean-stage site-balanced MAE subject to preserved calibration attainment. The new search uses {len(run['seeds'])} seed(s), {run['maxiter']} generations and a retry ceiling of {run['retry_maxiter']} generations. Every attempted search and its convergence status is saved. Function cardinals, start dates, process coupling and all non-threshold parameters remain fixed.

The FL/FB median benchmark uses equal-site-weighted medians of positive thermal requirements through observed calibration dates. Later-stage starts come from model predictions; observed preceding-stage dates never initialize predictions. Ineligible median inputs remain in evaluation and have an audit record. Median thermal requirements do not guarantee zero mean date error. Residual ML is not retrained or attached to the new process fits.

MAE and bias average within sites with finite predictions and then across sites; RMSE is the square root of the corresponding site-balanced mean squared error. Positive bias means late prediction. Attainment retains every observation in its denominator. The common-attainment tables compare each candidate and existing fit using exactly the same observations. Coverage-change records identify every observation whose attainment changes. Environmental-zone labels EZ01–EZ05 display the unchanged temperature-profile clusters.

All selected parameter sets pass replay against the original simulator, and all overall metrics pass independent pandas arithmetic. Original run artifacts and source code remain unchanged. Figures show point estimates without confidence intervals. Calibration-target compliance does not guarantee low test bias, lower MAE, or generalization beyond the sampled sites.

## Files

- [Complete figure book](pooled_calibration_comparison.pdf), [RMSE](rmse.pdf), [attainment](attainment.pdf).
- [All metrics](metrics.csv), [metric changes](metric_changes.csv), [matched-observation comparisons](matched_metrics.csv), [fit status](fit_status.csv).
- [Environmental-zone metrics and sample sizes](zone_metrics.csv), [test MAE by environmental zone](test_mae_by_environmental_zone.pdf), [test bias by environmental zone](test_bias_by_environmental_zone.pdf).
- [Median-threshold MAE comparison](median_mae.pdf), [population counts](population.csv), [coverage changes](coverage_changes.csv).
- Each model/temperature directory contains fit parameters, restarts, calibration locks, predictions, independent checks and artifact hashes. The run manifest records all input and fitting-code fingerprints.

Reproduce with `.venv/bin/python model_run/src/calibrate_pooled_sites.py --output NEW_DIRECTORY`, then `.venv/bin/python model_run/src/pooled_calibration_report.py NEW_DIRECTORY`. Existing matching run directories resume completed units after fingerprint verification.
'''
    if run['smoke']:
        text = '# SMOKE CHECK — REDUCED OPTIMIZATION BUDGET\n\n'+text
    (output/'README.md').write_text(text)
    artifacts = {p.name:digest(p) for p in output.iterdir() if p.is_file() and p.name not in {'.run.lock','report_manifest.json'}}
    (output/'report_manifest.json').write_text(json.dumps(dict(artifacts=artifacts,figure_pages=figure_pages,
        report_source=str(Path(__file__).resolve()),report_source_sha256=digest(Path(__file__))),indent=2)+'\n')
    print(json.dumps(dict(configurations=len(fits),bias_target_met=int(fits.bias_target_met.sum()),
        coverage_preserved=int(fits.coverage_preserved.sum()),test_mae_improved=int((test_changes.delta_mae_days < -1e-10).sum()),
        comparisons=len(test_changes)),indent=2))


if __name__ == '__main__':
    main()
