# Frozen ERA5-Land weather and climate

`sites/` retains the exact 3,171 original per-site temperature files required to
rebuild the publication snapshot. Each contains ISO `Date` and daily mean `Tmean`
in degrees Celsius. Site names and source-qualified identities are mapped in
`sites/metadata/paper_site_weather_crosswalk_20260908.csv`; original identities
and precision are preserved. Historical inventory entries outside the retained
snapshot remain documentary metadata, not available extra weather files.

`publication_20260910/` contains the corresponding RAW/DEM weather files, request,
file-level provenance and completion audit. Rebuild into a new directory:

```sh
.venv/bin/python src/weather_processing/prepare_publication_weather.py \
  --terrain data/topography/processed/publication_terrain_20260910_v2/terrain_manifest.csv \
  --weather-dir data/weather/sites --output build/weather_reproduced
```

Correction is `Tmean_DEM = Tmean - 0.0065 × site_minus_grid_elevation_m`. Site
Copernicus GLO-30 elevation and official ERA5-Land grid elevation are in metres.
The publication weather snapshot contains 14,728,566 daily rows. Stored finite
values do not independently establish complete model-season eligibility.

The frozen model-ready archive is
`model_run/results/publication_cohort_20260910/weather.csv.gz`. It retains the
original eligible site-years and RAW/DEM forcing used by the final calibration.
The revised phenology screen preserves this eligibility and original partitions.
Large archives use Git LFS; raw and corrected per-site inputs are also retained.

`climate/publication_20260910_v2/` contains RAW monthly normals, annual summer
temperatures, native-grid export and its provenance. Original environmental-zone
centroids and group assignments are frozen; they are not fitted again after
observation screening.

Renewed acquisition uses `src/weather_processing/site_weather.py` with an
explicit inventory and authenticated Earth Engine project; inspect `--help`
before selecting a new output directory. The old default historical inventory
is outside this cleaned repository. Native ERA5-Land point samples are neither
station observations nor DEM-resolution weather. Missing dates are not filled,
nearby sites are not substituted and existing observed temperatures are not
silently replaced. Reproduction of the included snapshot needs no new download.
