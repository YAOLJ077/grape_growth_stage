# Baseline accuracy, ML gains and reduced DEM benefits

Reproduce from the repository root:

```sh
.venv/bin/python src/visualization/reproduce.py
```

`baseline_hybrid_gain.csv` links original RAW process MAE, hybrid MAE and ML gain
on the existing common cohort for every model and stage. Rankings and ranges
are descriptive; no independent-replicate correlation test treats alternative
models as a sample. Gain includes baseline MAE by definition.

`paired_dem_gain_decrease.csv` reports the paired difference between DEM gains
without and with residual ML. `paired_site_stage_gains.csv` preserves inputs to
the comparison. Positive differences denote a smaller DEM gain in hybrids.
The analysis verifies identical observation identities across the source
packages, including original groups, and reproduces their marginal estimates
and intervals. Paired bootstrap intervals use identical group multiplicities
for the process and hybrid contrasts: 2,000 draws, seed 20260913, equal sites
within stages and equal weights across the four stages. The site-summary input
grain is recorded separately from observation counts.

`analysis.json` records hashes, cohort identity, summary ranges and estimand.
The results support Results 3.5–3.6 and the Discussion. Predictions, fitted
models, Figures 9–10 and the original sealed analysis packages are unchanged.
