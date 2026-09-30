#!/usr/bin/env python3
"""Editable graphical abstract with conceptual diagrams and source-backed paired error comparisons."""
from pathlib import Path
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, Polygon, FancyBboxPatch
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'fig/paper_figures'
INK, MUTED = '#233D3D', '#5A6D70'
GREEN, BLUE, GOLD, PURPLE = '#35806D', '#447C9A', '#B98436', '#80619A'

class Artwork:
    def __init__(self, width=800, height=1000, inches=(8,10)):
        plt.rcParams.update({'font.family':'Times New Roman', 'pdf.fonttype':42,
                             'ps.fonttype':42, 'svg.fonttype':'none'})
        self.fig=plt.figure(figsize=inches,facecolor='white')
        self.ax=self.fig.add_axes((0,0,1,1),xlim=(0,width),ylim=(0,height))
        self.ax.axis('off')
        self.width,self.height=width,height
    def text(self,x,y,s,size=12,color=INK,bold=False,ha='left'):
        return self.ax.text(x,y,s,fontsize=size,color=color,weight='bold' if bold else 'normal',ha=ha,va='center',linespacing=1.35)
    def line(self,x,y,color=INK,lw=1.5,**kw):
        self.ax.plot(x,y,color=color,lw=lw,solid_capstyle='round',**kw)
    def arrow(self,x0,y0,x1,y1,color=MUTED,lw=1.6,style='->'):
        self.ax.annotate('',xy=(x1,y1),xytext=(x0,y0),arrowprops=dict(arrowstyle=style,color=color,lw=lw,shrinkA=3,shrinkB=3))
    def box(self,x,y,w,h,fill='white',edge='none',r=10,lw=1):
        self.ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle=f'round,pad=0,rounding_size={r}',facecolor=fill,edgecolor=edge,lw=lw))
    def leaf(self,x,y,s=1,angle=25,color=GREEN):
        self.ax.add_patch(Ellipse((x,y),18*s,9*s,angle=angle,facecolor=color,edgecolor='none'))
    def vine(self,x,y,s=1):
        self.line([x,x+2*s,x-2*s],[y,y+20*s,y+37*s],'#8D7660',2)
        self.line([x,x-14*s],[y+20*s,y+27*s],'#8D7660',1)
        self.line([x+s,x+16*s],[y+25*s,y+31*s],'#8D7660',1)
        self.leaf(x-13*s,y+29*s,s,28);self.leaf(x+14*s,y+33*s,s,-28);self.leaf(x-s,y+42*s,s,65)
    def grapes(self,x,y,s=1,color=PURPLE,mixed=False):
        self.line([x,x+2*s],[y+14*s,y+27*s],GREEN,1.6)
        self.leaf(x+8*s,y+22*s,.8*s)
        for i,(dx,dy) in enumerate([(-9,9),(9,9),(-15,-5),(0,-5),(15,-5),(-8,-18),(8,-18),(0,-31)]):
            self.ax.add_patch(Circle((x+dx*s,y+dy*s),8*s,facecolor='#9AB573' if mixed and i in (0,2) else color,edgecolor='white',lw=.7))
    def bloom(self,x,y,s=1):
        self.line([x,x],[y-30*s,y+19*s],GREEN,1.5)
        for dx,dy in [(-14,12),(12,19),(-15,-4),(14,-3),(-9,-20),(10,-18)]:
            self.line([x,x+dx*s],[y-10*s,y+dy*s],GREEN,.8)
            for a in np.linspace(0,2*np.pi,5,endpoint=False):
                self.ax.add_patch(Circle((x+dx*s+3*s*np.cos(a),y+dy*s+3*s*np.sin(a)),3.4*s,facecolor='#DDD39A',edgecolor='none'))
            self.ax.add_patch(Circle((x+dx*s,y+dy*s),2.2*s,color=GOLD))
    def calendar(self,x,y,color=GOLD,s=1):
        self.box(x-26*s,y-25*s,52*s,50*s,'white',color,4,1.5)
        self.box(x-26*s,y+11*s,52*s,14*s,color,r=3)
        for dx in (-14,14): self.line([x+dx*s]*2,[y+21*s,y+31*s],color,1.8)
        for ix in range(3):
            for iy in range(2):
                xx,yy=x+(ix-1)*14*s,y+1*s-iy*14*s
                self.ax.add_patch(Circle((xx,yy),3*s,facecolor=color if (ix,iy)==(1,0) else '#D4DDDA',edgecolor='none'))
    def verify(self,blank_below=0):
        self.fig.canvas.draw(); renderer=self.fig.canvas.get_renderer()
        bounds=[]
        for a in self.ax.texts:
            if not a.get_text():continue
            b=a.get_window_extent(renderer)
            assert b.x0>=0 and b.y0>=0 and b.x1<=self.fig.bbox.width and b.y1<=self.fig.bbox.height,a.get_text()
            y_min=b.y0/self.fig.bbox.height*self.height
            assert y_min>=blank_below,(a.get_text(),y_min)
            bounds.append({'text':a.get_text(),'bounds_pixels':[round(v,2) for v in b.extents]})
        return bounds
    def export(self,stem,exts=('pdf','svg','png','tiff'),blank_below=0):
        stem.parent.mkdir(parents=True,exist_ok=True)
        bounds=self.verify(blank_below)
        for ext in exts:
            options={'pil_kwargs':{'compression':'tiff_lzw'}} if ext=='tiff' else {}
            self.fig.savefig(stem.with_suffix('.'+ext),dpi=300,facecolor='white',**options)
        return bounds

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    a=Artwork(width=1328,height=531,inches=(1328/300,531/300))
    # A narrow typographic scale, dark labels and a semantic, restrained palette.
    ink='#263336';muted='#5C686B';rule='#D9DFDF'
    cold='#537E99';warm='#C49B52';terrain='#54887B';residual='#7B708D'
    def t(x,y,s,size=6.6,bold=False,ha='left',color=ink):
        return a.text(x,y,s,size,color,bold,ha)
    from matplotlib.path import Path as MplPath
    from matplotlib.patches import PathPatch,FancyArrowPatch
    def arrow(x0,y0,x1,y1,color=muted,lw=.65):
        a.ax.add_patch(FancyArrowPatch((x0,y0),(x1,y1),arrowstyle='-|>',
            mutation_scale=5.5,lw=lw,color=color,shrinkA=0,shrinkB=0))
    def curved(points,color=muted,lw=.65):
        a.ax.add_patch(FancyArrowPatch(path=MplPath(points,[1,4,4,4]),
            arrowstyle='-|>',mutation_scale=5.5,lw=lw,color=color))
    def node(x,y,c,w=47,h=24):
        a.box(x-w/2,y-h/2,w,h,c,r=3)

    # Three visual fields share alignment; fine rules replace coloured panels.
    t(32,483,'Process structure',7.4,True)
    t(447,483,'Further improvement',7.4,True)
    t(957,483,'Grapevine phenology',7.4,True)
    for x in [414,922]:a.line([x,x],[70,460],rule,.4)

    # Process relationships, not repeated letters or illustrative fitted curves.
    t(32,438,'10 candidate structures',6.5,color=muted)
    a.line([33,58],[392,392],cold,1.7);t(71,392,'Chilling',6.3)
    a.line([213,238],[392,392],warm,1.7);t(251,392,'Forcing',6.3)
    t(32,343,'Forcing only',6.7)
    t(32,302,'2 structures',6.0,color=muted)
    arrow(211,323,365,323)
    node(288,323,warm,76,27)

    # The highlight marks the winning family without suggesting only it was corrected.
    a.line([23,23],[213,281],terrain,1.05)
    t(32,264,'Sequential',6.7,True)
    t(32,228,'4 structures',6.0,color=muted)
    node(235,246,cold,48,27);node(340,246,warm,48,27)
    arrow(260,246,315,246)

    t(32,183,'Parallel',6.7)
    t(32,143,'4 structures',6.0,color=muted)
    a.line([211,222,222],[165,165,187],muted,.55)
    a.line([222,222],[165,143],muted,.55)
    arrow(222,187,247,187);arrow(222,143,247,143)
    node(276,187,cold,55,23);node(276,143,warm,55,23)
    a.line([306,339,339],[187,187,165],muted,.55)
    a.line([306,339,339],[143,143,165],muted,.55)
    arrow(339,165,367,165)
    # Compact selected-model annotation sits with the selected structure.
    t(207,103,'Selected: CB-FL-S',6.6,True,ha='center')
    t(207,70,'Beta chilling → linear forcing',6.0,ha='center',color=muted)

    # Terrain-informed temperature input: original vector relief and vineyard rows.
    t(447,438,'Terrain-adjusted temperature',6.6,True)
    def surface(u,v):
        return np.array([460+146*u+57*v,350-62*u+46*v+24*np.sin(np.pi*u)*np.sin(np.pi*v)])
    u=np.linspace(0,1,50)
    perimeter=np.vstack([np.array([surface(q,0) for q in u]),
                         np.array([surface(1,q) for q in u]),
                         np.array([surface(q,1) for q in u[::-1]]),
                         np.array([surface(0,q) for q in u[::-1]])])
    a.ax.add_patch(Polygon(perimeter,facecolor='#EEF2E9',edgecolor='#AEC1B1',lw=.55))
    for vv in np.linspace(.1,.9,5):
        pts=np.array([surface(q,vv) for q in u]);a.line(pts[:,0],pts[:,1],'#AEC1B1',.4)
    for uu in [.16,.50,.84]:
        pts=np.array([surface(uu,q) for q in u]);a.line(pts[:,0],pts[:,1],'#C9D4C2',.4)
    # Small vines establish grapevine context without decorative landscape imagery.
    for uu,vv in [(.25,.27),(.60,.27),(.25,.73),(.60,.73)]:
        xx,yy=surface(uu,vv)
        a.line([xx,xx,xx+2],[yy,yy+15,yy+23],'#938572',.65)
        a.ax.add_patch(Ellipse((xx-7,yy+18),17,8,angle=30,facecolor=terrain,edgecolor='none'))
        a.ax.add_patch(Ellipse((xx+7,yy+21),17,8,angle=-30,facecolor=terrain,edgecolor='none'))
        for dx,dy in [(4,12),(9,12),(6.5,7)]:
            a.ax.add_patch(Circle((xx+dx,yy+dy),2.2,facecolor=residual,edgecolor='none'))
    a.line([663,689],[365,365],rule,.55)
    a.line([622,689],[308,308],rule,.55)
    a.ax.add_patch(FancyArrowPatch((684,312),(684,361),arrowstyle='<->',
                mutation_scale=5,lw=.65,color=terrain,shrinkA=0,shrinkB=0))
    t(700,355,'Elevation offset',6.1)
    t(700,319,'Recalibration',6.1)

    # The residual module explicitly combines process and environmental predictors.
    t(447,270,'Process-guided residual learning',6.6,True)
    t(447,222,'Process states',6.3)
    t(447,181,'Environment',6.3)
    a.line([626,642,642,626],[222,222,181,181],muted,.6)
    arrow(643,202,670,202)
    a.box(677,176,82,51,'#EEEAF1',r=4)
    t(718,202,'Δd',8.0,ha='center')
    arrow(763,202,794,202)
    # Date correction, represented as a calendar with an adjusted date marker.
    a.box(807,177,52,52,'white',muted,4,.6)
    a.line([807,859],[215,215],muted,.55)
    for dx in [819,847]:a.line([dx,dx],[224,237],muted,.65)
    for xx in [819,833,847]:
        for yy in [189,201]:
            a.ax.add_patch(Circle((xx,yy),2.5,facecolor='#CDD5D3',edgecolor='none'))
    a.ax.add_patch(Circle((833,201),4,facecolor=residual,edgecolor='none'))
    t(447,125,'Grouped out-of-fold errors',6.1,color=muted)
    t(447,72,'Both corrections evaluated across all 10',6.0,color=muted)

    # A paired 2 × 2 plot exposes the limited extra terrain gain after residual learning.
    source=ROOT/'data/paper_figures/workflow/graphical_abstract_results.json'
    results=json.loads(source.read_text())['primary']
    bars=[('Process only','raw_process_mae',cold),('Terrain','dem_process_mae',terrain),
          ('Residual','raw_hybrid_mae',cold),('Both','dem_hybrid_mae',terrain)]
    t(957,438,'Regional test MAE (days)',6.5)
    a.line([958,980],[395,395],cold,.8)
    a.ax.add_patch(Circle((969,395),4,facecolor=cold,edgecolor='none'))
    t(992,395,'Grid temperature',6.0)
    a.line([958,980],[359,359],terrain,.8)
    a.ax.add_patch(Polygon([[969,354],[974,359],[969,364],[964,359]],facecolor=terrain,edgecolor='none'))
    t(992,359,'Terrain adjusted',6.0)
    x_left,x_right=1032,1223
    y0,y1=110,325;low,high=7.5,13.5
    def yy(value):return y0+(value-low)/(high-low)*(y1-y0)
    for value in [8,10,12]:
        y=yy(value)
        a.line([995,1268],[y,y],'#E2E7E7',.4)
        t(979,y,str(value),6.0,ha='right',color=muted)
    # Values in each series are computed on the same cohort, with no synthetic data.
    for keys,c,marker in [(('raw_process_mae','raw_hybrid_mae'),cold,'o'),
                          (('dem_process_mae','dem_hybrid_mae'),terrain,'D')]:
        v0,v1=(results[k] for k in keys)
        # Tiny symmetric x offsets keep the two convergent endpoints distinguishable.
        offset=-3 if marker=='o' else 3
        xs=[x_left+offset,x_right+offset];ys=[yy(v0),yy(v1)]
        a.line(xs,ys,c,.95)
        a.ax.plot(xs,ys,ls='none',marker=marker,markersize=3.2,color=c,
                  markeredgecolor='white',markeredgewidth=.35)
        t(1014,ys[0]+23 if marker=='o' else ys[0]-17,f'{v0:.2f}',6.4,ha='right')
        # Separate leader labels avoid falsely separating almost equal MAEs.
        ylab=ys[1]+33 if marker=='o' else ys[1]-31
        a.line([xs[1]+5,1268],[ys[1],ylab],c,.45)
        t(1294,ylab,f'{v1:.2f}',6.2,ha='right')
    t(x_left,74,'Process',6.4,ha='center')
    t(x_right,74,'+ Residual',6.4,ha='center')

    stem=OUT/'graphical_abstract'
    bounds=a.export(stem,blank_below=52)
    metadata={
        'font_family':'Times New Roman','orientation':'landscape',
        'dimensions_inches':[1328/300,531/300],'raster_pixels':[1328,531],'raster_dpi':300,
        'design':'Title-free scientific schematic with three aligned fields, process topology, terrain and residual mechanisms, and a paired 2 × 2 MAE interaction plot; no footer.',
        'design_reference':'https://www.nature.com/documents/natrev-artworkguide_PS.pdf',
        'scientific_scope':{
            'design':'Ten structures × two temperature inputs × two residual options; corrections retain all ten structures.',
            'selection':'CB-FL-S is the selected RAW process structure: sequential beta chilling and linear forcing. Selection is not a filter on the correction experiment.',
            'terrain':'Fixed lapse-rate correction precedes separate process recalibration; surface and vines are conceptual, not an observed terrain dataset.',
            'residual':'Stage-specific residual design uses process states and environment; the Δd box is not a claim about neural-network architecture.',
            'target':'Observed minus raw out-of-fold process date, learned with grouped nested refits.',
            'output':'Correction adjusts attained dates; it does not repair non-attainment or modify process thermal states.',
            'validation':'Grouped site holdouts within five represented environmental zones; not independent regional transfer.',
            'gains':'The 2 × 2 paired plot shows the convergence of terrain-input MAEs after residual learning. No additive mechanism is assumed.'},
        'sources':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'data/paper_figures/workflow/workflow.md',ROOT/'paper/manuscript.tex']},
        'quantitative_results':{'source':str(source.relative_to(ROOT)),'source_sha256':sha(source),
            'cohort':{'observations':15105,'sites':633,'groups':355},
            'weighting':'Equal models, sites within each stage, and four stages',
            'mae_days':{key:results[key] for _,key,_ in bars},
            'axis_limits_days':[low,high],
            'plot':'Connected point estimates, with endpoint leader labels and circle/diamond coding; no uncertainty intervals are implied.'},
        'script_sha256':sha(Path(__file__)),
        'artifacts':{str(stem.with_suffix('.'+ext).relative_to(ROOT)):sha(stem.with_suffix('.'+ext)) for ext in ('pdf','svg','png','tiff')},
        'verification':{'canvas_text_bounds_checked':True,'minimum_text_y_canvas_units':52,'text_count':len(bounds),
                        'method':'Matplotlib rendered text extents asserted within canvas and above footer exclusion zone.'}
    }
    (OUT/'graphical_abstract.metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (OUT/'graphical_abstract.text_bounds.json').write_text(json.dumps(bounds,indent=2)+'\n')
    plt.close(a.fig)
    print(json.dumps({'output':str(stem),'pixels':metadata['raster_pixels'],'text_count':len(bounds)}))

if __name__=='__main__':main()
