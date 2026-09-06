# Repository Purpose

This is an academic paper repository for grapevine phenology modelling. The
study evaluates the predictive accuracy of classical process-based phenology
models and quantifies the contributions of DEM-based temperature correction
and machine-learning residual correction. It also compares how these model
choices affect projected phenological responses to climate change.

Prioritize scientifically defensible analyses, reproducibility, and
publication-ready text, figures, and tables. Keep manuscript claims consistent
with the data, implemented methods, and verified results.

## Study Context and Data

- Geographic scope: Germany (DE) and France (FR), within Europe. Findings from
  these countries do not automatically establish performance across Europe.
- Observations: grapevine phenological events recorded or harmonized using the
  BBCH scale. The approximately 4,000-site collection covers six countries;
  it is not the France–Germany modelling sample size.
- Main observation sources: German DWD and French TEMPO records.
- Current target stages: BBCH07 (budburst), BBCH65 (flowering), BBCH81 (veraison),
  and BBCH89 (maturity/harvest). Preserve source-specific stage definitions and
  document BBCH mappings. Treat maturity/harvest as an operational endpoint
  where appropriate; harvest timing is not necessarily physiological maturity.
- Meteorological forcing: ERA5-Land daily weather data.
- Terrain information: Copernicus DEM GLO-30 and corresponding weather-grid
  elevation information.
- Retain observation provenance, site identifiers, coordinates, observation
  year, stage codes, and quality flags throughout processing.

### Phenology Sources, Cohorts, and Harmonization

Use `data/README.md` as the data index, `data/phenology/README.md` for source
organization, and `data/phenology/metadata/standardization/README_columns.md`
with `grape_phenology_column_dictionary.csv` in the same directory for column
definitions and provenance.

- Complete source tables are in `data/phenology/processed/`:
  `france_grape_phenology_complete.csv` (TEMPO),
  `germany_grape_phenology_complete.csv` (DWD annual and immediate reporters),
  and `pep725_selected_countries_grape_phenology_complete.csv` (Austria,
  Switzerland, Slovakia, and Spain). Additional countries support the broader
  collection; they are outside the current paper's modelling scope.
- The current source-level country summary records 3,954 sites across six
  countries, including 2,297 in France and 732 in Germany (3,029 combined).
  Source: `data/phenology/derived/phenology_distribution/phenology_sites_by_source_with_pep725_country_summary.csv`.
- The 1951+ six-country base-table summary records 3,492 sites, including
  1,994 in France and 732 in Germany (2,726 combined). Its France records span
  1951–2022 and Germany records span 1951–2026; coverage is not complete for
  every site, stage, or year. Source:
  `data/phenology/derived/base_table/six_country_base_table_1951_country_summary.csv`.
- The current France–Germany four-stage validation inventory records 2,324
  sites, 17,172 site-years, and 31,439 events. These counts include sensitivity
  records and are not the final primary-analysis sample sizes. Source:
  `data/phenology/derived/modeling/france_germany_four_stage/validation/validation_design_summary.json`.
- Treat these counts as recorded snapshots. Recompute counts for the actual
  analysis filters, and never add stage-specific site counts to obtain a
  unique-site total. Source-level rows may include duplicates and multiple
  observations contributing to a single modelled event.
- The harmonized layer is
  `data/phenology/derived/standardized_bbch/six_country_phenology_bbch_standardized.csv`.
  Use `bbch_standard`, `bbch_mapping_confidence`, and `bbch_mapping_note`, with
  `bbch_stage_mapping_audit.csv` in the same directory. Source `stage_id`
  values are not globally equivalent; some DWD phases lack original BBCH codes
  and require documented mappings.
- `data/phenology/derived/base_table/six_country_base_table_1951.csv` retains
  records from 1951 onward with site ID, date, DOY, coordinates, and standard
  BBCH present, and DOY within 1–366. This is a phenology-only base table.
- `data/phenology/processed/phenology_observations_1951.csv` is observation-level;
  `phenology_site_year_stage_1951.csv` in the same directory aggregates to
  site × year × standard BBCH. Start-like stages (00–19, 50–61, and 81) use
  minimum DOY; stages 62–99 except 81 use median DOY. Retain `n_obs`,
  `doy_min`, `doy_median`, `doy_max`, and `doy_range` for aggregation diagnostics.
- The paper cohort is in
  `data/phenology/derived/modeling/france_germany_four_stage/`:
  `phenology_events_long.csv`, `phenology_site_year_wide.csv`,
  `site_inventory.csv`, `stage_country_summary.csv`, and
  `chronology_anomalies.csv`. It requires a unique ERA5-Land point sample for
  each retained site-year and already carries terrain and weather-QC fields.
- Preserve `site_uid` (country/source/site identity), `weather_id` (site-year
  identity), and `era5_grid_id` when joining tables. Bare source site IDs are
  not sufficient cross-source keys.

### ERA5-Land Weather

- The documented extraction uses Google Earth Engine collection
  `ECMWF/ERA5_LAND/DAILY_AGGR`, point sampling with `ee.Reducer.first()`, and
  `SAMPLE_SCALE = 11132` m. The grid crosswalk uses the official regular 0.1°
  ERA5-Land grid. Do not describe these data as station measurements or DEM-scale
  weather observations.
- `data/gee/weather_download_index_1951.csv` defines site-year extraction
  windows; `weather_download_index_1951_gee_20parts.csv` adds 20 export partitions.
  The default window is September 1 of the preceding year through December 31
  of the observation year. Use each record's actual start/end fields.
- `data/gee/gee_era5_download_script.md` contains the extraction script.
  `france_germany_prior_august_site_years_gee_20parts.csv` in the same directory
  provides a separate preceding-August index. An index or export script does
  not establish that its daily values have been downloaded or merged.
- The nine documented variables are mean/minimum/maximum 2-m temperature,
  2-m dewpoint temperature, total precipitation, surface pressure, downward
  solar radiation, and the 10-m wind u/v components.
- Documented source-unit storage is
  `data/weather/processed/era5_land_daily_complete/`, with 20 CSV parts named
  `era5_land_daily_grape_1951_part_00_of_20.csv` through
  `era5_land_daily_grape_1951_part_19_of_20.csv`. The data index describes restored
  station coordinates and filled French coastal/island site-years.
- Documented model-ready storage is
  `data/weather/processed/era5_land_daily_model_ready/`, with corresponding
  parts in °C, mm precipitation, kPa pressure, MJ m-2 day-1 radiation, and
  m s-1 wind. Preserve source-unit files and verify the unit dictionary before
  conversion. Tiny negative precipitation from round-off is clamped to zero
  and counted in QC.
- Documented QC files are in `data/weather/processed/qc/`:
  `weather_site_year_qc.csv`, `weather_model_ready_summary.json`, and
  `weather_model_ready_units.csv`. They describe date coverage, duplicates,
  missing values, physical checks, event coverage, and buffer-fill flags.
  Preserve `weather_fill_method` and `weather_fill_buffer_m`.
- The `data/weather/` directory was absent when these instructions were updated.
  Check local availability before modelling; documentation of prepared products
  is not evidence that the files are present or that a new run passed QC.

### DEM and ERA5-Land Model Orography

- Copernicus GLO-30 is documented as approximately 30-m GeoTIFF terrain data in
  `data/topography/metadata/copernicus_dem_glo30.md`. Country tiles are organized
  under `data/topography/raw/copernicus_dem_glo30/country_tiles/`; the manifest is
  `data/topography/metadata/copernicus_dem_glo30_country_tiles.csv`. Large raw
  tiles are excluded from normal Git tracking; verify local availability.
- Site terrain is in
  `data/phenology/derived/descriptive_phenology/site_topography.csv`, including
  `dem_elevation_m`, local elevation variability, slope, aspect, northness,
  eastness, coordinate stability, and terrain class. Use uniform DEM elevation
  for cross-country modelling; retain source elevation for QA. French source
  elevation prefers reported TEMPO altitude and otherwise uses `altitudeIgn`.
- Official ERA5-Land invariant geopotential and land-sea mask provenance,
  filenames, and checksums are recorded in
  `data/topography/metadata/era5_land_invariant.md` (download dated 2026-08-03).
  Model-grid elevation is geopotential divided by `9.80665 m s-2`.
- `data/topography/processed/site_era5_land_grid_crosswalk.csv` links sites to
  grid cells, official grid elevation, land fraction, terrain variability,
  spatial blocks, elevation differences, and weather-QC flags.
  `era5_land_grid_dem_summary.csv` in the same directory separates official
  `era5_grid_elevation_m` from Copernicus `glo30_grid_*` terrain statistics.
- Use `site_minus_grid_elevation_m = dem_elevation_m - era5_grid_elevation_m`
  for lapse-rate correction. GLO-30 cell means and 0.1° plotting backgrounds
  are not ERA5-Land model orography. Source-versus-DEM elevation discrepancies
  are also distinct from the site-minus-model-grid difference.

## Research Questions

1. How accurately do existing process-based models predict grapevine
   phenological dates across the observed sites and target BBCH stages?
2. Does DEM-based elevation correction of temperature forcing improve model
   accuracy, and how does its effect vary across stages, countries, elevations,
   and site-to-grid elevation differences?
3. Does machine learning applied to process-model residuals improve prediction
   accuracy, and do any gains generalize to held-out sites and regions?
4. Are DEM-based temperature correction and residual learning complementary,
   or does their combined benefit depend on the stage and environmental setting?
5. How do forcing functions, chilling formulations, residual learning and
   temperature correction alter projected phenological shifts under matched
   climate-change inputs?

Improvements are hypotheses to test. Report negligible changes, performance
degradation, and heterogeneous effects as well as improvements.

## Literature and Process-Based Models

- Use `reference/Fila et al.pdf` as a starting reference for reviewing existing
  grapevine phenology models. Consult other relevant primary literature to
  substantiate model formulations and implementation choices.
- Read the source before attributing models, equations, parameter values, or
  conclusions to it. Verify its bibliographic metadata before citing it.
- Document each candidate model's target stage, biological assumptions,
  temperature response, accumulation start or preceding-stage dependency,
  parameter definitions, calibration bounds, and required inputs.
- Distinguish published formulations from adaptations made in this repository.
  Record and justify material deviations from the source equations.
- Calibrate and compare models by stage using a consistent validation design.
  Select models and tune parameters without access to held-out test outcomes.

### Fila et al. (2014), Table 1: Model Summary

Source: Fila, G., Gardiman, M., Belvini, P., Meggio, F., and Pitacco, A. (2014).
*A comparison of different modelling solutions for studying grapevine phenology
under present and future climate scenarios*. Agricultural and Forest Meteorology,
195–196, 192–205. DOI: `10.1016/j.agrformet.2014.05.011`.
Table 1 is on printed page 195 (PDF page 4) of `reference/Fila et al.pdf`;
Section 2.1 explains the accumulation rules and temperature responses.

The nine formulations combine three model families with three levels of
phenophase-specific temperature response. Each predicts budburst, flowering,
and veraison with separate forcing requirements. The number in each model
name denotes its parameter count, not a BBCH stage.

| Model | Chilling response | Forcing response | Forcing-temperature parameters across stages | Parameters |
| --- | --- | --- | --- | --- |
| CF8 | Beta | Beta | One optimum shared by all three stages | 8 |
| CF9 | Beta | Beta | Budburst optimum; shared flowering–veraison optimum | 9 |
| CF10 | Beta | Beta | Separate optimum for each stage | 10 |
| Fbeta5 | No explicit chilling | Beta | One optimum shared by all three stages | 5 |
| Fbeta6 | No explicit chilling | Beta | Budburst optimum; shared flowering–veraison optimum | 6 |
| Fbeta7 | No explicit chilling | Beta | Separate optimum for each stage | 7 |
| FGDD5 | No explicit chilling | Linear GDD | One base temperature shared by all three stages | 5 |
| FGDD6 | No explicit chilling | Linear GDD | Budburst base; shared flowering–veraison base | 6 |
| FGDD7 | No explicit chilling | Linear GDD | Separate base temperature for each stage | 7 |

- **CF family:** sequential chilling–forcing models. Chilling accumulates from
  September 1 of the preceding year until `Ccrit` is reached; forcing starts
  after this estimated end of endodormancy. All CF variants have three chilling
  cardinal temperatures (`Tmin`, `Topt`, `Tmax`), `Ccrit`, three forcing sums
  (`Sbb`, `Sfl`, `Sve`), and one to three forcing-temperature optima. The forcing
  start is determined by chilling completion rather than a fitted calendar `t0`.
- **Fbeta family:** forcing-only models with a fitted calendar start `t0`,
  three forcing sums, and one to three temperature optima. The beta response
  reaches a maximum at its optimum and declines toward zero at the upper
  temperature boundary, representing inhibition at high temperatures.
- **FGDD family:** forcing-only models with a fitted `t0`, three thermal-time
  sums, and one to three base temperatures. GDD increases linearly above the
  relevant base temperature, without the beta response's high-temperature decline.
- `Sbb`, `Sfl`, and `Sve` denote requirements for successive phenophases;
  accumulation restarts after each preceding stage. They should not silently be
  interpreted as three cumulative thresholds from a common calendar origin.
  Beta-based sums accumulate normalized daily response units; GDD sums are in
  °C·day. Temperature parameters are in °C and `t0` is a day-of-year coordinate.
- The chilling cardinal temperatures in Table 1 are distinct from the forcing
  curve boundaries. Section 2.1 fixes the beta forcing minimum at 0 °C and
  compares upper boundaries of 30, 35, 40, and 45 °C. These boundary choices
  are not additional fitted parameters in the model-name counts; any selection
  among them in this repository belongs within training-data model selection.

The original observations concern Chardonnay at two sites in northeastern
Italy and use BBCH09, BBCH65, and BBCH81. The repository's BBCH07 budburst target
requires an explicit stage adaptation and calibration; BBCH07 and BBCH09 are
not interchangeable. Table 1 contains no maturity/harvest model or BBCH89
threshold. These formulations define literature comparisons, not evidence that
all nine are implemented here. Check
`data/phenology/derived/modeling/france_germany_four_stage/model_setup/mechanistic_model_registry.csv`
and the implementation before describing an executed model; existing GDD,
GFV, and BRIN entries are not automatically equivalent to the Table 1 variants.

## Experimental Comparisons

Separate the effects of temperature correction and residual learning using
the following comparisons wherever supported by the data:

| Temperature forcing | Process model | Process model with residual ML |
| --- | --- | --- |
| Original temperature | Baseline | Residual-learning contribution |
| DEM-corrected temperature | Temperature-correction contribution | Combined contribution |

Use matched observations, folds, and evaluation metrics across comparisons.
Document whether process-model parameters are recalibrated for each forcing
configuration; distinguish a recalibrated workflow comparison from changing
the temperature input while holding parameters fixed.

### DEM-Based Temperature Correction

- Define the correction using the difference between site elevation and the
  elevation represented by the meteorological forcing grid.
- The recorded main branch uses a fixed lapse rate of 6.5 °C/km:
  `T_adjusted = T_raw - 0.0065 * site_minus_grid_elevation_m`, with elevations
  in metres. Apply the same offset to daily mean, minimum, and maximum
  temperature. The raw and `adjusted_6p5` column mappings are recorded in
  `data/phenology/derived/modeling/france_germany_four_stage/model_setup/modeling_contract.json`.
- Document the equation, elevation units and reference, lapse-rate convention,
  lapse-rate source or estimation method, and temporal resolution.
- Keep correction parameters estimated from data within the training folds.
- Examine performance against elevation mismatch and terrain strata, with
  sample counts and uncertainty for each group.
- Improved phenology prediction alone does not establish that corrected
  temperatures are more accurate. Claims about temperature accuracy require
  independent temperature observations or other direct validation.

### Residual Machine Learning

- Define the residual consistently as observed day of year minus process-model
  predicted day of year. The hybrid prediction is the process prediction plus
  the predicted residual.
- Train residual models on process-model predictions generated out of fold
  within the training data. Keep the outer test observations independent of
  process-model calibration, residual training, and model selection.
- Use predictors available at the stated prediction time. Document whether
  each experiment represents retrospective estimation or operational forecasting.
- Fit preprocessing, imputation, feature selection, and hyperparameter tuning
  within the training folds.
- Interpret feature importance and SHAP results as predictive associations;
  they do not establish causal mechanisms.

## Validation and Reporting

- Prioritize spatially held-out evaluation for claims about transfer to unseen
  sites or regions. Prevent records from the same site crossing training and
  test partitions in site-transfer experiments.
- The proposed primary design in `fig/workflow/workflow.md` uses an approximately
  80/20 random site split stratified by country and common-period mean annual
  temperature, with four grouped inner calibration folds. Keep all records of
  each site and sites sharing an ERA5-Land cell in one partition. Use identical
  site assignments across model and temperature-input comparisons. This is a
  design specification; new split mappings have not been generated.
- The previously recorded validation design uses five outer and four inner
  folds grouped by 1° spatial blocks, with seed `20260804`. Preserve the mappings under
  `data/phenology/derived/modeling/france_germany_four_stage/validation/` for
  a separate spatial-transfer benchmark, keeping sites, ERA5 cells, and spatial
  blocks together. Do not label these existing mappings as the proposed random
  stratified split or overwrite them silently.
- Use separate temporal or country-transfer evaluations when making claims
  about future years or transfer between countries.
- Report stage-specific MAE, RMSE, and mean signed error in days, with the error
  sign convention stated. Include sample sizes and uncertainty in model
  comparisons; account for repeated observations and spatial grouping.
- Summarize performance by country and relevant terrain groups when sample
  sizes support the comparison. Distinguish pooled performance from subgroup
  performance and flag sparse groups.
- Document missing data, duplicate handling, BBCH harmonization, chronology
  checks, exclusions, and the treatment of leap years and day-of-year values.
- The recorded modelling contract pools core and extended events with equal
  status and weight, excludes sensitivity events from the primary analysis,
  and does not use tier as a predictor or stratification variable. Preserve
  these distinctions when reporting counts and selecting analysis records.
- Do not fabricate results, references, dataset counts, or statistical support.
  Clearly distinguish established findings from proposed analyses.

## Climate-Change Experiments

- Compare paired future-minus-baseline DOY shifts under identical climate
  inputs across phenology configurations, in addition to historical accuracy.
- Compare these shifts across stage-specific model rankings based on held-out,
  site-balanced baseline MAE, with separate warm-climate transfer rankings and
  rank uncertainty. Stronger adaptability implying greater climate-projection
  credibility is a hypothesis; baseline accuracy or ensemble agreement alone
  does not establish future accuracy. If held-out ranks select or weight models,
  use additional untouched data to evaluate the resulting ensemble.
- Distinguish idealised temperature perturbations from dated climate-scenario
  projections. ERA5-Land provides historical forcing, not future scenarios;
  scenario datasets and their processing require separate provenance.
- Freeze historically calibrated process parameters, residual learners and
  preprocessing during baseline/future comparisons. Separate model-structure
  variation from calibration-parameter and climate-ensemble variation.
- Retain spatial and warm-year/environmental holdouts as transfer tests. Flag
  future predictors outside the calibration domain, especially for residual ML;
  present-climate accuracy alone does not establish future projection skill.
- Report unmet chilling/forcing requirements separately from finite date shifts.
  Preserve phase order, prior-season spin-up, and fixed cultivar/management
  assumptions. BBCH89 projections remain conditional on the harvest endpoint.

## Repository Organization and Reproducibility

- `paper/`: manuscript source, bibliography, and compiled manuscript.
- `reference/`: supporting literature, including `Fila et al.pdf`.
- `data/`: observations, weather and terrain metadata, and derived tables.
- `src/`: data preparation, model implementation, evaluation, and plotting.
- `results/`: predictions, fitted-model summaries, and evaluation tables.
- `fig/`: manuscript figures and supporting visualizations.
- `tests/`: checks for data processing and modelling components.

Follow existing directory conventions and analysis workflows. Preserve raw
data and unrelated user changes. Record data versions, configurations, random
seeds, validation splits, and parameter settings needed to reproduce results.
Generate manuscript numbers, tables, and figures from traceable analysis
outputs. Verify methods and results against the relevant code and outputs
before revising scientific claims.

## Academic Writing Rules

- Use precise, formal academic language and consistent phenological and
  modelling terminology.
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
