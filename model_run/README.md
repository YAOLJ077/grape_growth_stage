# Frozen calibration and validation artifacts

The active entry points are [`src/calibration/`](../src/calibration/README.md) and [`src/validation/`](../src/validation/README.md). `src/` and `factorial/` here contain byte-preserved numerical engines required by source fingerprints in the completed runs.

| Results directory | Role in final reproduction |
| --- | --- |
| `publication_cohort_20260910` | Original weather eligibility, sites and daily RAW/DEM forcing |
| `publication_design_20260910` | Frozen RAW environmental zones and independent site groups |
| `publication_factorial_20260911_v3` | Frozen primary protocol and full-process initialization fits; obsolete model-comparison assemblies removed |
| `cleaned_reevaluation_20260912` | Final seven-column observations and record-level membership/eligibility evidence |
| `pooled_calibration_20260912` | Final observation partitions and source threshold calibration used to initialize the process run |
| `median_cutoff_calibration_20260912` | Twenty completed process-model × temperature fits, locks, raw/scoring predictions and metrics |
| `median_cutoff_ml_20260912` | Twenty completed hybrid configurations, 200 ordinary/nested process refits and 1,200 TabM checkpoints |

There are 240 final and 960 tuning checkpoints. Recursively hashed completion markers also cover features and fold-level artifacts; these are required verification inputs. All large data and weights are tracked through Git LFS. Final publication figures are in `fig/paper_figures/`; their classified renderer recomputes statistics from the compact prediction bundle.

Saved manifests retain their original absolute paths and hashes as historical evidence. The new validator maps original repository-relative suffixes to the current checkout and verifies the original bytes. Fresh calibration must use a new output directory; the old direct runners' resume checks expect their original physical root. Their saved configurations must not be silently rewritten. The historical cleaned-versus-original model-performance comparison is outside the final study and its former assembly artifacts are excluded.

[MEDIAN_CUTOFF.md](MEDIAN_CUTOFF.md) describes constrained early-stage fitting, equal-site weighted median maturity and the 4 November scoring convention. [CUTOFF_ML.md](CUTOFF_ML.md) describes the four ordinary and six pair-excluded process refits, fold-local preprocessing and three-seed TabM learners. Raw attainment, hybrid date availability and cutoff assignments remain distinct.
