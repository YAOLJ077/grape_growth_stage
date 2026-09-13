"""Figures 5 and S1 from locked, equal-site metric tables."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from common import DATA,MODELS,STAGES,_paper_style,_panel

def render(FIG):
    OUT=FIG
    stage=pd.read_csv(DATA/'pbm/stage_metrics.csv',dtype={'BBCH':str})
    overall=pd.read_csv(DATA/'pbm/overall_metrics.csv',dtype={'BBCH':str})
    raw=overall[overall.temperature.eq('RAW') & overall.metric_view.eq('scoring')]
    _paper_style()
    selected = stage[stage.metric_view.eq('scoring') & stage.temperature.eq('RAW')]
    styles=[('calibration',-.18,'#e5d3bf','#9a744e','Calibration'),
            ('test',.18,'#287d87','#287d87','Test')]
    def bars(ax, table, metric, label_models):
        signed=metric=='bias_days'
        for partition,offset,fill,edge,label in styles:
            values=table[table.partition.eq(partition)].set_index('model').reindex(MODELS)[metric]
            if not np.isfinite(values).all():raise ValueError('Missing bar value')
            baseline=0 if signed else 8
            if not signed and not values.between(8,18).all():raise ValueError('MAE outside annotated bar range')
            y=np.arange(10)+offset
            ax.barh(y, values-baseline, left=baseline, height=.31, color=fill,
                    edgecolor=edge,linewidth=.45,zorder=2)
            for yy,value in zip(y,values):
                negative=signed and value<0
                label=('0.0' if signed and abs(value)<.05 else f'{value:+.1f}' if signed else f'{value:.1f}')
                ax.text(value+(-.18 if negative else .16),yy,label,ha='right' if negative else 'left',
                    va='center',fontsize=8,color='#283a3d',zorder=3)
        ax.set_xlim((-12,8) if signed else (8,20));ax.set_ylim(9.6,-.6)
        ax.set_yticks(np.arange(10),MODELS if label_models else ['']*10)
        ax.tick_params(axis='y',length=0,pad=5)
        ax.set_xticks([-10,-5,0,5] if signed else [8,12,16,20])
        ax.tick_params(axis='x',length=3,width=.6)
        ax.set_xlabel('Bias (d)' if signed else 'MAE (d)',labelpad=5)
        for spine in ['left','right','top']:ax.spines[spine].set_visible(False)
        ax.spines['bottom'].set_color('#777777');ax.spines['bottom'].set_linewidth(.6)
        if signed:ax.axvline(0,color='#92999b',lw=.65,zorder=1)
        for yy in [1.5,5.5]:ax.axhline(yy,color='#e0e3e4',lw=.5,zorder=0)
    plotted=[]
    for stem,signed in [('pbm_mae',False),('pbm_bias_supplement',True)]:
        n=4 if signed else 5
        fig=plt.figure(figsize=(180/25.4,132/25.4))
        grid=fig.add_gridspec(1,n,left=.14,right=.985,bottom=.13,top=.83,wspace=.24,
            width_ratios=[1]*n if signed else [1.18,1,1,1,1])
        panels=STAGES if signed else ['ALL',*STAGES]
        for col,stage_code in enumerate(panels):
            ax=fig.add_subplot(grid[0,col])
            table=raw if stage_code=='ALL' else selected[selected.BBCH.eq(stage_code)]
            metric='bias_days' if signed else 'mae_days'
            for record in table.itertuples():
                value=getattr(record,metric)
                label=('0.0' if signed and abs(value)<.05 else f'{value:+.1f}' if signed else f'{value:.1f}')
                plotted.append(dict(figure=stem,panel='abcde'[col],BBCH=stage_code,model=record.model,
                    partition=record.partition,metric=metric,value=value,label=label))
            bars(ax,table,metric,col==0)
            _panel(ax,'abcde'[col],y=1.055)
        handles=[Patch(facecolor=fill,edgecolor=edge,linewidth=.6,label=label)
                 for _,_,fill,edge,label in styles]
        fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.57,.965),ncol=2,
            frameon=False,handlelength=1.5,handletextpad=.5,columnspacing=2)
        for suffix in ['pdf','png']:fig.savefig(FIG/f'{stem}.{suffix}',dpi=300)
        plt.close(fig)
    pd.DataFrame(plotted).to_csv(OUT/'plotted_values.csv',index=False)
