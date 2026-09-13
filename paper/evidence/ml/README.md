# ML gains and hybrid DEM comparison

Reproduce figures with `.venv/bin/python src/visualization/reproduce.py` from the
repository root. This package supplies Figures 9 and 10 and Results 3.5–3.6.

- `model_effects.csv`: each model on the common finite-scoring cohort.
- `zone_effects.csv`: fixed-model averages overall and across EZs, including
  pointwise 95% original-group bootstrap intervals and support.
- `site_stage_effects.csv`: per-site stage means for equal-site summaries.
- `support.csv`: eligibility, finite support and improved/worsened/unchanged sites.
- `cohort_membership.csv`: full test identities and both inclusion flags.
- `claim_evidence.csv`: exact selectors and values for manuscript claims.
- `analysis.json`: source/output hashes, comparisons, bootstrap and weighting.

Prediction exports contain empty group-ID placeholders. Groups are restored by
a validated many-to-one join to the original, hash-verified publication cohort,
matching the final-analysis procedure. Missing group IDs stop analysis. No
model, observation or original analysis artifact is modified.
