# Calibration

Run the complete final calibration chain in a fresh output directory:

```sh
.venv/bin/python src/calibration/run.py --output model_run/reproduced/run_01 --threads 7
```

The three sequential phases rebuild the pooled initialization comparison,
recalibrate the early-stage thresholds and median maturity requirement, and
train the ordinary/nested process refits and TabM learners. The complete chain
is computationally expensive. `--dry-run` prints its commands without starting
calibration. `--phase pooled`, `--phase process` and `--phase hybrid` run one
phase; the latter two accept `--population-run` and `--process-run` to select
completed upstream inputs.

The original full-process parameter artifacts under
`model_run/results/publication_factorial_20260911_v3/experiments/site_holdout/*/*/pbm/full/`
provide the recorded starting thresholds. The cleaned observations, frozen
weather, terrain and original group/fold allocations remain explicit inputs.
No historical ML assembly is required. Separate spatial and warm-condition
experiments are outside this final calibration chain.

The numerical engines remain byte-identical in `model_run/src/`, with shared
process definitions in `model/` and nested-learning support in
`model_run/factorial/`. Their original paths and hashes are part of the final
run evidence; moving them changes the recorded source identity. This directory
provides the classified public entrypoint without changing those engines.

Install the recorded Python 3.12 environment from
`model_run/requirements-lock.txt` before running. The wrapper refuses existing
output directories and any output under the frozen `model_run/results/` tree.
This also prevents a pooled resume from changing the gzip headers of frozen
population files. Interrupted fresh runs retain their generated commands in
`commands.json`; resume them only with the corresponding original engine and
the same arguments after checking source fingerprints.

On another checkout, use the full chain or rebuild the process phase before
hybrid training. A historical process run contains original absolute source
keys, so hybrid-only training refuses a relocated process source. The portable
validator in `src/validation/` verifies saved evidence in a new checkout
without rewriting its manifests. Numerical reproduction can vary with the
execution platform; timestamps, file paths and gzip metadata are not expected
to match a fresh run byte for byte.
