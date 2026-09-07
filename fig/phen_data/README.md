# Phenology observations by BBCH stage

## Figure contract

The vertical bar chart compares retained observation counts across BBCH stages.
The x-axis contains the four target stages, BBCH07, 65, 81 and 89, in developmental
order with equal categorical spacing. The y-axis
shows the number of CSV rows on a linear scale starting at zero. Counts are
observations, not unique sites, years or independently identified vines.

Input: `data/phenology/derived/paper_targets/observations.csv`, selected from the
unchanged full inventory of direct-source BBCH records from 1951 onward after
chronology-v2 screening. All countries and varieties are pooled. Partial
site–variety–year sequences are retained without date aggregation.
The current input contains 75,233 records: 25,303 at BBCH07, 26,657 at BBCH65,
18,734 at BBCH81 and 4,539 at BBCH89.

The figure uses a single blue fill, neutral grid lines and 15 pt axis titles.
No overall title, legend or footer is included, consistent with the paper's
figure style. Exact counts, site coverage, year coverage and date bounds are
provided in the companion CSV. The 420 × 350 pt vector PDF and 3× PNG preview
are rendered using Python's standard library and macOS Core Graphics.

## Reproduction

From the repository root:

```sh
python3 src/phenology/select_modeling_targets.py
python3 src/phenology/plot_stage_counts.py
```

Outputs: `phen_data.pdf`, `phen_data.png`, `stage_counts.csv`, and
`plot_quality.json`. Source hashes and count reconciliation are verified against
the target-selection quality report and unchanged parent inventory.
The PNG is inspected for legibility and clipping.

## Figure caption

Number of retained grapevine observations at four target stages: BBCH07
(beginning of budburst), BBCH65 (full flowering), BBCH81 (beginning of ripening)
and BBCH89 (berries ripe for harvest), 1951–2026. Counts pool all countries and
varieties; sites and years
with incomplete stage coverage remain eligible. Stage coverage reflects reporting
practices and data screening, not the biological frequency of development.
Counts precede weather matching and modelling-event preparation.
