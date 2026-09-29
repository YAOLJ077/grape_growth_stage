#!/usr/bin/env python3
"""Simplified manuscript workflow; editable vector output, no caption/footer."""
from pathlib import Path
import json
import matplotlib.pyplot as plt
from plot_graphical_abstract import Artwork,ROOT,INK,MUTED,GREEN,BLUE,GOLD,PURPLE,sha

OUT=ROOT/'build/comment_revision/figures'

def main():
    a=Artwork(width=1000,height=880,inches=(10,8.8));t=a.text
    plt.rcParams['font.family']='Times New Roman'
    a.box(26,719,948,135,'#EEF4F7',r=12)
    t(500,827,'Matched phenology, weather and terrain',17,BLUE,True,ha='center')
    for x in (354,663):a.line([x,x],[739,802],'#CFDCE1',1)
    t(192,791,'Phenology',14,BLUE,True,ha='center')
    t(192,765,'74,618 observations · 3,169 sites',11.8,ha='center')
    t(192,742,'Four stages · 11 European countries',11.5,MUTED,ha='center')
    t(509,791,'ERA5-Land weather',14,BLUE,True,ha='center')
    t(509,763,'Daily mean temperature',12,ha='center')
    t(509,742,'Matched site–year coverage',11.5,MUTED,ha='center')
    t(814,791,'Terrain',14,BLUE,True,ha='center')
    t(814,763,'Site and weather-grid elevation',11.8,ha='center')
    t(814,742,'Slope · aspect · local variability',11.5,MUTED,ha='center')
    a.arrow(500,715,500,695,BLUE)

    a.box(26,555,948,135,'#F0F6F2',r=12)
    t(500,664,'Grouped calibration/test split within five environmental zones',16,GREEN,True,ha='center')
    t(500,636,'Shared weather-grid cells and colocated sites stay in the same group',11.8,MUTED,ha='center')
    a.box(50,573,435,45,'white','#CDDED5',7)
    a.box(515,573,435,45,'white','#CDDED5',7)
    t(268,596,'Calibration: fit process and residual models',12.5,GREEN,True,ha='center')
    t(733,596,'Test: evaluate locked predictions',12.5,GREEN,True,ha='center')
    a.arrow(500,551,500,531,GREEN)

    a.box(26,231,948,296,'#F8F6F1',r=12)
    t(500,500,'Fully crossed design: 40 configurations per stage',17,bold=True,ha='center')
    for x,w,c in [(50,276,GOLD),(362,276,GREEN),(674,276,PURPLE)]:
        a.box(x,251,w,218,'white',c,8,1)
    t(188,444,'10 process structures',15,GOLD,True,ha='center')
    t(344,360,'×',24,MUTED,ha='center');t(656,360,'×',24,MUTED,ha='center')
    t(188,407,'2 forcing only',13,ha='center')
    t(188,378,'4 sequential chilling–forcing',12.5,ha='center')
    t(188,349,'4 parallel chilling–forcing',12.5,ha='center')
    a.line([75,301],[325,325],'#E3DBCC',1)
    t(188,301,'Simulate the developmental',12,MUTED,ha='center')
    t(188,279,'sequence and stage dates',12,MUTED,ha='center')

    t(500,444,'2 temperature inputs',15,GREEN,True,ha='center')
    t(500,407,'RAW',13,GREEN,True,ha='center')
    t(500,378,'Elevation-corrected',13,GREEN,True,ha='center')
    t(500,342,'Site–grid elevation difference',11.7,MUTED,ha='center')
    t(500,320,'Fixed temperature lapse rate',11.7,MUTED,ha='center')
    a.line([388,612],[302,302],'#D5E2DC',1)
    t(500,277,'Separate calibration per input',11.8,GREEN,ha='center')

    t(812,444,'2 residual options',15,PURPLE,True,ha='center')
    t(812,411,'Absent / present',13,PURPLE,True,ha='center')
    t(812,379,'Target: observed − process date',11.7,ha='center')
    t(812,357,'Grouped out-of-fold calibration',11.5,MUTED,ha='center')
    a.line([699,925],[337,337],'#E1D7E8',1)
    t(812,315,'Process dates · phase duration',11.6,ha='center')
    t(812,293,'Weather · day length · terrain',11.6,ha='center')
    t(812,271,'Adjust attained dates',11.7,PURPLE,ha='center')
    a.arrow(500,227,500,203,MUTED)

    a.box(26,33,948,166,'#F3F6F6',r=12)
    t(500,174,'Evaluate on the same held-out groups',17,bold=True,ha='center')
    a.box(50,56,435,88,'white','#D4DFDF',8)
    a.box(515,56,435,88,'white','#D4DFDF',8)
    t(268,120,'Compare process structures',14,GOLD,True,ha='center')
    t(268,91,'Regional baselines and structural contrasts',11.8,ha='center')
    t(268,71,'Accuracy by developmental stage and zone',11.5,MUTED,ha='center')
    t(733,120,'Quantify paired improvements',14,PURPLE,True,ha='center')
    t(733,91,'Temperature correction and residual learning',11.5,ha='center')
    t(733,71,'Final error · paired gains · group uncertainty',11.5,MUTED,ha='center')
    stem=OUT/'Fig_01'
    bounds=a.export(stem,exts=('pdf','svg','png'),blank_below=60)
    metadata={
        'font_family':'Times New Roman',
        'dimensions_inches':[10,8.8],'raster_pixels':[3000,2640],'raster_dpi':300,
        'source':str(Path(__file__).relative_to(ROOT)),
        'source_sha256':sha(Path(__file__)),
        'shared_drawing_source_sha256':sha(ROOT/'src/documents/plot_graphical_abstract.py'),
        'evidence':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'data/paper_figures/workflow/workflow.md',ROOT/'paper/manuscript.tex']},
        'scientific_scope':{
            'validation':'Group-preserving calibration/test split within represented environmental zones; not zone-transfer validation.',
            'design':'All ten process structures crossed with both temperature inputs and residual options.',
            'residual':'Out-of-fold observed-minus-raw-process residuals from calibration; nested refitting details remain in the caption and Methods.',
            'terrain':'DEM contrasts include separate calibration; no claim of measured local-temperature accuracy.',
            'scoring':'Fixed 4 November late-season scoring convention and raw attainment remain described in the separate caption and Methods.',
            'interpretation':'Study schematic, not a measured process trajectory or the TabM architecture.'},
        'verification':{'canvas_text_bounds_checked':True,'text_count':len(bounds),'minimum_text_y_canvas_units':60},
        'artifacts':{str(stem.with_suffix('.'+ext).relative_to(ROOT)):sha(stem.with_suffix('.'+ext)) for ext in ('pdf','svg','png')}
    }
    (OUT/'Fig_01.metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (OUT/'Fig_01.text_bounds.json').write_text(json.dumps(bounds,indent=2)+'\n')
    plt.close(a.fig)
    print(json.dumps({'output':str(stem),'pixels':metadata['raster_pixels'],'text_count':len(bounds)}))

if __name__=='__main__':main()
