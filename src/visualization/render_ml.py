#!/usr/bin/env python3
"""Render ML-focused Figure 9 and supplementary bias from locked analysis rows.

Run via src/visualization/reproduce.py.
No model fitting, prediction changes, or new bootstrap estimation is performed.
"""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from common import _paper_style, _panel
from common import DATA, ROOT, MODELS, STAGES

SOURCE = DATA/'hybrid'
OUT = None
RAW, DEM = '#644583', '#ad6b20'
LABELS = [m + '-ML' for m in MODELS]
ANALYSIS = DATA/'ml'


def forest(ax, rows, labels, colour, xlim, overall=None):
    rows = list(rows.itertuples())
    for i, row in enumerate(rows):
        if i % 2 == 0:
            ax.axhspan(i-.5, i+.5, color='#f3f5f6', lw=0)
        ax.plot([row.ci_low,row.ci_high], [i,i], color=colour, lw=1.1)
        ax.plot(row.value, i, 'o', color=colour, ms=4)
    if overall is not None:
        y = len(rows)+.3
        ax.plot([overall.ci_low,overall.ci_high], [y,y], color='#203843', lw=1.5)
        ax.plot(overall.value, y, 'D', color='#203843', ms=5)
        ax.set_yticks([*range(len(rows)),y], [*labels,'All models'])
        ax.set_ylim(y+.6,-.5)
    else:
        ax.set_yticks(range(len(rows)),labels)
        ax.set_ylim(len(rows)-.5,-.5)
    ax.set_xlim(*xlim)
    ax.axvline(0,color='#7f8b91',lw=.8)
    ax.grid(axis='x',color='#e3e8eb',lw=.5)
    ax.set_axisbelow(True)
    ax.tick_params(axis='y',length=0,pad=4)
    for side in ['top','right','left']:
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color('#7f8b91')


def zone_matrix(ax, rows, cmap, norm, metric='gain', show_support=False):
    zones = [f'EZ{i:02d}' for i in range(1,6)]
    for i, zone in enumerate(zones):
        for j, stage in enumerate(STAGES):
            row = rows[rows.zone.eq(zone)&rows.BBCH.eq(stage)&rows.metric.eq(metric)].iloc[0]
            finite = np.isfinite(row.value)
            supported = row.ci_status == 'available'
            face = cmap(norm(row.value)) if finite and supported else '#eaecef' if finite else '#f6f7f8'
            ax.add_patch(Rectangle((j-.5,i-.5),1,1,facecolor=face,edgecolor='white',lw=1.1))
            ink = 'white' if finite and supported and np.dot(face[:3],[.2126,.7152,.0722])<.53 else '#182630'
            digits = 2 if metric=='gain' and norm.vmax<=2 else 1
            value = (0. if abs(row.value)<.5*10**(-digits) else row.value) if finite else np.nan
            top = f'{value:.{digits}f}' + ('*' if not supported else '') if finite else '—'
            if not finite:
                bottom = 'no data'
            elif show_support:
                bottom = f'n = {row.n_sites}'
            elif supported:
                bottom = f'{row.ci_low:.{digits}f} to {row.ci_high:.{digits}f}'
            else:
                bottom = f'g = {row.n_groups}'
            ax.text(j,i-.14,top,ha='center',va='center',color=ink)
            ax.text(j,i+.19,bottom,ha='center',va='center',color=ink)
    ax.set_xlim(-.5,3.5);ax.set_ylim(4.5,-.5)
    ax.set_xticks(range(4),STAGES);ax.xaxis.tick_top()
    ax.set_yticks(range(5),zones);ax.tick_params(length=0,pad=5)
    for spine in ax.spines.values():spine.set_visible(False)


def horizontal_scale(fig, rect, cmap, norm, label, ticks):
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),
                     cax=fig.add_axes(rect), orientation='horizontal', ticks=ticks)
    cb.set_label(label,labelpad=3);cb.outline.set_visible(False)


def render_focused_figures():
    protocol=json.loads((ANALYSIS/'analysis.json').read_text())
    for name,expected in protocol['output_sha256'].items():
        assert digest(ANALYSIS/name)==expected, f'Analysis output changed: {name}'
    models = pd.read_csv(ANALYSIS/'model_effects.csv',dtype={'BBCH':str})
    zones = pd.read_csv(ANALYSIS/'zone_effects.csv',dtype={'BBCH':str})
    support = pd.read_csv(ANALYSIS/'support.csv',dtype={'BBCH':str})
    gain_cmap = LinearSegmentedColormap.from_list('ml_gain',['#f5f9f7','#a4cdc2','#286d62'])
    mae_cmap = LinearSegmentedColormap.from_list('hybrid_mae',['#f4f8fb','#a2c0d3','#294f73'])
    m=models[models.comparison.eq('ML_RAW')&models.metric.eq('gain')]
    z=zones[zones.comparison.eq('ML_RAW')]
    fig=plt.figure(figsize=(180/25.4,180/25.4))
    a=fig.add_axes([.175,.59,.32,.315]);b=fig.add_axes([.685,.565,.295,.34])
    c=fig.add_axes([.095,.14,.40,.30]);d=fig.add_axes([.585,.14,.40,.30])
    values=m[m.BBCH.ne('ALL')].pivot(index='model',columns='BBCH',values='value').loc[MODELS,STAGES]
    matrix(a,values.to_numpy(),gain_cmap,Normalize(0,12))
    _panel(a,'a',1.135)
    horizontal_scale(fig,[.175,.552,.32,.012],gain_cmap,Normalize(0,12),'ML gain (d)',[0,4,8,12])
    all_models=z[z.zone.eq('ALL')&z.BBCH.eq('ALL')&z.metric.eq('gain')].iloc[0]
    forest(b,m[m.BBCH.eq('ALL')].set_index('model').loc[MODELS],LABELS,RAW,(0,7.5),all_models)
    b.set_xlabel('Overall ML gain (d)');b.set_xticks([0,2,4,6]);_panel(b,'b',1.125)
    zone_matrix(c,z,gain_cmap,Normalize(0,12));_panel(c,'c',1.125)
    c.set_xlabel('ML gain and 95% interval (d)',labelpad=7)
    zone_matrix(d,z,mae_cmap,Normalize(0,20),metric='hybrid_mae',show_support=True);_panel(d,'d',1.125)
    horizontal_scale(fig,[.585,.09,.40,.012],mae_cmap,Normalize(0,20),'Hybrid MAE (d)',[0,5,10,15,20])
    fig.text(.095,.061,'* Fewer than 10 groups; g = groups',va='center')
    fig.text(.095,.031,'n = sites; all panels use RAW temperature',va='center')
    save(fig,'ml_accuracy_gains')
    # Figure 10 isolates the temperature correction within the hybrid workflow.
    cmap=LinearSegmentedColormap.from_list('dem_ml',['#9b6536','#faf8f3','#357a80'])
    norm=TwoSlopeNorm(vmin=-1.5,vcenter=0,vmax=1.5)
    m=models[models.comparison.eq('DEM_ML')&models.metric.eq('gain')]
    z=zones[zones.comparison.eq('DEM_ML')]
    fig=plt.figure(figsize=(180/25.4,163/25.4))
    a=fig.add_axes([.175,.56,.30,.355]);b=fig.add_axes([.73,.61,.24,.28])
    c=fig.add_axes([.175,.125,.80,.285])
    all_models=z[z.zone.eq('ALL')&z.BBCH.eq('ALL')&z.metric.eq('gain')].iloc[0]
    forest(a,m[m.BBCH.eq('ALL')].set_index('model').loc[MODELS],LABELS,'#357a80',(-1,1.2),all_models)
    a.set_xlabel('Overall DEM gain in hybrids (d)');a.set_xticks([-1,0,1]);_panel(a,'a',1.13)
    stage=z[z.zone.eq('ALL')&z.BBCH.ne('ALL')&z.metric.eq('gain')].set_index('BBCH').loc[STAGES]
    forest(b,stage,['BBCH '+s for s in STAGES],'#357a80',(-.8,1.05))
    b.set_xticks([-.5,0,.5]);b.set_xlabel('DEM gain in hybrids (d)');_panel(b,'b',1.26)
    ss=support[support.comparison.eq('DEM_ML')].set_index('BBCH')
    for i,s in enumerate(STAGES):
        b.text(.96,i,f'{100*ss.loc[s,"n_sites_improved"]/ss.loc[s,"n_sites"]:.0f}%',ha='right',va='center')
    b.text(.96,-.83,'Sites improved',ha='right',va='center')
    zone_matrix(c,z,cmap,norm);_panel(c,'c',1.14)
    horizontal_scale(fig,[.49,.07,.485,.012],cmap,norm,'DEM gain in hybrids and 95% interval (d)',[-1.5,0,1.5])
    fig.text(.175,.068,'* Fewer than 10 groups',va='center')
    fig.text(.175,.037,'g = groups',va='center')
    save(fig,'dem_effects_on_ml')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix(ax, values, cmap, norm, labels=True, paired=False, signed=False):
    im = ax.imshow(values, cmap=cmap, norm=norm, aspect='auto')
    ax.set_yticks(range(10), LABELS if labels else [''] * 10)
    ax.set_xticks(range(values.shape[1]), ['R', 'D'] * 4 if paired else STAGES)
    ax.xaxis.tick_top()
    ax.tick_params(length=0, pad=4)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for i in range(10):
        for j in range(values.shape[1]):
            value = values[i, j]
            rgb = cmap(norm(value))[:3]
            ink = 'white' if np.dot(rgb, [.2126, .7152, .0722]) < .53 else '#182630'
            display = 0. if abs(value) < .05 else value
            ax.text(j, i, f'{display:+.1f}' if signed else f'{value:.1f}',
                    ha='center', va='center', color=ink)
    for j in np.arange(.5, values.shape[1], 1):
        ax.axvline(j, color='white', lw=.5)
    for i in np.arange(.5, 10, 1):
        ax.axhline(i, color='white', lw=.5)
    ax.axhline(1.5, color='white', lw=2.)
    if paired:
        for j, stage in enumerate(STAGES):
            ax.text(2*j+.5, 1.105, stage, transform=ax.get_xaxis_transform(),
                    ha='center', va='bottom')
            if j:
                ax.axvline(2*j-.5, color='white', lw=2.)
        for label, colour in zip(ax.get_xticklabels(), [RAW, DEM] * 4):
            label.set_color(colour)
    return im


def save(fig, name):
    for suffix in ['pdf', 'png']:
        fig.savefig(OUT / f'{name}.{suffix}', dpi=300, facecolor='white')
    plt.close(fig)


def render(output):
    global OUT
    OUT=output
    OUT.mkdir(parents=True, exist_ok=True)
    _paper_style()
    inputs = [SOURCE / n for n in ['stage_metrics.csv', 'paired_effects.csv']]
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    # Check the sealed analysis before drawing from its derived rows.
    sealed = manifest['output_sha256']
    for path in inputs:
        key = next((k for k in sealed if k == path.name or k.endswith('/' + path.name)), None)
        assert key is not None and digest(path) == sealed[key], f'Unsealed source: {path}'
    metrics = pd.read_csv(inputs[0], dtype={'BBCH': str})
    effects = pd.read_csv(inputs[1], dtype={'BBCH': str})
    hybrid = metrics[metrics.method.eq('tabm') & metrics.metric_view.eq('scoring')]
    ml = effects[effects.comparison.isin(['ML_RAW', 'ML_DEM']) &
                 effects.stratum.eq('overall') & effects.level.eq('all')]
    test = ml[ml.partition.eq('test') & ml.metric.eq('mae_days')].copy()
    assert len(test) == 100 and not test.duplicated(['model', 'comparison', 'BBCH']).any()
    assert test.ci_status.eq('available').all()
    assert np.allclose(test.baseline - test.candidate, test.benefit, atol=1e-10)
    for row in test[test.BBCH.ne('ALL')].itertuples():
        h = hybrid[hybrid.partition.eq('test') & hybrid.model.eq(row.model) &
                   hybrid.temperature.eq(row.comparison[3:]) & hybrid.BBCH.eq(row.BBCH)]
        assert len(h) == 1 and np.isclose(h.iloc[0].mae_days, row.candidate, atol=1e-10)
    render_focused_figures()
    # Retain all four original bias slices in a separate supplementary figure.
    fig = plt.figure(figsize=(180/25.4, 159/25.4))
    cmap = LinearSegmentedColormap.from_list('signed_bias', ['#654982', '#faf9f5', '#b1742c'])
    for (temperature, partition), letter, rect in zip(
            [('RAW', 'calibration'), ('RAW', 'test'), ('DEM', 'calibration'), ('DEM', 'test')],
            'abcd', [[.175,.58,.32,.32],[.565,.58,.32,.32],[.175,.13,.32,.32],[.565,.13,.32,.32]]):
        ax = fig.add_axes(rect)
        values = hybrid[hybrid.temperature.eq(temperature) & hybrid.partition.eq(partition)].pivot(
            index='model', columns='BBCH', values='bias_days').loc[MODELS, STAGES]
        im = matrix(ax, values.to_numpy(), cmap, TwoSlopeNorm(vmin=-3, vcenter=0, vmax=3),
                    labels=letter in 'ac', signed=True)
        ax.set_xlabel(temperature + (' apparent calibration' if partition == 'calibration' else ' held-out test'), labelpad=8)
        _panel(ax, letter, 1.13)
    cb = fig.colorbar(im, cax=fig.add_axes([.922,.20,.018,.63]), ticks=[-3,-2,-1,0,1,2,3])
    cb.set_label('Hybrid signed bias (d)', labelpad=5)
    cb.outline.set_visible(False)
    save(fig, 'ml_bias_supplement')
    hybrid.to_csv(OUT / 'hybrid_metrics.csv', index=False)
    ml.to_csv(OUT / 'ml_paired_effects.csv', index=False)
