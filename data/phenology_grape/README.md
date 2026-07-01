# Grape Phenology Data

This directory stores grape phenology data from France TEMPO and Germany DWD.

## Directory Layout

- `raw/`: source downloads and source-adjacent auxiliary files.
  - `raw/france_tempo/`: TEMPO observation JSONL files, additional data, France site inventory, and non-France TEMPO auxiliary table.
  - `raw/germany_dwd/`: DWD annual and immediate reporter source files for grapevine phenology.
- `processed/`: analysis-ready complete country tables with harmonized columns.
  - `france_grape_phenology_complete.csv`: complete standardized France TEMPO table. This generated file is kept locally because it exceeds GitHub's single-file size limit; regenerate it with `src/standardize_grape_phenology.py`.
  - `germany_grape_phenology_complete.csv`: complete standardized Germany DWD table.
- `index/`: derived lookup/index files.
  - `grape_weather_download_index.csv`: site-year date windows for weather data downloads.
- `derived/`: reproducible analysis summaries derived from `processed/`.
  - `derived/phenology_distribution/`: tabular summaries used by phenology distribution figures.
  - `derived/descriptive_phenology/`: tabular summaries used by descriptive phenology overview figures.
- `metadata/`: source metadata, download logs, station metadata, column dictionary, and standardization QA reports.

## Current Data Policy

The repository currently keeps complete country-level processed tables only. It does not keep separate training tables or France+Germany concatenated tables, because those are easy to regenerate from `processed/` when a modeling task needs them.
