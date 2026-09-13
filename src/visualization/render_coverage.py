#!/usr/bin/env python3
"""Stage-specific observation availability in the frozen primary test partition."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.lines import Line2D
from common import _paper_style,_panel
from render_environment import draw_map,BOUNDARIES
from common import DATA

ROOT=Path(__file__).resolve().parents[2]
OUT=None
STAGES=['07','65','81','89']
COLORS=['#d4e7ee','#9dc7d5','#619fae','#357687','#15505f']
LABELS=['1–5','6–10','11–25','26–50','>50']
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def render(output):
    global OUT
    OUT=output
    OUT.mkdir(parents=True,exist_ok=True)
    observations=DATA/'observations/test_observations.csv.gz'
    inventory=DATA/'environment/environmental_zone_sites.csv'
    events=pd.read_csv(observations,dtype={'BBCH':str,'site':str})
    sites=pd.read_csv(inventory,dtype={'site':str,'group_id':str})
    sites=sites[sites.partition.eq('test')].copy()
    assert len(events)==15146 and len(sites)==635 and not sites.site.duplicated().any()
    assert events.partition.eq('test').all() and set(events.BBCH)==set(STAGES)
    assert not events.observation_id.duplicated().any()
    assert set(events.site)==set(sites.site)
    keys=['site','lat','lon','temperature_zone_id']
    pd.testing.assert_frame_equal(events[keys].drop_duplicates().sort_values('site').reset_index(drop=True),
        sites[keys].sort_values('site').reset_index(drop=True),check_dtype=False)
    events['year']=pd.to_datetime(events.Date).dt.year
    counts=events.groupby(['site','BBCH']).agg(n_observations=('observation_id','size'),
        n_years=('year','nunique'),first_year=('year','min'),last_year=('year','max')).reset_index()
    lattice=sites.merge(pd.DataFrame({'BBCH':STAGES}),how='cross')
    support=lattice.merge(counts,on=['site','BBCH'],how='left',validate='one_to_one')
    for col in ['n_observations','n_years']:support[col]=support[col].fillna(0).astype(int)
    for col in ['first_year','last_year']:support[col]=support[col].astype('Int64')
    support['has_observations']=support.n_observations.gt(0)
    support=support[['site','BBCH','lat','lon','group_id','temperature_zone_id','n_observations','n_years','first_year','last_year','has_observations']]
    assert len(support)==2540 and support.n_observations.sum()==15146
    support.to_csv(OUT/'site_stage_observation_support.csv',index=False)
    summary=support.groupby('BBCH').agg(n_test_sites=('site','nunique'),
        n_sites_with_observations=('has_observations','sum'),n_observations=('n_observations','sum')).reset_index()
    summary['n_sites_without_observations']=summary.n_test_sites-summary.n_sites_with_observations
    summary.to_csv(OUT/'stage_observation_summary.csv',index=False)
    zone=support.groupby(['temperature_zone_id','BBCH']).agg(n_test_sites=('site','nunique'),
        n_sites_with_observations=('has_observations','sum'),n_observations=('n_observations','sum')).reset_index()
    zone.to_csv(OUT/'zone_stage_observation_support.csv',index=False)
    _paper_style()
    fig,axes=plt.subplots(1,4,figsize=(180/25.4,92/25.4))
    fig.subplots_adjust(left=.065,right=.985,bottom=.29,top=.91,wspace=.28)
    cmap=ListedColormap(COLORS);norm=BoundaryNorm([1,6,11,26,51,np.inf],5)
    for ax,stage,letter in zip(axes,STAGES,'abcd'):
        draw_map(ax,sites,[])
        rows=support[support.BBCH.eq(stage)]
        absent=rows[~rows.has_observations];present=rows[rows.has_observations].sort_values('n_observations')
        ax.scatter(absent.lon,absent.lat,s=8,facecolor='none',edgecolor='#b0b6b8',lw=.4,zorder=2)
        ax.scatter(present.lon,present.lat,c=present.n_observations,cmap=cmap,norm=norm,
            s=10,edgecolor='#63787d',lw=.2,zorder=3)
        ax.set_xticks([0,20],['0°','20°E'])
        ax.set_yticks([40,50,60],['40°N','50°N','60°N'] if letter=='a' else ['']*3)
        _panel(ax,letter,y=1.055)
        ax.text(.5,-.19,f'{len(present):,} sites\n{present.n_observations.sum():,} observations',
            transform=ax.transAxes,ha='center',va='top',fontsize=8,linespacing=1.45)
    handles=[Line2D([],[],marker='o',ls='none',mfc='none',mec='#a4abad',mew=.6,ms=4,label='No observations')]
    handles += [Line2D([],[],marker='o',ls='none',mfc=color,mec='#63787d',mew=.4,ms=4,label=label)
                for color,label in zip(COLORS,LABELS)]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.525,.03),ncol=6,
        frameon=False,handlelength=.8,handletextpad=.45,columnspacing=1.2,
        title='Observations per site',title_fontsize=8)
    for ext in ['pdf','png']:fig.savefig(OUT/f'stage_observation_coverage.{ext}',dpi=300)
    plt.close(fig)
