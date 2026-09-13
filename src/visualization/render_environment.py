"""Publication labels for existing climate-profile zones; no cluster changes."""
import argparse,calendar,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import MaxNLocator
from matplotlib.patches import Polygon
from matplotlib.lines import Line2D
import pandas as pd
import numpy as np
from common import DATA,digest,ROOT,COLORS,MARKERS

BOUNDARIES = DATA/'common/countries.geojson'


def draw_map(ax, sites, zones):
    west,east,south,north = -7.,26.,36.5,61.
    if not (sites.lon.between(west,east)&sites.lat.between(south,north)).all():
        raise ValueError('Map extent excludes study sites')
    ax.set_facecolor('#edf3f5')
    for feature in json.loads(BOUNDARIES.read_text())['features']:
        geometry = feature['geometry']
        polygons = geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
        for polygon in polygons:
            for ring_index, ring in enumerate(polygon):
                xy = np.asarray(ring)[:,:2]
                if xy[:,0].max()<west or xy[:,0].min()>east or xy[:,1].max()<south or xy[:,1].min()>north:
                    continue
                ax.add_patch(Polygon(xy,closed=True,facecolor='#f4f2ed' if ring_index==0 else '#edf3f5',
                    edgecolor='#aeb7b9',linewidth=.3,zorder=1,rasterized=False))
    # Each site's frozen assignment is shown at its recorded coordinates.
    # Coincident records overlap; there is no jitter or spatial interpolation.
    for zone,color,marker in zip(zones,COLORS,MARKERS):
        rows=sites[sites.temperature_zone_id.eq(zone)]
        ax.scatter(rows.lon,rows.lat,s=7,marker=marker,facecolor=color,edgecolor='white',
            linewidth=.12,zorder=3,alpha=.9)
    ax.set_xlim(west,east);ax.set_ylim(south,north)
    ax.set_aspect(1/np.cos(np.deg2rad(50)))
    ax.set_xticks([0,10,20],['0°','10°E','20°E'])
    ax.set_yticks([40,50,60],['40°N','50°N','60°N'])
    ax.tick_params(length=3,width=.6,pad=3)
    for spine in ax.spines.values():spine.set_color('#9ba6a9');spine.set_linewidth(.5)

def render(profiles, counts, output, sites=None):
    font_path = Path('/System/Library/Fonts/Helvetica.ttc')
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
    plt.rcParams.update({'font.family': 'Helvetica', 'font.size': 8, 'axes.labelsize': 8,
        'axes.titlesize': 9, 'xtick.labelsize': 8, 'ytick.labelsize': 8, 'legend.fontsize': 8,
        'axes.linewidth': .7, 'pdf.fonttype': 42, 'ps.fonttype': 42,
        'text.color': '#252525', 'axes.labelcolor': '#252525', 'axes.edgecolor': '#454545'})
    if sites is None: raise ValueError('Explicit frozen sites are required')
    fig = plt.figure(figsize=(180/25.4,145/25.4))
    map_ax=fig.add_axes([.065,.16,.405,.72])
    profile_ax=fig.add_axes([.59,.57,.385,.29])
    count_ax=fig.add_axes([.59,.12,.385,.29])
    zones = sorted(profiles.temperature_zone_id.unique())
    if set(sites.temperature_zone_id)!=set(zones):raise ValueError('Map and profiles have different zones')
    draw_map(map_ax,sites,zones)
    map_ax.text(0,1.035,'(a)',transform=map_ax.transAxes,fontsize=9,fontweight='bold',va='bottom')
    handles=[Line2D([],[],color=c,marker=m,markersize=4,linewidth=1,label=z.replace('TZ','EZ'))
             for z,c,m in zip(zones,COLORS,MARKERS)]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.53,.98),ncol=5,frameon=False,
        handlelength=1.4,handletextpad=.4,columnspacing=1.3)
    for ax in [profile_ax,count_ax]:
        ax.spines[['top','right']].set_visible(False)
        ax.set_axisbelow(True);ax.grid(axis='y',color='#e1e5e6',linewidth=.5)
        ax.tick_params(width=.7,length=3)
    for zone,color,marker in zip(zones,COLORS,MARKERS):
        row=profiles[profiles.temperature_zone_id.eq(zone)]
        profile_ax.plot(row.month,row.tmean_c,color=color,marker=marker,markersize=3,
            linewidth=1.1,markeredgewidth=.5)
    profile_ax.set(xlim=(.7,12.3),ylim=(-8,26),xlabel='Calendar month',ylabel='Mean temperature (°C)')
    profile_ax.set_xticks(range(1,13),[calendar.month_abbr[m][0] for m in range(1,13)])
    profile_ax.set_yticks([-5,0,5,10,15,20,25])
    profile_ax.text(0,1.055,'(b)',transform=profile_ax.transAxes,fontsize=9,fontweight='bold',va='bottom')
    x=np.arange(len(zones));width=.34
    for partition,offset,color,hatch,label in [('calibration',-.5,'#507A9C',None,'Calibration'),
                                             ('test',.5,'#F2E0B9','//','Test')]:
        values=counts[counts.partition.eq(partition)].set_index('temperature_zone_id').n_sites.reindex(zones)
        bars=count_ax.bar(x+offset*width,values,width=width,color=color,hatch=hatch,
            edgecolor='#3A4C58',linewidth=.6,label=label)
        count_ax.bar_label(bars,padding=3,fontsize=8,fmt='%d')
    count_ax.set_xticks(x,[z.replace('TZ','EZ') for z in zones])
    count_ax.set(ylim=(0,1180),xlabel='Environmental zone',ylabel='Reported sites (n)')
    count_ax.yaxis.set_major_locator(MaxNLocator(integer=True,nbins=5))
    count_ax.text(0,1.24,'(c)',transform=count_ax.transAxes,fontsize=9,fontweight='bold',va='bottom')
    count_ax.legend(loc='lower left',bbox_to_anchor=(-.02,1.015),ncol=2,frameon=False,
        handlelength=1.4,handletextpad=.4,columnspacing=1,borderaxespad=0)
    for suffix in ('pdf', 'png'):
        fig.savefig(output/f'environmental_zones_and_split.{suffix}', dpi=360, facecolor='white')
    plt.close(fig)
