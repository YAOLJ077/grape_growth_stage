# Grapevine phenology workflow

## Scientific workflow

The study compares predictive accuracy across grapevine phenology models of
different structural complexity. DEM-based temperature correction is a separate
input factor crossed with every process-only and residual-learning model.
Terrain-associated variation in correction benefits is assessed through paired
held-out errors. Spatial and warm-climate holdouts assess transferability.

| Panel | Inputs and comparison | Output |
| --- | --- | --- |
| (a) Data | All-country European observations of the four equal target stages BBCH07, 65, 81 and 89; daily ERA5-Land weather; Copernicus GLO-30 and official grid geopotential | Harmonized, quality-controlled site–year records |
| (b) Temperature | Raw and elevation-corrected temperatures | Two paired temperature-input variants |
| (c) Models | Linear/beta forcing × no/piecewise-linear/beta chilling; sequential/parallel interaction when chilling is present; without/with residual ML | 10 process structures; 40 configurations per BBCH stage across the two inputs and two residual-ML options |
| (d) Calibration and testing | Cluster site temperature profiles into temperature zones; randomly allocate whole sites within each zone to 80% calibration and 20% testing | Locked-model MAE, RMSE and bias, with spatial and warm-year transfer tests |
| (e) Terrain effects | Paired RAW/DEM errors at matched sites, years and stages; elevation mismatch, elevation, slope, aspect and local relief | Correction benefit by terrain condition, without/with residual ML, and paired site-group uncertainty |

The ten process-only structures are implemented in `model/` and verified with
synthetic tests. Real-data calibration, residual learning, new split mappings
and terrain-effect analyses remain prospective. Climate-change projections and
GCM downscaling are outside the current study scope.

## Figure design

One portrait figure at A4 width, cropped vertically to approximately
210 × 261.1 mm (595.28 × 740 pt), with five full-width sections connected
vertically. Panel letters and short headings sit outside the left edge of each
section, with letters in parentheses: (a), (b), (c), (d), (e). Headings are
rotated 90° counterclockwise to read bottom-to-top and centred on the panel
height. No internal heading row or title badge is present. Removing the
heading rows saves 18 pt per panel, with body text unchanged. Panel (e) includes
a paired-test comparison row above the terrain descriptors and correction-benefit cards.
A model matrix carries the model catalogue.
Top and bottom blank space is cropped to approximately 12 pt around the panels;
the content scale and horizontal margins are unchanged.
No figure title, subtitle or bottom explanatory notes are included. References
and abbreviation definitions are retained in this file and the caption.

| Section | Content | Colour |
| --- | --- | --- |
| (a) | Data | Blue |
| (b) | Temperature | Ochre |
| (c) | Models | Purple |
| (d) | Calibration and testing | Green |
| (e) | Terrain effects | Rose |

The model matrix has five columns: Process, Function, Interaction, ML and T.
Its three rows describe forcing-only, sequential chilling–forcing and parallel
chilling–forcing families, with alternatives fully crossed within each row.
The ten model names are retained below the matrix; -S and -P distinguish
interactions, and -ML identifies residual learning. Forcing-only names remain
FL and FB. T denotes original (RAW) or DEM-corrected temperature.

## Model catalogue

The workflow figure uses the compact factor table below. Manuscript Table 4
lists all 20 model names, with ML off/on as separate rows. Original (RAW) and
DEM-corrected (DEM) temperature are levels of a separate input factor crossed
with every model, giving 40 experimental configurations per stage. Temperature
labels are not part of model names. The temperature factor is described in the
manuscript methods, without an extra block at the end of Table 4.

| Process | Function | Interaction | ML | T |
| --- | --- | --- | --- | --- |
| Forcing | Linear / beta | — | No / Yes | Original / DEM-corrected |
| Chilling + forcing | F: linear / beta; C: triangular / beta | Sequential | No / Yes | Original / DEM-corrected |
| Chilling + forcing | F: linear / beta; C: triangular / beta | Parallel | No / Yes | Original / DEM-corrected |

Alternatives within each row are fully crossed. The rows contain 2, 4 and 4
process structures, respectively. Original temperature is the RAW input;
DEM-corrected temperature is the DEM input. No / Yes denotes absence or presence
of residual machine learning. The ten structure names remain FL, FB, CL-FL-S,
CL-FL-P, CB-FL-S, CB-FL-P, CL-FB-S, CL-FB-P, CB-FB-S and CB-FB-P; residual
variants append -ML (for example CL-FL-S-ML and CL-FL-P-ML).

F = forcing; C = chilling; L = linear; B = beta; S = sequential interaction;
P = parallel interaction; ML = residual machine learning.
In CL, “linear” specifically denotes the triangular, piecewise-linear chilling
response defined below. It is not an unrestricted straight-line chilling response.

The three rows represent two forcing-only structures and eight chilling–forcing
structures (four function combinations × two interactions): ten process
structures in total. Each receives raw (RAW) or DEM-corrected (DEM)
temperature, without or with residual learning: 10 × 2 × 2 = 40 candidate
configurations per BBCH stage. All structures enter the factorial comparison;
there is no preliminary selection of a single best process model.
Model names comprise the process structure and optional -ML suffix only;
record RAW or DEM separately as `temperature_input`. A run identifier may
retain `BBCH{stage}-{model}[-ML]-{RAW|DEM}` for provenance, where `model`
includes -S or -P for chilling–forcing structures, for example
`BBCH07-CL-FL-S-DEM` and `BBCH07-CL-FL-P-ML-DEM`. The interaction suffix
precedes -ML. Forcing-only examples remain `BBCH65-FL-RAW` and
`BBCH65-FL-ML-RAW`. An accompanying `interaction` field (`none`, `sequential`
or `parallel`) must agree with the model name. Historical unsuffixed outputs
are not silently renamed; their interaction must first be verified from run metadata.

Chilling begins on 1 September of the preceding year. Sequential models start
forcing on the day after the chilling requirement is fulfilled. Parallel
models multiply daily budburst forcing by
`K = Kmin + (1-Kmin)*min(C_before_day/Ccrit, 1)`, with `Kmin` fixed at 0.2
as an experimental control, not a literature-established grapevine constant.
This competence response follows Liu et al. (2018), Eq. (7), adapted to the
selected forcing and chilling functions; chilling and forcing overlap and
budburst does not require a separate full-chilling gate. These alternatives
concern dormancy release and budburst, not simultaneous progression of the four
target stages. Later stages retain the ordered BBCH07→65→81→89 development
sequence, restarting unmodified forcing on the next day after each predicted
stage and discarding overshoot. Observed dates never initialize later stages.
Forcing-only models have no chilling–forcing interaction (—). The interaction
applies to both ML options in each chilling–forcing row. Parallel variants
are proposed adaptations, not models evaluated by Fila et al. (2014).

Interaction reference: Chuine, I. (2000). A unified model for budburst of trees.
*Journal of Theoretical Biology*, 207, 337–347.
[DOI: 10.1006/jtbi.2000.2178](https://doi.org/10.1006/jtbi.2000.2178).
Local source: `reference/Chuine et al.pdf`.

Parallel competence reference: Liu, Q., Fu, Y. H., Liu, Y., Janssens, I. A.,
and Piao, S. (2018). Simulating the onset of spring vegetation growth across
the Northern Hemisphere. *Global Change Biology*, 24, 1342–1356.
[DOI: 10.1111/gcb.13954](https://doi.org/10.1111/gcb.13954).

The process structures are implemented but not yet calibrated or evaluated on
the matched study data. Residual-ML variants remain unimplemented.
Complexity reflects component inclusion and response-function flexibility,
not a universal ranking of parameter counts or expected accuracy.

## Chilling functions and references

**Beta chilling.** Fila et al. (2014), Table 1 and Section 2.1, uses beta chilling
in CF8, CF9 and CF10. Its forcing-only families use beta or linear forcing.
The paper does not provide the piecewise-linear chilling comparator.

**Piecewise-linear chilling.** Equation (1) in de Wergifosse et al. (2020)
defines a triangular daily chilling response, based on Hänninen (1990):

```text
Rc(T) = 0                                T ≤ Tmin or T ≥ Tmax
        (T − Tmin) / (Topt − Tmin)        Tmin < T ≤ Topt
        (Tmax − T) / (Tmax − Topt)        Topt < T < Tmax
```

The response peaks at 1 at Topt and is zero outside the effective temperature
range. Daily rates accumulate until a chilling requirement is met.
This is direct published support for the response shape. The source model
concerns forest trees; its application to grapevine is a candidate adaptation,
requiring grapevine-specific calibration and independent testing. It is not
a linear chilling model attributed to Fila.

References:

1. Fila, G., Gardiman, M., Belvini, P., Meggio, F., and Pitacco, A. (2014).
   A comparison of different modelling solutions for studying grapevine
   phenology under present and future climate scenarios. *Agricultural and
   Forest Meteorology*, 195–196, 192–205.
   [DOI: 10.1016/j.agrformet.2014.05.011](https://doi.org/10.1016/j.agrformet.2014.05.011).
   Local source: `reference/Fila et al.pdf`.
2. de Wergifosse, L., André, F., Beudez, N., de Coligny, F., Goosse, H.,
   Jonard, F., Ponette, Q., Titeux, H., Vincke, C., and Jonard, M. (2020).
   HETEROFOR 1.0: a spatially explicit model for exploring the response of
   structurally complex forests to uncertain future conditions – Part 2:
   Phenology and water cycle. *Geoscientific Model Development*, 13, 1459–1498.
   [Equation (1), DOI: 10.5194/gmd-13-1459-2020](https://gmd.copernicus.org/articles/13/1459/2020/).
   This is the directly inspected source of the triangular chilling equation;
   its attribution to Hänninen (1990) is retained as provenance.

## Temperature correction

\[
T_{\mathrm{adj}} = T_{\mathrm{raw}} - 0.0065\,(z_{\mathrm{site}}-z_{\mathrm{grid}}).
\]

Temperatures are in °C and elevations in metres; the coefficient is
0.0065 °C m⁻¹, equivalent to 6.5 °C km⁻¹. A site 100 m above the grid elevation
receives a −0.65 °C adjustment. The same offset applies to daily mean, minimum
and maximum temperature. Site elevation is from Copernicus GLO-30; grid
elevation is official ERA5-Land geopotential divided by 9.80665 m s⁻², not a
DEM average. This is a fixed lapse-rate approximation, not a measurement of
the site's daily lapse rate. Any alternative fitted lapse rate belongs inside
calibration. The figure uses typographic subscripts and metres throughout.

## Recommended site split

The primary comparison uses a proposed **80% calibration / 20% test split of
whole sites**, randomly allocated within **temperature zones derived by
clustering site temperature profiles** across the eligible multi-country
domain. Country is not a clustering feature, stratum or allocation quota;
temperature zones can cross national borders. Stratification balances the
sampled climate domain but does not establish extrapolation skill.

- Use a common climate-normal period for all sites, preferably 1991–2020 if
  complete daily weather is available. Do not calculate each site's climate
  mean over its unequal phenology-record period. Derive the clustering profiles
  from raw ERA5-Land temperature, so RAW and DEM comparisons share zone labels.
- Define zones by unsupervised clustering of temperature-only climatological
  features. A common-period monthly temperature profile is a candidate feature
  representation; the precise features, scaling, algorithm and cluster count
  remain implementation choices to document, not an already fitted zoning.
  Do not substitute country groups or fixed temperature-quantile bins for clusters.
- Define the clustering on the eligible sites' climate covariates before random
  site allocation, without using observed phenological dates, process residuals,
  or model errors. This use of covariates defines the
  sampling strata; it is distinct from fitting predictive preprocessing, which
  remains calibration-only. Keep the resulting zones fixed across comparisons.
- Require adequate independent site/grid groups per zone for both partitions
  and grouped inner folds. Resolve sparse clusters using temperature similarity
  or a reduced cluster count, with the rule fixed before evaluating phenology
  errors. Check elevation, seasonal temperature, record-period and stage coverage
  for imbalance. Country remains a descriptive reporting variable only.
- Keep every year, stage, and duplicate/co-located site identity in the same
  partition. Also keep sites sharing an ERA5-Land cell together, preventing
  identical raw temperature series from crossing the split. Allocate these
  groups with approximate balance in site counts and climate strata; the
  achieved site proportion may differ slightly from 80/20.
- Record the climate-normal period, clustering features/scaling, algorithm,
  cluster count, fitted clustering representation, clustering and split seeds,
  and each site's `temperature_zone_id` before inspecting prediction errors.
  Save the zone-to-partition mapping separately from legacy spatial folds.
  Use one master site
  assignment across all BBCH stages and configurations; report each stage's
  realised sample sizes after quality filtering.
- Use four grouped inner folds within the calibration set for process and ML
  tuning. A repeated grouped 80/20 split can quantify split sensitivity if
  specified in advance; outer-test outcomes never guide tuning or selection.
- Include an unstratified random site-group split as a sensitivity comparison.
  Its purpose is to assess sensitivity to balancing, not to choose whichever
  partition yields the best performance.

The primary split estimates performance at unseen sites within the sampled
climate domain. Spatially blocked tests assess regional transfer, while warm-year
and warm-site holdouts probe climatic transfer. Validation must reflect both
dependence structure and the intended interpolation or extrapolation target
([Roberts et al., 2017](https://doi.org/10.1111/ecog.02881)).

The existing five-outer/four-inner, 1°-block mappings remain a separate spatial
benchmark. They are not the new stratified random split, and no stored mappings
or modelling results are changed by this workflow specification.

## Calibration and test protocol

- Fix temperature responses from literature: linear forcing base 0 °C
  (Parker et al. 2011), beta forcing 0/25.4/35 °C (Fila et al. 2014, Fbeta5*)
  and both chilling responses −1.7/1.7/13.2 °C (Fila CF10*). The triangular
  transfer is an adaptation. Reuse these values across stages, sites, models
  and temperature treatments. See `fig/model_functions/README.md` for exact
  citations, original target stages and transfer limitations.
- Calibrate four stage-specific forcing requirements and, when present, one
  chilling requirement. Fix forcing-only start at January 1 and minimum
  parallel competence at 0.2. If the lapse rate is tuned, tune it only within
  calibration. No test errors determine fixed settings or search ranges.
- Fit four stages jointly for each structure and temperature input, using
  matched observations and identical site-group splits. Each stage has its own
  forcing requirement, pooled across sites, years and cultivars. Temperature
  response parameters are shared and fixed. The fitted chilling requirement
  and fixed parallel competence apply only to budburst.
  A site may supply any one stage; all four stages must occur somewhere in the
  calibration dataset. Keep repeated accepted observations without aggregation.
- Minimize the mean of the four stage-specific site-balanced RMSEs using
  differential evolution. Within each stage, average squared errors within
  sites and then equally across sites before taking the square root. Unattained
  observed events receive a 1000-day fitting penalty, without assigning a false
  prediction date. A fit with no finite prediction for any stage is rejected.
- Default optimizer settings are three seeds (20260907, 20260908, 20260909),
  population multiplier 15, maximum 300 generations, tolerance 0.001, one worker
  and no polishing. The active threshold-only profile has four free parameters
  for forcing-only structures and five for chilling–forcing structures. Use
  `model.structure_comparison.threshold_only_settings` explicitly; unrestricted
  API defaults and previous pilot outputs are not this experiment. Full bounds
  and scientific provenance are in `model/README.md`. Save settings, input fingerprints,
  convergence and boundary diagnostics. No real-data fit or split is generated
  automatically by the model implementation.
- Train residual ML on out-of-fold process residuals generated within the
  calibration set: residual = observed DOY − process-predicted DOY.
- Restrict preprocessing, hyperparameter tuning and model selection to the
  calibration set. Lock the fitted workflow before applying it to test data.
- Calculate hybrid test predictions as process DOY + predicted residual.
  Test observations calculate predictive errors and post-fit descriptive skill
  rankings; they do not enter parameter fitting or tuning.
- Compare MAE, RMSE and mean signed error in days, defining error as predicted
  minus observed DOY. Report event-weighted and site-balanced summaries, with
  paired uncertainty intervals resampled at the independent site-group level.
- For each inner validation fold, fit preprocessing and process models only
  on that fold's training portion. Generate the residual learner's training
  targets by additional cross-fitting inside that portion. This prevents inner
  validation outcomes from entering residual training indirectly. After tuning,
  regenerate calibration-only out-of-fold residuals for final residual fitting
  and refit the process model on the complete calibration set.
- BBCH07, 65, 81 and 89 are equal targets for budburst, flowering, veraison and
  maturity/harvest, ordered as 07→65→81→89. Any one stage qualifies a site or
  year; a complete sequence is not required. Fila uses BBCH09 for budburst and
  does not define a BBCH89 model; BBCH09 is
  not substituted for BBCH07. Those adaptations require separate methodological
  justification.

## Terrain effects

Manuscript Section 2.5 contains (2.5.1) Calibration and test partitioning,
(2.5.2) Terrain effects, and (2.5.3) Predictive performance and uncertainty.

- Compare original and DEM-corrected temperature for every process-only and
  residual-learning model using identical held-out sites, years and stages.
  Both temperature treatments are calibrated independently on the same
  calibration observations; no test-set recalibration is allowed.
- Define correction benefit as MAE(RAW) − MAE(DEM), in days. Positive values
  indicate improved phenological prediction. Compare this benefit without and
  with residual learning to assess complementarity.
- Examine signed and absolute site-to-grid elevation differences, site elevation,
  slope, aspect (northness/eastness) and local elevation variability. Document
  terrain summaries and any class boundaries before inspecting test errors.
- Report stage-specific, site-balanced paired contrasts with sample sizes and
  temperature-zone composition. Use paired independent-site-group resampling
  for uncertainty and within-zone comparisons for broad climatic context.
- Interpret terrain associations as descriptive, not causal. Better phenology
  predictions alone do not validate corrected temperature; independent
  temperature observations are required for temperature-accuracy claims.
- Report unmet chilling/forcing requirements separately from finite prediction
  errors. Residual ML cannot supply a date if the process prediction is missing.
  Keep warm-year and warm-site holdouts independent of fitting and tuning.

Additional methodological reference: Roberts, D. R., et al. (2017).
Cross-validation strategies for data with temporal, spatial, hierarchical, or
phylogenetic structure. *Ecography*, 40, 913–929.
[DOI: 10.1111/ecog.02881](https://doi.org/10.1111/ecog.02881).

## Panel content

### (a) Data

Three source cards contain phenology (European all-country observations;
BBCH07/65/81/89 targets),
weather (ERA5-Land daily; 0.1° grid), and terrain (Copernicus GLO-30 ~30 m;
ERA5 grid geopotential). Their shared preparation sequence is
“BBCH harmonization → quality control → site–year matching”.

### (b) Temperature

Two input cards identify “Raw temperature” and “DEM-corrected temperature”.
The correction equation uses typographic subscripts and the unit label
“T in °C; z in m”. Both inputs apply to every candidate model.

### (c) Models

The five-factor table uses Process, Function, Interaction, ML and T columns.
Forcing-only models use linear or beta forcing and no interaction. The sequential
and parallel rows independently cross linear/beta forcing with triangular/beta
chilling. Every row includes “No / Yes” under ML and “Original / DEM-corrected”
under T. The ML and T columns have stronger purple shading. Two compact lines
below the matrix retain all ten process-model names and the instruction to append
-ML for residual learning. The models panel is 12 pt taller than the original
193-pt panel; panels (d) and (e) shift by the same amount, preserving their
layouts and the outer margins. The summary is
“10 structures × 2 inputs × 2 ML options = 40 per BBCH stage”.

### (d) Calibration and testing

The split label is “Random site split · stratified by clustered temperature
zones”. Zones derive from temperature-profile clustering, not country boundaries.
Two cards are connected by a one-way “Lock” arrow:

| Calibration set · 80% | Test set · 20% |
| --- | --- |
| Calibrate stage / chilling thresholds | Apply locked process / hybrid models |
| Fit ML on out-of-fold residuals | MAE · RMSE · Bias (days) |
| Tune within grouped inner folds | Identical held-out sites for all models |

The transfer-test label is “Keep each site intact · Additional spatial and
warm-year holdouts”.

### (e) Terrain effects

The input row is “Paired test errors · same sites, years and stages”.

| Terrain descriptors | Temperature-correction benefit |
| --- | --- |
| Site-to-grid elevation difference | MAE(RAW) − MAE(DEM) |
| Elevation · slope · aspect · relief | Compare without / with residual ML |

The left card connects to the right card. The bottom line within the panel is
“Positive difference = improvement · Paired site-group uncertainty”.
Relief denotes local elevation variability, with its spatial support documented
in the terrain-processing metadata.

## Rendering and verification

The figure uses selectable text, vector shapes, pale coloured panels, white
cards and short arrows. External headings are 9.5 pt; body text is approximately
10–11 pt. Rotated labels remain within page margins and do not overlap adjacent
labels; up to 6 pt of extension into the 16-pt panel gaps is permitted.

The exported PDF is a single 595.28 × 740 pt page, with approximately 12 pt
of blank margin above and below the panels. The complete model catalogue,
parenthesized panel letters, temperature equation, 80/20 split and paired
terrain-effect comparison remain legible at the intended print scale.
References and abbreviation definitions are outside the figure; no overall
title, subtitle or explanatory footer is present.

Reproduction command from the repository root:

```sh
swift -module-cache-path /tmp/grape-workflow-swift-cache src/phenology/draw_workflow.swift
```

The drawing source checks page size and required PDF text, then exports the PNG
preview for visual inspection. The scientific workflow and panel content are
the current specification; historical prompt wording is superseded.

## Caption

Workflow for comparing grapevine phenology models across the eligible
multi-country European domain. (a) All-country BBCH observations, daily weather
and terrain data are harmonized and matched; BBCH07, 65, 81 and 89 have equal
target status.
(b) Raw and elevation-corrected ERA5-Land temperatures define paired input
variants. (c) Six forcing/chilling function combinations, with sequential and
parallel interactions for chilling–forcing models, define ten process structures.
Each is evaluated under both temperature inputs with and without residual
learning, giving 40 configurations per stage. Beta chilling follows
Fila et al. (2014); the piecewise-linear chilling comparator uses the triangular
response in de Wergifosse et al. (2020), Eq. (1), as a candidate adaptation for
grapevine. Sequential models start forcing after chilling completion; parallel
models allow overlap, following the interaction concepts of Chuine (2000).
(d) Random allocation within temperature zones derived by clustering
site temperature profiles reserves approximately 20% of sites for testing,
retaining repeated site records and
shared weather-grid groups within partitions. All adjustable process and ML
parameters are calibrated within the remaining data. Separate spatial and
warm-year holdouts assess transfer. (e) Paired prediction errors quantify the
benefit of DEM-based temperature correction across site-to-grid elevation
differences, elevation, slope, aspect and local relief. Contrasts compare
process-only and residual-learning models, with uncertainty from paired
site-group resampling. Positive MAE(RAW) − MAE(DEM) indicates improved prediction.
ML denotes additive residual machine learning. The diagram specifies the
experimental design, not completed modelling results.

## Files

- `workflow.pdf`: A4-width vector figure with cropped top and bottom margins.
- `workflow.png`: rendered preview.
- `../../src/phenology/draw_workflow.swift`: reproducible drawing source.
