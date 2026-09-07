# Grape Phenology Data

This directory stores prepared grape phenology data from France TEMPO,
Germany DWD, and selected PEP725 countries.

## Consolidated all-country table

`phenology_data.csv` is the single seven-column, direct-BBCH grapevine inventory:
`site,variety,country,lat,lon,Date,BBCH`. It includes the full PEP725 extract and
grapevine observations from auxiliary TEMPO countries, beyond the older selected-
country tables below. Only records with valid direct source BBCH codes are retained;
inferred mappings and unmapped phases are excluded before deduplication.
Only observation dates on or after 1951-01-01 are included. This study-period
cutoff does not establish complete weather or preceding-season input coverage.
The active export also applies chronology-v2 seasonal windows, stage order and
phase-interval screening documented in `../../AGENTS.md`. Original values of
excluded observations and reasons are retained in `phenology_data_quarantine.jsonl.gz`.
The canonical processing procedure, field handling, duplicate policy and mapping
limitations are documented in `../../AGENTS.md`; independent checks are run with
`python3 src/phenology/verify_data.py` from the repository root.
Source files remain unchanged. This all-country inventory is not a final
modelling cohort; source-qualified site IDs require cross-network matching before
they can represent independent physical sites.

## Paper target observations

`derived/paper_targets/observations.csv` is the single all-country phenology
export for the four equal target stages BBCH07, BBCH65, BBCH81 and BBCH89. It
contains 75,233 observations, 3,198 source-qualified site IDs, 3,023 distinct
coordinate pairs and 11 countries, spanning 1951-04-15 to 2026-06-23. Stage
counts are 25,303, 26,657, 18,734 and 4,539, respectively.

The developmental order is 07→65→81→89, but any one target stage qualifies a
site or year; no complete sequence is required. BBCH09 remains distinct from
BBCH07. The export preserves the source table's seven-column schema, missing
varieties and repeated accepted observations. Non-target stages remain valid
inventory records and are not QC errors.

Regenerate and validate the target export from the repository root with:

```sh
python3 src/phenology/select_modeling_targets.py
python3 src/phenology/verify_data.py
```

The selector writes `quality.json` beside the export. The target file establishes
phenology eligibility only; weather matching, cultivar or plant identity, and
resolution of source-qualified identifiers into independent sites remain
modelling tasks. Historical France–Germany products are retained unchanged and
do not define the current all-country paper scope.

## Directory Layout

- `raw/`: source downloads and source-adjacent auxiliary files.
  - `raw/france_tempo/`: TEMPO observation JSONL files, additional data, France site inventory, and non-France TEMPO auxiliary table.
  - `raw/germany_dwd/`: DWD annual and immediate reporter source files for grapevine phenology.
- `processed/`: analysis-ready complete phenology tables with harmonized columns.
  - `france_grape_phenology_complete.csv`: complete standardized France TEMPO table. This generated file is kept locally because it exceeds GitHub's single-file size limit; regenerate the consolidated inventory through `src/phenology/organize_phenology.py`.
  - `germany_grape_phenology_complete.csv`: complete standardized Germany DWD table.
  - `pep725_selected_countries_grape_phenology_complete.csv`: complete standardized PEP725 table for Austria, Slovakia, Spain, and Switzerland.
  - `phenology_observations_1951.csv`: simplified 1951+ observation-level table for modeling.
  - `phenology_site_year_stage_1951.csv`: 1951+ site-year-standard-BBCH event table for modeling.
- `index/`: derived lookup/index files.
  - `grape_weather_download_index.csv`: site-year date windows for weather data downloads.
- `derived/`: reproducible analysis summaries derived from `processed/`.
  - `derived/standardized_bbch/`: six-country standardized BBCH analysis layer.
  - `derived/base_table/`: 1951+ six-country phenology base table and summaries.
  - `derived/phenology_distribution/`: tabular summaries used by phenology distribution figures.
  - `derived/descriptive_phenology/`: tabular summaries used by descriptive phenology overview figures.
  - `derived/paper_targets/`: combined BBCH07/65/81/89 phenology-only paper observations and validation metadata.
- `archive/pre_combined_targets_20260906/`: superseded split target exports, standalone methods note and verification notebook.
- `metadata/`: source metadata, download logs, station metadata, column dictionary, and standardization QA reports.

## Current Data Policy

The repository keeps complete phenology tables and phenology-only derived
tables here. Weather values are stored under `data/weather/`, topographic
values under `data/topography/`, and GEE/weather export inputs under
`data/gee/`.
