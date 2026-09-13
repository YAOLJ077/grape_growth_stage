# Scientific evidence retained with the final paper

The folders retain numerical analyses, source hashes, provenance and validation
records supporting the current manuscript. Dated build reviews and obsolete text
drafts are excluded. The current sources are `paper/manuscript.tex` and
`paper/supplementary.tex`.

| Evidence | Scope |
| --- | --- |
| `pbm/` | RAW process accuracy and controlled structure contrasts |
| `structure_spatial/` | Site and environmental-zone distributions |
| `dem/` | Paired DEM benefits, terrain/country strata and uncertainty |
| `ml/` | Paired ML gains and combined DEM–ML effects |
| `ml_baseline/` | Baseline dependence and paired decrease in DEM benefit after ML |
| `population/` | Current population/method evidence and historical table-source manifest |
| `provenance/` | Provider citations, source licences and historical cohort reconciliation |
| `documents/` | Final document fingerprints and current verification |
| `claim_evidence.csv` | Numerical claim traceability |
| `structure_contrast_catalogue.csv` | Controlled process-structure comparisons |

Historic source paths and hashes inside original analysis manifests identify the
inputs and code used at analysis time. They are provenance, not executable current
paths. Current figure reproduction uses the self-contained
[`data/paper_figures/`](../../data/paper_figures/README.md) bundle and
[`src/visualization/`](../../src/visualization/README.md).

The source/licence register describes a historical **74,341-observation** export.
The historical cohort-flow audit records 75,233 target observations, 892 exclusions
at missing-weather sites and 30 incomplete-year exclusions, leaving 74,311 rows.
These snapshots document their respective source populations; they do not replace
the current final-analysis cohort or establish later weather coverage. Source
licences and attribution remain provider-specific.
