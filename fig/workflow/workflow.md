# Grapevine phenology workflow

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
| a | Data | Blue |
| b | Temperature | Ochre |
| c | Models | Purple |
| d | Calibration and testing | Green |
| e | Climate-change impacts | Rose |

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
whole sites**, randomly allocated within **country × long-term mean annual
temperature strata**. Stratification balances the sampled climate range; it
does not establish extrapolation skill. The ratio and bin choices are study
design proposals, not requirements from the cited literature.

- Use a common climate-normal period for all sites, preferably 1991–2020 if
  complete daily weather is available. Do not calculate each site's climate
  mean over its unequal phenology-record period. Use raw ERA5-Land mean annual
  temperature as the common stratification variable for RAW and DEM branches.
- Start with temperature quintiles within each country. Merge adjacent bins
  when independent groups are too sparse to support both partitions and
  grouped inner folds. Check winter and spring temperatures, elevation,
  observation-period coverage, and BBCH-stage coverage for imbalance; avoid
  crossing many additional variables into sparse strata.
- Keep every year, stage, and duplicate/co-located site identity in the same
  partition. Also keep sites sharing an ERA5-Land cell together, preventing
  identical raw temperature series from crossing the split. Allocate these
  groups with approximate balance in site counts and climate strata; the
  achieved site proportion may differ slightly from 80/20.
- Fix and record the seed, climate-normal period, stratum boundaries and site
  mapping before inspecting phenology prediction errors. Use one master site
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
  Test observations are used only to calculate predictive errors.
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
  indicates better baseline predictive skill. Report country and temperature
  strata alongside the pooled metric so that dense or easy environments do not
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

## Main figure prompt

Create a concise scientific workflow at A4 width with cropped top and bottom
margins (approximately 12 pt), with selectable
text and vector shapes. Stack five full-width sections vertically, using
blue, ochre, purple, green and rose respectively. Use pale section backgrounds,
9.5-pt panel letters and headings outside the left panel edges, rotated 90°
counterclockwise and centred vertically. Use white cards and short arrows.
Remove internal heading rows, large letter badges and separate heading bands;
reduce each panel's height by 18 pt without shrinking its body text.
Keep body text around 10–11 pt. Maintain
white space, consistent alignment, restrained borders and clear reading order.

**a — Data.** Show three source cards: “Phenology”
(FR: TEMPO; DE: DWD; BBCH07/65/81/89), “Weather” (ERA5-Land daily; 0.1° grid)
and “Terrain” (Copernicus GLO-30 ~30 m; ERA5 grid geopotential).
Connect them to “BBCH harmonization → quality control → site–year matching”.

**b — Temperature.** Show two equal cards: “Raw temperature” and
“DEM-corrected temperature”. Below them, show
“T_adj = T_raw − 0.0065 × (z_site − z_grid)” with actual typographic subscripts,
followed by the compact unit label “T in °C; z in m”.
Apply both inputs to every candidate model. Site elevation is from GLO-30;
grid elevation is from official ERA5-Land geopotential.

**c — Models.** Display the six-row model catalogue above,
with Forcing in the first column. Group the first three rows under linear
forcing and the next three under beta forcing. Display all twelve model
names. Label the triangular chilling response “Piecewise linear”.
Shade the residual-ML column slightly more strongly in purple.
Below the matrix, write
“12 combinations × 2 inputs = 24 configurations per BBCH stage”.

**d — Calibration and testing.** Above two cards, show
“Random site split · stratified by country × mean annual temperature”.
Label the cards “Calibration set · 80%” and “Test set · 20%”, with a one-way
“Lock” arrow between them. The calibration card contains
“Calibrate all process parameters”, “Fit ML on out-of-fold residuals” and
“Tune within grouped inner folds”. The test card contains
“Apply locked process / hybrid models”, “MAE · RMSE · Bias (days)” and
“Identical held-out sites for all models”.
Below the cards, write
“Keep each site intact · Additional spatial and warm-year holdouts”.

**e — Climate-change impacts.** Above the cards, show
“Baseline climate → future climate scenarios (SSP2-4.5 / SSP5-8.5)”.
These are proposed scenario pathways, not existing ERA5-Land products.
Connect “Rank model adaptability”
(“Baseline test MAE → skill rank”; “Check warm-climate transfer”) to
“Project phenology shifts” (“Shared scenarios; fixed parameters”;
“Future − baseline DOY by skill rank”). Within this panel, add
“Hypothesis: stronger environmental transfer → greater projection credibility”.
This is the research hypothesis within an analysis panel, not an explanatory
footer or a claim that baseline accuracy validates future projections.

Do not add a figure title, subtitle, footnote markers, abbreviation legend,
references or explanatory text below the sections. Keep those details in this
file and the manuscript caption.

Keep detailed explanations, full references and parameter definitions in this
Markdown file and the manuscript caption. Omit sample counts, invented
performance values, decorative imagery, redundant prose and unsupported claims
that more complex models perform better. Never route test outcomes into fitting.

## Refinement prompt

Preserve the A4-width, vertically cropped portrait figure, five coloured sections
and forcing-first matrix. Do not restore the large top and bottom blank margins.
Keep all section letters in parentheses and headings outside the left edges,
reading vertically bottom-to-top. Check that rotated labels remain inside the
page margins and do not overlap adjacent labels; a label may extend up to 6 pt
into the 16-pt inter-panel gap at either end.
Check all twelve model names against the catalogue. Make the calibration/test
separation explicit. Keep piecewise-linear chilling distinct from Fila's beta
chilling and retain its reference in this file. Simplify labels and decorative elements
before reducing font size. Remove overlapping arrows or text and keep every
label inside its intended card.

## Caption

Workflow for comparing grapevine phenology models in France and Germany.
(a) BBCH observations, daily weather and terrain data are harmonized and matched.
(b) Raw and elevation-corrected ERA5-Land temperatures define paired input
variants. (c) Forcing function, chilling response and residual learning define
twelve model combinations, evaluated under both inputs. Beta chilling follows
Fila et al. (2014); the piecewise-linear chilling comparator uses the triangular
response in de Wergifosse et al. (2020), Eq. (1), as a candidate adaptation for
grapevine. (d) A country- and temperature-stratified random allocation reserves
approximately 20% of sites for testing, retaining repeated site records and
shared weather-grid groups within partitions. All adjustable process and ML
parameters are calibrated within the remaining data. Separate spatial and
warm-year holdouts assess transfer. (e) Held-out baseline MAE ranks model skill,
with warm-climate tests assessing environmental transfer. Fixed calibrated
configurations receive matched baseline, perturbed and scenario climate inputs;
future-minus-baseline phenological shifts are compared across the ranked models.
Greater projection credibility for models with stronger environmental transfer
is a hypothesis, not a consequence established by baseline MAE alone.
ML denotes additive residual machine learning. The diagram specifies the
experimental design, not completed modelling results.

## Files

- `workflow.pdf`: A4-width vector figure with cropped top and bottom margins.
- `workflow.png`: rendered preview.
- `draw_workflow.swift`: reproducible drawing source.
