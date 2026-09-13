#!/usr/bin/env python3
"""Zone comparison with expanded 0–30 d errors and a separate high-error strip."""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from common import _paper_style,_panel
from common import COLORS


def render(site,zone,output):
    _paper_style();rng=np.random.default_rng(20260913)
    fig=plt.figure(figsize=(180/25.4,150/25.4))
    outer=fig.add_gridspec(2,2,left=.075,right=.985,bottom=.10,top=.84,hspace=.48,wspace=.24)
    plotted=[]
    for cell,stage,letter in zip(outer,['07','65','81','89'],'abcd'):
        grid=cell.subgridspec(1,3,width_ratios=[4.4,1.4,1.65],wspace=.15)
        main=fig.add_subplot(grid[0]);tail=fig.add_subplot(grid[1],sharey=main)
        labels=fig.add_subplot(grid[2],sharey=main)
        for ax,limits,ticks in [(main,(0,30),[0,10,20,30]),(tail,(30,85),[50,80])]:
            ax.set(xlim=limits,ylim=(4.5,-.6));ax.set_xticks(ticks)
            ax.spines[['left','right','top']].set_visible(False)
            ax.tick_params(axis='y',length=0,labelleft=ax is main)
        main.set_yticks(range(5),[f'EZ{k:02d}' for k in range(1,6)])
        main.set_xlabel('Site MAE (d)')
        labels.set(xlim=(0,1),ylim=(4.5,-.6));labels.axis('off')
        labels.text(.02,-.76,'Median',ha='left',va='center',fontsize=8)
        labels.text(.99,-.76,'n',ha='right',va='center',fontsize=8)
        for k,z in enumerate(['TZ01','TZ02','TZ03','TZ04','TZ05']):
            rows=site[site.BBCH.eq(stage)&site.temperature_zone_id.eq(z)&site.mae_days.notna()]
            r=zone[zone.BBCH.eq(stage)&zone.temperature_zone_id.eq(z)&zone.metric.eq('abs_error')].iloc[0]
            assert len(rows)==r.n_sites
            for ax in [main,tail]:ax.hlines(k,*ax.get_xlim(),color='#e6e9e9',lw=.45,zorder=0)
            if len(rows):
                x=rows.mae_days.to_numpy();y=k+rng.uniform(-.20,.20,len(x))
                assert np.isfinite(x).all() and (x>=0).all() and (x<=85).all()
                for ax,mask in [(main,x<=30),(tail,x>30)]:
                    ax.scatter(x[mask],y[mask],s=5,color='#b7c0c3',edgecolor='none',alpha=.6,zorder=1)
                median=float(np.median(x));q25,q75=np.quantile(x,[.25,.75])
                groups=rows.group_id.nunique();assert groups==r.n_groups
                supported=groups>=10
                for ax in [main,tail]:
                    lo,hi=ax.get_xlim();a=max(lo,q25);b=min(hi,q75)
                    if a<=b:ax.plot([a,b],[k,k],color=COLORS[k],lw=1.4,zorder=4)
                target=main if median<=30 else tail
                target.scatter(median,k,marker='D',s=24,facecolor=COLORS[k] if supported else 'white',edgecolor=COLORS[k],lw=1,zorder=5)
                labels.text(.02,k,f'{median:.1f}',ha='left',va='center',fontsize=8,color='#253238')
                labels.text(.99,k,str(len(rows)),ha='right',va='center',fontsize=8,color='#637075')
                plotted.append(dict(BBCH=stage,zone=z,median_site_mae=median,q25_site_mae=q25,q75_site_mae=q75,
                    mean_site_mae=r.value,n_sites=len(rows),n_groups=groups,n_sites_above_30=int((x>30).sum()),maximum_site_mae=float(x.max())))
            else:
                main.text(1,k,'No observations',va='center',fontsize=8,color='#778186')
                labels.text(.99,k,'0',ha='right',va='center',fontsize=8,color='#637075')
        # Slashes explicitly mark the change in horizontal scale between strips.
        for ax,xpos in [(main,1),(tail,0)]:
            ax.plot([xpos,xpos],[-.008,.008],transform=ax.transAxes,marker=[(-1,-.6),(1,.6)],
                markersize=5,linestyle='none',color='#637075',mew=.7,clip_on=False)
        _panel(main,letter,y=1.17)
    handles=[Line2D([],[],ls='none',marker='o',mfc='#b7c0c3',mec='none',ms=3,label='Individual site'),
        Line2D([],[],color='#357687',lw=1.3,marker='D',mfc='#357687',ms=4,label='Median and interquartile range'),
        Line2D([],[],ls='none',marker='D',mfc='white',mec='#357687',ms=4,label='Fewer than 10 groups')]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.52,.995),frameon=False,ncol=3,handlelength=1.4,columnspacing=1.4)
    for ext in ['pdf','png']:fig.savefig(output.with_suffix('.'+ext),dpi=300)
    plt.close(fig)
    return pd.DataFrame(plotted)
