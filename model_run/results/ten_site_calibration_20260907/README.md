# Ten-site calibration pilot

Calibration reduced mean stage-balanced test MAE for all ten process models
relative to their illustrative default parameters. Paired reductions ranged
from 64.9% to 84.7%. All calibrated models attained the 22 observed test events.
Three default models each failed to attain one event; their error comparisons
therefore contain 21 matched observations.

## Held-out comparison

MAEs are in days. Errors are averaged within site, equally across sites within
each stage, and equally across the four stages. Before/after errors use only
observations attained by both parameter sets. Positive reductions indicate
lower error after calibration. Paired samples can differ between model rows.

| Model | Paired observations | Default MAE | Calibrated MAE | Reduction (%) |
| --- | ---: | ---: | ---: | ---: |
| FL | 22 | 37.30 | 10.41 | 72.1 |
| FB | 21 | 35.81 | 10.07 | 71.9 |
| CL-FL-S | 22 | 35.09 | 10.84 | 69.1 |
| CL-FL-P | 22 | 63.81 | 11.40 | 82.1 |
| CB-FL-S | 22 | 37.00 | 10.88 | 70.6 |
| CB-FL-P | 22 | 74.77 | 11.44 | 84.7 |
| CL-FB-S | 21 | 36.51 | 11.35 | 68.9 |
| CL-FB-P | 22 | 30.78 | 10.81 | 64.9 |
| CB-FB-S | 21 | 33.97 | 10.64 | 68.7 |
| CB-FB-P | 22 | 31.55 | 9.64 | 69.4 |

The defaults for FB, CL-FB-S and CB-FB-S attained 21/22 test observations
(95.5%); all other defaults and all calibrated models attained 22/22 (100%).
Attainment uses all observations, independently of the paired error subset.

MAE decreased in 37 of the 40 model–stage comparisons. Flowering MAE increased
by 0.67 days for CL-FL-S and 3.00 days for CB-FL-S. Budburst MAE increased by
6.67 days for CL-FB-S. These are descriptive comparisons, not significance tests.

## Sample and fitting

The frozen cohort contains ten French sites during 2013–2022, with six sites
and 129 observations for calibration and four sites and 22 observations for
testing. Site selection is conditioned on available downloaded weather and
collective stage coverage, with seed 20260907. No selected sites share an
inventory ERA5 grid group or rounded-coordinate group. Individual sites retain
missing stages, and accepted observations remain unaggregated.

| BBCH | Calibration observations | Calibration sites | Test observations | Test sites |
| --- | ---: | ---: | ---: | ---: |
| 07 | 22 | 4 | 3 | 1 |
| 65 | 18 | 4 | 4 | 2 |
| 81 | 60 | 6 | 10 | 3 |
| 89 | 29 | 4 | 5 | 2 |

All models use RAW ERA5-Land temperature without DEM correction or residual
ML. Parameters are pooled across calibration sites, years and varieties.
Only calibration observations and calibration-site weather enter fitting.
The objective is the mean of four site-balanced stage RMSEs, with the shared
1000-day penalty for unattained calibration observations. Test observations
do not initialize stages, select optimizer restarts or tune parameters.

Each model has three differential-evolution restarts, with seeds
20260907–20260909, population multiplier 15, at most 300 generations and
tolerance 0.001. All 30 restarts reached the generation limit without meeting
the convergence criterion. No selected parameter triggered the implementation's
boundary-hit diagnostic. These are budget-limited fits, not demonstrated
optimizer optima.

## Interpretation limits

The baseline parameter sets are illustrative defaults, not calibrated
literature benchmarks. The observed reductions establish improvement over
these defaults in this pilot only. Four French test sites, including only one
site with budburst observations, do not support precise model rankings or
European transfer claims. This availability-conditioned pilot is separate from
the planned clustered-temperature-zone validation. No pilot results enter the
manuscript.

## Files

- [summary.csv](summary.csv): equal-stage paired MAE, mean stage RMSE, bias,
  reductions and observation-weighted attainment by model and partition.
- [improvement.csv](improvement.csv): stage-specific paired comparisons and
  sample counts, including deteriorations.
- [metrics.csv](metrics.csv): stage metrics on all finite predictions, with
  full-denominator attainment.
- [comparison.csv](comparison.csv): 3,020 observation–model–parameter-set rows;
  signed errors are predicted minus observed calendar date.
- [sites.csv](sites.csv), [observations.csv](observations.csv),
  [weather.csv](weather.csv), [eligibility.csv](eligibility.csv) and
  [cohort.json](cohort.json): frozen inputs, selection audit and checksums.
- Each named model folder contains `fit.json`, `default_parameters.json`,
  predictions and comparison tables.
- [diagnostics.csv](diagnostics.csv), [settings.json](settings.json),
  [execution_provenance.json](execution_provenance.json) and
  [verification.json](verification.json): fitting settings, source fingerprints,
  convergence and reproducibility checks.

Reproduction and read-only verification commands are in
[the experiment instructions](../../README.md).
