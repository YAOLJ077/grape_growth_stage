# Locked-model errors after four-target data screening

All **20 completed primary structure–temperature units**, including their residual-ML variants (**40 configurations per stage**), were reassessed on the revised observations. Model weights, temperature inputs and site-year calibration/test assignments remain fixed. There is no refitting. The reassessment contains **74,618 observations**, compared with 74,311 originally: 503 original observations were excluded and 810 newly eligible observations restored at the original weather-eligible site-years. Another 1,120 observations in the wider revised inventory lack the exact frozen site/coordinate/country/year match required for this evaluation.

| Partition | Original | Removed | Retained original | Restored | Revised |
|---|---:|---:|---:|---:|---:|
| Calibration | 59,199 | 368 | 58,831 | 641 | 59,472 |
| Test | 15,112 | 135 | 14,977 | 169 | 15,146 |
| Total | 74,311 | 503 | 73,808 | 810 | 74,618 |

The calibration-partition reassessment includes restored observations that were not used for fitting. It is not an out-of-fold score. The test partition retains its original held-out site membership. Cleaning was reviewed after model-result inspection; revised scores are post hoc screening sensitivity estimates.

## Results

The revised errors change modestly and do not improve uniformly. Across all 20 process configurations, test MAE changes by +0.02 to +0.08 days for budburst, +0.09 to +0.32 for flowering, −0.06 to −0.01 for veraison and −0.17 to −0.13 for maturity/harvest. For residual-ML configurations, corresponding ranges are +0.08 to +0.11, +0.09 to +0.16, −0.12 to +0.02 and +0.07 to +0.12 days. Changes include restoration of newly eligible observations and changes in site weighting; they do not identify a causal effect of cleaning.

The large process-only beta-forcing maturity error persists. For RAW forcing, FB test MAE changes from 39.83 to 39.67 days and FL from 26.30 to 26.16 days. Their residual-ML variants score 9.69 and 10.01 days after screening. This reassessment does not support attributing the large FB process-model error to the screened observations alone.

![Revised calibration/test MAE](mae.png)

![Change from original scores](mae_change.png)

## Metrics and populations

[metrics.csv](metrics.csv) contains 960 rows: 40 configurations × four stages × two partitions × three observation populations. `original` uses the frozen training/evaluation observations; `cleaned_common` uses only original observations that survive revised QC; `cleaned_eligible` also includes restored eligible observations at the frozen site-years. [metric_changes.csv](metric_changes.csv) gives revised-minus-original differences.

MAE and signed bias are averaged within each site and then equally across sites with attained predictions. RMSE is the square root of the equal-site mean of site mean squared errors. Signed error is predicted date minus observed date. Error metrics use finite predictions only; unattained dates remain in the population and are counted separately. Attainment is the fraction of all observations with a finite prediction; equal-site attainment is also exported. Prediction dates remain exactly as saved, including any date outside observation-screening bounds. Point estimates have no confidence intervals and do not establish a final model ranking.

## Deliverables

- [Cleaned weather-eligible observations](observations.csv), [membership changes](membership.csv), [partition/stage counts](population_changes.csv) and [wider candidate matching audit](candidate_weather_matching.csv).
- [MAE](mae.pdf), [RMSE](rmse.pdf), [signed bias](bias.pdf), [attainment](attainment.pdf), with PNG previews and corresponding `_change` figures.
- `site_holdout__MODEL__RAW_OR_DEM__comparison.csv.gz`: every revised observed/predicted date, original-cohort flag, partition, group, model and error. Both process-only and residual-ML arms are included.
- [Completed units](completed_units.csv) and [manifest](manifest.json): immutable source hashes, snapshot membership, counts and checks.
- [Cleaning rules and source audit](../../../data/phenology/derived/target_qc_v3_20260912/README.md).

Every metric group passed independent calendar-date and equal-site arithmetic checks. The 304 original metric rows shared with the previous delivered snapshot reproduce to numerical tolerance. All saved prediction dates reproduce the original comparison files; all sealed artifact hashes remain unchanged. Ten unit tests passed, including leap-year arithmetic, unequal site sample sizes, missing predictions, exact identity and per-record chronology support.

Reproduction requires a new output directory:

```sh
.venv/bin/python model_run/src/reevaluate_cleaned_predictions.py \
  --run model_run/results/publication_factorial_20260911_v3 \
  --cleaned data/phenology/derived/target_qc_v3_20260912 \
  --output /path/to/new_reevaluation_directory
```

This snapshot contains primary site-holdout results only. Additional validation protocols require their own completed saved predictions; completion of these 20 units does not establish completion of the entire multi-protocol experiment.
