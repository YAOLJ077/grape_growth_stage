#!/usr/bin/env python3
"""Editable scientific schematic; all drawings are conceptual, not data plots."""
from pathlib import Path
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, Polygon, FancyBboxPatch
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'fig/graphical_abstract'
INK, MUTED = '#233D3D', '#5A6D70'
GREEN, BLUE, GOLD, PURPLE = '#35806D', '#447C9A', '#B98436', '#80619A'

class Artwork:
    def __init__(self, width=800, height=1000, inches=(8,10)):
        plt.rcParams.update({'font.family':'Arial', 'pdf.fonttype':42,
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
    a=Artwork();t=a.text
    t(400,960,'Grapevine phenology across environments',22,bold=True,ha='center')
    t(400,925,'Identify regional baselines · Improve stage-date estimates',13,MUTED,ha='center')

    # Structure comparison precedes the correction experiments in the narrative.
    a.box(32,689,736,201,'#F8F4EB',r=14)
    t(56,860,'1',15,GOLD,True);t(84,860,'Compare ten process structures',17,bold=True)
    groups=[(160,'Forcing only',2),(400,'Sequential',4),(640,'Parallel',4)]
    for x,label,n in groups:
        t(x,820,label,12,GOLD,True,ha='center')
        for i in range(n):
            xx=x-(n-1)*24+i*48
            a.box(xx-18,758,36,39,'white','#D5C5A7',5)
            q=np.linspace(0,1,20)
            peak=25.4/35; alpha=np.log(2)/np.log(1/peak)
            response=q if i%2==0 else np.maximum(0,2*(q/peak)**alpha-(q/peak)**(2*alpha))
            a.line(xx-11+22*q,767+21*response,GOLD,1.7)
        t(x,738,'Heat' if n==2 else 'Chilling + heat',11,MUTED,ha='center')
    t(400,710,'Grouped site holdouts within five environmental zones',11.5,MUTED,ha='center')
    a.arrow(400,686,400,652,GOLD)
    t(400,633,'2   Test both corrections across all ten structures',16,bold=True,ha='center')
    # Two routes are factors, not additive improvements or a selected-model pipeline.
    a.box(32,299,356,307,'#F0F6F2',r=14)
    a.box(412,299,356,307,'#F4F0F8',r=14)
    t(210,578,'Terrain-adjusted temperature',14,GREEN,True,ha='center')
    t(590,578,'Process-guided residual model',13.5,PURPLE,True,ha='center')
    hill=np.array([[58,429],[104,449],[162,506],[215,495],[278,461],[363,435],[363,419],[58,419]])
    a.ax.add_patch(Polygon(hill,facecolor='#D3E3C9',edgecolor='none'))
    a.line(hill[:6,0],hill[:6,1],GREEN,1.8)
    a.line([60,364],[451,451],'#7FA194',1.2,ls=(0,(4,3)))
    a.vine(162,506,.7)
    a.line([168,309],[506,506],'#7FA194',1,ls=(0,(3,3)))
    a.arrow(307,451,307,506,GREEN,1.2,'<->')
    t(210,552,'Site–grid elevation difference',11.5,MUTED,ha='center')
    t(210,397,'RAW  ↔  Elevation-corrected',12,GREEN,True,ha='center')
    a.arrow(210,380,210,355,GREEN)
    t(210,333,'Recalibrate each process structure',11.5,MUTED,ha='center')

    t(590,543,'Process dates + phase duration',11.5,MUTED,ha='center')
    t(590,521,'Weather + day length + terrain',11.5,MUTED,ha='center')
    a.arrow(590,504,590,480,PURPLE)
    a.box(454,434,272,44,'white','#CBBAD8',8)
    t(590,456,'Learn date residuals',13,PURPLE,True,ha='center')
    t(590,411,'Target: observed − process date',11.5,MUTED,ha='center')
    t(590,389,'Out-of-fold calibration predictions',10.5,MUTED,ha='center')
    a.arrow(590,374,590,351,PURPLE)
    t(590,331,'Adjust attained stage dates',12,PURPLE,True,ha='center')

    a.line([210,210,590,590],[296,272,272,296],MUTED,1.3)
    a.arrow(400,272,400,237,GREEN)
    a.box(32,39,736,197,'#F6F8F8',r=14)
    t(400,207,'3   Evaluate final accuracy and paired gains',16,bold=True,ha='center')
    for x,label in [(124,'Budburst'),(305,'Flowering'),(487,'Veraison'),(669,'Maturity / harvest')]:
        t(x,160,label,11.5,MUTED,ha='center')
    a.vine(124,70,1.35);a.bloom(305,105,1.2)
    a.grapes(487,108,1.05,'#AF91B4',mixed=True);a.grapes(669,108,1.05,'#6F5689')
    # No footer, abbreviation block, performance-number block or text below icons.
    stem=OUT/'graphical_abstract'
    bounds=a.export(stem,blank_below=145)
    metadata={
        'orientation':'portrait','dimensions_inches':[8,10],'raster_pixels':[2400,3000],'raster_dpi':300,
        'design':'Structure comparison, fully crossed terrain and residual corrections, and four stage endpoints; no bottom explanatory text.',
        'scientific_scope':{
            'design':'Ten structures × two temperature inputs × two residual options; corrections retain all ten structures.',
            'terrain':'Fixed lapse-rate correction precedes separate process recalibration; no claim of independently validated local temperature accuracy.',
            'residual':'Schematic stage-specific residual model, not a neural-network architecture. Predictors include process dates, phase duration, weather, day length and terrain.',
            'target':'Observed minus raw out-of-fold process date in calibration, with grouped nested refits.',
            'output':'Correction adjusts attained dates; it does not repair non-attainment or modify process thermal states.',
            'validation':'Grouped site holdouts within five represented environmental zones; not independent regional transfer.',
            'gains':'No numerical gain or additive sequential-gain claim; corrections are evaluated as factorial contrasts.'},
        'sources':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'data/paper_figures/workflow/workflow.md',ROOT/'paper/manuscript.tex']},
        'script_sha256':sha(Path(__file__)),
        'artifacts':{str(stem.with_suffix('.'+ext).relative_to(ROOT)):sha(stem.with_suffix('.'+ext)) for ext in ('pdf','svg','png','tiff')},
        'verification':{'canvas_text_bounds_checked':True,'minimum_text_y_canvas_units':145,'text_count':len(bounds),'method':'Matplotlib rendered text extents asserted within canvas and above footer exclusion zone.'}
    }
    (OUT/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (OUT/'text_bounds.json').write_text(json.dumps(bounds,indent=2)+'\n')
    plt.close(a.fig)
    print(json.dumps({'output':str(stem),'pixels':metadata['raster_pixels'],'text_count':len(bounds)}))

if __name__=='__main__':main()
