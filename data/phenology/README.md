# Phenology source and screening data

The four canonical source representations are the France and Germany complete
tables in `processed/`, the auxiliary TEMPO country table under `raw/france_tempo/`,
and the complete PEP725 extract under `raw/pep725/`. France and Germany are Git LFS
objects; `.source_cache/` links preserve the original verified input identities.
Provider notices, column definitions and attribution remain under `metadata/`,
`raw/pep725/README.txt` and `paper/evidence/provenance/`.

`phenology_data.csv` is the seven-column all-stage chronology-v2 inventory.
Its provenance and quarantine preserve the exact upstream target-record universe
needed by the revised four-target screen. No date or stage repairs are applied.
The source code for this historical boundary is `src/phenology/phenology_qc.py`.

`derived/target_qc_v3_20260912/` contains the final target-specific screen: 75,738
retained observations and 1,575 exclusions, with per-record evidence. Screening
uses no model predictions or residuals. The final weather-eligible subset has
74,618 observations at 3,169 reported sites. It is independently reconstructed
by [`src/data_preparation/`](../../src/data_preparation/README.md), preserving
all original site partitions, inner folds and environmental zones.

`derived/paper_targets/observations.csv` is the separate, earlier 74,341-row,
3,171-site phenology-only snapshot used by Fig. 2 and original weather
preparation. It follows the recorded 27-site weather exclusion. The generic
`select_modeling_targets.py` alone produces the pre-exclusion selection; do not
overwrite the frozen figure snapshot by treating that command as its complete
reproduction. Complete-sequence coverage is never required.

`derived/descriptive_phenology/site_topography.csv` is a terrain donor input
retained by publication-terrain preparation. It does not define the final
phenology population. Repeated accepted dates, empty variety labels and source
identity are preserved throughout; reported sites are not necessarily
independent vineyards.
