#!/usr/bin/env python3
"""Draw the portrait graphical abstract as editable vector artwork.

The landscape, thermal curve and neural network are conceptual illustrations,
not measured data or an exact neural architecture.
"""
from pathlib import Path
import hashlib
import json
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, Polygon, FancyBboxPatch, PathPatch
from matplotlib.path import Path as MPath
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "fig/graphical_abstract"
INK, MUTED = "#243C39", "#60736C"
GREEN, BLUE, GOLD, PURPLE = "#39806B", "#548FAC", "#D6A052", "#826099"

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "Arial", "pdf.fonttype": 42,
                         "ps.fonttype": 42, "svg.fonttype": "none"})
    fig = plt.figure(figsize=(7.2, 10.4), facecolor="white")
    ax = fig.add_axes((0, 0, 1, 1), xlim=(0, 720), ylim=(-40, 1000))
    ax.axis("off")

    def txt(x, y, s, size=11, color=INK, bold=False, ha="left"):
        return ax.text(x, y, s, fontsize=size, color=color,
                       weight="bold" if bold else "normal", ha=ha, va="center")

    def line(x, y, color=INK, lw=1.4, **kw):
        ax.plot(x, y, color=color, lw=lw, solid_capstyle="round", **kw)

    def arrow(x0, y0, x1, y1, color=MUTED, lw=1.6, style="->"):
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                                    shrinkA=2, shrinkB=2))

    def rounded(x, y, w, h, fill, edge="none", r=8, lw=1):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                     boxstyle=f"round,pad=0,rounding_size={r}",
                     facecolor=fill, edgecolor=edge, lw=lw))

    def leaf(x, y, scale=1, angle=25, color=GREEN):
        ax.add_patch(Ellipse((x, y), 18*scale, 9*scale,
                            angle=angle, facecolor=color, edgecolor="none"))

    def vine(x, y, scale=1):
        line([x, x+2*scale, x-2*scale], [y, y+20*scale, y+37*scale], "#8D7660", 2)
        line([x, x-14*scale], [y+20*scale, y+27*scale], "#8D7660", 1)
        line([x+1*scale, x+16*scale], [y+25*scale, y+31*scale], "#8D7660", 1)
        leaf(x-13*scale, y+29*scale, scale, 28)
        leaf(x+14*scale, y+33*scale, scale, -28)
        leaf(x-1*scale, y+42*scale, scale, 65)

    def grapes(x, y, scale=1, color=PURPLE):
        line([x, x+2*scale], [y+14*scale, y+27*scale], GREEN, 1.6)
        leaf(x+8*scale, y+22*scale, .8*scale)
        for dx,dy in [(-9,9),(9,9),(-15,-5),(0,-5),(15,-5),(-8,-18),(8,-18),(0,-31)]:
            ax.add_patch(Circle((x+dx*scale, y+dy*scale), 8*scale,
                               facecolor=color, edgecolor="white", lw=.65))

    def bloom(x, y, scale=1):
        line([x,x], [y-30*scale,y+19*scale], GREEN, 1.5)
        for dx,dy in [(-14,12),(12,19),(-15,-4),(14,-3),(-9,-20),(10,-18)]:
            line([x,x+dx*scale], [y-10*scale,y+dy*scale], GREEN, .8)
            for a in np.linspace(0, 2*np.pi, 5, endpoint=False):
                ax.add_patch(Circle((x+dx*scale+3*scale*np.cos(a),
                                     y+dy*scale+3*scale*np.sin(a)), 3.4*scale,
                                     facecolor="#DDD39A", edgecolor="none"))
            ax.add_patch(Circle((x+dx*scale,y+dy*scale), 2.2*scale, color=GOLD))

    def calendar(x, y, color, scale=1, corrected=False, observed=False):
        w,h=65*scale,64*scale
        rounded(x-w/2,y-h/2,w,h,"white",color,r=5,lw=1.5)
        rounded(x-w/2,y+h/2-17*scale,w,17*scale,color,r=4)
        for dx in [-18,18]:
            line([x+dx*scale]*2,[y+h/2-5*scale,y+h/2+6*scale],color,2.2)
        for ix in range(3):
            for iy in range(2):
                xx=x+(ix-1)*17*scale;yy=y+2*scale-iy*17*scale
                if (ix,iy)==((1,0) if (corrected or observed) else (0,1)):
                    rounded(xx-5*scale,yy-5*scale,10*scale,10*scale,color,r=1.5)
                else:
                    ax.add_patch(Circle((xx,yy),2*scale,facecolor="#CFD8D2"))
        if corrected:
            line([x+20*scale,x+27*scale,x+40*scale],
                 [y-28*scale,y-35*scale,y-18*scale],GREEN,2.5)

    def thermometer(x, y, color, height):
        rounded(x-7,y+1,14,59,"white",color,r=7,lw=1.6)
        rounded(x-3,y+3,6,height,color,r=3)
        ax.add_patch(Circle((x,y),11,facecolor="white",edgecolor=color,lw=1.6))
        ax.add_patch(Circle((x,y),7,facecolor=color,edgecolor="none"))

    txt(360,962,"Grapevine phenology prediction",22,bold=True,ha="center")
    txt(360,928,"Five environmental zones (EZs)  •  Four developmental stages",12,MUTED,ha="center")

    # DEM: the temperature adjustment occurs before the process simulation.
    rounded(28,665,664,227,"#F1F6F0",r=14)
    txt(51,864,"DEM",15,GREEN,True)
    txt(124,864,"Adjust temperature to vineyard elevation",14,bold=True)
    hill=np.array([[55,724],[99,730],[140,754],[183,794],[226,814],
                   [263,807],[304,781],[340,761],[360,749],[360,707],[55,707]])
    ax.add_patch(Polygon(hill,facecolor="#D3E3C9",edgecolor="none"))
    line(hill[:9,0],hill[:9,1],GREEN,1.8)
    # Official model-grid elevation is a distinct horizontal reference.
    line([57,365],[740,740],"#8EAAA0",1.2,ls=(0,(4,3)))
    txt(65,716,"Weather-grid elevation",9,MUTED)
    vine(221,813,.75)
    vine(273,800,.6)
    vine(174,786,.55)
    txt(129,810,"Vineyard",10,GREEN,ha="center")
    arrow(326,742,326,810,GREEN,1.3,"<->")
    txt(339,783,"Elevation",9,GREEN)
    txt(339,769,"difference",9,GREEN)
    thermometer(473,746,GOLD,44)
    thermometer(594,746,BLUE,25)
    arrow(493,775,574,775,GREEN)
    txt(473,725,"Grid input",10,MUTED,ha="center")
    txt(594,725,"Adjusted input",10,MUTED,ha="center")
    txt(535,827,"Relative to the weather grid",10,MUTED,ha="center")
    txt(535,810,"Higher → cooler   •   Lower → warmer",9.5,GREEN,ha="center")
    txt(360,687,"Reduce elevation-related mismatch in temperature forcing",11,GREEN,ha="center")
    arrow(360,659,360,632,GREEN)

    # PBMs: an unscaled, conceptual accumulation-to-threshold illustration.
    rounded(28,425,664,205,"#F9F5EC",r=14)
    txt(51,602,"PBMs",15,"#A87532",True)
    txt(124,602,"Translate temperature into development",14,bold=True)
    # Snowflake + sun provide a compact cold / heat cue.
    for angle in np.linspace(0,np.pi,3,endpoint=False):
        dx,dy=18*np.cos(angle),18*np.sin(angle)
        line([90-dx,90+dx],[526-dy,526+dy],BLUE,1.8)
        for sign in [-1,1]:
            ex,ey=90+sign*dx,526+sign*dy
            bx,by=90+sign*dx*.57,526+sign*dy*.57
            line([ex,bx-5*np.sin(angle)],[ey,by+5*np.cos(angle)],BLUE,1)
            line([ex,bx+5*np.sin(angle)],[ey,by-5*np.cos(angle)],BLUE,1)
    ax.add_patch(Circle((148,526),13,facecolor=GOLD,edgecolor="none"))
    for angle in np.linspace(0,2*np.pi,8,endpoint=False):
        line([148+18*np.cos(angle),148+24*np.cos(angle)],
             [526+18*np.sin(angle),526+24*np.sin(angle)],GOLD,1.7)
    txt(117,482,"Heat + optional chilling",9,MUTED,ha="center")
    arrow(185,523,226,523,"#A87532")
    arrow(246,476,458,476,MUTED,1)
    arrow(246,476,246,566,MUTED,1)
    x=np.linspace(250,438,100)
    y=480+76*((x-250)/188)**1.65
    line(x,y,"#B98236",2.7)
    line([246,447],[545,545],"#B69B70",1,ls=(0,(3,3)))
    crossx=250+188*((545-480)/76)**(1/1.65)
    ax.add_patch(Circle((crossx,545),4,facecolor="#B98236"))
    line([crossx,crossx],[476,545],"#B69B70",1,ls=(0,(3,3)))
    txt(252,558,"Stage threshold",9,"#A87532")
    txt(351,454,"Accumulate development",10,MUTED,ha="center")
    arrow(464,523,535,523,"#A87532")
    calendar(587,522,"#B98236")
    txt(587,470,"PBM date",10,MUTED,ha="center")
    arrow(360,419,360,394,PURPLE)

    # ML: calibration residual targets and environmental inputs drive learning.
    rounded(28,181,664,211,"#F4F0F7",r=14)
    txt(51,364,"ML",15,PURPLE,True)
    txt(124,364,"Learn and correct remaining date errors",14,bold=True)
    calendar(86,291,"#9A88AA",.56,observed=True)
    calendar(147,291,"#B98236",.56)
    txt(119,250,"Observed − PBM date",10,MUTED,ha="center")
    txt(119,233,"Calibration records",9,PURPLE,ha="center")
    arrow(211,290,298,290,PURPLE)
    txt(251,308,"Errors",9,PURPLE,ha="center")
    layers=[[(321,309),(321,274),(321,239)],
            [(370,322),(370,287),(370,252)],
            [(419,307),(419,272)]]
    for la,lb in zip(layers,layers[1:]):
        for x0,y0 in la:
            for x1,y1 in lb:
                line([x0,x1],[y0,y1],"#C9B7D7",.85)
    for layer in layers:
        for x0,y0 in layer:
            ax.add_patch(Circle((x0,y0),7,facecolor="white",edgecolor=PURPLE,lw=1.5))
    txt(370,210,"Residual patterns",10,PURPLE,ha="center")
    txt(137,204,"Weather + terrain",9.5,MUTED,ha="center")
    arrow(212,211,304,239,PURPLE,1.2)
    arrow(439,290,538,290,PURPLE)
    txt(489,309,"Adjust date",9,PURPLE,ha="center")
    calendar(586,287,GREEN,corrected=True)
    txt(586,237,"Corrected date",10,GREEN,ha="center")
    arrow(360,175,360,150,GREEN)

    # Four developmental endpoints, using simple botanical vector drawings.
    vine(115,99,.75)
    bloom(277,115,.77)
    grapes(439,118,.67,"#AD91B6")
    # A mixed green/purple bunch indicates onset of veraison.
    for dx,dy in [(-9,9),(-15,-5)]:
        ax.add_patch(Circle((439+dx*.67,118+dy*.67),8*.67,
                           facecolor="#9AB573",edgecolor="white",lw=.65))
    grapes(601,118,.67,"#6F5689")
    for x0,label in [(115,"Budburst"),(277,"Flowering"),(439,"Veraison"),(601,"Maturity / harvest")]:
        txt(x0,74,label,10,MUTED,ha="center")
    txt(360,44,"DEM helps PBMs; little extra gain after ML.",12,GREEN,True,ha="center")
    txt(360,21,"Flowering ML gain: EZ05 10.58 d  •  EZ03 1.44 d",10.7,PURPLE,True,ha="center")
    txt(360,1,"Gains depend on zone and stage; sparse coverage limits inference.",9,MUTED,ha="center")
    txt(360,-22,"PBMs: process-based models  •  DEM: digital elevation model  •  ML: machine learning",
        8.2,MUTED,ha="center")

    # Confirm all live labels remain inside the canvas.
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    for artist in ax.texts:
        bounds=artist.get_window_extent(renderer)
        assert bounds.x0>=0 and bounds.y0>=0 and bounds.x1<=fig.bbox.width and bounds.y1<=fig.bbox.height,artist.get_text()
    stem=OUT/"graphical_abstract"
    for ext in ("pdf","svg","png","tiff"):
        options={"pil_kwargs":{"compression":"tiff_lzw"}} if ext=="tiff" else {}
        fig.savefig(stem.with_suffix("."+ext),dpi=300,facecolor="white",**options)
    plt.close(fig)
    evidence=[ROOT/"paper/manuscript.tex",
              ROOT/"paper/evidence/ml_baseline/paired_dem_gain_decrease.csv",
              ROOT/"paper/evidence/ml/zone_effects.csv"]
    metadata={
        "orientation":"portrait","dimensions_inches":[7.2,10.4],
        "raster_pixels":[2160,3120],"raster_dpi":300,
        "design":"Conceptual DEM → PBMs → residual ML pipeline with botanical stage illustrations.",
        "scientific_scope":{
            "dem":"Fixed lapse-rate adjustment using site minus official weather-grid elevation, before separately recalibrated PBMs.",
            "pbms":"Forcing with or without chilling; schematic threshold curve is not an empirical response or fitted trajectory.",
            "ml":"Calibration observations define residual targets; weather and terrain provide predictive covariates. The illustrated network does not specify TabM architecture.",
            "output":"ML adjusts dates for attained process stages; it does not change thermal states or repair non-attainment.",
            "interpretation":"Illustrated correction roles do not identify the mechanisms responsible for observed accuracy gains.",
            "main_finding":"DEM improved mean PBM accuracy; its additional mean benefit after ML was small and uncertain.",
            "environmental_zones":"Five zones summarize monthly RAW temperature profiles. RAW flowering residual-learning MAE gains were 10.58 d in EZ05 and 1.44 d in EZ03. Zone comparisons use primary held-out sites and do not establish independent regional transfer; sparse zone-stage coverage limits inference."
        },
        "sources":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence},
        "script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "artifacts":{str(stem.with_suffix("."+ext).relative_to(ROOT)):hashlib.sha256(stem.with_suffix("."+ext).read_bytes()).hexdigest()
                     for ext in ("pdf","svg","png","tiff")},
        "text_bounds_checked":True
    }
    (OUT/"metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    print(json.dumps({"output":str(OUT),"pixels":metadata["raster_pixels"],"orientation":"portrait"},indent=2))

if __name__=="__main__":
    main()
