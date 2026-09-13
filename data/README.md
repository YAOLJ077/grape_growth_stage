# Final-study data

| Location | Retained content |
| --- | --- |
| `phenology/processed/` | Canonical France and Germany source representations, materialized through Git LFS |
| `phenology/raw/` | Auxiliary TEMPO and full PEP725 source representations and source notices |
| `phenology/phenology_data*` | All-stage chronology-v2 inventory, provenance and exclusions needed to reconstruct the original target inventory |
| `phenology/derived/target_qc_v3_20260912/` | Final four-target screening: 75,738 retained and 1,575 excluded observations |
| `phenology/derived/paper_targets/` | Earlier 74,341-row, 3,171-site inventory used by Fig. 2 and original weather preparation |
| `weather/sites/` | Exact original daily temperature files needed by the publication cohort |
| `weather/publication_20260910/` | RAW/DEM weather snapshot and file-by-file provenance |
| `weather/climate/publication_20260910_v2/` | Original RAW monthly normals, annual summer data, export and climate provenance |
| `topography/processed/` | Native grid assignments, terrain donors, native sample caches and verified publication terrain |
| `topography/raw/era5_land_invariant/` | Official ERA5-Land geopotential and land-sea mask; Git LFS objects |
| `paper_figures/` | Compact frozen inputs for all final figures, including the locked scoring-error cube |

Final weather-eligible observations and partitions are under `model_run/results/`; [`src/data_preparation/`](../src/data_preparation/README.md) reconstructs them independently. The full weather archive and model checkpoints are included through Git LFS. `.source_cache/` contains relative links to the canonical source objects, preserving original input identities without duplicate data.

Source-qualified identifiers are not necessarily distinct vineyards. No dates, coordinates or missing temperatures are fabricated. The final four-target screen differs from the preceding all-stage screen; original source representations, exclusions and provenance preserve both boundaries. Provider-level source assembly and complete raw-raster terrain reconstruction are upstream of the included canonical/prepared data.

## Attribution and licences

TEMPO, DWD and PEP725 records retain their source notices and provenance. PEP725 includes CC BY-NC 4.0 records; the repository does not replace provider licences with a uniform licence. See `phenology/raw/pep725/README.txt`, `phenology/metadata/`, and [`paper/evidence/provenance/`](../paper/evidence/provenance/) for source registration. Those source-register counts describe their dated historical inventory, not the final 74,618-row cohort.

ERA5-Land forcing and official model orography, Copernicus DEM GLO-30 terrain, and map-boundary attribution are documented under `topography/metadata/` and [`paper_figures/study_area/SOURCES.md`](paper_figures/study_area/SOURCES.md). Cached map backgrounds are display inputs, not weather or new DEM measurements.
