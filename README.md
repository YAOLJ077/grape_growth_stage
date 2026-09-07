# Grape Growth Stage

This repository supports a regional grapevine phenology prediction study using
French TEMPO and German DWD phenological observations, ERA5-Land daily weather
data, Copernicus DEM terrain information, process-based phenology models, and
machine-learning residual correction.

The current main analysis focuses on four major BBCH phenological stages:
BBCH07 (budburst), BBCH65 (flowering), BBCH81 (veraison), and BBCH89
(maturity or harvest). The study evaluates whether stage-specific process
models transfer across unseen spatial regions, whether terrain-adjusted
temperature forcing improves prediction, and whether machine-learning residual
correction provides spatially stable gains.

## Study Focus

The repository is organized around three linked components of the manuscript:

- Stage-specific process-model calibration and selection for the four target
  grapevine phenological stages.
- Raw versus terrain-adjusted temperature forcing, using ERA5-Land weather data
  and DEM-derived site elevation information.
- Hybrid phenology prediction, where machine-learning models learn
  spatially out-of-fold process-model residuals and are evaluated under strict
  held-out spatial validation.

The analysis is designed to separate the baseline performance of process
models, the effect of terrain-aware temperature representation, and the added
value of residual correction.

## Data Sources

The main analysis uses:

- Phenological observations from France TEMPO and Germany DWD.
- ERA5-Land daily meteorological forcing.
- Copernicus DEM GLO-30 terrain information.
- Standardized target stages mapped to the extended BBCH grapevine scale.

The repository also contains intermediate harmonization products and supporting
data-processing artifacts. These are retained for reproducibility, but the
current manuscript-level analysis is the France-Germany four-stage modelling
framework described above.

## Repository Structure

```text
data/       Phenology, terrain, weather metadata, and derived analysis tables
fig/        Workflow, spatial validation, descriptive, and manuscript figures
paper/      Manuscript source, compiled manuscript, and bibliography
reference/  Supporting literature files
model/      Ten process-only models, shared prediction/calibration code and usage documentation
results/    Model-selection outputs, validation summaries, and result tables
src/        Data preparation, modelling, validation, and plotting code
tests/      Unit tests for core data-processing and modelling components
```

Large gridded weather products and local temporary outputs are intentionally
kept outside normal Git tracking.

## Main Outputs

The main analysis produces:

- Terrain-temperature correction diagnostics and spatial maps.
- Selected stage-specific process models and process-model predictions.
- Hybrid day-of-year predictions after machine-learning residual correction.
- Spatial validation summaries across held-out outer test sets.
- Process versus hybrid-model accuracy gains.
- Mechanism-group ablation and SHAP-based residual interpretation outputs.
- Manuscript-ready figures and tables.

## Reproducibility

The current ten-model process implementation is documented in
[model/README.md](model/README.md). It supports joint four-stage calibration,
saved-parameter prediction and evaluation without ML. Its minimal environment
is defined in `model/requirements.txt`; tests run with `python -m pytest tests`.
Daily weather and independently prepared calibration/test inputs are required
for real-data runs. The older `src/modeling/` workflows below remain unchanged.

The analysis environment is defined by the Python dependency files in the
repository. The modelling and figure-generation code is organized under `src/`,
with manuscript-ready outputs stored under `fig/`, `results/`, and `paper/`.

For a fresh environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Development and validation tests can be run with:

```bash
python -m pip install -r requirements-dev.txt
pytest
```

Some geospatial dependencies may require platform-specific binary libraries.
When installation from PyPI is inconvenient, conda-forge is usually the most
practical option.

## Large Files

Selected large analysis tables are managed with Git LFS. Install Git LFS before
cloning or pulling the full repository:

```bash
git lfs install
git clone <repository-url>
```

Very large weather-processing products are not tracked in Git and can be
recreated from the documented processing workflow when needed.

## Manuscript

The manuscript source is located in `paper/manuscript.tex`, with the compiled
PDF stored as `paper/manuscript.pdf`. The manuscript describes the study
framework, data sources, candidate process models, residual-learning models,
spatial validation design, and resulting stage-specific prediction performance.
