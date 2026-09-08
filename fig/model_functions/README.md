# Fixed temperature-response functions

The figure compares literature-fixed forcing and chilling responses, not fitted
phenological dates or empirical prediction accuracy. It has no overall title.
Panel (a) combines linear and beta forcing on a relative-response scale:
`R(T) / R(25.4 °C)`. Linear forcing is divided by 25.4; beta forcing already
equals one at 25.4 °C. Linear forcing remains uncapped and can exceed one.
This normalization is for display only: model equations, native rate units and
calibrated threshold units are unchanged. Panel (b) retains the chilling curves
in native daily response units on a narrower temperature axis. Solid and dashed
lines distinguish linear/triangular from beta responses in grayscale; legends
are 15 pt in the standalone vector PDF.

## Parameter provenance

| Component | Fixed temperatures (°C) | Evidence and scope |
| --- | --- | --- |
| Linear forcing | Base 0 | Parker et al. (2011), GFV base temperature; originally flowering and veraison |
| Beta forcing | Minimum 0, optimum 25.4, maximum 35 | Fila et al. (2014), Eq. 1, §3.2 and Table 8, Fbeta5* shared optimum |
| Beta chilling | Minimum −1.7, optimum 1.7, maximum 13.2 | Fila et al. (2014), Table 7, CF10* |
| Triangular chilling | Minimum −1.7, optimum 1.7, maximum 13.2 | Same grapevine cardinals as beta chilling, transferred to de Wergifosse et al. (2020), Eq. 1 |

Parker et al.: [General phenological model to characterise the timing of flowering
and veraison of Vitis vinifera L.](https://doi.org/10.1111/j.1755-0238.2011.00140.x).
The local paper is `reference/Parker et al.pdf`, pp. 206 and 211. Its original
GFV start is DOY 60, not the January 1 convention used here. Its flowering and
veraison predictions are not the same four-stage, next-day-restart model.

Fila et al.: [A comparison of different modelling solutions for studying grapevine
phenology under present and future climate scenarios](https://doi.org/10.1016/j.agrformet.2014.05.011).
The local paper is `reference/Fila et al.pdf`: Eq. 1 on printed p. 194; adopted
forcing maximum in §3.2 on p. 197; chilling Table 7 on p. 198; forcing Table 8
on p. 199. Asterisks denote calibration using field plus growth-room data.
Fbeta5* has one 25.4 °C optimum across the three original stages; the shared
curve is used here across all four targets. CF10* provides the exact chilling
triple. Its published chilling requirement (11.6 daily response units) is NOT
fixed here: chilling requirements remain calibrated per model.

de Wergifosse et al.: [HETEROFOR 1.0, Part 2: Phenology and water
cycle](https://doi.org/10.5194/gmd-13-1459-2020), Eq. 1, following Hänninen (1990).
This source supplies the triangular equation, not grapevine temperatures.
Transferring Fila's cardinals to it is a deliberate structural comparator, not
a published grapevine triangular parameterization.

These values are literature-calibrated modelling parameters, not universal
physiological constants. Fila's study concerns Chardonnay in northeastern Italy
and BBCH09/65/81, not this study's BBCH07/65/81/89. Its discussion explicitly
questions the interpretation of chilling effectiveness above 10 °C. Cultivar,
regional and stage transfer remain limitations; comparisons are conditional on
the fixed values. Fixed-parameter sensitivity must use calibration data, not
test outcomes. No test MAE was used to select these temperatures.

## Threshold-only calibration

`model/structure_comparison.py` is the single source of the fixed response
values. `threshold_only_settings(model_name)` creates an explicit opt-in
configuration for the existing model calibration API:

- Four forcing requirements, one per stage, are calibrated jointly for every
  model; chilling models also calibrate one chilling requirement.
- Each threshold is shared across sites, years and cultivars. Thresholds are
  model-specific and recalibrated separately for RAW/DEM treatments.
- Linear forcing requirements range over 0.001–3000 °C d; beta forcing and
  chilling requirements over 0.001–200 daily response units. The wider linear
  allowance accommodates the 0 °C base; these are numerical search ranges,
  not literature estimates or physiological bounds.
- Forcing-only start is fixed at January 1, following the common convention
  discussed by Fila et al. Chilling starts September 1 of the preceding year.
- Parallel `minimum_response=0.2` is a fixed project control retained from the
  implementation's illustrative setting, NOT a literature-derived grapevine
  constant. It needs calibration-only sensitivity assessment alongside the
  fixed temperatures and calendar origin.
- Four parameters are free in FL/FB and five in each chilling–forcing model.
  Equality bounds freeze all other adjustable API parameters. Saved fit
  settings retain these bounds explicitly.

The general-purpose API defaults and historical ten-site pilot are unchanged.
That pilot fitted response temperatures and is not evidence for this new
threshold-only experiment. No full-site recalibration has been executed.

## Files and reproduction

- `temperature_responses.pdf`: vector figure, 453 × 420 pt.
- `temperature_responses.png`: 300-dpi-sized preview.
- `temperature_responses.csv`: four curves on a 0.1 °C grid, retaining native
  units, cardinal values, parameter provenance and source DOIs. Separate
  `display_rate`, `display_divisor` and `display_rate_unit` fields document the
  plotted transformation without replacing the native `rate` values.
- `temperature_responses.json`: chart contract, colors, source hashes and values.
- `calibration_settings/<model>.json`: ten threshold-only settings files, usable
  with `python -m model fit --settings <path>` and calibration-only observations.

Code is in `model_run/src/plot_temperature_responses.py` and its Swift renderer.
Regenerate into a new directory to preserve existing artifacts:

```sh
/tmp/grape-model-env.hgwikC/bin/python model_run/src/plot_temperature_responses.py --output /tmp/grape-response-figure-new
```

The mathematical curves use `model/responses.py` directly. They do not read
phenology observations, weather, fitted parameters or test errors.
