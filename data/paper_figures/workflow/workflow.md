# Grapevine phenology workflow

## Implemented study

Figure 1 describes the completed primary held-out-site analysis in the current
manuscript. The process run is `model_run/results/median_cutoff_calibration_20260912/`;
the residual-learning run is `model_run/results/median_cutoff_ml_20260912/`.
Completion is established by their saved status, locks, predictions and analysis
manifests, independently of the workflow illustration. Separate spatial-block,
warm-year and warm-site experiments have not been completed under this final
procedure. Environmental-zone comparisons describe held-out sites within the
represented climate domain; they are not zone-exclusion experiments.

| Panel | Implemented operation | Output |
| --- | --- | --- |
| (a) Data | Phenology QC and exact weather/terrain matching for BBCH07, 65, 81 and 89 | 74,618 observations at 3,169 source-qualified sites in 11 countries, 1951–2025 |
| (b) Temperature | RAW ERA5-Land and DEM-based elevation correction | Two temperature inputs, each calibrated separately |
| (c) Models | Ten process structures crossed with temperature and absence/presence of TabM | 40 configurations per stage |
| (d) Calibration and testing | Group-preserving primary split, early threshold fitting, median maturity calibration and nested residual learning | Locked process and hybrid dates, attainment flags and scoring errors |
| (e) Results | Process accuracy, structural contrasts, spatial patterns, DEM effects, ML gains and DEM effects within hybrids | Figures 5–10 and supporting supplementary results |

## (a) Matched data

The four equal target stages are budburst (BBCH07), flowering (BBCH65), veraison
(BBCH81) and maturity/harvest (BBCH89). BBCH07 remains distinct from BBCH09;
BBCH89 is an operational endpoint that can include harvest decisions. The final
matched population contains 26,443 site–years. Repeated accepted observations
are retained. A source-qualified identifier is not proof of an independent
physical vineyard; the partition preserves larger independence groups.

The modelling snapshot follows the revised screening and matching described in
manuscript Section 2.3. It differs from the phenology-only population used for
the study-area overview. Its authoritative inputs are
`model_run/results/pooled_calibration_20260912/calibration_observations.csv.gz`
and `test_observations.csv.gz`. Site/grid identities are retained from
`model_run/results/publication_cohort_20260910/sites.csv`.

Weather is daily ERA5-Land mean temperature on the official 0.1° grid. Terrain
uses Copernicus GLO-30, approximately 30 m, and official ERA5-Land invariant
geopotential. Daily weather is neither station measurement nor DEM-resolution
meteorology.

## (b) Temperature inputs

The paired inputs are RAW and DEM-corrected temperature:

T_adj = T_raw − 0.0065 × (z_site − z_grid),

where temperature is in °C and elevation is in metres. Site elevation is from
GLO-30. Grid elevation is official ERA5-Land geopotential divided by
9.80665 m s⁻²; a Copernicus grid-cell mean is not model orography. The lapse
rate is fixed at 0.0065 °C m⁻¹. Process thresholds and residual learners are
fitted separately for each input on the same calibration population. DEM
contrasts therefore compare fitted prediction workflows, including
recalibration, rather than temperature changes with parameters held fixed.

## (c) Factorial model catalogue

| Process | Function | Interaction | ML | T |
| --- | --- | --- | --- | --- |
| Forcing | Linear / beta | — | No / Yes | RAW / DEM |
| Chilling + forcing | F: linear / beta; C: triangular / beta | Sequential | No / Yes | RAW / DEM |
| Chilling + forcing | F: linear / beta; C: triangular / beta | Parallel | No / Yes | RAW / DEM |

Alternatives are fully crossed within each row. The two forcing-only, four
sequential and four parallel structures are FL, FB, CL-FL-S, CL-FL-P, CB-FL-S,
CB-FL-P, CL-FB-S, CL-FB-P, CB-FB-S and CB-FB-P. Residual variants append -ML.
Temperature input remains a separate factor. Ten structures × two inputs ×
two ML options give 40 configurations for each of the four stages.

Cardinal temperatures and response shapes are fixed; forcing thresholds and
chilling requirements are calibrated. Forcing-only budburst starts on
1 January; chilling starts on 1 September of the preceding year. Later stages
follow the simulated 07 → 65 → 81 → 89 sequence without observed-stage
initialization. Full equations and numerical bounds are in manuscript Models
and Model calibration sections and the implemented process catalogue in `model/`.

## (d) Calibration, residual training and scoring

### Primary allocation

Five environmental zones use k-means on standardized twelve-month RAW
ERA5-Land temperature profiles for 1991–2020. Each of 1,792 unique weather-grid
cells contributes once to clustering. The seeded clustering uses 20
initializations and seed 20260909; labels are ordered by mean annual
temperature. Countries and phenological outcomes are not clustering inputs.

Transitive independence groups join sites sharing a weather grid, identical
coordinates or coordinates rounded to four decimals. Seeded within-zone
allocation targets approximately 80% calibration and 20% test sites with
intact groups and collective four-stage support. Revised screening preserves
the existing assignments of surviving sites.

| Partition | Observations | Source-qualified sites | Independence groups |
| --- | ---: | ---: | ---: |
| Calibration | 59,472 | 2,534 | 1,434 |
| Test | 15,146 | 635 | 357 |
| Total | 74,618 | 3,169 | 1,791 |

The same partitions apply to every process structure, temperature input and
ML option. Four inner calibration folds preserve groups and environmental-zone
balance. No test labels enter parameter fitting, predictive preprocessing or
neural tuning.

### Process calibration

BBCH07, 65 and 81 thresholds and any chilling requirement are fitted jointly
using equal-site MAE, a ±1 d bias target and a raw-attainment floor of 99% under
both site and observation weighting. The bias target can remain infeasible;
diagnostics retain that information. After early fitting, these parameters
are frozen. Maturity requirements are the lower equal-site weighted median
of valid thermal accumulation between raw predicted veraison and observed
maturity, subject only to numerical requirement bounds. Maturity has no
full-attainment constraint.

`calibrate_median_cutoff.py` and `median_cutoff.py` in `model_run/src/` implement
this procedure. Fitted parameters, calibration locks, completion records,
raw/scoring predictions and attainment metrics are saved per structure/input.

### Residual learning

Stage-specific TabM targets observed minus raw, unassigned process dates.
Four ordinary process refits exclude each prediction fold. Six further refits
exclude each unordered pair of folds. During neural validation in fold h,
training observations in fold k use the process fit excluding h and k;
validation observations use the fit excluding h. Every refit repeats the
same early-stage and median-maturity calibration procedure.

Preprocessing is fitted within the relevant neural-training folds. Epoch
selection uses the grouped inner validation; final residual learners train
on ordinary out-of-fold residuals using three seeds. Locked full-calibration
process predictions supply the test inputs. Hybrid ordering preserves at least
one day between attained consecutive stages; residual learning does not create
raw attainment for an unattained process stage. Implementation is in
`model_run/src/cutoff_ml_crossfit.py` and `run_cutoff_ml.py`.

### Prediction and scoring

Raw dates and attainment flags remain separate from administrative scoring
dates. The fixed 4 November cutoff is the latest calibration BBCH89 month–day,
not recalculated inside folds. Late or unattained BBCH81/89 predictions receive
this date for scoring; assignment of veraison also assigns maturity. The rule
also applies during early veraison fitting but does not alter thermal
accumulation or the raw-attainment constraint. Historical observation-screening
windows never clip process predictions. Calibration error from the final fit
is apparent training performance, not out-of-fold predictive accuracy.

## (e) Production of manuscript results

| Figure / results | Computation | Source and saved analysis |
| --- | --- | --- |
| Fig. 5 / 3.1 | RAW process MAE by model and stage, separately for calibration and test; descriptive point estimates | `model_run/src/prepare_pbm_results.py`; `paper/pbm_results_20260913/` |
| Fig. 6 / 3.2 | 21 controlled RAW structure pairs: 5 forcing, 4 chilling, 4 interaction and 8 chilling-presence contrasts; common finite observations within each contrast family | `model_run/src/analyze_raw_structure_spatial.py`; `paper/structure_spatial_20260913/` |
| Fig. 7 / 3.3 | RAW CB-FL-S site MAE distributions and environmental-zone summaries | Same structural/spatial analysis package |
| Fig. 8 / 3.4 | Paired process RAW − DEM MAE across all ten structures; stage and terrain contrasts, with supporting zone/country summaries | `model_run/src/analyze_dem_results.py` and `plot_dem_results.py`; `paper/dem_results_20260913/` |
| Fig. 9 / 3.5 | RAW process − hybrid MAE, model-specific gains, environmental-zone gains and remaining hybrid error | `model_run/src/analyze_ml_zones.py` and `plot_ml_results.py`; `paper/ml_results_20260913/` |
| Fig. 10 / 3.6 | RAW-hybrid − DEM-hybrid MAE by model, stage and environmental zone | Same ML analysis package |
| Results 3.5–3.6 and Discussion | Original process accuracy versus ML gain; paired decrease in DEM benefit after ML | `model_run/src/analyze_ml_baseline_link.py`; `paper/ml_baseline_link_20260913/` |

CB-FL-S is the lowest-MAE RAW process model in the primary test ranking.
Its spatial display is descriptive; this ranking is not an independent
selection-validation experiment, and the other contrasts retain all ten
structures. Site interquartile ranges in Figure 7 describe between-site
variation, not confidence intervals.

The process DEM, RAW ML and hybrid DEM comparisons each require finite scoring
errors in every included arm and retain the same 15,105 observations at 633
sites in 355 original independence groups. The smaller cohort is specific to
these paired comparisons; it does not replace the primary test count. Losses
are averaged across the ten fixed structures, within sites and equally across
sites; overall results give each of the four stages equal weight. Averaging
model errors does not create an ensemble prediction. Per-model RAW summaries
and structural contrast families retain their own documented finite masks.

Positive MAE gain denotes improvement. The paired decrease in DEM benefit is
[MAE(process, RAW) − MAE(process, DEM)] −
[MAE(hybrid, RAW) − MAE(hybrid, DEM)]. It uses identical observation identities
and the same original-group multiplicities in each bootstrap draw. A positive
value means that the additional DEM benefit is smaller after ML. Percentage
gains use the corresponding workflow's own RAW MAE. The baseline–ML-gain
association is descriptive because gain contains baseline error arithmetically.

Pointwise 95% intervals use 2,000 resamples of the original independence groups,
with site weights multiplied by sampled group multiplicity. Fixed model
structures are not resampled. Intervals require at least ten contributing
groups in each included stage and at least 95% finite draws, without
renormalizing away unsupported stages. Sparse cells remain descriptive and
are visibly marked. Bias and supplementary DEM RMSE diagnostics accompany
MAE; primary ML figures focus on gains and final accuracy.

Terrain classes use calibration-site tertiles. Local elevation variability is
the native 11 × 11-pixel GLO-30 standard deviation; regional semivariogram sill
uses smoothed terrain within 20 km. Unsupported sill fits remain missing.
Terrain and environmental-zone contrasts are predictive associations, not
causal effects. Climate-change projections and GCM downscaling are outside the
study scope.

## Figure specification and reproduction

The active source is `src/phenology/draw_workflow.swift`. Five pastel panels
run vertically: blue data, ochre temperature, purple models, green
calibration/testing and rose results. Horizontal bold panel letters in
parentheses sit outside the left edge. The fully crossed model table and
single calibration-to-test lock arrow preserve the experimental structure.
Six analysis cards summarize the comparisons without figure-number references.
The bias target remains in the methods specification, outside the figure. There is no
separate overall title or rotated panel heading.

The vector PDF is 180 mm wide and approximately 223.8 mm high. Helvetica body
and card labels are 8 pt, bold panel letters 9 pt and equation subscripts 6 pt.
All text remains selectable. Vector arrows avoid substituted arrow glyphs.
The PNG is a preview; the manuscript embeds the PDF at the shared figure
scaling. The caption and Overall workflow subsection use the same panel map.

Rebuild from the repository root:

```sh
swift -module-cache-path /tmp/grape-workflow-swift-cache src/phenology/draw_workflow.swift
.venv/bin/tectonic --keep-logs --keep-intermediates --outdir paper paper/manuscript.tex
.venv/bin/python src/phenology/verify_paper_figure_style.py --manuscript paper/manuscript.pdf --supplementary paper/supplementary.pdf --output paper/workflow_update_20260913/figure_verification.json
```

The drawing checks text overflow, model names and configuration count, required
content, native dimensions and fonts. `typography_verification.json` records
the native export checks. The manuscript build additionally requires clean
references, no overfull boxes and visual inspection of Figure 1 at its final
embedded size. `paper/workflow_update_20260913/` records cohort and artifact
verification. The preceding workflow source and outputs are retained in
`paper/archive/before_fig1_current_workflow_20260913/`.
