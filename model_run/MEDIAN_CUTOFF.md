# Early-stage calibration and median maturity with a fixed scoring cutoff

The frozen primary split contains 59,472 calibration observations at 2,534 source-qualified sites and 15,146 test observations at 635 sites. Thresholds are shared across environmental zones and fitted separately for the ten process structures and RAW/DEM input. Temperature-response functions, accumulation starts and process equations retain the fixed-response profile. Residual machine learning is outside this comparison.

## Fitting and scoring

The three forcing thresholds for BBCH07, 65 and 81 and the chilling threshold, where applicable, are fitted on calibration observations. The first objective minimizes the largest absolute stage bias exceeding one day. After all three stage biases lie within ±1 day, the objective minimizes their equally weighted mean site-balanced MAE under the same bias bounds. Observation-level and equal-site raw attainment must each remain at least 99% at each early stage. Raw attainment means a finite process prediction within the original simulation period ending on December 31. Maturity error and maturity attainment do not constrain this optimization. An unmet early bias target is recorded explicitly; unsuccessful searches are not labelled successful constrained MAE fits.

The early-stage and chilling thresholds are then frozen. For every calibration observation of BBCH89, the maturity thermal requirement is the forcing accumulated from the day after raw predicted BBCH81 through the observed maturity date, inclusive. The maturity threshold is the weighted median of valid positive requirements; each site receives equal total weight among eligible records. Missing preceding predictions, observations on or before the preceding predicted stage, and nonpositive requirements are excluded from this median calculation with record-level reasons. These records remain in the evaluation population. The same post-BBCH81 forcing accumulation applies to all ten structures. Existing bounds apply to the median, and any bound adjustment is recorded.

The common scoring cutoff is **4 November** in each observation year. This is the latest month–day among the frozen calibration BBCH89 observations, including observations dated 1970-11-04 at `FR:tempo:7460`. The cutoff is independent of test observations, model, temperature input and environmental zone. Its derivation and input hashes are stored in `run.json`. A changed calibration maximum stops this version of the runner.

For BBCH81 and BBCH89, a raw prediction on or before 4 November retains its date. A later or missing prediction receives 4 November as its scoring date. When BBCH81 receives the cutoff, BBCH89 receives that same date. These assignments do not alter process accumulation, predicted preceding stages or observed dates. BBCH07/65 scoring remains unchanged. Calibration BBCH81 bias and MAE use this scoring convention, while its 99% attainment constraint uses the unmodified process prediction.

Assigned dates provide a defined error for every observed BBCH81/89 record. They are administrative evaluation dates, not evidence of developmental completion. Test observations after 4 November remain present; an assigned cutoff can consequently produce a negative error for those observations. Cutoff scoring can improve metrics mechanically by replacing later or missing predictions. Raw and cutoff-adjusted metrics and assignment fractions distinguish this effect from threshold-calibration performance.

## Output definitions

Each verified unit contains `fit.json`, `early_fit.json` and its checksum, `calibration_lock.json`, `median_requirements.csv.gz`, `predictions.csv.gz`, `metrics.csv` and an artifact-hash `complete.json`. `failure.json` records unsuccessful configurations. An all-invalid median retains the exclusion audit and is unsuccessful; no threshold is fabricated.

- `raw_predicted_date` and compatibility field `predicted_date`: unmodified process date.
- `raw_error_days` and compatibility field `error_days`: raw predicted date minus observed date.
- `scoring_date` and `scoring_error_days`: date and error after the explicit 4 November rule.
- `raw_attained`: raw date is finite within the original simulation period.
- `attained_by_cutoff`: raw date is finite and on or before 4 November.
- `cutoff_assigned` and `assignment_reason`: identify replacements; a prediction exactly on the cutoff is not a replacement.

`metrics.csv` has separate `raw` and `scoring` views for existing thresholds and the new `median_cutoff` fit. Both views retain actual raw attainment, actual attainment by the cutoff and cutoff assignment fractions, at observation and equal-site levels. `n_scored` counts finite errors in the selected view and is not an attainment count. MAE and signed bias average within sites and then equally across sites; RMSE is the square root of equally weighted within-site mean squared errors. No confidence intervals are included.

The report contains model-wise MAE/bias figures, separate attainment/assignment panels, and existing/new comparisons under both scoring conventions. Partial reports show only verified units; unfinished and failed configurations remain explicit. Complete scoring coverage never becomes 100% actual attainment by relabelling assigned dates.

## Execution and verification

```sh
.venv/bin/python model_run/src/calibrate_median_cutoff.py
.venv/bin/python model_run/src/report_median_cutoff.py model_run/results/median_cutoff_calibration_20260912
NUMBA_NUM_THREADS=1 .venv/bin/python -m pytest tests/test_median_cutoff.py tests/test_pooled_calibration.py -q
```

The source pooled run must be complete. Inputs and fitting code are fingerprinted; resume requires identical inputs/configuration. Per-unit predictions are checked against the canonical simulator, metrics are independently recomputed, and all source hashes are checked before unit verification and final completion. Resumed completed runs regenerate their reports. Altered inputs or fitting code require a separate output directory.

The production search uses seeds 20260907/20260908/20260909, 300 generations with a 600-generation retry, population multiplier 15 and tolerance 0.001. `--smoke` permits a reduced budget in a separate benchmark directory; smoke figures are explicitly labelled. `--threads` is capped at seven. With an existing competing process, `--competing-pid PID --reserved-threads 4` reserves four threads and allocates three to this calibration, increasing to seven at the next configuration after that process exits. The process identity and allocations are recorded in runtime metadata and the log. No running legacy process is modified.
