# Graphical abstract

[PDF](graphical_abstract.pdf), [editable SVG](graphical_abstract.svg),
[PNG](graphical_abstract.png), [300-dpi TIFF](graphical_abstract.tiff).

The portrait graphic places comparison of ten process structures before the
terrain and residual corrections. Both corrections apply across all ten
structures; the diagram does not depict correction of a selected winner only.
The terrain and residual panels represent crossed experimental factors, not
additive sequential gains. Four botanical stage illustrations finish the
figure, with their labels above the illustrations and no explanatory footer.

Terrain correction uses site-minus-weather-grid elevation and a fixed lapse
rate, with separate calibration under each temperature input. Residual learning
uses process dates, phase duration, weather, day length and terrain. Its target
is observed minus raw out-of-fold process date in calibration. Corrections
adjust attained stage dates; they do not modify thermal states or create stage
attainment. The schematic does not depict the TabM architecture.

The ten small curves and the vineyard terrain are conceptual illustrations,
not fitted temperature responses or measured topography. Grouped held-out-site
evaluation takes place within five represented environmental zones and does
not establish transfer to an independent region. No empirical improvement
numbers or independently validated local-temperature claims appear in the
figure.

The editable canvas is 8 × 10 inches. PNG and TIFF exports are 2,400 × 3,000
pixels at 300 dpi. PDF and SVG retain vector elements and selectable text.
[metadata.json](metadata.json) records sources, hashes and the performed
rendered text-bound checks; [text_bounds.json](text_bounds.json) records the
individual rendered extents. These checks establish canvas containment and
an empty lower text margin, not automated detection of all possible overlaps.

```sh
.venv/bin/python src/documents/plot_graphical_abstract.py
```
