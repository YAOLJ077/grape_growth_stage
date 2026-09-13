# DEM elevation-correction results

Section 3.4 and Figure 8 use locked, completed process-based predictions, with no residual ML. The common finite-scoring cohort across all twenty model/temperature arms retains 15,105 observations (99.73%), including every BBCH81 and BBCH89 observation and the fixed November 4 scoring assignments. Aggregate losses average across ten fixed structures, within site and then equally across sites; overall summaries weight four stages equally.

`analysis.json` defines the estimand, bootstrap and exact calibration-only terrain cutpoints. `paired_effects.csv` includes the full terrain, zone and country exploration, including missing strata and sparse combinations. `model_effects.csv` separates the common cohort from each model's own finite-pair cohort. `site_stage_effects.csv`, `site_benefit_distribution.csv`, `continuous_associations.csv`, `stratum_contrasts.csv` and `sensitivity.csv` preserve distributional, continuous and robustness diagnostics. Source rows are in `paired_observation_metrics.csv.gz`.

Main Figure 8 connects overall model gains, stage benefits and share of sites improved, signed elevation mismatch, and the distinct terrain measures. Supplementary Figures S3 and S4 retain stage-specific terrain patterns and signed bias/RMSE. Environmental-zone support is in [`dem_zone_effects.tex`](../../tables/dem_zone_effects.tex). Country and joint-terrain estimates remain in the complete CSV instead of a map or dense figure with poorly supported cells. `figure_values.csv` retains numeric labels, and `claim_evidence.csv` links narrative metrics to source rows.

The regional sill is a separate exploratory diagnostic at 20 km, based on verified, smoothed GLO-30 overview elevations. It is not relabelled local variance, native site terrain or ERA5-Land orography. Only 475 of 1,791 cells have a supported plateau; absent plateaus and insufficient land coverage remain missing. Protocol, source-tile hashes, empirical variograms and fit-quality records are under `data/topography/processed/dem_variogram_20260913/`. The scale and zero-nugget spherical fitting choices are this repository's adaptation, not an asserted reproduction of Zhao et al. (2015).

The AFM paper's publisher-indexed abstract and introduction support the terrain-heterogeneity motivation; `afm_reference.json` records verified Crossref metadata. The user identified sill as the paper's metric. Full text was unavailable through the publisher page, public publisher API and inactive local Zotero API, so no unverified sampling scale, variogram family or thresholds are attributed to that paper.

Reproduce from the repository root:

```sh
.venv/bin/python src/visualization/reproduce.py
```

The final ML renderer preserves this package's reviewed section and figure. The comparisons describe predictive performance after independent threshold recalibration, not causal terrain effects, validation of corrected temperature, or an estimate of optimal weather-grid resolution.
