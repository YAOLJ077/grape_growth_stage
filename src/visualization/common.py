"""Shared constants and native-layout style for the reproducible paper figures."""
from pathlib import Path
import hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/paper_figures'
MODELS=['FL','FB','CL-FL-S','CL-FL-P','CB-FL-S','CB-FL-P','CL-FB-S','CL-FB-P','CB-FB-S','CB-FB-P']
STAGES=['07','65','81','89']
COLORS=['#376D9A','#7196B6','#7A8535','#D08A27','#B34D67']
MARKERS=['o','s','^','D','v']
def require(condition,message):
    if not condition: raise ValueError(message)
def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _paper_style():
    from matplotlib import font_manager
    font=Path('/System/Library/Fonts/Helvetica.ttc')
    require(font.is_file(), 'The shared paper font Helvetica is unavailable')
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':'Helvetica','font.size':8,'axes.labelsize':8,
        'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8,'pdf.fonttype':42,
        'text.color':'#182630','axes.unicode_minus':True,'savefig.bbox':None})

def _panel(ax,letter,y=1.15):
    ax.text(0,y,f'({letter})',transform=ax.transAxes,ha='left',va='bottom',fontsize=9,fontweight='bold')
