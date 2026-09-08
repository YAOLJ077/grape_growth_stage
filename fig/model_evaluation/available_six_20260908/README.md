# Calibration and test errors: six completed models

The figure compares stage-specific, site-balanced MAE for FL, FB, CL-FL-S,
CL-FL-P, CB-FL-S and CB-FL-P. The common frozen cohort contains 1,460 French
sites and 10,921 observations during 1951–2022, with 1,168 calibration sites
(9,080 observations) and 292 held-out sites (1,841 observations).

These are partial results from the literature-fixed-response, RAW-temperature
experiment. Four other structures are omitted, not assigned zero error.
The split preserves shared weather-grid/location groups but is not stratified
by clustered temperature zones. No DEM correction or residual ML is included.

MAE is averaged within each site and then equally across sites, separately for
each stage and partition. Calibration errors describe fitting, not independent
predictive accuracy. Test errors use locked parameters at held-out sites.
Calibration attains all observations; BBCH89 testing has one unattained event
for FB and two for each other plotted model. All other test events are attained.
The dagger and following number indicate unattained observations; MAE uses only
attained events. Different attainment therefore gives slightly different finite
test subsets. All six selected fits report optimizer convergence; this does not
establish global optimality. The figure does not show uncertainty intervals.

## Figure specification

- Question: how do calibration and held-out test MAE differ by stage and model?
- Comparison: 48 metrics, six models × four stages × two partitions.
- Form: grouped bars in four stage panels, with a common zero-based MAE axis
  and model order. No overall title; 15-point legend; panel letters in parentheses.
- Encoding: blue solid calibration bars; gold open test bars. Colour and fill
  distinguish partitions. Dagger counts identify incomplete attainment.
- Export: 720 × 655 pt vector PDF and 300-dpi PNG, using Swift CoreGraphics.
- Evidence: model-level saved metrics, regenerated prediction/error verification,
  model fits, frozen cohort checksums and accompanying source CSV/JSON.

Reproduce into a new directory; existing figures are not overwritten:

```sh
python model_run/src/plot_calibration_test.py \
  --run model_run/results/available_site_calibration_20260907 \
  --models FL FB CL-FL-S CL-FL-P CB-FL-S CB-FL-P \
  --output fig/model_evaluation/available_six_rerun
```
