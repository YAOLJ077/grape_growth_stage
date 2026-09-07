# Grapevine phenology targets

`observations.csv` contains all eligible BBCH07, 65, 81 and 89 observations
from every represented country. The four stages have equal target status and
retain the seven-column schema `site,variety,country,lat,lon,Date,BBCH`, with all
selected field values unchanged.

Any one target observation qualifies a site or site–variety–year. Complete
four-stage sequences are not required. Repeated observations, source-qualified
site identifiers and missing variety labels retain their existing meaning.
BBCH09 is not substituted for BBCH07. Non-target observations remain in the
full inventory; target selection is not an additional data-quality exclusion.

| Target file | Observations | Source-qualified sites | Coordinate pairs | Countries |
| --- | ---: | ---: | ---: | ---: |
| BBCH07/65/81/89 | 75,233 | 3,198 | 3,023 | 11 |

Stage counts are 25,303 for BBCH07, 26,657 for BBCH65, 18,734 for BBCH81 and
4,539 for BBCH89. Dates span 1951-04-15 to 2026-06-23. These counts precede
weather matching, modelling-event preparation and site partitioning. Site IDs
do not guarantee distinct physical vineyards; unknown variety labels and
maturity classes do not identify individual cultivars.

The study-area map uses every site with any of the four stages. Its colour
statistic counts distinct calendar years with at least one target observation,
pooled across varieties and stages. The stage-count plot includes one bar for
each of the four targets.

## Reproduction and lineage

From the repository root:

```sh
python3 src/phenology/select_modeling_targets.py
python3 src/phenology/plot_study_area.py
python3 src/phenology/plot_stage_counts.py
python3 src/phenology/verify_data.py
```

The selector validates the full inventory against
`data/phenology/phenology_data_quality.json` before exporting the target file.
`quality.json` records parent and output SHA-256 checksums, selection policy,
date bounds, country and stage counts, and site coverage. The full inventory and
its row-level provenance are unchanged. Selected rows retain their original
provenance through their unchanged seven-field event hash. The 184,765
observations outside the four target codes remain in that inventory.

The superseded split target exports are archived under
`data/phenology/archive/pre_combined_targets_20260906/`.
