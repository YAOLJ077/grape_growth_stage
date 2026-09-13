# Final observation preparation

`reproduce.py` reconstructs the final **74,618 observations at 3,169 reported
sites** from the revised four-target screening inventory and the original frozen
weather/site-year eligibility. It preserves every original seven-column field,
observation order, calibration/test assignment, inner fold and environmental zone.
The implementation uses Python's standard library and reads no predictions or
fitted models.

From the repository root, verify every field and row against the final tables:

```sh
.venv/bin/python src/data_preparation/reproduce.py --verify
```

To write the independently reconstructed tables and an input/output hash manifest:

```sh
.venv/bin/python src/data_preparation/reproduce.py --verify --output /tmp/grape-final-observations
```

The output directory must not already exist. Outputs are `observations.csv`,
`calibration_observations.csv.gz`, `test_observations.csv.gz`, `eligibility.csv.gz`
and `manifest.json`. Gzip headers are deterministic; compressed hashes can differ
from historical files, whose gzip headers contain their original creation times.
Verification compares decompressed fields and row order exactly. With no options,
the command verifies without writing files.

## Prepared inputs and exact population

| Input | Function |
| --- | --- |
| `data/phenology/derived/target_qc_v3_20260912/observations.csv` and `summary.json` | The 75,738 observations retained by revised target-specific QC; input hash checked |
| `model_run/results/publication_cohort_20260910/observations.csv`, `sites.csv` and `manifest.json` | Original site/country/coordinates, eligible site-years and independence groups; input hashes checked |
| `model_run/results/publication_factorial_20260911_v3/protocols.csv` | Frozen primary site holdout, environmental zones and four calibration folds |

The revised observations must match original source-qualified site, country and
exact numeric coordinates, and belong to an original weather-eligible site-year.
No coordinates are rounded for matching. This removes 1,120 revised observations
outside the frozen eligibility. Calibration retains 59,472 observations at 2,534
reported sites and 1,434 original independence groups; testing retains 15,146
observations at 635 sites and 357 groups. Entire sites and groups retain their
original partition, fold and zone.

`--verify` compares the reconstruction against
`model_run/results/cleaned_reevaluation_20260912/observations.csv` and the two
observation tables under `model_run/results/pooled_calibration_20260912/`. It checks
all fields and row order, not only totals. `--qc-dir`, `--cohort-dir` and
`--protocols` accept equivalent reconstructed inputs at explicit alternative paths.
This fixed-study entry point refuses different policy identifiers or populations.

## Rebuilding the screening input

The original screening code is retained under `src/phenology/`. To recreate QC-v3
in a new directory and verify it independently:

```sh
.venv/bin/python src/phenology/prepare_target_qc_v3.py --output /tmp/grape-target-qc-v3
.venv/bin/python src/phenology/verify_target_qc_v3.py /tmp/grape-target-qc-v3
.venv/bin/python src/data_preparation/reproduce.py --verify --qc-dir /tmp/grape-target-qc-v3
```

QC-v3 requires four canonical source representations: the France and Germany
complete tables in `data/phenology/processed/`, the auxiliary TEMPO table
`data/phenology/raw/france_tempo/tempo_other_countries_observations_joined.csv`,
and `data/phenology/raw/pep725/pep725_20260701_0.csv`. The canonical France/Germany
paths can be Git LFS pointers; their verified actual bytes are resolved through
`data/phenology/.source_cache/`. The existing `fetch_phenology_inputs.py` helper
retrieves missing objects from its explicitly configured original GitHub remote.
It needs network access and, where applicable, existing Git credentials.

QC-v3 also requires `data/phenology/phenology_data.csv` and
`phenology_data_quarantine.jsonl.gz` to assert reconstruction of the original
target inventory. `organize_phenology.py` recreates that all-stage chronology-v2
inventory and provenance from the four canonical source representations. These
canonical inputs already contain source assembly; this pipeline does not rebuild
them from live provider feeds. Provider licences and observation provenance remain
applicable, including the PEP725 noncommercial subset.

## Weather, terrain, zones and figures

The original publication cohort contains 74,311 observations at 3,170 sites.
It was prepared from the earlier 74,341-row target inventory, exact terrain
matching, and complete RAW/DEM temperature windows from the preceding June 4
through December 31 of each observation year. Its frozen site-year eligibility
is retained when revised screening changes observation membership. The adapter
does not replace this eligibility with a new weather download or a new split.

Raw weather acquisition is implemented in
`src/weather_processing/site_weather.py`. Publication weather correction is in
`prepare_publication_weather.py`, with `Tmean_DEM = Tmean - 0.0065 ×
site_minus_grid_elevation_m`. The publication snapshot uses
`data/topography/processed/publication_terrain_20260910_v2/terrain_manifest.csv`,
native grid assignments, official ERA5-Land geopotential and retained Copernicus
terrain samples. `prepare_publication_terrain.py` also depends on the audited
legacy terrain donor tables and imported helpers under `src/base_table/` and
`src/descriptive_phenology/`. Retaining those prepared donors does not establish a
complete rebuild from original terrain rasters.

The final process/ML runtime uses the frozen
`model_run/results/publication_cohort_20260910/weather.csv.gz` and `sites.csv`
with the final calibration/test observations. The weather archive, corrected
per-site weather copies and official invariant NetCDFs are included in the final
repository. Large objects use Git LFS; run `git lfs pull` after cloning. Earth Engine downloads require
authenticated project access; missing source values are never fabricated.

RAW monthly normals and their source export are under
`data/weather/climate/publication_20260910_v2/`. Climate preparation and grouped
zoning are implemented in `src/weather_processing/publication_climate.py` and
`model_run/factorial/climate_zones.py`. The final 1,791 surviving groups retain
centroids originally fitted using 1,792 grids; revised screening does not
recluster them.

`src/visualization/reproduce.py` independently recomputes the final plotted
statistics and graphics from the frozen `data/paper_figures/` bundle. Fig.2 uses
the historical 74,341-row, 3,171-site inventory, while the model analyses use the
74,618-row final population. That earlier inventory requires the recorded
27-site weather exclusion after chronology-v2 stage selection. The figure bundle
starts from locked predictions and prepared map backgrounds; it does not retrain
models or repeat raw DEM acquisition. Figure rendering needs macOS Swift and the
documented plotting dependencies.
