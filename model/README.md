# Process-based grapevine phenology models

Ten process-only models share one prediction and calibration implementation.
The model-named folders define the component combinations; shared Python
modules live directly in this directory. No residual ML, data downloads,
automatic splitting or full-data calibration are performed at import time.

## Active paper experiment: fixed responses, fitted thresholds

The paper's structure comparison now uses the explicit
`model.structure_comparison.threshold_only_settings(model_name)` profile.
Temperature responses are fixed from literature and reused across stages,
sites and all models containing the same component: linear forcing base 0 °C;
beta forcing cardinals 0/25.4/35 °C; triangular and beta chilling cardinals
−1.7/1.7/13.2 °C. References, qualifications and the plotted curves are in
`fig/model_functions/README.md` and `temperature_responses.pdf` there.

Only four stage-specific forcing requirements and, where present, one chilling
requirement are calibrated, each shared across sites, years and cultivars.
The forcing-only start is fixed at January 1 and parallel minimum competence at
0.2 (an explicit project control, not a literature-derived temperature parameter).
Thus the active experiment has four or five free parameters, not the counts
for the unrestricted API below. The helper uses equality bounds, leaving the
general API, saved fits and historical pilot unchanged. Call it explicitly:

```python
from model import fit
from model.structure_comparison import threshold_only_settings

fitted = fit("CB-FB-P", calibration_observations, weather,
             threshold_only_settings("CB-FB-P", temperature_column="Tmean"))
```

Equivalent CLI JSON files are in `fig/model_functions/calibration_settings/`.
Do not pass held-out observations to `fit`. This profile has not yet undergone
full-site calibration; the existing ten-site results used unrestricted fitting.

## Models

The counts below describe the general-purpose, unrestricted calibration API,
retained for reproducibility and sensitivity work, not the active paper profile.

| Model | Forcing | Chilling | Interaction | Fitted parameters |
| --- | --- | --- | --- | --- |
| FL | Linear | None | None | 9 |
| FB | Beta | None | None | 9 |
| CL-FL-S | Linear | Triangular | Sequential | 12 |
| CL-FL-P | Linear | Triangular | Parallel | 13 |
| CB-FL-S | Linear | Beta | Sequential | 12 |
| CB-FL-P | Linear | Beta | Parallel | 13 |
| CL-FB-S | Beta | Triangular | Sequential | 12 |
| CL-FB-P | Beta | Triangular | Parallel | 13 |
| CB-FB-S | Beta | Beta | Sequential | 12 |
| CB-FB-P | Beta | Beta | Parallel | 13 |

Each model predicts the full BBCH07 → 65 → 81 → 89 sequence. Four forcing
responses and four forcing requirements are stage-specific, but shared across
sites, years and varieties. Chilling parameters and the parallel competence
parameter apply only to budburst. Counts exclude fixed beta forcing cardinals.
RAW/DEM denotes the temperature-input factor, not a separate model.

## Environment and commands

From the repository root, using Python 3.12:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r model/requirements.txt
.venv/bin/python -m model list
.venv/bin/python -m pytest tests -q
```

The dependency file contains only NumPy, pandas, SciPy and pytest. It does not
install the legacy workflow's ML or geospatial dependencies.

```sh
.venv/bin/python -m model fit --model CL-FL-P \
  --calibration-observations calibration_observations.csv \
  --weather daily_weather.csv --settings calibration_settings.json \
  --output results/CL-FL-P-RAW-fit.json

.venv/bin/python -m model predict --fit results/CL-FL-P-RAW-fit.json \
  --weather daily_weather.csv --seasons test_seasons.csv \
  --output results/CL-FL-P-RAW-predictions.csv

.venv/bin/python -m model evaluate --observations test_observations.csv \
  --predictions results/CL-FL-P-RAW-predictions.csv \
  --output results/CL-FL-P-RAW-metrics.csv
```

These input filenames are examples, not supplied datasets. Outputs refuse to
overwrite existing files. The fit command accepts **calibration-only** records;
it cannot establish that a caller-supplied CSV excludes test sites. The study's
site/grid grouping and clustered-temperature-zone splits remain a separate
preparation step. Reuse the same partitions for every model and temperature
treatment; do not pass the complete unsplit observation dataset to `fit`.

An optional settings JSON can override the defaults:

```json
{
  "temperature_column": "tmean_c",
  "temperature_input": "RAW",
  "seeds": [20260907, 20260908, 20260909],
  "maxiter": 300,
  "popsize": 15,
  "tol": 0.001
}
```

DEM fitting uses the already corrected temperature column with
`temperature_input` set to `DEM`. The model does not apply an elevation offset;
temperature preparation is external. Saved fits retain their input label and
column, which the prediction command reuses without fitting.

## Python interface

```python
from model import FitSettings, fit, get_model, list_models, predict
from model.artifacts import load_fit, read_csv, save_fit
from model.metrics import evaluate

observations = read_csv("calibration_observations.csv")
weather = read_csv("daily_weather.csv")
fitted = fit("FL", observations, weather, FitSettings())
save_fit(fitted, "results/FL-RAW-fit.json")
predictions = predict(
    fitted.model_name, fitted.parameters, weather,
    [("DE:dwd:example", 2000)],
    temperature_column=fitted.temperature_column,
    temperature_input=fitted.temperature_input,
)
```

- Observations accept the canonical seven columns
  `site,variety,country,lat,lon,Date,BBCH`; numerical fitting requires `site`,
  `Date` and `BBCH`. All original rows are retained, including repeated dates
  and missing cultivar labels. BBCH09 is not substituted for BBCH07.
- Daily weather requires `site`, `Date` and the explicitly selected mean
  temperature column, in **degrees Celsius**. Site identifiers must be strings.
  Dates are timezone-free calendar dates. Overlapping season windows reuse a
  unique site/date weather row; duplicate rows are not summed or averaged.
- Prediction seasons are `(site, year)` pairs, or a DataFrame/CSV with `site`
  and `season`. Every requested site-season produces four rows.
- Continuous daily coverage is required from the earliest allowed start
  through December 31 of the target year. Calibration of forcing-only models
  checks the earliest start allowed by the search bounds, not the eventual
  fitted start. Prediction checks the supplied start. Chilling models require
  September 1 of the preceding year. Missing days or temperatures are errors;
  no interpolation, silent row removal or raw/DEM fallback is performed.
- Weather for unrelated sites/seasons does not enter the calibration objective
  or the hash of the prepared calibration weather.

## Equations and timing

Linear forcing is `max(T − Tb, 0)`. The beta response is

```text
r(T) = [(Tmax − T)/(Tmax − Topt)]
       × [(T − Tmin)/(Topt − Tmin)]^[(Topt − Tmin)/(Tmax − Topt)]
```

It is zero at/outside the cardinal limits and one at the optimum. The same
normalized response is used for beta chilling. Triangular chilling is

```text
Rc(T) = 0                                T ≤ Tmin or T ≥ Tmax
        (T − Tmin)/(Topt − Tmin)          Tmin < T ≤ Topt
        (Tmax − T)/(Tmax − Topt)          Topt < T < Tmax
```

Sequential forcing begins on the day after cumulative chilling first reaches
`chilling_requirement`. Parallel models use chilling accumulated **before**
the current day:

```text
K = minimum_response + (1 − minimum_response) × min(Cbefore / Ccrit, 1)
effective budburst forcing = K × forcing_response(T)
```

The parallel model can reach budburst before full chilling. `Ccrit` marks full
forcing competence, not an additional budburst gate. Chilling no longer
modifies forcing after budburst. The following stage begins on the day after
the preceding predicted stage; threshold overshoot is discarded. Thus no daily
forcing is counted toward two stages, and predicted dates are strictly ordered.
No observed stage initializes later-stage predictions, including during fitting.

Forcing-only `start_doy` is signed relative to January 1 = 1: 0 is December 31,
−1 is December 30 of the preceding year. Accumulation includes the start day.
Real calendar dates preserve leap years. Prior-year stage predictions remain
visible and contribute their actual date errors; they are not clipped to January.

## Parameters and calibration

`default_parameters(name)` supplies **illustrative, uncalibrated** values.
`default_bounds(name)` supplies the complete fitted-parameter mapping.
An optional `FitSettings.bounds` replaces that mapping in full. Equal bounds
fix a parameter explicitly and are recorded separately from boundary hits.

| Parameter | Default search range or fixed value |
| --- | --- |
| `forcing_base_{stage}` (linear only) | 0–15 °C |
| `forcing_optimum_{stage}` (beta only) | 10–39.9 °C |
| `forcing_minimum`, `forcing_maximum` (beta only) | Fixed: 0, 40 °C |
| `forcing_requirement_{stage}` (linear) | 0.001–1,000 °C·days |
| `forcing_requirement_{stage}` (beta) | 0.001–200 normalized units |
| `start_doy` (forcing only) | Integer −60 to 90 |
| `chilling_minimum` | −5–5 °C |
| `chilling_optimum` | 0–10 °C |
| `chilling_maximum` | 0–20 °C |
| `chilling_requirement` | 0.001–200 normalized units |
| `minimum_response` (parallel only) | 0–1 |

Here `{stage}` is `07`, `65`, `81` or `89`. Cardinal temperatures are separated
by at least 0.1 °C. `FitSettings.fixed_parameters` can explicitly override beta
forcing minimum/maximum; these are structural inputs rather than optimizer
parameters. Changes to fixed cardinals or search bounds must be prespecified
or evaluated entirely within calibration folds, never chosen from test errors.
The default 40 °C upper limit is not a data-selected optimum.

The objective is the mean of four stage-specific RMSEs. Each stage first
averages squared errors within each site, then across sites with equal site
weights, and takes the square root. Sites need not have all stages. All four
stages must occur somewhere in the calibration dataset; absent entire stages
would leave their parameters unidentified. Multiple accepted observations remain
separate contributions within a site and stage.

Unattained observed events contribute a 1,000-day error **only to the numerical
fitting loss**, never a fabricated date. This penalty exceeds finite errors
within the supported seasonal window. Differential evolution uses three seeds
(`20260907`, `20260908`, `20260909`), population multiplier 15, up to 300
generations per restart, tolerance 0.001, one worker and no gradient polishing.
Start DOY is an integer optimization variable. All four stages and their
response parameters are fitted jointly. A best result with no finite prediction
for any one stage is rejected.

## Outputs and interpretation

Predictions contain `site,season,BBCH,model_name,temperature_input,predicted_date,
predicted_doy,status,chilling_attained,outside_target_year`.
`predicted_doy` is signed relative to the target year's January 1 = 1, not the
calendar DOY of a preceding-year prediction. `chilling_attained` describes
chilling at budburst, or at the simulation horizon if budburst is unattained;
it is absent for forcing-only models.

Statuses distinguish `attained`, `unmet_chilling` (sequential models only),
`unmet_forcing` and `previous_stage_unattained`. Missing predictions remain
missing dates. Unmet chilling on the last available day is distinguished from
fulfilled chilling with no remaining day for forcing.

Saved JSON includes schema/definition versions, parameters, bounds, fixed
settings, seeds, convergence messages, evaluation counts, boundary hits,
attainment counts, dependency versions and SHA-256 hashes of normalized
calibration observations and prepared weather. A nonconverged fit can be saved
for inspection but is never labelled converged; synthetic success does not
establish a global optimum or scientific validity.

Evaluation reports event-weighted and site-balanced MAE, RMSE and bias
(predicted minus observed), alongside observation/site counts and attainment
rates. Date metrics are conditional on attained events; sites with no finite
predictions do not contribute to those metrics and are visible in coverage
counts. Comparisons must consider both accuracy and coverage. The fitting-only
1,000-day penalty is not reported as predictive accuracy.

## Scientific provenance and limits

- [Fila et al. (2014)](https://doi.org/10.1016/j.agrformet.2014.05.011), Eq. 1
  and Sections 2.1–2.3: beta response, sequential accumulation and starting
  search ranges. These ten component combinations are not the paper's nine
  parameter-sharing variants. BBCH07 replaces its BBCH09 target, and BBCH89 is
  an added operational maturity/harvest endpoint.
- [de Wergifosse et al. (2020)](https://doi.org/10.5194/gmd-13-1459-2020), Eq. 1:
  triangular chilling, following Hänninen. Application to grapevine and the
  adopted cardinal search ranges require calibration and independent testing.
- [Liu et al. (2018)](https://doi.org/10.1111/gcb.13954), Eq. 7:
  parallel competence, adapted to the selected forcing/chilling functions.
  [Chuine (2000)](https://doi.org/10.1006/jtbi.2000.2178) supplies the broader
  interaction concepts; this implementation is not an exact UniChill replica.
- The 0.1 °C separation, positive threshold floors, four-stage extension,
  beginning-of-day parallel convention, next-day stage restarts, fixed 40 °C
  forcing maximum, joint site-balanced loss and optimizer are explicit design
  choices. Calibration bounds are not universal physiological limits.

The implementation is verified with synthetic inputs and regression tests.
The documented daily weather products are absent from this checkout, so no
full European-data fit or predictive-performance result is supplied. Model
validation, RAW/DEM terrain comparisons and later residual ML remain separate
analyses. Existing data, figures, legacy model code and historical outputs are
not migrated or renamed by this package.
