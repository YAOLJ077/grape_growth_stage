# Grapevine phenology observation sites

## Figure contract

The map shows the geographic coverage of every site in
`data/phenology/derived/paper_targets/observations.csv`. The observation grain is a
source-qualified site ID, not an independently verified physical vineyard.
All countries and varieties with at least one retained BBCH07, 65, 81 or 89
observation are included after chronology-v2 screening. Neither a site nor a
site–variety–year needs all four stages.
The full cleaned observation inventory remains unchanged.

The figure is a geographic point map of coverage and record availability, with
equal-size site markers, neutral country boundaries and direct country labels.
Colour represents the number of distinct calendar years containing at least one
target-stage observation at each source-qualified site, pooled across varieties
and BBCH07, 65, 81 and 89. It is not the first-to-last-year span, observation count,
or number of complete-stage or complete-weather years. The 3,198 sites contain
1–72 observed years each.
Five ordered classes (1–5, 6–10, 11–20, 21–40 and >40 years) use a single-root
light-to-dark blue palette, preserving their order in grayscale. Markers are
opaque to prevent overlap from changing their encoded colour; longer records
are drawn last. The legend heading and entries are 15 pt. No overall title,
subtitle or footer appears in the figure. A spherical Lambert
conformal conic projection uses standard parallels of 43°N and 59°N, central
longitude 10°E and origin latitude 50°N. Coordinates are interpreted as WGS84
longitude and latitude. Sites are not jittered; coincident markers overlap.
Colour does not encode country. Coincident IDs remain separate in the inventory;
their visible marker colour is that of the longest record at that coordinate.

The output is a tightly framed 496 × 590 pt portrait vector PDF with a 3× PNG preview. Python's standard
library prepares the site inventory; macOS Core Graphics renders the figure.
QA requires a unique, consistent coordinate/country tuple per site, valid
coordinates and dates, reconciliation with every input row, and inclusion of
every projected site within the map frame. Distinct-year counts and colour-class
totals require independent reconciliation against the observation CSV. The exported PNG provides visual
checks for legibility, overlap and clipping.

## Reproduction

From the repository root on macOS with Python 3 and Swift:

```sh
python3 src/phenology/select_modeling_targets.py
python3 src/phenology/plot_study_area.py
```

Outputs: `study_area.pdf`, `study_area.png`, `site_inventory.csv` and
`map_quality.json`. The quality report records counts, coordinate bounds,
target-selection policy and SHA-256 checksums for the target CSV, full inventory
and boundary file. Rendering rejects a target file whose checksum or
parent-inventory checksum is stale. Current year-class site counts are 2,091
(1–5), 453 (6–10), 270 (11–20), 260 (21–40) and 124 (>40).

Country geometry comes from the existing repository file
`data/topography/metadata/countries.geojson`. The archived downloader
`src/bak/download_country_copernicus_dem_glo30.py` identifies the upstream source
as `datasets/geo-countries`, `data/countries.geojson` on its `master` branch.
The downloaded upstream revision and licence are not recorded in local metadata;
publication attribution requires confirmation. Country labels provide geographic
context and do not reassign source country values.

## Figure caption

Geographic distribution of grapevine observation sites for BBCH07 (beginning of
budburst), BBCH65 (full flowering), BBCH81 (beginning of ripening) and BBCH89
(berries ripe for harvest). The target file contains 75,233 observations at
3,198 source-qualified site IDs and 3,023 distinct coordinate pairs across 11
countries, spanning 1951–2026. A single observation of any target stage qualifies
a site. Marker colour indicates distinct calendar years with at least one
target-stage observation, pooled across varieties and stages. Gaps do not count as
available years. Coincident site coordinates overlap, with longer records drawn
on top. Coverage represents phenology availability, not verified weather coverage
or the final calibration/test population.
