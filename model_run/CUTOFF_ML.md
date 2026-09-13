# Residual TabM after median/cutoff process calibration

The current ML experiment is `results/median_cutoff_ml_20260912/`. Its process
source is the verified 20-unit `median_cutoff_calibration_20260912/` run. The
primary frozen split contains 59,472 calibration observations at 2,534 reported
sites and 15,146 test observations at 635 sites. Environmental zones share
process parameters; RAW and DEM are fitted separately. The other spatial and
warm-condition experiments in historical directories are not final results
under this calibration protocol.

## Training

Each of the ten process structures and two temperature inputs has four fresh
out-of-fold process fits and six pair-excluded process fits for nested neural
validation. Every fit uses only its training calibration groups. Full-calibration
thresholds are never used to initialize these fits. Fixed response parameters
and a label-independent small initial threshold are used instead. Optimization
and the median maturity requirement follow [MEDIAN_CUTOFF.md](MEDIAN_CUTOFF.md).
The 4 November scoring cutoff is a frozen protocol constant in every fold.

Residual targets are observed date minus the **raw fold-specific process date**.
An unattained process stage has no residual target. It remains in evaluation,
including the explicit BBCH81/89 cutoff assignment. Predictor windows end at
raw process dates and use realized weather; these are retrospective estimates.
Site identity, country, observation year, variety and observed dates are excluded
from the predictor vector.

TabM uses the existing fixed architecture, four nested folds for epoch selection,
and three seeds (20260907–20260909). Fold-local training data determine missing
value replacement and numerical preprocessing. Final learners train on all
calibration out-of-fold residuals for the rounded median selected epoch count.
Test labels do not tune either component. Predictions average the three seeds;
rounded residuals adjust the locked full-calibration process dates. Corrected
attained stages are ordered at least one day apart before cutoff scoring.

## Evaluation and files

Each `MODEL/T/` unit contains `pbm/`, cached `features/`, stage-specific neural
checkpoints in `stages/`, `residual_training.csv.gz`, `ml_lock.json`, predictions,
metrics, provenance and a recursively hashed completion marker. Final source
hash verification and all 20 completion markers are required for run completion.
Completed process jobs are canonically replayed on resume. Calibration scores
are apparent full-fit performance, not out-of-fold performance estimates.

Metrics have `process` and `tabm` methods and separate `raw` and `scoring` views.
MAE and bias average within sites, then equally across sites. RMSE is the square
root of the equally weighted site mean squared errors. Error sign is predicted
minus observed. `pbm_raw_attained` and `pbm_attained_by_cutoff` preserve actual
process attainment. A finite corrected hybrid date is not a new thermal
attainment event. Cutoff assignments are administrative scoring dates and never
count as actual developmental attainment.

The report shows exact MAE and bias values with shared colour scales of 8–20
days and −10 to +10 days, respectively. Colourbar extensions identify values
outside these ranges. Partial and smoke reports are explicitly identified.

```sh
.venv/bin/python model_run/src/run_cutoff_ml.py --threads 7
.venv/bin/python model_run/src/report_cutoff_ml.py model_run/results/median_cutoff_ml_20260912
NUMBA_NUM_THREADS=1 .venv/bin/python -m pytest tests/test_cutoff_ml_run.py tests/test_cutoff_ml_crossfit.py tests/test_tabm_learner.py tests/test_factorial_features.py -q
```

The single process alternates seven-thread process optimization and seven-thread
TabM training. Source data and fitting code are fingerprinted; changes require
a new run directory. A real-data reduced-budget smoke run and its resumed
canonical replay passed before production launch. Smoke outputs establish
pipeline execution, not scientific model accuracy.

## Final reproduction

Use `src/calibration/run.py` for a fresh calibration chain and
`src/validation/verify.py` to check frozen artifacts without changing them.
`src/visualization/reproduce.command` regenerates all current publication
figures and PDFs. The former finalization writer and obsolete comparison
assemblies are outside this retained final-study repository.
