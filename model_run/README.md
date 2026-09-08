# Process-model experiments

## Interim calibration on all weather-complete sites

[`src/calibrate_available_sites.py`](src/calibrate_available_sites.py) runs all
ten process-only models using RAW weather and the `literature_fixed_responses_v1`
profile. Four stage forcing requirements, plus one chilling requirement where
present, are calibrated jointly and shared across sites, years and cultivars.
Temperature-response parameters, January 1 forcing-only start and parallel
minimum competence remain fixed. No DEM correction or residual ML is applied.

The frozen snapshot is
[`results/available_site_cohort_20260907/`](results/available_site_cohort_20260907/):
1,460 French sites, 5,647 site-years and 10,921 observations. The calibration
partition contains 1,168 sites and 9,080 observations; testing contains 292
sites and 1,841 observations. Every weather-complete site in the selected
historical inventory is retained, including sites with only one target stage.
Shared ERA5 cells and coordinates rounded to four decimals form transitive
groups kept within one partition. Group permutations target an 80/20 site split
and require all four stages collectively in both partitions. Country is not
used for allocation. This is an interim availability-conditioned holdout, not
the manuscript's temperature-zone-stratified, multi-country evaluation.
Complete common-period temperature normals remain unavailable for clustering.

The batch was launched on 2026-09-07 with two concurrent models. Its output is
[`results/available_site_calibration_20260907/`](results/available_site_calibration_20260907/)
and progress is recorded in
[`results/available_site_calibration_20260907.log`](results/available_site_calibration_20260907.log).
The initial parent PID is `25136`. Completion requires the final
`verification.json`, not merely the presence of the output directory.

Eligibility requires complete finite daily weather from the preceding
September 1 through December 31 of every observed year at a site. No days are
filled and no observations are aggregated. The inventory-wide audit records
exclusions; metadata separately counts canonical sites outside the historical
download inventory. Frozen observations, weather and assignments are hashed.
Background downloads cannot add sites or change the inputs of this run.

```sh
python model_run/src/calibrate_available_sites.py --prepare-only \
  --output model_run/results/available_site_cohort_new
python model_run/src/calibrate_available_sites.py \
  --cohort model_run/results/available_site_cohort_20260907 \
  --output model_run/results/available_site_calibration_20260907 --workers 2
python model_run/src/calibrate_available_sites.py --verify-only \
  --output model_run/results/available_site_calibration_20260907
```

Each model uses three optimizer seeds, up to 300 generations and population
multiplier 15. Two independent models run concurrently by default. The baseline
uses the same fixed response parameters, but illustrative uncalibrated thresholds;
it is not a literature-calibrated comparator. Predictions, errors, attainment,
site-balanced stage metrics, paired before/after contrasts and restart diagnostics
are saved per model as each completes. Combined outputs and `verification.json`
are created after all ten finish. A running process or `fit.json` alone is not
evidence of a completed, verified comparison. Numerical routines and the earlier
ten-site pilot's default behavior are unchanged.

Tests: `python -m pytest tests/test_available_site_calibration.py -q`.

The [six-model calibration/test figure](../fig/model_evaluation/available_six_20260908/calibration_test_mae.pdf)
compares stage-specific site-balanced MAE in both partitions. It is generated
from explicitly selected finished models with `src/plot_calibration_test.py`;
the [figure notes](../fig/model_evaluation/available_six_20260908/README.md)
document the partial scope, attainment counts and reproduction command.

## Ten-site calibration pilot

[`src/calibrate_ten_sites.py`](src/calibrate_ten_sites.py) fits all ten process
models jointly across BBCH07, 65, 81 and 89 using six calibration sites and
evaluates their locked parameters at four other sites. The experiment uses RAW
ERA5-Land temperature without DEM correction or residual ML.

The frozen input cohort is in
[`results/ten_site_cohort_20260907/`](results/ten_site_cohort_20260907/).
The model outputs are in
[`results/ten_site_calibration_20260907/`](results/ten_site_calibration_20260907/).
The [completed results](results/ten_site_calibration_20260907/README.md) show
64.9–84.7% lower paired test MAE than the illustrative defaults across the ten
models. All calibrated models attained every test observation, but three
model–stage comparisons worsened. All optimizer restarts reached the generation
limit; these are budget-limited pilot fits, not demonstrated optima.
The cohort contains 129 calibration observations and 22 test observations,
spanning 2013–2022. All ten sites are French; availability during the ongoing
weather download conditions the sampling frame. These results are a small
transfer pilot, not the manuscript's clustered-temperature-zone validation.

Selection uses seed 20260907 and only site identity, observation availability,
stage presence and weather completeness—not prediction errors. Sites sharing
an ERA5 grid cell or coordinates rounded to four decimals form transitive
groups across the full inventory. A seeded permutation contributes at most one
site from each group, with the first six assigned to calibration and the next
four to testing. Permutations are repeated until all four stages occur
collectively in both partitions. Individual sites do not need all stages.
All accepted observations at the selected sites remain unaggregated.

Required daily temperatures are checked from September 1 of the preceding year
through December 31 of each observed year; this also covers the earliest
allowed forcing-only start. No missing-day filling occurs. The frozen cohort
contains the selected weather and observation records, split assignments,
an inventory-wide eligibility audit and SHA-256 checksums. Subsequent downloads
cannot change a run based on `--cohort`.

```sh
# Freeze an independently named snapshot from currently available weather.
python model_run/src/calibrate_ten_sites.py --prepare-only \
  --output model_run/results/ten_site_cohort_new

# Reproduce the supplied selection and fit all ten models into a new directory.
python model_run/src/calibrate_ten_sites.py \
  --cohort model_run/results/ten_site_cohort_20260907 \
  --output model_run/results/ten_site_calibration_rerun --workers 3

# Check saved inputs, parameters, predictions and metrics without fitting.
python model_run/src/calibrate_ten_sites.py --verify-only \
  --output model_run/results/ten_site_calibration_20260907
```

Defaults are three differential-evolution seeds (20260907–20260909), 300
generations, population multiplier 15 and tolerance 0.001. Each optimizer uses
one worker; `--workers` controls independent model fits. Bounds and the fitting
objective are unchanged from `model/`. Neither test observations nor test
weather enter calibration. The selected restart minimizes calibration loss,
not test error. Nonconverged fits remain explicitly flagged.

Each model folder contains `fit.json`, `default_parameters.json`, predictions,
observation-level comparisons, stage metrics and paired improvement metrics.
Combined tables retain `model`, `partition` and `parameter_source` columns.
`delta_days` and bias are predicted minus observed calendar date; positive
values mean late predictions. Positive improvement is default error minus
calibrated error.

`metrics.csv` reports finite-prediction errors and attainment for all observed
events. `improvement.csv` compares errors only on events attained by both
parameter sets, with explicit paired counts and full-denominator attainment.
`summary.csv` averages the four site-balanced stage metrics equally; its mean
stage RMSE is not a pooled-event RMSE. No stage is silently omitted. Default
and calibrated attainment rates are observation-weighted. When attainment
falls, the paired error change is conditional on jointly attained events and
does not establish improvement across all observations. The parameter defaults
are illustrative values, not previously calibrated literature models.
Gains over these defaults do not establish superiority over other calibrated
models. Test budburst has only three observations at one site; this pilot
does not support precise model rankings or broad European accuracy claims.

Tests: `python -m pytest tests/test_ten_site_calibration.py -q`.

The [MAE histogram](../fig/model_evaluation/mae_histogram.pdf) shows one
calibrated test MAE per model, using all 22 observations and equal stage
weights. Its values come from `metrics.csv`, not the paired subset in
`summary.csv`. Reproduce with `python model_run/src/plot_mae_histogram.py
--output fig/model_evaluation_rerun`; vector PDF, PNG and supporting data are
saved together.

The [stage-by-model figure](../fig/model_evaluation/mae_by_stage_model.pdf)
retains all 40 stage-specific MAEs in four panels, with a shared zero-based
scale and identical model order. Generate it with `--by-stage`; the original
histogram is preserved. The figure's CSV contains the underlying stage metrics
and observation/site counts.

## First-site comparisons

The single example script is [`src/run_first_site.py`](src/run_first_site.py).
It uses the shared implementation in `model/`, without copying response
functions or fitting parameters to the comparison observations.

The all-model comparison is in
[`results/first_site_all/comparison.csv`](results/first_site_all/comparison.csv).
It contains all ten process structures and a first column named `model`, with
20 rows for the first site's two observed events. Predictions and metrics also
include this column; `model_name` is retained for compatibility with the shared
model output schema. Exact parameters for every model are in the accompanying
`run.json`. No ML or calibration is performed.

To run all models into a new directory:

```sh
python model_run/src/run_first_site.py --model all \
  --output model_run/results/first_site_all_rerun
```

All models use the same weather and accepted observations. Comparisons retain
every accepted observation once per model, and all four predicted stages are
saved for each observation year. The ten structures use their documented,
uncalibrated example parameter sets; differences among them are not calibrated
model rankings. A single `--fit` cannot be combined with `--model all`.

From the repository root, with the model dependencies installed:

```sh
python model_run/src/run_first_site.py
```

The default is **FL with illustrative, uncalibrated parameters**: forcing
starts on January 1, the base temperature is 5 °C for each stage, and each
successive stage requires 300 degree-days. These values are not fitted to the
first site and are not a calibrated European model.

The script selects the first row of
`data/phenology/derived/modeling/france_germany_four_stage/site_inventory.csv`:

- Inventory identity: `France|france_tempo|100354`.
- Canonical observation identity: `FR:tempo:100354`.
- Site name: `16369-27875-2852-36032-2505`.
- Weather: `data/weather/sites/16369-27875-2852-36032-2505.csv`, with `Date,Tmean`
  and temperature in Celsius.
- Observations: `data/phenology/derived/paper_targets/observations.csv`, retaining
  all accepted matching rows and cultivar labels without aggregation.

The identity mapping is explicit and coordinates must agree within 0.0001°.
Historical aggregated phenology tables are not substituted for the canonical
cleaned observations. Other sites do not enter this comparison.

## Original FL-only comparison

The supplied example outputs are in [`results/first_site_FL/`](results/first_site_FL/).

| Year | BBCH | Observed date | Predicted date | Delta (days) |
| --- | --- | --- | --- | --- |
| 2019 | 07 | 2019-03-25 | 2019-04-05 | +11 |
| 2020 | 65 | 2020-06-02 | 2020-05-01 | −32 |

Delta is **predicted calendar date minus observed calendar date**. Positive
values mean late prediction and negative values mean early prediction. Missing
predicted events retain missing dates and differences, with attainment status.
The two observed events are insufficient to calibrate the full four-stage
model. No independent predictive-skill claim follows from this demonstration.

Outputs:

- `comparison.csv`: observed records, predicted dates, signed differences and
  absolute errors, with the uncalibrated parameter label.
- `predictions.csv`: all four predicted stages in each observed year, including
  stages without observations. Later stages start from predicted, not observed,
  preceding stages.
- `metrics.csv`: stage-specific error and attainment summaries, explicitly
  labelled by parameter source.
- `run.json`: exact parameters, identity mapping, input paths and SHA-256 hashes,
  temperature convention and interpretation limits.

## Rerun or use another model

Existing output directories are never overwritten. Because an example result
is already supplied, choose a new directory for another run:

```sh
python model_run/src/run_first_site.py \
  --output model_run/results/first_site_FL_rerun

python model_run/src/run_first_site.py --model CB-FB-P \
  --output model_run/results/first_site_CB-FB-P
```

Without `--fit`, every model uses its documented uncalibrated example values.
To reuse a saved calibrated RAW-temperature fit:

```sh
python model_run/src/run_first_site.py --fit /path/to/fit.json \
  --output model_run/results/first_site_saved_fit
```

The fit determines the model name and parameters. No refitting occurs. A DEM
fit is rejected because these downloaded temperatures are RAW. Saved optimizer
convergence is recorded; whether the comparison site was excluded from that
fit's calibration data must be checked separately before calling it test skill.

The optional `--inventory`, `--observations` and `--weather-dir` flags allow
explicit alternative input paths. The first row of the chosen inventory remains
the target site; missing observations or incomplete required daily weather stop
the run before output creation. No downloads or weather-file edits occur here.

Tests: `python -m pytest tests/test_first_site_run.py -q`.
