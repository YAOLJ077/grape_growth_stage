# Phenology processing and figure sources

This directory contains the active phenology data-processing, verification and
figure-generation code. Data products remain under `data/phenology/`; rendered
figures and their companion metadata remain under `fig/`.

## Processing sequence

Run from the repository root:

```sh
python3 src/phenology/fetch_phenology_inputs.py
python3 src/phenology/organize_phenology.py
python3 src/phenology/select_modeling_targets.py
python3 src/phenology/plot_study_area.py
python3 src/phenology/plot_stage_counts.py
swift -module-cache-path /tmp/grape-workflow-swift-cache src/phenology/draw_workflow.swift
python3 src/phenology/verify_data.py
```

The fetch step is unnecessary when the required canonical inputs are already
available and checksum-verified. `organize_phenology.py` rebuilds the cleaned
seven-column inventory and QC sidecars. `select_modeling_targets.py` writes the
single BBCH07/65/81/89 target file and its quality metadata. The two plotting
drivers rebuild the study-area and stage-count figures from that combined target
file. `draw_workflow.swift` rebuilds the workflow PDF and PNG.

`verify_data.py` checks source reconciliation, schema and field validity,
chronology-v2 support, quarantine recovery, exact four-stage target selection,
figure metadata and the unit/integration test suite. The canonical scientific
and processing requirements are in `AGENTS.md`.

`phenology_qc.py` supplies the shared chronology rules. `draw_map.swift` and
`draw_plot.swift` are rendering backends called by the Python figure drivers.
The `test_*.py` files contain the processing, selector and figure regression
tests.

Superseded split target exports, the standalone methods note and the verification
notebook are archived under
`data/phenology/archive/pre_combined_targets_20260906/`.

## Manuscript build

From `paper/`, with Tectonic 0.17.0 and its cached TeX bundle:

```sh
tectonic --only-cached --keep-logs --keep-intermediates manuscript.tex
```

The verified local executable is `/private/tmp/grape_tectonic_0_17_0/tectonic`.
That temporary installation is environment-specific; an installed `tectonic`
executable can replace it. The manuscript uses Times New Roman, Menlo and STIX
Two Math fonts available on this macOS system. Figure generation uses Python's
standard library and macOS Swift with AppKit/PDFKit.
