# Historical four-target snapshot for Fig. 2

The frozen seven-column file contains 74,341 observations at 3,171 reported sites
and 2,996 distinct coordinate pairs across 11 countries. It starts with the
75,233 target-stage records in the chronology-v2 inventory and removes the
recorded 27 sites/892 observations with no usable weather. Its role is Fig. 2 and
original weather preparation; it is distinct from the final 74,618-row modelling
cohort reconstructed by `src/data_preparation/reproduce.py`.

The exclusion identities are in
`data/weather/sites/metadata/unweathered_site_exclusion_20260909.json`.
`quality.json` retains its original preceding-selection provenance; the exact
frozen file hash and figure counts are also retained in the figure bundle.
Do not overwrite this snapshot with the generic pre-exclusion selector alone.
