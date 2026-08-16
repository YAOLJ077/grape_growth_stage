# Grape Phenology Data

This directory stores prepared grape phenology data from France TEMPO,
Germany DWD, and selected PEP725 countries.

## Directory Layout

- `raw/`: source downloads and source-adjacent auxiliary files.
  - `raw/france_tempo/`: TEMPO observation JSONL files, additional data, France site inventory, and non-France TEMPO auxiliary table.
  - `raw/germany_dwd/`: DWD annual and immediate reporter source files for grapevine phenology.
- `processed/`: analysis-ready complete phenology tables with harmonized columns.
  - `france_grape_phenology_complete.csv`: complete standardized France TEMPO table. This generated file is kept locally because it exceeds GitHub's single-file size limit; regenerate it with `src/standardize_grape_phenology.py`.
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
- `metadata/`: source metadata, download logs, station metadata, column dictionary, and standardization QA reports.

## Current Data Policy

The repository keeps complete phenology tables and phenology-only derived
tables here. Weather values are stored under `data/weather/`, topographic
values under `data/topography/`, and GEE/weather export inputs under
`data/gee/`.
