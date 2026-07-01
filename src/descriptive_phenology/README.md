# Descriptive Phenology Figures

This module creates a small set of overview figures from the complete processed
France and Germany grape phenology tables.

Run:

```bash
python src/descriptive_phenology/plot_descriptive_phenology.py
python src/descriptive_phenology/plot_phenology_data_coverage.py
python src/descriptive_phenology/plot_site_topography_overlay.py
```

Default outputs:

- Figures: `fig/descriptive_phenology/`
- Derived summaries: `data/phenology_grape/derived/descriptive_phenology/`
- Processed topography cache: `data/topography/processed/`

The script intentionally produces a few combined figures instead of many
single-purpose plots.
