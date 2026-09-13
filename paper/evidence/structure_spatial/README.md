# RAW process components and CB-FL-S spatial performance

Results 3.2 compares function/process levels; Results 3.3 describes CB-FL-S site-error distributions
and environmental-zone variation. Both use the completed process
run, raw ERA5-Land forcing, `median_cutoff` scoring dates and the frozen primary
test partition. They precede DEM and residual-learning Results.

- [Function comparison figure](../../../fig/paper_figures/Fig_06.pdf)
- [Site-error distributions by environmental zone](../../../fig/paper_figures/Fig_07.pdf)
- [Component metrics and paired intervals](function_performance.csv)
- [Constituent model pairs](controlled_pairs.csv) and [common observation support](function_support.csv)
- [Site metrics](cb_fl_s_site_metrics.csv), [zone metrics](cb_fl_s_zone_metrics.csv), and [supplementary support table](../../tables/zone_support.tex)
- [Sources and artifact hashes](manifest.json), [independent numerical checks](verification.json), and [claim evidence](claim_evidence.csv)

Component summaries weight the fixed matched pairs equally: five FL–FB pairs,
four CL–CB pairs, four S–P pairs and eight absent/present-chilling pairs. Every
constituent model within a family uses the same finite-scoring observations.
Absolute errors, squared errors and signed errors are averaged separately across
pairs, within sites and across equally weighted sites. This is not an ensemble
prediction, and the model pairs are not independent replicates. Family MAE
changes are right minus left; negative values favour the right-hand level.
Columns labelled `left_rmse`, `right_rmse` and zone `rmse` contain the square
root of averaged squared errors, in days. Bias is predicted minus
observed date, in days. Overall summaries weight all four stages equally;
an absent stage prevents an overall summary.

Uncertainty uses 2,000 resamples of the frozen independence groups, preserving
all member sites with their group multiplicity. Stage intervals require ten
contributing groups and 95% finite resamples; overall intervals require ten
groups separately in every stage. Intervals are pointwise and not adjusted for
multiple comparisons. Sparse zones retain descriptive estimates and explicit
support. CB-FL-S is identified from the same RAW test comparison; its spatial
summary provides no separate validation of model selection or causal climate
effect. Zone IDs are stored unchanged as TZ01–TZ05 and displayed as EZ01–EZ05.

The fixed 4 November administrative scoring convention remains in force for
BBCH81 and BBCH89; these assigned dates do not establish thermal attainment.
Figure 6 shows only four overall component comparisons using paired dots and
exact MAE labels. Figure 7 shows individual site MAEs, their zone median and
interquartile range, and contributing site counts. Quartiles use linear
interpolation across equally weighted site MAEs; these ranges are descriptive,
not confidence intervals. Zone mean MAEs and their bootstrap intervals remain
in the supporting tables. Each Figure 7 panel expands 0–30 d and shows 30–85 d
in an adjacent narrow strip; slashes mark the change of scale and no values
are omitted. Vertical jitter separates overlapping site errors without
quantitative meaning. The legend occupies one row. Geography and observation
coverage remain in Figure 4 and Supplementary Figure S2.

```sh
.venv/bin/python src/visualization/reproduce.py
```

Current prose is maintained in `paper/manuscript.tex` and `paper/supplementary.tex`.
Original manifests preserve the hashes of the analysis-time sources.
