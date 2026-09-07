# FB

Process-only model with beta forcing, no explicit chilling and a calibrated calendar start.

The local `model.py` defines this combination; numerical prediction and calibration
use the shared parent modules through `get_model("FB")`. No code is copied
from other model folders.

## Equations and timing

Forcing: Fila's normalized beta curve, with fixed minimum 0 °C, fixed maximum
40 °C and a separate fitted optimum for each stage.
Accumulation begins on fitted signed DOY `start_doy`, inclusive.


All four stages (07 → 65 → 81 → 89) have separate forcing responses and
requirements. Each later stage starts the day after the preceding predicted
stage, discarding overshoot; observed dates never initialize predictions.

## Parameters and use

`start_doy`, plus `forcing_optimum_{stage}` and
`forcing_requirement_{stage}` for all four stages: 9 fitted parameters.
Beta forcing minimum/maximum are explicit fixed inputs, not fitted parameters.

The [shared documentation](../README.md#parameters-and-calibration) specifies
all bounds, units, calibration settings, I/O and examples. Calibrate with
`python -m model fit --model FB --help`; RAW/DEM is a separate input factor,
and no ML is included.

## References and adaptations

[Fila et al. (2014)](https://doi.org/10.1016/j.agrformet.2014.05.011) supplies the
forcing/accumulation framework and beta equation.
The BBCH07/BBCH89 targets, four independently parameterized stages, search-bound
choices and daily timing conventions are documented project adaptations.
No parameter values in this folder represent a calibrated European dataset.
