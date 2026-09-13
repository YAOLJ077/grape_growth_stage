#!/usr/bin/env python3
"""Publication figures and source rows for the paired DEM analysis."""
from pathlib import Path
import json
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from common import _paper_style,_panel
from common import DATA,STAGES,MODELS,digest
OUT=DATA/'dem'
FIG=None

STAGE_COLORS=['#35678d','#b17a29','#4f8875','#935477']
CLASS_COLORS=['#b4c6d4','#628ba2','#203f55']
MARKERS=['o','s','D','^']

def clean(ax,xlim=None):
    for side in ['top','right','left']:ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color('#8f999e');ax.spines['bottom'].set_linewidth(.6)
    ax.tick_params(axis='y',length=0,pad=5)
    ax.tick_params(axis='x',length=3,color='#8f999e')
    ax.axvline(0,color='#66737a',lw=.7,zorder=0)
    ax.grid(axis='x',color='#e9ecee',lw=.5);ax.set_axisbelow(True)
    if xlim:ax.set_xlim(*xlim)

def point(ax,row,y,color='#35678d',marker='o',size=4):
    if not np.isfinite(row.value):return
    supported=np.isfinite(row.ci_low) and np.isfinite(row.ci_high)
    if supported:ax.plot([row.ci_low,row.ci_high],[y,y],color=color,lw=1.05,alpha=.85,zorder=2)
    ax.plot(row.value,y,marker=marker,markersize=size,color=color,markerfacecolor=color if supported else 'white',markeredgewidth=.85,zorder=3)

def one(data,stratum,level,stage,metric='benefit'):
    x=data[data.stratum.eq(stratum)&data.level.eq(level)&data.BBCH.eq(stage)&data.metric.eq(metric)]
    assert len(x)==1,(stratum,level,stage,metric)
    return x.iloc[0]

def save(fig,name):
    for ext in ['pdf','png']:fig.savefig(FIG/f'{name}.{ext}',dpi=240,facecolor='white')
    plt.close(fig)

def stage_handles():return [Line2D([],[],color=c,marker=m,lw=0,label=f'BBCH {s}',markersize=4) for c,m,s in zip(STAGE_COLORS,MARKERS,STAGES)]

def grouped_stage(ax,data,stratum,levels,labels,xlim):
    for j,s in enumerate(STAGES):
        for i,level in enumerate(levels):
            row=one(data,stratum,level,s);point(ax,row,len(levels)-1-i+(1.5-j)*.16,STAGE_COLORS[j],MARKERS[j],3.6)
    ax.set_yticks(range(len(levels)),labels[::-1]);ax.set_ylim(-.55,len(levels)-.45)
    clean(ax,xlim);ax.set_xlabel('MAE reduction (d)')

def render(output):
    global FIG
    FIG=output
    FIG.mkdir(exist_ok=True);_paper_style()
    d=pd.read_csv(OUT/'paired_effects.csv',dtype={'BBCH':str});models=pd.read_csv(OUT/'model_effects.csv',dtype={'BBCH':str})
    dist=pd.read_csv(OUT/'site_benefit_distribution.csv',dtype={'BBCH':str}).set_index('BBCH')
    cuts=json.loads((OUT/'analysis.json').read_text())['terrain_cuts'];plotted=[]
    fig=plt.figure(figsize=(180/25.4,175/25.4))
    a=fig.add_axes([.18,.57,.30,.35]);b=fig.add_axes([.67,.57,.28,.35]);c=fig.add_axes([.18,.12,.30,.30]);e=fig.add_axes([.72,.12,.23,.30])
    order=MODELS
    m=models[models.cohort.eq('common_all_twenty')&models.BBCH.eq('ALL')&models.metric.eq('benefit')].set_index('model')
    for i,name in enumerate(order):
        row=m.loc[name];y=len(order)-i;point(a,row,y);a.text(2.62,y,f'{row.value:.2f}',ha='right',va='center');plotted.append(dict(figure='dem_benefits',panel='a',model=name,**row.to_dict()))
    total=one(d,'all','all','ALL');point(a,total,-.4,'#172f42','D',5);a.text(2.62,-.4,f'{total.value:.2f}',ha='right',va='center')
    a.set_yticks([*range(len(order),0,-1),-.4],[*order,'All models']);a.set_ylim(-1.3,11.2);clean(a,(-.15,2.75));a.set_xticks([0,1,2]);a.set_xlabel('Overall MAE reduction (d)');_panel(a,'a',1.035)
    a.text(2.62,11.1,'Days',ha='right',va='center')
    for i,s in enumerate(STAGES):
        row=one(d,'all','all',s);y=3-i;point(b,row,y,STAGE_COLORS[i],MARKERS[i],5)
        pct=100*dist.loc[s,'n_improved']/dist.loc[s,'n_sites'];b.text(3.00,y,f'{pct:.0f}%',ha='right',va='center')
        b.text(row.value,y+.23,f'{row.value:.2f} d',ha='center',va='bottom',color=STAGE_COLORS[i]);plotted.append(dict(figure='dem_benefits',panel='b',**row.to_dict(),percent_improved=pct))
    b.text(3.00,3.76,'Sites improved',ha='right',va='center');b.set_yticks([3,2,1,0],['Budburst','Flowering','Veraison','Maturity/harvest']);b.set_ylim(-.55,4);clean(b,(-.15,3.15));b.set_xticks([0,1,2]);b.set_xlabel('MAE reduction (d)');_panel(b,'b',1.035)
    q=cuts['site_minus_grid_elevation_m']['cutpoints'];labels=[f'≤ {q[0]:.1f}',f'{q[0]:.1f} to {q[1]:.1f}',f'> {q[1]:.1f}']
    grouped_stage(c,d,'site_minus_grid_elevation_m_class',['low','middle','high'],labels,(-3,7.5));c.set_ylabel('Site minus grid elevation (m)',labelpad=4);c.set_xticks([-2,0,2,4,6]);_panel(c,'c',1.035)
    variables=[('absolute_elevation_mismatch_m_class','Elevation\nmismatch'),('dem_local_std_m_class','Local elevation\nvariability'),('sill_m2_class','Regional\nsill')]
    for i,(col,label) in enumerate(variables):
        for j,level in enumerate(['low','middle','high']):
            row=one(d,col,level,'ALL');point(e,row,2-i+(1-j)*.2,CLASS_COLORS[j],['o','s','D'][j],4.4)
            plotted.append(dict(figure='dem_benefits',panel='d',**row.to_dict()))
    e.set_yticks([2,1,0],[x[1] for x in variables]);e.set_ylim(-.6,2.6);clean(e,(-.65,3.4));e.set_xticks([0,1,2,3]);e.set_xlabel('Overall MAE reduction (d)');_panel(e,'d',1.035)
    fig.legend(handles=stage_handles(),loc='center',bbox_to_anchor=(.5,.495),ncol=4,frameon=False,columnspacing=1.6,handletextpad=.45)
    fig.legend(handles=[Line2D([],[],color=col,marker=marker,lw=0,label=level,markersize=4) for col,marker,level in zip(CLASS_COLORS,['o','s','D'],['Low','Middle','High'])],loc='center',bbox_to_anchor=(.76,.039),ncol=3,frameon=False,columnspacing=.85,handletextpad=.35)
    fig.text(.18,.035,'Positive values indicate improvement',va='center')
    save(fig,'dem_benefits')
    # Supplementary stage-specific terrain patterns use common axes.
    fig,axes=plt.subplots(3,2,figsize=(180/25.4,190/25.4));fig.subplots_adjust(left=.18,right=.98,bottom=.065,top=.90,wspace=.72,hspace=.62)
    variables=[('absolute_elevation_mismatch_m','Absolute elevation mismatch (m)'),('dem_local_std_m','Local elevation variability (m)'),('sill_m2','Regional sill (m²)'),('dem_elevation_m','Site elevation (m)'),('northness','Northness'),('eastness','Eastness')]
    for ax,(variable,label),letter in zip(axes.flat,variables,'abcdef'):
        q=cuts[variable]['cutpoints'];fmt='.0f' if variable=='sill_m2' else '.1f' if variable not in ['northness','eastness'] else '.2f'
        labels=[f'≤ {q[0]:{fmt}}',f'{q[0]:{fmt}} to {q[1]:{fmt}}',f'> {q[1]:{fmt}}']
        grouped_stage(ax,d,variable+'_class',['low','middle','high'],labels,(-4.5,6.2));ax.set_ylabel(label);ax.set_xticks([-4,-2,0,2,4,6]);_panel(ax,letter,1.065)
    fig.legend(handles=stage_handles(),loc='upper center',bbox_to_anchor=(.52,.984),ncol=4,frameon=False,columnspacing=1.8,handletextpad=.4)
    save(fig,'dem_terrain_stages')
    # Metric changes: retain stage-specific signed errors and RMSE together.
    fig,axes=plt.subplots(1,2,figsize=(180/25.4,85/25.4));fig.subplots_adjust(left=.18,right=.97,bottom=.23,top=.78,wspace=.5)
    for ax,metric,label,letter in zip(axes,['bias','rmse'],['Signed bias (d)','RMSE (d)'],'ab'):
        for i,s in enumerate(STAGES):
            raw=one(d,'all','all',s,'raw_'+metric);dem=one(d,'all','all',s,'dem_'+metric);y=3-i
            ax.plot([raw.value,dem.value],[y,y],color='#bfc8cd',lw=1.1)
            for row,color,marker in [(raw,'#a5743f','o'),(dem,'#386f80','D')]:
                ax.plot(row.value,y,marker=marker,color=color,ms=4.5)
                ax.text(row.value,y+(.18 if marker=='o' else -.18),f'{row.value:.2f}',color=color,ha='center',va='bottom' if marker=='o' else 'top')
                plotted.append(dict(figure='dem_bias_rmse',panel=letter,**row.to_dict()))
        ax.set_yticks([3,2,1,0],['BBCH 07','BBCH 65','BBCH 81','BBCH 89']);ax.set_ylim(-.5,3.7);clean(ax,(-4.8,2) if metric=='bias' else (12.8,19));ax.set_xlabel(label);_panel(ax,letter,1.06)
    fig.legend(handles=[Line2D([],[],color=c,marker=m,lw=0,label=l,ms=4.5) for c,m,l in [('#a5743f','o','RAW'),('#386f80','D','DEM-corrected')]],loc='upper center',bbox_to_anchor=(.53,.985),ncol=2,frameon=False)
    save(fig,'dem_bias_rmse')
    pd.DataFrame(plotted).to_csv(FIG/'dem_figure_values.csv',index=False)
    # All regional effects, including sparse strata, in a compact booktabs table.
    rows=[r'\begin{longtable}{@{}lcrrr@{}}',r'\caption{Paired DEM effects by environmental zone. MAE reduction is the mean across ten fixed PMBs, with sites and stages weighted as described in the main text. Intervals are pointwise 95\% original-group bootstrap intervals; a dash denotes insufficient support. Counts refer to the common twenty-arm cohort.}\label{tab:dem_zone_effects}\\',r'\toprule',r'Zone & BBCH & Sites/groups & MAE reduction, d & 95\% interval, d \\',r'\midrule\endfirsthead',r'\toprule Zone & BBCH & Sites/groups & MAE reduction, d & 95\% interval, d \\ \midrule\endhead']
    for zone in ['TZ01','TZ02','TZ03','TZ04','TZ05']:
        for stage in STAGES:
            row=one(d,'temperature_zone_id',zone,stage)
            value=f'{row.value:.2f}' if np.isfinite(row.value) else '---';ci=f'{row.ci_low:.2f} to {row.ci_high:.2f}' if np.isfinite(row.ci_low) else '---'
            rows.append(f'{zone.replace("TZ","EZ")} & {stage} & {row.n_sites}/{row.n_groups} & {value} & {ci} '+r'\\')
        rows.append(r'\addlinespace')
    rows.extend([r'\bottomrule',r'\end{longtable}']);(FIG/'zone_effects.tex').write_text('\n'.join(rows)+'\n')
    print('Rendered three DEM figures and environmental-zone support table.')
