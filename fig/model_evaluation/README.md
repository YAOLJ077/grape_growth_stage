# Calibrated test MAE figures

## Stage and model comparison

`mae_by_stage_model.pdf` and `mae_by_stage_model.png` show four panels:
(a) BBCH07, (b) BBCH65, (c) BBCH81 and (d) BBCH89. Each panel contains the
same ten models in catalogue order, with stage-specific, site-balanced MAE
in days. All panels share a 0–15-day y-axis. There is no overall title.

These are calibrated RAW-temperature test errors from all available target
observations, not changes from default parameters. Test sample sizes are
3 observations at 1 site for BBCH07, 4 at 2 sites for BBCH65, 10 at 3 sites
for BBCH81, and 5 at 2 sites for BBCH89. Model rankings are descriptive;
the small pilot and nonconverged fits limit generalization.

The 40 original metric rows are in `mae_by_stage_model.csv`; the plotting
contract, shared axis limits and source fingerprint are in
`mae_by_stage_model.json`. The renderer is
`model_run/src/draw_stage_mae.swift`.

```sh
python model_run/src/plot_mae_histogram.py --by-stage --output fig/model_evaluation_rerun
```

Stage/model exports can share a folder with the original histogram, but
existing stage/model files are never overwritten.

## Across-model histogram

`mae_histogram.pdf` is a vector figure; `mae_histogram.png` is its
1800 × 1300-pixel preview. The figure has no title or legend.

Each of the ten process models contributes one calibrated test MAE. Within
each stage, absolute errors are averaged within site and then equally across
sites; the four stage MAEs are averaged equally. All 22 held-out observations
are included for every model. Source: the calibrated, test, RAW rows of
`model_run/results/ten_site_calibration_20260907/metrics.csv`.

The numeric x-axis uses 0.5-day bins; the y-axis counts models and starts at
zero. Bins are left-inclusive and right-exclusive, except the final bin,
which includes its upper edge. Counts total ten. Values are in `model_mae.csv`,
bin counts in `histogram_bins.csv`, and source fingerprints and figure settings
in `plot_quality.json`.

This is a distribution across model evaluations, not individual observation
errors or independent samples. The pilot has four French test sites, and all
fits reached the optimizer generation limit. FB, CL-FB-S and CB-FB-S values
differ from their earlier paired summaries because this histogram also includes
the observations missed by their default models.

Reproduce with the model Python dependencies and macOS Swift/AppKit:

```sh
python model_run/src/plot_mae_histogram.py --output fig/model_evaluation_rerun
```

Existing output directories are not overwritten. The rendering source is
`model_run/src/draw_mae_histogram.swift`. Tests are in
`tests/test_mae_histogram.py`.
