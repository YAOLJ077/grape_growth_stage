# Grapevine phenology observation sites

The two-panel map shows geographic coverage and record availability in the
active four-target phenology inventory. Panel **a** includes every eligible site;
panel **b** enlarges the dense France–Germany–Switzerland region. The dashed
rectangle in panel a is the exact projected extent of panel b.

## Observation population and encoding

The source is `data/phenology/derived/paper_targets/observations.csv`, containing
74,341 observations at 3,171 source-qualified site IDs, 2,996 distinct coordinate
pairs and 11 countries. Dates span 1951-04-15 to 2026-06-23. Eligibility requires
any one of BBCH07, 65, 81 or 89 under the active chronology-v2 selection. These
counts describe phenology availability, not the final modelling cohort.

Marker colour represents distinct calendar years with at least one target-stage
observation per source-qualified site, pooled across varieties and stages.
Gaps do not count as observed years. Five ordered blue classes are 1–5, 6–10,
11–20, 21–40 and >40 years. Their site counts are 2,069, 450, 270, 259 and 123;
availability ranges from 1 to 72 years.

Markers are opaque and equal-sized within each panel. Longer records are drawn
last, so coincident markers display the longest record at that coordinate.
Coordinates are not jittered. Source-qualified IDs are not necessarily distinct
physical vineyards. Panel-b sites repeat a subset of panel a and must not be
added to the overview count.

## Terrain background and cartography

The background uses actual Copernicus GLO-30 Public COG tiles from the AWS 2021
release. The DEM is a digital surface model, including vegetation and structures.
The remote COG overviews are read with average resampling and preserved as
georeferenced, checksummed extracts. Four concurrent I/O requests reduce network
latency; GDAL reads and subsequent mosaic/reprojection/shading use one thread.

The plotting projection is spherical Lambert conformal conic, with standard
parallels 43°N and 59°N, origin 50°N, central longitude 10°E and sphere radius
6,371,008.8 m. Input coordinates are WGS84 longitude and latitude. The DEM is
placed on a common 1/240-degree source mosaic and then bilinearly reprojected
onto a grid with spacing no greater than 500 m. Joining neighbours before
reprojection allows interpolation across tile boundaries and prevents artificial
shading seams. Grid
spacing is retained in the audit, and both panels preserve projection aspect.
Hillshade uses azimuth 315°, light altitude 45° and no vertical exaggeration.
Elevation and horizontal distances are in metres. Subtle shading modulates a
muted elevation tint; the elevation legend shows its unshaded colours.

Missing source elevations remain missing. The renderer rejects missing DEM in
land interiors. A two-pixel coastal tolerance accommodates small discrepancies
between the DSM shore and vector country boundaries; those pixels receive a
neutral fill, never invented elevations. Derivative gaps at water edges receive
no shading. Oceans have a pale blue-grey fill. Background resampling is solely
for geographic context and does not change any weather, site terrain, phenology
or model input.

Panel b starts from 2°W–11°E, 43–51°N and expands to a rectangular projected
frame of the required aspect ratio. All sites inside that actual frame are
shown. Exact projected bounds and panel counts are in `map_quality.json`.
Scale bars use the local Lambert scale at each panel's centre latitude.

## Reproduction and artifacts

From the repository root:

```sh
# First build, or completion of an interrupted background download:
.venv/bin/python src/phenology/plot_study_area.py --prepare-dem

# Repeat using the verified local tile cache:
.venv/bin/python src/phenology/plot_study_area.py

# Independent observation and numeric terrain checks:
.venv/bin/python -m unittest src.phenology.test_paper_figures src.phenology.test_study_area_relief
.venv/bin/python src/phenology/verify_study_area.py
```

The script consumes the existing target file. It does not rebuild or clean
observations. Source hashes must match the target-selection audit and its parent
inventory. Rendering requires NumPy, rasterio, SciPy, Pillow and macOS Swift with
AppKit/PDFKit; existing repository virtual-environment dependencies suffice.

Outputs are `study_area.pdf` (180 × 132 mm), `study_area.png` (300 dpi preview),
`study_area.tiff` (600 dpi), `site_inventory.csv` and `map_quality.json`.
`verify_study_area.py` independently reconciles observations and raster coverage,
checks source/artifact hashes and writes `verification.json`.
Text, markers, borders, graticules and legends remain editable/vector in the PDF;
only the terrain background is raster, embedded at approximately 557–600 dpi.
The full 500-m DEM grids remain in the cache. Helvetica lettering is 8 pt, with
9 pt bold panel letters `(a)` and `(b)`. There are no subplot titles, overall
figure title or explanatory footer. Legend spacing uses measured 8 pt text
widths. Country labels in the detail panel are omitted when the larger text
would intersect a site marker; all observation markers remain unchanged.
The years-with-data legend occupies the lower-left space beneath the overview;
the elevation legend sits beneath the detail panel. The cropped page reduces
unused space while preserving both map panels at their original sizes.

The DEM extracts, panel DEM rasters, backgrounds and provenance are in
`data/topography/processed/study_area_relief_20260912/`. The manifest records
remote URLs, native and extract transforms, acquisition dates and SHA-256 hashes.
Download progress can resume from independently verified tile files. A missing
or altered cache prevents a nominally complete offline render.

## Sources and attribution

- [Copernicus DEM on AWS](https://registry.opendata.aws/copernicus-dem/) and
  [COG processing documentation](https://copernicus-dem-30m.s3.amazonaws.com/readme.html).
  © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided
  under COPERNICUS by the European Union and ESA; all rights reserved.
- Country boundaries use the repository's checksummed
  `data/topography/metadata/countries.geojson`. The archived downloader records
  [datasets/geo-countries](https://github.com/datasets/geo-countries) as the source;
  its underlying [Natural Earth data](https://www.naturalearthdata.com/about/terms-of-use/)
  are public domain. The historical upstream revision was not recorded; the
  local-file checksum identifies the exact geometry used here.
- Export typography and editable artwork follow the
  [Nature research figure guide](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/).
