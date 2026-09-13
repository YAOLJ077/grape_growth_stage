# Process-based models under raw ERA5-Land forcing

Fig. 5 reports MAE for the ten completed process-based models (PMBs).
Panel (a) gives overall performance with equal weight for BBCH07, 65, 81 and 89;
panels (b–e) give the four stages individually. Light brown bars show apparent
calibration performance and blue bars show held-out test performance. Bar-end
numbers give MAE in days to one decimal. All bars span 8 d to the annotated MAE;
identical 8–20 d axes show error above the explicitly stated 8 d baseline.

Supplementary Fig. S1 gives stage-specific signed bias as labelled bars from zero.
The same partition colours and model order apply. Detailed bias interpretation
is in Supplementary Section S11; the main Results retain a concise summary.

- [Main MAE figure](../../../fig/paper_figures/Fig_05.pdf)
- [Supplementary bias figure](../../../fig/paper_figures/Fig_S01.pdf)
- [Exact plotted values and labels](plotted_values.csv)
- [Stage metrics](stage_metrics.csv), [equal-stage summaries](overall_metrics.csv)
- [Calibration flags](calibration_flags.csv), [evidence and hashes](manifest.json)

All 20 PMB units were artifact-verified and date-based metrics independently
recomputed. DEM rows remain in supporting CSVs but do not enter these figures.
Errors average within sites and then equally across sites. Scoring dates use the
4 November rule for BBCH81/89; assignment is separate from actual attainment.
The charts show point estimates, without confidence intervals or significance
claims. Fonts are Helvetica 8 pt, with bold 9 pt parenthesized panel letters,
no subplot titles, and 180 mm native width. The numerical LaTeX accuracy table
is a supporting export and is not inserted in the main paper.

```sh
.venv/bin/python src/visualization/reproduce.py
```

The post-ML renderer verifies that its RAW process comparator matches this
reviewed evidence, then preserves the main MAE section and supplementary bias.

