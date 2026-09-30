# Reproduce all paper figures

Double-click **`reproduce.command`** in Finder. It runs the complete local
workflow and rebuilds both documents. The equivalent shell command is:

```sh
src/visualization/reproduce.command
```

To regenerate statistics and figures without compiling the documents:

```sh
.venv/bin/python src/visualization/reproduce.py
```

Inputs are in [`data/paper_figures/`](../../data/paper_figures/README.md).
Outputs are in [`fig/paper_figures/`](../../fig/paper_figures/README.md), named
`Fig_01`–`Fig_10`, `Fig_S01`–`Fig_S05`, and `graphical_abstract`.
Figure 1 is 10 inches wide, the graphical abstract is 8 inches wide, and the
remaining figures are 7.8 inches wide. PNG previews use 300 dpi.
`All_figures.pdf` combines the 16 current PDFs with bookmarks.
Figure 1 and the graphical abstract use Times New Roman.

To synchronize the latest numbered figures in the edited Word manuscript:

```sh
.venv/bin/python src/visualization/merge_figures.py --update-manuscript
```

## Requirements

- macOS with Swift and AppKit/PDFKit (Xcode command-line tools).
- The repository `.venv`, with the versions in `requirements.txt`.
- Tectonic for document compilation; the launcher uses `.venv/bin/tectonic`.

If a new Python environment is needed:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r src/visualization/requirements.txt
```

The run is offline once these dependencies are available. No reference to
historical `model_run/` or `paper/*_20260913/` analysis files is needed for
ordinary reproduction. `pack_predictions.py` is the separate, one-time
packaging tool for the original locked predictions; it is not called by the
launcher.

## Code and checks

- `recompute_results.py` rebuilds the reported scoring-error statistics from
  the bundled prediction cube; `group_bootstrap.py` retains the original
  paired-group uncertainty calculation.
- `render_*.py` contains the existing plot designs adapted to bundled inputs.
  Each renderer receives an explicit temporary output directory.
- `src/documents/plot_revision_workflow.py` draws the current workflow.
  `draw_map.swift` includes the projected north arrow;
  `draw_temperature_responses.swift` draws the temperature response curves.
- `reproduce.py` validates input hashes, recomputes statistics, compares numerical
  labels, redraws figures and checks all 15 exports before replacing them.
  Pypdf performs proportional scaling without losing embedded Unicode mappings;
  `export_figures.swift` renders the PNG previews.
- `audit_pdf.swift` verifies actual PDF dimensions and editable fonts. Every PNG
  is also compared against an independent PDFKit rendering to detect clipping
  or incorrect scaling. Changes
  in PDF extraction order are handled by comparing complete non-whitespace
  character counts; numerical values are separately checked by keyed tables.
- With document compilation enabled, every `includegraphics` path and compiled
  figure number must match the catalogue. Unresolved references/citations,
  overfull boxes and oversized floats fail verification.

`fig/paper_figures/verification.json` records numerical checks, dimensions,
input/code/output hashes, runtime versions, elapsed time and document checks.
`data/paper_figures/reproduced/` retains the recalculated numerical tables.

The numbered 7.8-inch bundle is the active publication output. Frozen input
metadata retain historical source identities; duplicate older exports are excluded.
After intentional changes to the underlying analysis, update the input data,
source manifest and reference results together; the checks do not silently
accept modified published numbers.
