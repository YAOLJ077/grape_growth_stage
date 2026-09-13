# Final manuscript and submission documents

The current journal target is **European Journal of Agronomy**. Scientific sources,
deliverables and compact supporting evidence are organized together here.

| Document | Final files |
| --- | --- |
| Main manuscript | [LaTeX](manuscript.tex), [PDF](manuscript.pdf), [Word](manuscript.docx) |
| Supplementary information | [LaTeX](supplementary.tex), [PDF](supplementary.pdf), [Word](supplementary.docx) |
| Complete submission | [Word](submission_complete.docx) |
| Cover letter and highlights | [Submission files](eja_submission/README.md) |
| Graphical abstract | [Editable vector and raster files](../fig/graphical_abstract/README.md) |
| Supplementary table inputs | [Tables](tables/README.md) |
| Scientific evidence and provenance | [Evidence](evidence/README.md) |
| Bibliography | [BibTeX](references/Phenological.bib) |

The manuscript Word file contains the cover letter, highlights, graphical abstract
and manuscript. The complete Word file appends supplementary information and uses
one shared bibliography. Supplementary sources all occur in that bibliography.
The separate supplement retains its own bibliography.

Word text, captions, references and table cells are double spaced. Manuscript line
numbering starts at 1 after the front matter and continues through the appended
supplement. Tables have outer and internal borders; equations remain editable,
with centered expressions and numbers at the right margin. Citation fields carry
self-contained CSL records and Zotero preferences. They are not linked to a local
Zotero library, and live Zotero refresh has not been tested.

[Document code and reproduction commands](../src/documents/README.md) compile PDFs,
create Word files and verify citations, editable equations, tables and formatting.
Compiler intermediates and regenerated previews belong in ignored `build/documents/`.
[Content fingerprints](evidence/documents/content_fingerprints.json) preserve
the final Word text, mathematical expressions, citation fields and image bytes.

The [15 numbered figures](../fig/paper_figures/README.md) are reproduced by
[visualization code](../src/visualization/README.md) using the
[frozen figure inputs](../data/paper_figures/README.md). The primary site holdout
supplies test evidence; calibration results are apparent performance. Scoring
dates remain distinct from developmental attainment, and terrain associations
do not identify causal effects.
