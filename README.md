# Grapevine phenology: final reproducible study

Process models, DEM temperature correction and TabM residual learning for European grapevine stages BBCH07, 65, 81 and 89. The final analysis contains **74,618 observations, 3,169 reported sites and 1,791 independent groups**. Calibration uses 59,472 observations; held-out testing uses 15,146. The final manuscript and submission documents are in [`paper/`](paper/README.md).

## Repository layout

| Stage | Entry point | Inputs and outputs |
| --- | --- | --- |
| Data preparation | [`src/data_preparation/`](src/data_preparation/README.md) | Source records, screening, weather eligibility and frozen partitions |
| Model calibration | [`src/calibration/`](src/calibration/README.md) | Pooled initialization, constrained process calibration and nested TabM training |
| Model validation | [`src/validation/`](src/validation/README.md) | Saved source/artifact hashes, prediction dates, attainment and metrics |
| Visualization | [`src/visualization/`](src/visualization/README.md) | All 10 main and 5 supplementary figures; numerical checks from locked predictions |
| Manuscript and Word | [`src/documents/`](src/documents/README.md) | PDFs, Zotero-field DOCX, cover letter, highlights and graphical abstract |
| Numerical engines | `model/`, `model_run/factorial/`, `model_run/src/` | Original model code and calibration engines with frozen source fingerprints |
| Source data | [`data/`](data/README.md) | Canonical observations, weather, terrain, climate and figure inputs |
| Frozen model results | [`model_run/results/`](model_run/README.md) | Fitted parameters, folds, checkpoints, raw/scoring predictions and completion markers |
| Publication artifacts | `fig/paper_figures/`, `fig/graphical_abstract/`, `paper/` | Final figures, manuscripts and submission files |

The small numerical engines retain their physical paths and original bytes because the completed runs fingerprint them. Classified entry points call those engines. Dated result directory names identify frozen scientific inputs; they are dependencies of the final run. Superseded pilots, old model-comparison assemblies, partial-run snapshots, drafting archives and duplicate historical figure exports are excluded.

## Setup

Install **Git LFS** before retrieving the large data and model objects:

```sh
git lfs install
git lfs pull
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The recorded environment uses Python 3.12.14. Statistical verification and training use Python; publication rendering also requires macOS, Swift/Xcode command-line tools, Helvetica and Tectonic. Put `tectonic` on PATH or at `.venv/bin/tectonic`. Pinned Python dependencies are retained with each component. Earth Engine authentication is needed only for renewed acquisition, not replay of the included snapshots. Provider-specific data licences remain applicable; see [`data/README.md`](data/README.md).

## Verify and reproduce the published results

Run from the repository root:

```sh
.venv/bin/python src/data_preparation/reproduce.py --verify
.venv/bin/python src/validation/verify.py
NUMBA_NUM_THREADS=1 .venv/bin/python -m pytest -q
.venv/bin/python src/visualization/reproduce.py --build-documents
.venv/bin/python src/documents/build.py --word-only
```

The visualization command recomputes the plotted statistics and 2,000 original-group bootstrap draws from locked predictions, verifies the saved values, redraws all 15 figures and compiles both PDFs. On macOS, `src/visualization/reproduce.command` provides the same figure/PDF workflow. The document command produces `paper/manuscript.docx`, `paper/supplementary.docx` and `paper/submission_complete.docx`. Temporary files go under ignored `build/`.

The combined Word file places the cover letter, highlights and graphical abstract before the manuscript title, with supplementary material after the manuscript. Body text is double spaced, manuscript line numbers are continuous, tables have borders, and equations are centered. Citations carry embedded Zotero field data; they are not linked to an installed personal Zotero library.

## Recalibrate from the frozen data

```sh
.venv/bin/python src/calibration/run.py --help
.venv/bin/python src/calibration/run.py --output build/recalibration --threads 7
```

The calibration guide distinguishes upstream initialization, process fitting and hybrid fitting. New runs use new output directories; frozen results must not be overwritten. Full optimization and neural fitting are substantial computations. Recalibration has recorded seeds and settings, but timestamps and hardware-dependent stochastic training can prevent byte-identical new model files. The saved artifacts support exact validation without refitting.

The final screening can also be rebuilt from the four included canonical source tables; commands are in the data-preparation guide. These tables already contain provider-level assembly. Prepared terrain donors and map backgrounds are retained; rebuilding all original terrain rasters requires renewed acquisition. Fig. 2 uses the separately documented earlier 3,171-site phenology-only snapshot. Historical screening sensitivity in supplementary Table S4 is retained as a documented comparison, with its available population evidence; it is not the final modelling population.

Main results report MAE and signed bias. All uncertainty and correction contrasts preserve paired finite errors, equal site/stage weights and original independence groups. Raw developmental attainment remains separate from the administrative 4 November scoring assignment for BBCH81/89. Terrain associations do not establish causal effects, and weather features ending at predicted dates support retrospective evaluation.
