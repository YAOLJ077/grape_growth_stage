# CB-FL-S

Process-only model with linear forcing, beta chilling and sequential interaction.

The local `model.py` defines this combination; numerical prediction and calibration
use the shared parent modules through `get_model("CB-FL-S")`. No code is copied
from other model folders.

## Equations and timing

Forcing: `max(T − forcing_base_{stage}, 0)`.
Chilling: Fila's normalized beta curve using three fitted chilling cardinal
temperatures. Accumulation begins September 1 of the preceding year.
Forcing begins the day after `chilling_requirement` is reached.

All four stages (07 → 65 → 81 → 89) have separate forcing responses and
requirements. Each later stage starts the day after the preceding predicted
stage, discarding overshoot; observed dates never initialize predictions.

## Parameters and use

`chilling_minimum`, `chilling_optimum`, `chilling_maximum`, `chilling_requirement`, plus `forcing_base_{stage}` and
`forcing_requirement_{stage}` for all four stages: 12 fitted parameters.

The [shared documentation](../README.md#parameters-and-calibration) specifies
all bounds, units, calibration settings, I/O and examples. Calibrate with
`python -m model fit --model CB-FL-S --help`; RAW/DEM is a separate input factor,
and no ML is included.

## References and adaptations

[Fila et al. (2014)](https://doi.org/10.1016/j.agrformet.2014.05.011) supplies the
forcing/accumulation framework and beta equation.
The BBCH07/BBCH89 targets, four independently parameterized stages, search-bound
choices and daily timing conventions are documented project adaptations.
No parameter values in this folder represent a calibrated European dataset.
