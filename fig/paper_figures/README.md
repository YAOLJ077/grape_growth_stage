# Current manuscript figures

This folder contains the single current set: graphical abstract, Figures 1–10
and Figures S1–S5. PDF, PNG, SVG and TIFF files are export formats of the same
figure, not historical versions.

[All figures — combined 16-page PDF](All_figures.pdf)

[Graphical abstract](graphical_abstract.md): [PDF](graphical_abstract.pdf),
[PNG](graphical_abstract.png), [SVG](graphical_abstract.svg),
[TIFF](graphical_abstract.tiff).

Figure 1 uses Times New Roman throughout and a centered top heading. The
graphical abstract also uses Times New Roman and has no bottom explanatory
text. Figure 2 includes a north arrow aligned with the map projection.

| Figure | Content | PDF | PNG |
| --- | --- | --- | --- |
| 1 | Overall workflow | [Fig_01.pdf](Fig_01.pdf) | [Fig_01.png](Fig_01.png) |
| 2 | Study area | [Fig_02.pdf](Fig_02.pdf) | [Fig_02.png](Fig_02.png) |
| 3 | Temperature-response functions | [Fig_03.pdf](Fig_03.pdf) | [Fig_03.png](Fig_03.png) |
| 4 | Environmental zones and calibration/test split | [Fig_04.pdf](Fig_04.pdf) | [Fig_04.png](Fig_04.png) |
| 5 | Process-model MAE | [Fig_05.pdf](Fig_05.pdf) | [Fig_05.png](Fig_05.png) |
| 6 | Process-structure contrasts | [Fig_06.pdf](Fig_06.pdf) | [Fig_06.png](Fig_06.png) |
| 7 | CB-FL-S site errors across zones | [Fig_07.pdf](Fig_07.pdf) | [Fig_07.png](Fig_07.png) |
| 8 | DEM benefits for process models | [Fig_08.pdf](Fig_08.pdf) | [Fig_08.png](Fig_08.png) |
| 9 | ML gains and hybrid accuracy | [Fig_09.pdf](Fig_09.pdf) | [Fig_09.png](Fig_09.png) |
| 10 | DEM effects within hybrids | [Fig_10.pdf](Fig_10.pdf) | [Fig_10.png](Fig_10.png) |
| S1 | Process-model signed bias | [Fig_S01.pdf](Fig_S01.pdf) | [Fig_S01.png](Fig_S01.png) |
| S2 | Stage-specific test observation availability | [Fig_S02.pdf](Fig_S02.pdf) | [Fig_S02.png](Fig_S02.png) |
| S3 | Stage-specific DEM terrain effects | [Fig_S03.pdf](Fig_S03.pdf) | [Fig_S03.png](Fig_S03.png) |
| S4 | DEM effects on bias and RMSE | [Fig_S04.pdf](Fig_S04.pdf) | [Fig_S04.png](Fig_S04.png) |
| S5 | Hybrid signed bias | [Fig_S05.pdf](Fig_S05.pdf) | [Fig_S05.png](Fig_S05.png) |


Figure 1 is 10 × 8.8 inches; its editable [SVG](Fig_01.svg) is retained.
The graphical abstract is landscape, 1328 × 531 pixels. Other figures are 7.8 inches wide.
PNG exports use 300 dpi. PDFs retain vector artwork and searchable text.

## Update and reproduce

- `src/documents/plot_revision_workflow.py`: current Figure 1.
- `src/documents/plot_graphical_abstract.py`: current graphical abstract.
- `src/visualization/reproduce.py`: numbered figures and graphical abstract,
  with statistical checks against the frozen data inputs.
- `src/visualization/merge_figures.py --update-manuscript`: combined PDF and
  synchronization of Figures 1–10 in `paper/grape_pheno_manuscript_ylj.docx`.

[Figure manifest](figure_manifest.json) records current assets and PDF order.
[Verification](verification.json) records the latest reproduction checks.
