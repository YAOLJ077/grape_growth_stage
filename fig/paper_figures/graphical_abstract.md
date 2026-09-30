# Graphical abstract

[PDF](graphical_abstract.pdf), [editable SVG](graphical_abstract.svg),
[PNG](graphical_abstract.png), [TIFF](graphical_abstract.tiff).

The current figure is landscape: **1328 pixels wide × 531 pixels high**, with
300-dpi raster exports and Times New Roman lettering. It uses the required
pixel proportions for display at approximately 13 × 5 cm. The exact pixel ratio
is 2.501:1; proportional placement at 13 cm wide gives a height of 5.20 cm.

The title-free layout has three aligned fields: process topology; terrain and
process-guided residual corrections; and a paired prediction-error comparison.
Dark text, a narrow font-size range and consistent line weights follow the
clarity and consistency principles in the
[Nature Reviews artwork guide](https://www.nature.com/documents/natrev-artworkguide_PS.pdf).
Times New Roman is retained as specified for this manuscript; the figure does not
claim compliance with Nature's separate sans-serif typography requirements.

The process diagrams distinguish forcing-only, sequential chilling–forcing and
parallel chilling–forcing structures. The selected CB-FL-S model combines beta
chilling and linear forcing sequentially. Both corrections are evaluated across
all ten structures. The terrain surface and vines are conceptual illustrations.
The residual module combines process states and environmental predictors to
adjust dates; the delta box does not depict a neural-network architecture.

The connected-point chart uses the same 15,105 observations, 633 sites and 355
held-out groups in all four configurations. Weighting is equal across the ten
models, sites within each stage, and four stages. Grid-temperature process and
hybrid MAEs are 12.58 and 8.49 days; terrain-adjusted equivalents are 11.53 and
8.37 days. The y-axis spans 7.5–13.5 days; points and their connecting lines encode
values, not areas or bars. Circle/diamond markers supplement the colour key.
Leader labels distinguish the nearly coincident corrected endpoints without
altering the data. No uncertainty intervals are implied. Validation uses grouped
site holdouts within five represented temperature-defined zones.

There is no overall title or footer. All artwork and lettering remain editable
vectors. The quantitative source is
`data/paper_figures/workflow/graphical_abstract_results.json`.

[Metadata](graphical_abstract.metadata.json) records the current exports and
[text bounds](graphical_abstract.text_bounds.json) record rendered lettering.

```sh
.venv/bin/python src/documents/plot_graphical_abstract.py
.venv/bin/python src/visualization/merge_figures.py
```
