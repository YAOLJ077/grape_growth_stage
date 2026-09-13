# Final-study repository instructions

## Scope and scientific authority

This repository supports the completed European grapevine phenology study in
`paper/manuscript.tex` and `paper/supplementary.tex`. Preserve the title:
“Beyond thermal accumulation: improving cross-regional grapevine phenology
prediction with terrain-aware forcing and residual learning”. Climate-change
projections, GCM downscaling, spatial-transfer experiments and warm-climate
holdout results are outside the final primary study.

Use the completed runs, locked predictions, source hashes and independently
verified results as evidence. A workflow picture, saved status alone or a
previous plan does not establish completion. Main results use MAE and signed
bias; supplementary RMSE diagnostics remain explicitly supplementary. Terrain
and environmental-zone differences are predictive associations, not causal
effects. Report degradation and heterogeneous benefits as well as gains.

## Active organization

- `src/data_preparation/`: final observation/partition reconstruction entrypoint.
- `src/calibration/`: fresh pooled, process and TabM training entrypoint.
- `src/validation/`: portable validation of locked sources, artifacts and metrics.
- `src/visualization/`: all active main/supplementary figure renderers and numerical replay.
- `src/documents/`: manuscript PDF/Word, front matter, graphical abstract and citation tools.
- `src/phenology/`, `src/weather_processing/`, `src/base_table/`,
  `src/descriptive_phenology/`: minimal upstream preparation implementations
  retained at their original paths for provenance and imports.
- `model/`, `model_run/factorial/`, `model_run/src/`: original numerical engines.
- `data/`: canonical source representations, prepared weather/terrain/climate,
  provenance, exclusions and the compact `paper_figures` input bundle.
- `model_run/results/`: only frozen final runs and required upstream inputs.
- `fig/paper_figures/`: numbered final figures; `fig/graphical_abstract/`: final graphical abstract.
- `paper/`: final sources/deliverables, references, tables, submission front matter
  and compact scientific evidence.
- `tests/`: relevant implementation checks. Reproduction caches belong in ignored `build/`.

The user authorized removing material unrelated to final-result reproduction.
Do not restore obsolete pilots, partial snapshots, historical ML assemblies,
figure duplicates or writing archives. Dated retained inputs are dependencies,
not cleanup targets merely because their names are old. Do not move or change
byte-fingerprinted numerical engines as an incidental formatting change.
Preserve original source manifests; new portable validation maps their original
repository suffixes without changing expected hashes. Recalibration writes a
new output directory. Never resume pooled calibration in a frozen output: it
can rewrite compressed observation headers and invalidate downstream hashes.

## Data and final populations

The four equal targets are BBCH07, 65, 81 and 89, ordered 07→65→81→89.
BBCH09 remains distinct. Maturity/harvest is an operational endpoint; harvest
is not necessarily physiological maturity. Sites can qualify with any target
stage; no complete sequence or minimum-duration criterion is introduced.
Preserve repeated observations, missing varieties, source provenance, leading
zeros in identifiers, coordinates and exact dates. Reported site IDs do not
prove independent physical vineyards.

The canonical source representations are the France/Germany complete tables,
auxiliary TEMPO country table and full PEP725 extract. Require direct source
BBCH codes, valid dates from 1951 onward and exact seven-field deduplication.
Never infer missing BBCH codes, repair dates, impute observations or choose QC
thresholds from model residuals. Preserve provider licences and source notices.

Final QC-v3 retains 75,738 observations and quarantines 1,575 of 77,313 target
records. `src/phenology/target_qc_v3.py` specifies the target-specific policy:

| BBCH | Inclusive calendar window |
| --- | --- |
| 07 | February 1–June 15 |
| 65 | April 1–July 31 |
| 81 | June 1–October 15 |
| 89 | July 15–November 15 |

Adjacent inclusive intervals are 20–120 days (07→65), 30–120 (65→81) and
10–90 (81→89); other target-pair limits are sums of intervening intervals.
Compare within exact site × reported variety × year. Every retained record
needs a supporting counterpart for each observed pair. Remove unsupported
records simultaneously per iteration until stable. Missing endpoints impose
no constraint. Provider quality and documented DWD annual/immediate precedence
are applied before chronology. These are project screening rules, not universal
physiological bounds; they never clip process predictions.

Final weather/site-year eligibility retains 74,618 observations at 3,169 sites,
26,443 site-years and 1,791 original independence groups across 11 countries,
1951–2025. Calibration: 59,472 observations, 2,534 sites and 1,434 groups.
Test: 15,146 observations, 635 sites and 357 groups. Exact matching to the
original eligible site/country/coordinates/site-year removes 1,120 revised-QC
rows. All surviving sites retain original partitions, folds and zones.

The Fig. 2 historical phenology-only snapshot has 74,341 observations at 3,171
sites. It is distinct from the final modelling population and follows the
recorded 27-site/892-observation weather exclusion. Original zone centroids use
1,792 grids; the final cohort has 1,791 surviving groups. Do not recluster on
final test outcomes. Historical supplementary screening counts remain labelled
as historical sensitivity evidence, not final sample sizes.

## Weather, terrain and modelling

ERA5-Land daily mean 2-m temperature is in Celsius. Point extraction uses the
native regular 0.1° grid; it is not station weather or 30-m weather. Preserve
original identities, dates, finite coverage and source units. Official grid
elevation is invariant geopotential divided by 9.80665 m s−2. Use Copernicus
GLO-30 site elevation minus official grid elevation for correction:
T_DEM = T_RAW − 0.0065 × (z_site − z_grid), with elevations in metres.
GLO-30 cell means and plotting backgrounds are not model orography.

Ten structures are FL, FB, CL-FL-S, CL-FL-P, CB-FL-S, CB-FL-P, CL-FB-S,
CL-FB-P, CB-FB-S and CB-FB-P. Preserve explicit -S/-P suffixes; residual variants
append -ML. Cross RAW/DEM forcing with process/hybrid prediction for 40
configurations per stage. The active fixed-response profile is defined in
`model/structure_comparison.py`; distinguish it from the general unrestricted
API. Accumulation uses predicted preceding stages, restarts the next day and
discards overshoot. No observed preceding date initializes a prediction.

Final early-stage fitting imposes calibration bias and raw-attainment bounds
and minimizes equal-site/equal-stage MAE. Maturity requirement is an equal-site
weighted median from calibration observations after raw predicted veraison.
All response functions, starts, bounds, optimizers and seeds remain as recorded.
The 4 November BBCH81/89 scoring convention is administrative: preserve raw
attainment, raw dates and assignment flags separately. It does not establish
developmental completion and does not modify process accumulation.

TabM uses four ordinary out-of-fold and six pair-excluded process refits per
model/input, three seeds and fold-local preprocessing. Test labels never tune
parameters, features or epochs. Process dates without attainment have no
residual target. Weather windows end at raw predicted dates, so the evaluation
is retrospective. Corrected finite dates do not establish thermal attainment.

Paired comparisons use matched finite errors, equal site/stage weights and
original-group bootstrap resampling (2,000 draws, seed 20260913). Preserve
sparse-support rules and missing intervals. The shared held-out correction
cohort contains 15,105 observations, 633 sites and 355 groups. Environmental-zone
findings belong in the written abstract, discussion and graphical abstract.

## Publication and verification

All 15 publication figures are numbered Fig_01–Fig_10 and Fig_S01–Fig_S05.
Use 7.8-inch vector PDFs and 2,340-pixel PNGs at 300 dpi, preserving the native
180-mm design proportions. Main text is Helvetica 8 pt, panel letters bold 9 pt
and subscripts 6 pt before proportional scaling. Keep original source licences,
plotted values, uncertainty and panel arrangements. Figures are redrawn from
numerical/geographic inputs, not copied from prior PDFs.

Use source-backed scientific prose. Cite all references, figures, tables and
retained supplementary sections in the manuscript. Every cited reference must
exist in its bibliography. Main Word documents include cover letter, highlights
and graphical abstract before the title. Combined Word appends the supplement.
Keep editable tables/equations and embedded Zotero fields. Body paragraphs use
double spacing, continuous manuscript line numbers, bordered tables and centred
equations. Self-contained Zotero fields are not personal-library links; live
Zotero refresh requires the application and has not been verified here.

Run `python -m pytest`, the classified population and artifact validators, and
relevant numerical/figure/document checks before claiming success. Full model
retraining is a separate expensive operation; do not imply it ran when only
locked predictions or hashes were checked. Requirements and reproduction scope
are documented in the root and component READMEs.

## Academic Writing Rules

- The manuscript is in English. Use flush-left paragraph starts without
  first-line indentation; separate paragraphs with modest vertical spacing.
- Use precise, formal academic language and consistent phenological and
  modelling terminology.
- Use conventional scientific prose rather than database or repository jargon
  in the manuscript. Prefer observations, monitoring sites, data preparation and
  excluded records to source occurrences, source-qualified site identifiers,
  paper-target exports and quarantine. Keep hashes, schemas, file paths and
  internal policy names in processing documentation unless scientifically needed.
  Explain once in the data methods that sites reported by different networks
  can share a physical location; do not equate reported site counts with
  independent vineyards or repeatedly present coordinate-pair bookkeeping.
- When producing reports, proposals, or academic text, output only the formal
  deliverable text. Exclude prompts, reasoning, writing plans, revision notes,
  and self-evaluation from the deliverable.
- Avoid metadiscourse about the writing process, including phrases such as
  “this report will,” “according to the user's requirements,” “to avoid
  misunderstanding,” and “the following introduces.”
- State methodological choices and limitations as objective facts. For
  example: “The model supports association analysis and does not identify
  causal effects.”
- Support scientific claims with verified references or reproducible results.
  Distinguish hypotheses, methods, results, and interpretation.
- Before delivering a draft, silently remove writing-process metadiscourse;
  do not include a description of this check.
- Indent the first line of each Chinese prose paragraph by two full-width
  Chinese spaces (`　　`).
