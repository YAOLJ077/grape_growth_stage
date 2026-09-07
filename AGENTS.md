# Repository Purpose

This is an academic paper repository for grapevine phenology modelling. The
study evaluates the predictive accuracy of classical process-based phenology
models and quantifies the contributions of DEM-based temperature correction
and machine-learning residual correction, including variation in correction
benefits across terrain conditions. Climate-change projections and GCM
downscaling are outside the current study scope.

Prioritize scientifically defensible analyses, reproducibility, and
publication-ready text, figures, and tables. Keep manuscript claims consistent
with the data, implemented methods, and verified results.

## Current Workflow

Use `fig/workflow/workflow.md` as the detailed specification of the current
study design, with `fig/workflow/workflow.pdf` and `workflow.png` as its figure
and preview. Keep these documents, the drawing source and manuscript methods
consistent. The workflow is a design, not evidence of completed analyses.

1. **(a) Data:** harmonize and quality-control all-country European observations
   of the four target stages BBCH07, 65, 81 and 89;
   match daily ERA5-Land weather and terrain to site–year records.
2. **(b) Temperature:** compare raw forcing with DEM-based elevation correction,
   using official ERA5-Land grid elevation and elevations in metres.
3. **(c) Models:** cross forcing function, chilling function, sequential/parallel
   interaction where chilling is present, and residual learning using the model
   catalogue below; run both temperature-input variants (40 configurations per stage).
4. **(d) Calibration and testing:** calibrate all adjustable process parameters
   and residual ML within the calibration set; evaluate locked models on the
   matched held-out sites. Randomly split whole sites within temperature zones
   derived by clustering site temperature profiles, not by country. Include
   separate spatial and warm-year holdouts.
5. **(e) Terrain effects:** compare paired original/DEM-corrected test errors
   across elevation mismatch, elevation, slope, aspect and local elevation
   variability. Assess correction benefits without/with residual ML using matched
   observations and paired site-group uncertainty. These are predictive
   associations, not causal terrain effects.

## Study Context and Data

- Geographic scope: the eligible all-country European observation domain. The
  current phenology-only target export spans 11 countries; subsequent
  weather, terrain and independence requirements can reduce the modelling cohort.
- Observations: grapevine phenological events recorded or harmonized using the
  BBCH scale. Source-qualified identifiers are not automatically independent
  physical sites.
- Main observation sources include TEMPO, DWD and PEP725 records.
- The four equal target stages are BBCH07 (budburst), BBCH65 (flowering), BBCH81
  (veraison) and BBCH89 (maturity/harvest), ordered as 07→65→81→89. BBCH09
  remains distinct from BBCH07. Preserve source-specific stage
  definitions and document BBCH mappings. Treat maturity/harvest as an operational
  endpoint where appropriate; harvest timing is not necessarily physiological
  maturity.
- Meteorological forcing: ERA5-Land daily weather data.
- Terrain information: Copernicus DEM GLO-30 and corresponding weather-grid
  elevation information.
- Retain observation provenance, site identifiers, coordinates, observation
  year, stage codes, and quality flags throughout processing.

### Phenology Sources, Cohorts, and Harmonization

#### Chronology and interval QC: tightened policy v2

Apply these rules to the 1951-onward, direct-source-BBCH consolidated inventory
after exact seven-field deduplication. This is conservative screening for the
European collection, not proof that quarantined observations are erroneous.
Thresholds are project screening choices, not universal physiological limits
or limits estimated from model residuals. No dates or BBCH codes are repaired,
interpolated, swapped or inferred.

1. Apply inclusive calendar-date windows to each observation:

   | BBCH | Stage group | Eligible dates |
   | --- | --- | --- |
   | 01–09 | Bud development | February 1–June 15 |
   | 10–19 | Leaf development | March 1–July 31 |
   | 50–59 | Inflorescence development | April 1–July 15 |
   | 60–69 | Flowering | May 1–July 31 |
   | 70–79 | Fruit development | May 15–September 15 |
   | 80–85 | Veraison / early ripening | July 1–October 15 |
   | 86–89 | Late ripening / maturity | July 15–November 15 |

   BBCH00 and 90–99 have no blanket seasonal filter. Dormancy and late-season
   processes can cross calendar years. Stages outside the listed families are
   not automatically assigned a calendar window. Month-day comparisons
   preserve leap days without imposing a fixed 365-day calendar.
2. Group comparisons by exact source-qualified `site`, reported `variety`
   and calendar year. Do not pool sites, sources, years or cultivar labels.
   Empty variety labels form their own group; they are not matched to named
   cultivars. Such groups and DWD maturity classes can contain multiple plants
   or cultivars, so their conflicts indicate ambiguous evidence, not a proven
   error in an individual vine.
3. Apply chronology separately to these two ordered branches:
   `01,03,05,07,09,10,11,12,13,14,15,16,17,18,19` and
   `01,03,05,07,09,53,55,57,60,61,62,63,64,65,66,67,68,69,71,73,75,77,79,81,83,85,87,89`.
   Compare every observed pair within a branch; equal dates are allowed for
   ordinary stage pairs. Do not order leaf development against inflorescence,
   flowering or fruit development merely by numeric BBCH value. Codes 10 and
   87 retain their existing source coding as intermediate positions; they are
   not relabelled as other codes. BBCH00 and 90–99 are outside these chains.
4. Override the ordinary non-negative interval rule for these exact pairs:

   | Earlier BBCH | Later BBCH | Inclusive interval (days) |
   | --- | --- | --- |
   | 07 or 09 | 65 | 20–100 |
   | 65 | 81 | 30–120 |
   | 81 | 89 | 10–90 |

   BBCH07 and BBCH09 remain distinct. Other flowering percentages and ripening
   stages are not substituted for these endpoints. Missing endpoints do not
   trigger exclusion or imputation; their interval remains untested.
5. Apply seasonal exclusions first. For each remaining ordered stage pair,
   every individual record must have at least one counterpart date satisfying
   its interval. Quarantine unsupported records, not a plausible alternative
   date from the same stage. If no compatible date pair exists, quarantine both
   stage groups because the erroneous endpoint is unknown. Evaluate all pairs
   against the same snapshot within a pass and remove their union simultaneously.
   Recheck surviving pairs until stable; a completely removed stage becomes a
   missing endpoint and imposes no further constraint. Record the pass number
   and counterpart dates for each exclusion. This strengthens v1, which allowed
   one feasible date pair to conceal unsupported observations. Retain unrelated
   stages and do not replace repeated observations with a median or minimum.
6. Keep a single active seven-column `phenology_data.csv`. Preserve all QC
   exclusions in `phenology_data_quarantine.jsonl.gz`, including the original
   seven fields, event hash, rule IDs and pair/date evidence. Reconcile source
   provenance, counts and hashes with the final cleaned table. Rebuild from
   original inputs, never from an already cleaned CSV alone. Update the site
   map from the final table and independently verify the retained population.
7. Report exclusions by country, source, BBCH, year and rule. Do not use these
   historical screening bounds to clip model predictions.
   Evaluate sensitivity to screening before interpreting warm-climate transfer;
   atypical management, reporting intervals and genuine extremes can produce
   observations outside these bounds.

Stage definitions: [INRAE/IFV grapevine phenological scale](https://rdf.codex.cati.inrae.fr/ppd-res/grapevine),
which cites Lorenz et al. (1995) and the JKI BBCH monograph (2018). These
references support stage interpretation; the numeric screening thresholds
above are project-specific choices.

Evidence for the tightened interval choices includes a 163-cultivar study
reporting mean cultivar intervals of 40–104 days from flowering onset to veraison
onset and 20–73 days from veraison onset to harvest:
[Grzeskowiak et al. (2013)](https://pmc.ncbi.nlm.nih.gov/articles/PMC3825586/).
Flowering onset is not BBCH65, and cultivar means are not individual-event
bounds; these results motivate broad screening margins, not exact cutoffs.
The pre-QC inventory's earliest-date paired medians are 54 days (07→65),
71 days (65→81) and 33 days (81→89). These are descriptive diagnostics only;
thresholds must not be optimized to improve model performance.

The current all-country consolidated inventory is
`data/phenology/phenology_data.csv`, with columns
`site,variety,country,lat,lon,Date,BBCH`. It retains only valid direct source
BBCH codes and dates on or after 1951-01-01. Inferred mappings and earlier
observations are excluded before exact seven-field deduplication; chronology-v2
screening follows deduplication. The current
snapshot contains 259,998 observations and 4,244 source-qualified site IDs across
13 countries; these are not necessarily distinct physical sites. Processing and
provenance are documented by the processing procedure below. The active map
in `fig/study_area/` uses all four target stages, not the full inventory. Its
site-year colour statistic counts distinct years containing any target stage,
pooled across varieties; it does not require complete stage sequences. The
stage bar in `fig/phen_data/` likewise includes all four targets. Older
source and modelling snapshots below represent different filters, not the
current all-country inventory or active paper-target exports.
The 1951 cutoff is not evidence of complete weather coverage; check preceding-
season inputs separately for chilling models.

Use `data/README.md` as the data index, `data/phenology/README.md` for source
organization, and `data/phenology/metadata/standardization/README_columns.md`
with `grape_phenology_column_dictionary.csv` in the same directory for column
definitions and provenance.

- Complete source tables are in `data/phenology/processed/`:
  `france_grape_phenology_complete.csv` (TEMPO),
  `germany_grape_phenology_complete.csv` (DWD annual and immediate reporters),
  and `pep725_selected_countries_grape_phenology_complete.csv` (Austria,
  Switzerland, Slovakia, and Spain). Additional countries support the broader
  collection. Their historical selection does not define the current paper scope.
- The single active paper observation file is
  `data/phenology/derived/paper_targets/observations.csv`: 75,233 rows, 3,198
  source-qualified sites, 3,023 distinct coordinate pairs and 11 countries.
  It retains exactly the original seven columns and spans 1951-04-15 to
  2026-06-23. Stage counts are 25,303 (BBCH07), 26,657 (BBCH65), 18,734
  (BBCH81) and 4,539 (BBCH89). The full inventory `phenology_data.csv` remains
  unchanged; non-target observations are not destroyed.
- A site or year qualifies for the target file when any one of the four stages
  is present; a complete 07→65→81→89 sequence is not required. Missing varieties
  and repeated accepted observations remain unchanged. Non-target stages are
  not errors. `python3 src/phenology/select_modeling_targets.py` regenerates the
  combined CSV and writes `quality.json`, including overall and stage-specific
  counts. Do not recreate separate stage-group CSVs.
- This export establishes phenological eligibility only. Weather matching,
  cultivar or plant identity, and resolution of source-qualified identifiers
  into independent sites remain modelling tasks.
- The current source-level country summary records 3,954 sites across six
  countries, including 2,297 in France and 732 in Germany (3,029 combined).
  Source: `data/phenology/derived/phenology_distribution/phenology_sites_by_source_with_pep725_country_summary.csv`.
- The 1951+ six-country base-table summary records 3,492 sites, including
  1,994 in France and 732 in Germany (2,726 combined). Its France records span
  1951–2022 and Germany records span 1951–2026; coverage is not complete for
  every site, stage, or year. Source:
  `data/phenology/derived/base_table/six_country_base_table_1951_country_summary.csv`.
- The historical France–Germany four-stage validation inventory records 2,324
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
- A historical France–Germany modelling cohort is in
  `data/phenology/derived/modeling/france_germany_four_stage/`:
  `phenology_events_long.csv`, `phenology_site_year_wide.csv`,
  `site_inventory.csv`, `stage_country_summary.csv`, and
  `chronology_anomalies.csv`. It remains unchanged and does not define the active
  all-country paper scope. It requires a unique ERA5-Land point sample for
  each retained site-year and already carries terrain and weather-QC fields.
- Preserve `site_uid` (country/source/site identity), `weather_id` (site-year
  identity), and `era5_grid_id` when joining tables. Bare source site IDs are
  not sufficient cross-source keys.

### Canonical Phenology Processing Procedure

All active data-processing, verification and figure-generation scripts are in
`src/phenology/`. Data folders contain observations and audit metadata; figure
folders contain exported figures, supporting counts and figure specifications.
The procedures below are the canonical processing instructions, superseding
the archived standalone methods note and notebook.

1. **Verify inputs.** Use exactly four source representations: the canonical
   France and Germany complete tables, the auxiliary TEMPO country table and
   the full PEP725 extract. Resolve Git LFS pointers to size- and SHA-256-verified
   objects before parsing. Do not append the selected-country PEP725 table or
   older DWD releases again. Missing required inputs stop a complete rebuild.
2. **Select grapevine.** Retain source taxa matching `Vitis vinifera` across all
   countries. The current four tables contain 823,028 source occurrences;
   25,471 non-grape occurrences are excluded before BBCH filtering.
3. **Preserve identity.** Construct `COUNTRY:tempo:site_id`, `DE:dwd:site_id` or
   `COUNTRY:pep725:provider_id:s_id`. Preserve identifier strings and leading
   zeros. Derive country from provider metadata, not coordinates. Normalize
   whitespace and missing-value sentinels; preserve cultivar spellings and DWD
   maturity-class labels without inferring cultivar or individual-plant identity.
4. **Validate fields.** Normalize valid calendar dates to ISO `YYYY-MM-DD` and
   finite coordinates to decimal degrees within latitude/longitude bounds.
   Preserve coordinate precision, leap days and missing variety labels. Do not
   fabricate missing dates or locations. Invalid or missing values remain
   explicitly audited; no eligible invalid dates or coordinates occur in the
   current inventory.
5. **Require direct BBCH evidence.** TEMPO France uses populated `bbch_code`,
   auxiliary TEMPO uses `stage_code`, DWD requires a populated source `bbch_code`,
   and PEP725 uses directly coded integer `phase_id` values from 0 to 99.
   Normalize to two digits. Exclude inferred lookup conversions and unmapped
   phases before deduplication (79,864 and 13,690 source occurrences,
   respectively). A direct record is not displaced by an earlier inferred one.
   In particular, do not infer BBCH89/92/95 from PEP725 phases 100/201/205, or
   populate absent DWD BBCH codes from phase names. BBCH07 and BBCH09 are distinct.
6. **Apply the study period.** Retain dates on or after 1951-01-01, after BBCH
   confidence filtering. Audit the 17,494 pre-1951 source occurrences separately.
   The date cutoff does not establish weather availability or preceding-season
   coverage for chilling models.
7. **Deduplicate exact observations.** Use all seven normalized fields
   `site,variety,country,lat,lon,Date,BBCH`. Different dates or varieties within
   the same site–year–stage remain separate. No minimum-date, median-date or
   other event aggregation is applied. The 1951-onward pre-QC inventory contains
   271,032 unique records.
8. **Apply chronology-v2.** Use the seasonal windows, separate developmental
   branches, exact major-phase bounds and iterative per-record support rules
   above. Group by source-qualified site × reported variety × calendar year.
   Remove unsupported observations simultaneously within each pass; missing
   stages impose no constraint. Quarantine both endpoints if no compatible pair
   exists; preserve unrelated stages. No date or BBCH repair is allowed.
   The 11,034 unique quarantined records leave 259,998 rows at 4,244 identifiers.
9. **Preserve and reconcile evidence.** Sort the full inventory by country,
   site, date, BBCH, variety and coordinates. Keep one provenance entry for every
   source occurrence and original fields plus rule/date evidence for every
   quarantined record. An event ID is SHA-256 of its seven-string JSON array,
   encoded as UTF-8 with `ensure_ascii=False` and separators `(',', ':')`.
   Retained plus quarantined rows must reconstruct the pre-QC inventory exactly.
   Retain source licences and attribution; source-qualified IDs are not proven
   independent vineyards, and source licences are not replaced by a uniform one.
10. **Select paper targets into one file.** Export unchanged rows with BBCH07,
    65, 81 or 89 to `derived/paper_targets/observations.csv`. All four stages
    have equal target status, and any one target observation qualifies its site
    and year. No complete-sequence, minimum-duration, country or weather
    filter is added. Preserve all other stages in the full inventory.
11. **Regenerate figures from the combined file.** Both the study-area map and
    stage-count plot use BBCH07/65/81/89. Map colour counts distinct years with
    any target observation, pooled over varieties. Record the combined-file
    hash and four-stage filter in figure metadata.
12. **Verify independently.** Run `verify_data.py` to check schema, fields,
    hashes, source reconciliation, chronological support, quarantine recovery,
    exact target selection and all unit/integration tests. Do not tune cleaning
    thresholds against model errors or use historical bounds to clip model
    predictions.

Rebuild from the repository root (the fetch step is optional when verified input
objects are already available):

```sh
python3 src/phenology/fetch_phenology_inputs.py
python3 src/phenology/organize_phenology.py
python3 src/phenology/select_modeling_targets.py
python3 src/phenology/plot_study_area.py
python3 src/phenology/plot_stage_counts.py
swift -module-cache-path /tmp/grape-workflow-swift-cache src/phenology/draw_workflow.swift
python3 src/phenology/verify_data.py
```

`data/phenology/archive/pre_combined_targets_20260906/` preserves the superseded
split exports, methods note and notebook. Raw inputs, historical modelling
products and full-inventory QC/provenance are not cleanup targets.

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

### Current Workflow Model Catalogue

Use the five-factor table layout Process, Function, Interaction, ML and T.
Group the rows by forcing only, sequential chilling–forcing and parallel
chilling–forcing. Keep explicit -S (sequential) or -P (parallel) suffixes for
chilling–forcing model names in analysis outputs, figures and manuscript text.

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

- The six function combinations represent ten process structures: two forcing-only
  structures plus four chilling–forcing combinations with sequential and parallel
  variants. Cross all ten with RAW/DEM temperatures and without/with residual ML:
  40 candidate configurations per BBCH stage. Do not select a single best process
  model before the DEM/ML comparisons.
- Model names identify the process structure and optional -ML variant only:
  ten process models plus ten residual-ML hybrids give twenty model names.
  RAW and DEM are levels of a separate `temperature_input` factor, not models.
  A run identifier may retain `BBCH{stage}-{model}[-ML]-{RAW|DEM}` for provenance,
  where `model` is the complete
  structure name listed below the table (including -S or -P when chilling is present).
  Examples: `BBCH07-CL-FL-S-DEM`, `BBCH07-CL-FL-P-ML-DEM` and
  `BBCH65-FL-ML-RAW`. Append the interaction suffix before -ML. Forcing-only
  names remain FL and FB, without an interaction suffix. An accompanying
  `interaction` field must agree with the name. Historical unsuffixed
  chilling–forcing outputs must not be silently relabelled: verify their
  interaction from run metadata before any explicit migration.
  F denotes forcing, C chilling, L linear, B beta, S sequential, P parallel,
  and ML additive residual learning. CL specifically means bounded triangular,
  piecewise-linear chilling, not an unrestricted linear response.
- Sequential models start forcing after chilling completion. Parallel models allow
  chilling and forcing to overlap, with forcing effectiveness dependent on chilling
  status, following the interaction concepts of Chuine (2000),
  DOI `10.1006/jtbi.2000.2178` (`reference/Chuine et al.pdf`). Their grapevine
  variants are proposed adaptations, not parallel models attributed to Fila.
  Interaction concerns dormancy release and budburst, not the BBCH stage order:
  retain BBCH07→65→81→89 and initialize later stages from predicted dates.
- Fila et al. (2014) supports beta chilling and linear/beta forcing. Its Table 1
  does not supply a linear chilling response. The candidate triangular chilling
  comparator follows de Wergifosse et al. (2020), Eq. (1),
  DOI `10.5194/gmd-13-1459-2020`, with attribution there to Hänninen (1990).
  That source concerns forest trees; grapevine use is an adaptation requiring
  independent calibration and testing. The equation is in `workflow.md`.
- Distinguish these component-combination identifiers from Fila's original
  nine model names and parameter-sharing variants below. Do not imply a one-to-one
  equivalence. The ten process-only structures are implemented in `model/`;
  residual-ML variants and the full experimental comparisons remain prospective.
- Recalibrate each RAW/DEM configuration on matched historical calibration
  observations. Freeze that configuration's fitted parameters during testing.
  Complexity is not evidence of improved accuracy.

### Current Process-Model Implementation

- Shared prediction, calibration, response functions, validation, evaluation and
  command-line code reside directly in `model/`. Each of the ten named structures
  has its own `model/<model-name>/model.py` declaration and README. Use
  `model/README.md` for parameter names, bounds, scientific references and commands.
  Do not duplicate numerical code across model folders or alter legacy
  `src/modeling/` implementations silently. Residual ML is not implemented here.
- Fit all four stages jointly, with separate forcing response temperatures and
  requirements for each stage, pooled across sites, years and cultivars. Sites
  may contribute any one stage, but all four stages must occur somewhere in the
  calibration dataset. Keep all accepted observations, including repeated dates.
- Predict 07→65→81→89. Restart forcing on the day after the previous predicted
  stage, discarding accumulated overshoot. Observed preceding stages never
  initialize a prediction, including during calibration. Preserve signed DOY
  and dates outside the target year; never clip predictions to observation QC.
- Chilling begins on 1 September of the preceding year. Sequential forcing
  begins the day after chilling completion. Parallel budburst forcing is
  multiplied by `Kmin + (1-Kmin)*min(C_before_day/Ccrit, 1)`, following the
  competence formulation of Liu et al. (2018), DOI `10.1111/gcb.13954`, adapted
  to the selected response functions. Fit `Kmin` in [0,1]. Full chilling is not
  an additional budburst gate in parallel models. Chilling does not modify
  forcing after budburst.
- Forcing-only start DOY is fitted as an integer in [-60,90], with Jan 1 = 1
  and the preceding Dec 31 = 0. Default beta forcing limits are fixed at 0 and
  40 °C; fit a separate optimum for each stage. Ordered chilling cardinals
  require gaps of at least 0.1 °C. Bounds and fixed settings are explicit and
  recorded; any changes must be chosen within calibration, not from test errors.
- The objective is the mean of four stage-specific, site-balanced RMSEs: average
  squared error within site, then equally across sites, then take the square
  root for each stage. An unattained observed event receives a 1000-day fitting
  penalty, without inventing a prediction date. Reject a fitted model if any
  stage has no finite predicted observation. Report attainment alongside test
  metrics, which use finite predictions only.
- Differential evolution defaults are seeds 20260907–20260909, population
  multiplier 15, 300 generations, tolerance 0.001, one worker and no polishing.
  Save restart diagnostics, convergence, boundary hits, complete settings,
  dependency versions and SHA-256 input fingerprints. A saved fit need not have
  converged; check its diagnostics before scientific use.
- Require complete finite daily mean temperature in Celsius for each requested
  model window through 31 December of the target year. No missing-day filling,
  observation aggregation, DEM correction or automatic train/test splitting
  occurs in the model API. `temperature_input` is RAW or DEM independently of
  model names; use the corresponding supplied temperature column.
- `python -m model list`, `fit`, `predict` and `evaluate` expose the workflow;
  output files are exclusive-create and existing files are not overwritten.
  Run `python -m pytest tests -q` with `model/requirements.txt` installed.
  Synthetic and regression tests establish implementation behavior, not
  empirical grapevine accuracy. Real-data calibration requires matched weather
  and approved site partitions and has not been performed for these models.

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
  80/20 random site split stratified by clustered temperature zones, with four
  grouped inner calibration folds. Form zones across the eligible multi-country
  domain from common-period, temperature-only climatological features. Country
  is not a clustering input, stratification variable or allocation quota.
  Fixed temperature-quantile bins are not a substitute for clustering.
  Keep all records of
  each site and sites sharing an ERA5-Land cell in one partition. Use identical
  site assignments across model and temperature-input comparisons. This is a
  design specification; new split mappings have not been generated.
- Use raw ERA5-Land climate profiles for shared RAW/DEM zone labels. Document
  the normal period, features, scaling, clustering algorithm and cluster count,
  fitted clustering representation, seeds and `temperature_zone_id` assignments.
  Determine zoning from eligible sites' climate covariates before partitioning,
  without phenology outcomes or model errors; fit predictive preprocessing only
  within calibration. Resolve sparse zones by temperature similarity or cluster
  count, not country boundaries, before evaluating errors.
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
- Summarize performance by clustered temperature zone, country and relevant
  terrain groups when sample
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

## Terrain-Effect Evaluation

- Place Terrain effects at manuscript Section 2.5.2, after Calibration and test
  partitioning and before Predictive performance and uncertainty (2.5.3).
- Treat temperature input as a separate experimental factor. For each of the
  twenty model names, compare RAW and DEM at identical held-out sites, years
  and stages, with both treatments calibrated on the same calibration records.
- Define correction benefit as MAE(RAW) − MAE(DEM); positive values indicate
  improved phenological prediction. Compare benefits without/with residual ML.
- Examine signed and absolute site-to-grid elevation differences, site elevation,
  slope, aspect (northness/eastness) and local elevation variability. Specify
  terrain summaries and any class boundaries before examining test errors.
- Report site-balanced stage-specific contrasts, independent-site counts,
  temperature-zone composition and uncertainty from paired site-group resampling.
  Include within-temperature-zone comparisons where sample sizes support them.
- Interpret terrain associations descriptively, not causally. Improved phenology
  predictions do not establish corrected-temperature accuracy without independent
  temperature observations. Report unmet process requirements separately.
- Keep spatial and warm-year/site holdouts as historical transfer tests.
  Do not restore climate-change projections, warming perturbations, GCM data
  requirements or projection-credibility rankings without renewed authorization.

## Repository Organization and Reproducibility

### Workflow Figure Conventions

- Preserve five pastel panels in the sequence (a)–(e): blue data, ochre
  temperature, purple models, green calibration/testing and rose terrain
  effects. Panel letters are in parentheses; headings are outside the left
  edges, rotated counterclockwise to read bottom-to-top.
- Retain the five-factor matrix, named model combinations, site-level split,
  locked calibration/test separation and paired terrain-effect comparisons.
  Panel (e) shows terrain descriptors, MAE(RAW) − MAE(DEM), comparison without/with
  residual ML and paired site-group uncertainty.
- No overall figure title, subtitle or explanatory footer. Use a portrait,
  A4-width export cropped above and below the content, with small margins;
  the current page is 595.28 × 740 pt, not full-height A4.
- Rebuild with `swift -module-cache-path /tmp/grape-workflow-swift-cache src/phenology/draw_workflow.swift`
  from the repository root. Check PDF text, page size, model names and the PNG
  preview after changes. `fig/bak/` contains archived figures, not the active
  workflow source.

### Repository Paths

- Preserve the manuscript title: “Beyond thermal accumulation: improving
  cross-regional grapevine phenology prediction with terrain-aware forcing and
  residual learning”. Do not reframe the study as a data-resource paper.
- Organize Methods as: Overall workflow; Study area; Data; Models; Model
  evaluation. Within Data, use Phenology observations, Temperature data, Digital
  elevation model and DEM-based temperature correction. Retain process/residual-
  learning comparisons and terrain-effect evaluation; omit GCM/downscaling and
  climate-change assessment.
- Fig. 1 supports Overall workflow. Reference its panels (a)–(e) in that
  subsection, use an overall-workflow caption, and keep the rendered figure
  before the Study area subsection rather than allowing it to float into it.
- Fig. 2 supports Study area. Keep the map and its site/temporal-coverage
  caption after the study-area text and before the Data subsection.
- Keep Study area to a concise geographic, climatic, terrain and grape-growing
  description supporting Fig. 2. Support regional environmental context with
  literature; do not present it as measured site-level climate or terrain statistics.
  Observation sources, coverage periods, record-length definitions, stage counts,
  selection criteria and quality control belong in Data, without duplication
  in the Study area text. Figure captions may define their plotted quantities.
- Keep the Introduction general, without names of the study's observation,
  weather or terrain datasets. Retain the concise two-paragraph process-model
  review, including sequential and parallel interactions. The complex-terrain
  temperature-variation paragraph is penultimate, immediately before objectives.
- Preserve the existing Models subsection organization. Table 4 lists all twenty
  model names explicitly, with Process, Function, Interaction, ML and Model name
  columns. Each of the ten structures has two rows (without/with residual ML).
  Describe original (RAW) and DEM-corrected (DEM) temperature as a separate
  experimental factor in the methods text, not as suffixes, duplicated model
  rows or an extra factor block at the end of the table.
  Twenty models crossed with two temperature inputs give forty configurations.
  Retain explicit -S/-P interaction suffixes before the optional -ML suffix.
  Use a continued table with repeated headers if needed, rather than clipping
  rows or shrinking the text excessively. The workflow figure retains its
  compact three-family factor table, representing the same forty configurations.
  Place Table 4 after the residual-machine-learning description, not before its
  introduction; verify the rendered placement as well as the source order.
  Put abbreviation and model-naming explanations in the Table 4 caption, not
  in a note beneath the table.
- `paper/`: manuscript source, bibliography, and compiled manuscript. The active
  manuscript contains abstract, keywords, introduction and methods, plus cited
  references. Do not restore legacy results, discussion or conclusions without
  new analyses and explicit authorization. Completed observation preparation
  must remain distinct from planned modelling and terrain-effect comparisons.
  Embed `fig/study_area/study_area.pdf` and `fig/workflow/workflow.pdf` as vector
  figures. The full earlier manuscript is preserved in
  `paper/archive/pre_target_consolidation_20260906/`.
- `reference/`: supporting literature, including `Fila et al.pdf`.
- `data/`: observations, weather and terrain metadata, and derived tables.
- `model/`: active ten-model process-only library, shared code and named model
  folders; calibration and prediction interface documented in `model/README.md`.
- `src/`: data preparation, historical modelling, evaluation, and plotting.
  `src/phenology/` contains all active phenology preparation, audits and paper
  figure scripts; other subfolders retain historical or separate workflows.
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
