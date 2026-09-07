# CL-FB-P

Process-only model with beta forcing, triangular chilling and parallel interaction.

The local `model.py` defines this combination; numerical prediction and calibration
use the shared parent modules through `get_model("CL-FB-P")`. No code is copied
from other model folders.

## Equations and timing

Forcing: Fila's normalized beta curve, with fixed minimum 0 °C, fixed maximum
40 °C and a separate fitted optimum for each stage.
Chilling: the bounded triangular response, zero at/outside its cardinal limits
and one at its optimum. Accumulation begins September 1 of the preceding year.
Budburst forcing is multiplied by
`minimum_response + (1 − minimum_response) × min(Cbefore / chilling_requirement, 1)`.
`Cbefore` excludes the current day. Full chilling is not an additional budburst
gate; chilling does not modify later-stage forcing.

All four stages (07 → 65 → 81 → 89) have separate forcing responses and
requirements. Each later stage starts the day after the preceding predicted
stage, discarding overshoot; observed dates never initialize predictions.

## Parameters and use

`chilling_minimum`, `chilling_optimum`, `chilling_maximum`, `chilling_requirement`, `minimum_response`, plus `forcing_optimum_{stage}` and
`forcing_requirement_{stage}` for all four stages: 13 fitted parameters.
Beta forcing minimum/maximum are explicit fixed inputs, not fitted parameters.

The [shared documentation](../README.md#parameters-and-calibration) specifies
all bounds, units, calibration settings, I/O and examples. Calibrate with
`python -m model fit --model CL-FB-P --help`; RAW/DEM is a separate input factor,
and no ML is included.

## References and adaptations

[Fila et al. (2014)](https://doi.org/10.1016/j.agrformet.2014.05.011) supplies the
forcing/accumulation framework and beta equation.
[de Wergifosse et al. (2020), Eq. 1](https://doi.org/10.5194/gmd-13-1459-2020)
supports triangular chilling; grapevine use is an adaptation.
[Liu et al. (2018), Eq. 7](https://doi.org/10.1111/gcb.13954) supports the
parallel competence function; its combination with these responses is an adaptation.
The BBCH07/BBCH89 targets, four independently parameterized stages, search-bound
choices and daily timing conventions are documented project adaptations.
No parameter values in this folder represent a calibrated European dataset.
