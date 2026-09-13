# Supplementary table inputs

These seven LaTeX files are included directly by `paper/supplementary.tex`.
CSV companions preserve the source values where available.

| Table source | Content |
| --- | --- |
| `country_population` | Country-specific retained population |
| `protocol_population` | Completed primary calibration/test split |
| `parameter_bounds` | Process parameter bounds |
| `screening_population` | Historical screening-sensitivity population |
| `country_test_support` | Country-specific primary test support |
| `zone_support` | Environmental-zone and stage support |
| `dem_zone_effects` | Environmental-zone DEM effects |

Population snapshots have different filters and are not interchangeable. The
screening table is an eligibility diagnostic, not evidence of completed transfer
or model-sensitivity runs. Original derivation manifests are retained in
[`../evidence/population/`](../evidence/population/).
