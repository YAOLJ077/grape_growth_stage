# Data for manuscript and supplementary figures

This bundle supplies the inputs for all 10 manuscript figures and all 5
supplementary figures. `manifest.json` records the original source and SHA-256
of every frozen input; `catalogue.json` links the published figure numbers,
LaTeX labels and historical source exports.

## One-click reproduction

Double-click [`reproduce.command`](../../src/visualization/reproduce.command)
on macOS, or run from the repository root:

```sh
src/visualization/reproduce.command
```

The command recomputes the plotted scoring-error summaries from the locked
prediction errors, verifies them against the saved results, redraws all 15
figures, exports 7.8-inch-wide PDF and PNG files to `fig/paper_figures/`, and
rebuilds `paper/manuscript.pdf` and `paper/supplementary.pdf`. Newly recomputed
numerical tables are written to `reproduced/`; they are outputs, not frozen
inputs. A missing or altered input stops the run.

## Data contents

| Directory | Contents and use |
| --- | --- |
| `predictions/` | 74,618 observation identities and a 74,618 × 10 × 4 scoring-error array: ten process structures, with RAW process, RAW hybrid, DEM process and DEM hybrid arms. Source hashes and date-to-error checks are in `provenance.json`. |
| `observations/` | The final 59,472 calibration and 15,146 test observations, used to verify population counts and recompute stage availability. |
| `environment/` | Frozen site coordinates, environmental-zone and independence-group assignments, monthly cluster centres and partition counts. |
| `study_area/` | Historical phenology-only site inventory, cartographic geometry payload, two georeferenced-background previews and terrain provenance for Fig. 2. Its 3,171 sites are distinct from the final 3,169-site modelling cohort. |
| `responses/` | Fixed temperature-response curves, cardinal temperatures and documented source equations for Fig. 3. |
| `common/` | Natural Earth country boundaries via geo-countries. |
| `pbm/` | Verified process-model metric tables and plotted values for Fig. 5 and Fig. S1. |
| `structure/` | The 21 structural pairs, fixed-pair summaries, site errors and zone summaries for Figs. 6–7. |
| `dem/` | Paired DEM summaries, site terrain, calibration-defined classes and source evidence for Fig. 8 and Figs. S3–S4. |
| `ml/` | Paired RAW ML and hybrid DEM summaries, shared cohort membership and support for Figs. 9–10. |
| `hybrid/` | Sealed hybrid metric tables supporting supplementary Fig. S5. |
| `ml_baseline_link/` | Supporting numerical evidence for baseline dependence and the paired change in DEM benefit after ML. |
| `workflow/` | Study specification supporting Fig. 1. |

`reference_figure_text.json` contains text extracted from the preceding figure
exports. It is an independent content check, not artwork used in rendering.
Figures are drawn from the numerical and geographic inputs, not copied from
existing PDFs. Codes are under `src/visualization/`.

## Statistical scope

The reproduction starts from **locked scoring predictions**, not raw weather
and model retraining. The packing code verified every original prediction-file
hash and recalculated errors from observed and scoring dates. The error array
retains missing scores and the existing 4 November BBCH81/89 scoring convention.
Original raw attainment is documented in the archived model runs; it is not
inferred from the scoring-error array.

The pipeline recomputes process and hybrid MAE/RMSE/bias, controlled structural
contrasts, site and environmental-zone summaries, paired process DEM effects,
RAW ML gains and paired DEM effects within hybrids. It repeats 2,000 original-
group bootstrap draws with seed 20260913, equal-site and equal-stage weighting,
fixed constituent models, the original finite masks, and sparse-group rules.
Calibration terrain tertiles and site-improvement counts are verified. Recomputed
values and interval endpoints must match the saved results within 1e-9.

The map background is a frozen display-only raster input generated from
Copernicus GLO-30; vector sites, boundaries, labels and legends are redrawn.
Raw DEM acquisition, phenology screening, weather downloading, model fitting
and climate zoning are upstream procedures, not rerun by this figure command.
Original data licences and source attribution remain applicable; see
`study_area/SOURCES.md` and the repository's phenology and weather provenance.
