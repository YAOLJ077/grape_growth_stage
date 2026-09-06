# Grapevine phenology workflow

## Scientific workflow

The study compares historical predictive accuracy and projected climate-change
impacts across grapevine phenology models of different structural complexity.
DEM-based temperature correction and residual learning are crossed experimental
factors. Environmental adaptability is assessed through held-out prediction
errors and warm-climate transfer, with model-ranked phenological shifts as the
climate-impact comparison.

| Panel | Inputs and comparison | Output |
| --- | --- | --- |
| (a) Data | French TEMPO and German DWD BBCH observations; daily ERA5-Land weather; Copernicus GLO-30 and official grid geopotential | Harmonized, quality-controlled site–year records |
| (b) Temperature | Raw and elevation-corrected temperatures | Two paired temperature-input variants |
| (c) Models | Linear/beta forcing × no/piecewise-linear/beta chilling × without/with residual ML | 12 model combinations; 24 configurations per BBCH stage across the two inputs |
| (d) Calibration and testing | Cluster site temperature profiles into temperature zones; randomly allocate whole sites within each zone to 80% calibration and 20% testing | Locked-model MAE, RMSE and bias, with spatial and warm-year transfer tests |
| (e) Climate-change impacts | Shared baseline and future SSP2-4.5 / SSP5-8.5 scenarios; historically calibrated parameters fixed | Future-minus-baseline DOY compared across models ranked by baseline test MAE, with warm-climate transfer checks |

Stronger environmental transfer implying greater projection credibility is the
central climate-impact hypothesis. Baseline accuracy is an initial indicator,
not direct evidence of accuracy under unobserved future climates. The workflow
defines the study design; candidate models, new split mappings and future
scenario datasets require implementation or availability checks before results
can be reported.

## Figure design

One portrait figure at A4 width, cropped vertically to approximately
210 × 256.8 mm (595.28 × 728 pt), with five full-width sections connected
vertically. Panel letters and short headings sit outside the left edge of each
section, with letters in parentheses: (a), (b), (c), (d), (e). Headings are
rotated 90° counterclockwise to read bottom-to-top and centred on the panel
height. No internal heading row or title badge is present. Removing the
heading rows saves 18 pt per panel, with body text unchanged. Panel (e) includes
additional height for an explicit baseline-to-future climate-scenario input row.
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
| (e) | Climate-change impacts | Rose |

Forcing is the first column of the model matrix. Rows are grouped by forcing
function, followed by chilling option. Existing model identifiers remain stable.

## Model catalogue

| Forcing | Chilling | Process model | With residual ML |
| --- | --- | --- | --- |
| Linear | None | FL | FL-ML |
| Linear | Piecewise linear | CL-FL | CL-FL-ML |
| Linear | Beta | CB-FL | CB-FL-ML |
| Beta | None | FB | FB-ML |
| Beta | Piecewise linear | CL-FB | CL-FB-ML |
| Beta | Beta | CB-FB | CB-FB-ML |

F = forcing; C = chilling; L = linear; B = beta; ML = residual machine learning.
In CL, “linear” specifically denotes the triangular, piecewise-linear chilling
response defined below. It is not an unrestricted straight-line chilling response.

Each of the 12 combinations has a raw-temperature (-RAW) and a DEM-corrected
(-DEM) variant: 24 candidate configurations per BBCH stage.
The complete identifier is `BBCH{stage}-{model}[-ML]-{RAW|DEM}`;
for example, `BBCH07-CB-FL-ML-DEM`.

These are proposed candidate structures. Their inclusion in the figure does
not establish that they have been implemented, calibrated or validated.
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
clustering site temperature profiles** across the combined France–Germany
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
  model errors or future impact estimates. This use of covariates defines the
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

- Calibrate all adjustable process-model parameters in the calibration set,
  including response temperatures, accumulation requirements and applicable
  start-date parameters. Fixed units and structural constraints are not fitted
  parameters. If the lapse rate is tuned, tune it only within calibration.
- For each stage, structure and temperature input, use matched observations and
  identical site-group splits. Specify phase sequencing and any parameter sharing
  explicitly in the methods.
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
- BBCH07, 65, 81 and 89 represent budburst, flowering, veraison and
  maturity/harvest. Fila uses BBCH09 for budburst and does not define a BBCH89
  model. Those adaptations require separate methodological justification.

## Climate-change comparison

**Research question.** How much do projected phenological shifts differ among
forcing functions, chilling formulations and residual-ML variants, and does
DEM-based temperature correction change those differences? How do these shifts
vary across models ranked by environmental adaptability, and is stronger
observed transfer skill associated with more credible climate-impact estimates?

**Hypothesis.** Models with stronger environmental transfer skill provide more
credible climate-impact estimates. Held-out baseline MAE is an initial skill
indicator, not a direct validation of climate-change response. Warm-climate
transfer tests provide additional evidence relevant to this hypothesis.

### Skill-ranked climate-impact comparison

- Rank all configurations separately for each BBCH stage by increasing
  site-balanced MAE on the same held-out baseline observations. Lower MAE
  indicates better baseline predictive skill. Report clustered temperature-zone
  performance and descriptive country summaries alongside the pooled metric so
  that dense or easy environments do not
  determine the interpretation of adaptability.
- Quantify uncertainty in MAE differences and rank stability with paired
  site-group resampling. Avoid treating nearly tied ranks as clear evidence
  that one model transfers better than another.
- Assess environmental adaptability independently through climate-defined
  warm-site and warm-year holdouts, reporting both their absolute MAE and
  performance degradation relative to baseline. Keep baseline and transfer
  rankings separate; do not invent an arbitrary combined adaptability score.
- Plot future-minus-baseline DOY against baseline skill rank, with the warm-climate
  transfer rank available as a complementary ordering. Pair models on the same
  sites, climate members, scenarios and periods. Include all candidate structures,
  distinguishing forcing, chilling, residual-ML and temperature-input variants.
- Assess whether higher-skill groups differ systematically in projected shift,
  and whether their shifts are stable across calibration resamples and climate
  members. Prespecify any top-ranked group before examining climate-impact
  patterns. Smaller inter-model spread or agreement is not evidence of accuracy
  by itself; structurally similar models can share biases.
- Test response credibility with observed warm-period anomalies where possible:
  fit on non-held-out data, predict both reference and warm-period phenology,
  and compare predicted and observed changes at matched sites/stages. Such
  hindcast tests support transfer within observed conditions, not verification
  of unobserved future climates or attribution of observed changes solely to
  temperature. Account for changes in cultivar, management and observation mix.
- Baseline test outcomes can define a descriptive ranking after all fitting is
  locked. If this ranking selects models or determines ensemble weights, that
  test set becomes selection data: use separate untouched evaluation data for
  claims about the selected or weighted ensemble. Do not treat inverse-MAE
  weights as probabilities of future correctness.

Present-climate prediction errors and future-climate responses are separate
endpoints. Similar historical accuracy does not guarantee similar future
responses; Fila et al. (2014) explicitly evaluates model structure and calibration
data as influences on future behaviour. All configurations receive the same
calibration information and climate inputs for paired comparisons.

### Controlled warming sensitivity

- Use the same complete historical daily sequences for every configuration,
  with temperature perturbations of 0, +1, +2, +3 and +4 °C applied to mean,
  minimum and maximum temperature, including the preceding chilling season.
  These are idealised sensitivity experiments, not dated climate projections.
- Add separate winter-only and forcing-season perturbations to distinguish
  reduced chilling from accelerated forcing. Define seasonal windows in advance.
  Keep site properties and non-temperature drivers fixed for the temperature-only
  experiment; consistently recompute all temperature-derived ML predictors.
- Freeze every process parameter, residual learner and fitted preprocessing
  transformation after calibration. RAW and DEM configurations each retain
  their own historical calibration. Neither future climate nor test outcomes
  trigger recalibration.
- Compare stage shifts, temperature sensitivity in days per °C, stage intervals
  and the frequency of unmet chilling or forcing requirements. A missing event
  has no finite DOY shift; report its frequency separately, with paired shifts
  calculated only where both baseline and perturbed events occur. Do not replace
  missing events with the last day of the simulation.

### Climate-scenario ensemble

Future scenario inputs are an additional data requirement; ERA5-Land is the
historical forcing and does not provide future projections. A proposed extension
uses a documented, bias-adjusted daily multi-climate-model ensemble under
SSP2-4.5 and SSP5-8.5, comparing 2041–2070 and 2071–2100 with 1991–2020.
These periods and pathways are design candidates, subject to data availability.

Use each climate model's consistently processed historical and future series
for its paired change estimate. Historical comparisons against ERA5-Land check
forcing compatibility; subtracting an ERA5-driven baseline directly from a
different model's unaligned future climatology would confound climate change
with forcing-source differences. Preserve calendars, accumulation windows and
temperature-variable consistency, with sufficient preceding-season spin-up.
Avoid double elevation correction: anomalies already mapped to the ERA5 grid
receive the site-to-ERA5 correction once; other products require their own
documented orography and downscaling convention.

For phenology configuration m, climate model g and scenario s:

\[
\Delta D_{m,g,s} = \overline{D}^{\mathrm{future}}_{m,g,s}
                 - \overline{D}^{\mathrm{baseline}}_{m,g}.
\]

Negative values indicate earlier occurrence. Paired differences
\(\Delta D_{m_1,g,s}-\Delta D_{m_2,g,s}\) isolate configuration contrasts under
the same climate member, scenario, site and stage. Report contrasts for forcing
shape, chilling inclusion/shape, residual ML and DEM correction, with interactions
where supported. Separate variation across phenology structures, calibration
parameter resamples, climate models and scenarios; a raw ensemble range is not
a calibrated confidence interval.

### Climate-transfer safeguards

- Evaluate warm-year holdouts using climate-defined anomalies and a preregistered
  threshold, without using phenology outcomes to select the years. Keep held-out
  years out of all calibration and residual fitting. A warm-site/environmental
  holdout is a separate test, with all records of those sites excluded. Report
  these separately from the within-domain primary test.
- Compare future predictor ranges and combinations with the calibration domain,
  especially for residual ML. Better interpolation accuracy alone does not
  validate a future residual correction. Retain process-only projections as
  references and label unsupported hybrid extrapolation explicitly.
- Do not provide a hybrid DOY when the process model fails to reach the event;
  an additive residual cannot supply the missing process prediction. Record
  chronological violations and assess stage ordering separately.
- Hold cultivar and management assumptions fixed for climate-only comparisons.
  BBCH89 may incorporate management-driven harvest timing; its projected shift
  is conditional on the endpoint definition and these assumptions.

Additional methodological reference: Roberts, D. R., et al. (2017).
Cross-validation strategies for data with temporal, spatial, hierarchical, or
phylogenetic structure. *Ecography*, 40, 913–929.
[DOI: 10.1111/ecog.02881](https://doi.org/10.1111/ecog.02881).

## Panel content

### (a) Data

Three source cards contain phenology (FR: TEMPO; DE: DWD; BBCH07/65/81/89),
weather (ERA5-Land daily; 0.1° grid), and terrain (Copernicus GLO-30 ~30 m;
ERA5 grid geopotential). Their shared preparation sequence is
“BBCH harmonization → quality control → site–year matching”.

### (b) Temperature

Two input cards identify “Raw temperature” and “DEM-corrected temperature”.
The correction equation uses typographic subscripts and the unit label
“T in °C; z in m”. Both inputs apply to every candidate model.

### (c) Models

The forcing-first, six-row catalogue contains all twelve model names.
Linear and beta forcing each have no-chilling, piecewise-linear and beta-chilling
rows. The residual-ML column has stronger purple shading. The matrix summary is
“12 combinations × 2 inputs = 24 configurations per BBCH stage”.

### (d) Calibration and testing

The split label is “Random site split · stratified by clustered temperature
zones”. Zones derive from temperature-profile clustering, not country boundaries.
Two cards are connected by a one-way “Lock” arrow:

| Calibration set · 80% | Test set · 20% |
| --- | --- |
| Calibrate all process parameters | Apply locked process / hybrid models |
| Fit ML on out-of-fold residuals | MAE · RMSE · Bias (days) |
| Tune within grouped inner folds | Identical held-out sites for all models |

The transfer-test label is “Keep each site intact · Additional spatial and
warm-year holdouts”.

### (e) Climate-change impacts

The climate input row is “Baseline climate → future climate scenarios
(SSP2-4.5 / SSP5-8.5)”. These pathways require future scenario data distinct
from historical ERA5-Land forcing.

| Rank model adaptability | Project phenology shifts |
| --- | --- |
| Baseline test MAE → skill rank | Shared scenarios; fixed parameters |
| Check warm-climate transfer | Future − baseline DOY by skill rank |

The left card connects to the right card. The hypothesis within the panel is
“Hypothesis: stronger environmental transfer → greater projection credibility”.

## Rendering and verification

The figure uses selectable text, vector shapes, pale coloured panels, white
cards and short arrows. External headings are 9.5 pt; body text is approximately
10–11 pt. Rotated labels remain within page margins and do not overlap adjacent
labels; up to 6 pt of extension into the 16-pt panel gaps is permitted.

The exported PDF is a single 595.28 × 728 pt page, with approximately 12 pt
of blank margin above and below the panels. The complete model catalogue,
parenthesized panel letters, temperature equation, 80/20 split, future pathways
and skill-ranked impact comparison remain legible at the intended print scale.
References and abbreviation definitions are outside the figure; no overall
title, subtitle or explanatory footer is present.

Reproduction command from the repository root:

```sh
swift -module-cache-path /tmp/grape-workflow-swift-cache fig/workflow/draw_workflow.swift
```

The drawing source checks page size and required PDF text, then exports the PNG
preview for visual inspection. The scientific workflow and panel content are
the current specification; historical prompt wording is superseded.

## Caption

Workflow for comparing grapevine phenology models in France and Germany.
(a) BBCH observations, daily weather and terrain data are harmonized and matched.
(b) Raw and elevation-corrected ERA5-Land temperatures define paired input
variants. (c) Forcing function, chilling response and residual learning define
twelve model combinations, evaluated under both inputs. Beta chilling follows
Fila et al. (2014); the piecewise-linear chilling comparator uses the triangular
response in de Wergifosse et al. (2020), Eq. (1), as a candidate adaptation for
grapevine. (d) Random allocation within temperature zones derived by clustering
site temperature profiles reserves approximately 20% of sites for testing,
retaining repeated site records and
shared weather-grid groups within partitions. All adjustable process and ML
parameters are calibrated within the remaining data. Separate spatial and
warm-year holdouts assess transfer. (e) Held-out baseline MAE ranks model skill,
with warm-climate tests assessing environmental transfer. Fixed calibrated
configurations receive matched baseline and future climate-scenario inputs under
SSP2-4.5 and SSP5-8.5; future-minus-baseline phenological shifts are compared
across the ranked models. Controlled warming perturbations provide a separate
sensitivity analysis.
Greater projection credibility for models with stronger environmental transfer
is a hypothesis, not a consequence established by baseline MAE alone.
ML denotes additive residual machine learning. The diagram specifies the
experimental design, not completed modelling results.

## Files

- `workflow.pdf`: A4-width vector figure with cropped top and bottom margins.
- `workflow.png`: rendered preview.
- `draw_workflow.swift`: reproducible drawing source.
