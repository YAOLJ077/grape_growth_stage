"""Figures 6 and 7 from frozen paired summaries and site-level errors."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from common import DATA,_paper_style
from render_zone_distribution import render as render_zone_distribution
FAMILIES=[('forcing_response','FL','FB'),('chilling_response','CL','CB'),('interaction','S','P'),('chilling_addition','F','C + F')]
def render(FIG):
    OUT=FIG
    summary=pd.read_csv(DATA/'structure/function_performance.csv',dtype={'BBCH':str})
    mapped=pd.read_csv(DATA/'structure/cb_fl_s_site_metrics.csv',dtype={'BBCH':str,'group_id':str})
    zone=pd.read_csv(DATA/'structure/cb_fl_s_zone_metrics.csv',dtype={'BBCH':str})
    _paper_style()
    fig,ax=plt.subplots(figsize=(180/25.4,80/25.4))
    fig.subplots_adjust(left=.32,right=.985,bottom=.18,top=.92)
    names=['Forcing response','Chilling response','Chilling–forcing interaction','Process structure']
    display_labels=[('Linear','Beta'),('Triangular','Beta'),('Sequential','Parallel'),('Forcing-only','Chilling–forcing')]
    function_labels=[]
    for k,((family,left,right),name) in enumerate(zip(FAMILIES,names)):
        table=summary[summary.family.eq(family)&summary.BBCH.eq('ALL')].set_index('metric')
        a,b=table.loc['left_abs','value'],table.loc['right_abs','value']
        ax.plot([a,b],[k,k],color='#bbc3c5',lw=1.2,zorder=1)
        for value,code,label,fill,marker,offset in [(a,left,display_labels[k][0],'#9a744e','o',-.20),(b,right,display_labels[k][1],'#287d87','D',.20)]:
            ax.scatter(value,k,s=28,color=fill,marker=marker,zorder=3)
            ax.text(value,k+offset,f'{label}  {value:.2f}',ha='center',va='center',color=fill,fontsize=8)
            function_labels.append(dict(family=family,level=code,display_label=label,mae_days=value))
    ax.set(xlim=(11,14),ylim=(3.55,-.55),xlabel='Overall MAE (d)')
    ax.set_xticks([11,11.5,12,12.5,13,13.5,14])
    ax.set_yticks(range(4),names);ax.tick_params(axis='y',length=0,pad=12)
    ax.spines[['left','right','top']].set_visible(False)
    for ext in ['pdf','png']:fig.savefig(FIG/f'function_performance.{ext}',dpi=300)
    plt.close(fig)
    pd.DataFrame(function_labels).to_csv(OUT/'function_plotted_values.csv',index=False)
    plotted=render_zone_distribution(mapped,zone,FIG/'cb_fl_s_spatial')
    plotted.to_csv(OUT/'cb_fl_s_zone_plotted_values.csv',index=False)
