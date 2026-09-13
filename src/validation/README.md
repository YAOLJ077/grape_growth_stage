# Validation

Verify the final saved calibration and held-out predictions without refitting:

```sh
.venv/bin/python src/validation/verify.py --output model_run/verification_01.json
```

The validator checks both complete 20-unit production catalogues, declared
source hashes, all recursively sealed unit files, the pooled initialization
artifacts and original full-process parameter markers. It checks the frozen
group/fold separation, calendar-date error arithmetic, the 4 November scoring
rule, attainment flags and independently calculated equal-site MAE, RMSE,
signed bias and coverage rates for both raw and scoring views. Accepted repeated
observations retain separate identities. Raw process attainment remains
distinct from administrative scoring dates and hybrid date availability.

Historical absolute source paths are resolved by their repository suffix
within the current checkout; the expected original SHA-256 values are unchanged.
Unrelated historical comparison manifests are not traversed. In particular,
the removed earlier process/ML assembly outputs are unnecessary for checking
the final models and revised calibration population.

`--hashes-only` skips independent prediction arithmetic. `--replay-process`
also loads the full weather table and canonically simulates the 20 saved full
process fits. This optional operation can use substantial memory and time;
it performs no optimization or neural training. The default checks checkpoint
hashes but does not rerun TabM inference or replay all nested process fits.
`--threads 1` through `--threads 7` control the optional process replay.
Existing verification JSON files are never overwritten.

Focused implementation checks:

```sh
NUMBA_NUM_THREADS=1 .venv/bin/python -m pytest src/validation/test_verify.py tests/test_median_cutoff.py tests/test_pooled_calibration.py tests/test_cutoff_ml_run.py tests/test_cutoff_ml_crossfit.py tests/test_tabm_learner.py tests/test_factorial_features.py -q
```

The figure and manuscript reproduction entrypoint is
`src/visualization/reproduce.command`; calibration entrypoints are documented
in `src/calibration/README.md`.
