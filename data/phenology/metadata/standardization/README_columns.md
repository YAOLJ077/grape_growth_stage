# Standardized grape phenology column dictionary

This directory contains metadata for standardized grape phenology tables generated from France TEMPO and Germany DWD data.

The main machine-readable dictionary is:

- `grape_phenology_column_dictionary.csv`

Use it to look up each standardized column's Chinese meaning, English meaning, source/derivation, applicable dataset, and modeling note.

Key processed tables:

- `data/phenology/processed/france_grape_phenology_complete.csv`: complete France TEMPO table with source metadata attached.
- `data/phenology/processed/germany_grape_phenology_complete.csv`: complete Germany DWD table with source metadata attached.
- `data/phenology/index/grape_weather_download_index.csv`: site-year weather download windows derived from the processed tables.

Important modeling fields:

- `date`, `year`, `doy`: event timing variables.
- `latitude`, `longitude`, `altitude`: spatial and climate matching variables. France `altitude` uses reported TEMPO elevation when present and otherwise falls back to `altitudeIgn`.
- `altitude_reported`, `altitude_ign`, `altitude_source`: elevation provenance fields used to audit the canonical source elevation.
- `taxon_fullname`, `cultivar`, `cultivar_group`: crop and variety/maturity-group variables.
- `stage_id`, `bbch_code`, `stage_event`, `stage_description`: phenological stage variables.
- `source_system`, `source_dataset`, `datasource_name`, `reporter_type`: source-control variables.
- `dedup_group_id`: duplicate-control key available for optional downstream filtering.

Notes:

- `stage_id` is source-specific and should not be treated as globally equivalent between TEMPO and DWD.
- `bbch_code` is the preferred cross-source stage code where available.
- DWD has no BBCH code for some phases such as harvest and leaf-fall, so `bbch_code` can be empty for Germany.
- France-specific administrative fields are `region`, `department`, and `commune`.
- Germany-specific geography fields are `natural_region` and `federal_state`.
- Cross-country modeling should preferentially use the uniform Copernicus `dem_elevation_m` from `data/phenology/derived/descriptive_phenology/site_topography.csv`; source elevation remains a QA reference.
