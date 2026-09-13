# Portrait graphical abstract

[PDF](graphical_abstract.pdf), [editable SVG](graphical_abstract.svg),
[PNG](graphical_abstract.png), [300-dpi TIFF](graphical_abstract.tiff).

The portrait diagram explains three components of grapevine phenology
prediction in the order of computation:

1. **DEM:** site-to-grid elevation differences adjust temperature forcing.
   Under the fixed lapse rate, a site above the weather-grid elevation has
   cooler adjusted input, and a site below it has warmer input.
2. **PBMs:** forcing, with or without chilling, accumulates development until
   a stage threshold is reached.
3. **ML:** calibration observations define date residuals; environmental
   covariates help predict a residual adjustment to the process date.

The hill, thermometers, development curve, calendars and network are conceptual
illustrations, not measured values, a fitted trajectory or the exact TabM
architecture. The graphic shows the combined pipeline; RAW and no-ML controls
remain part of the manuscript's factorial comparison. Process thresholds and
learners are fitted separately under each temperature input. ML adjusts dates
for attained stages without changing thermal states or repairing non-attainment.
The illustrated roles explain how corrections can help; the experiments do not
identify the physical or biological mechanisms behind the accuracy gains.

The final statements summarize the paired result: DEM improved mean PBM
accuracy, with a small, uncertain additional benefit after residual learning.
Flowering gains from residual learning under RAW temperature were 10.58 days
in EZ05 and 1.44 days in EZ03. The five environmental zones summarize monthly
temperature profiles; sparse zone--stage coverage limits regional inference.
Sources and file hashes are recorded in [metadata.json](metadata.json).

The editable vector canvas is 7.2 × 10.4 inches; raster exports are 2,160 × 3,120
pixels at 300 dpi.

```sh
.venv/bin/python src/documents/plot_graphical_abstract.py
```
