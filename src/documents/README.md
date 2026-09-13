# Final document reproduction

All commands run from the repository root. Python 3.12 and the exact conversion
packages used for the verified Word build are recorded in
[requirements.txt](requirements.txt). Tectonic compiles LaTeX. The current sources
use the macOS Times New Roman, STIX Two Math and Menlo fonts; the graphical abstract
uses Arial. Graphical-abstract regeneration additionally requires the project's
NumPy and Matplotlib environment.

```sh
python3 -m venv .venv-documents
.venv-documents/bin/python -m pip install -r src/documents/requirements.txt
.venv-documents/bin/python src/documents/build.py
```

`build.py` compiles the manuscript, supplement and cover-letter PDFs, generates the
cover-letter and highlights DOCXs, converts the main and supplementary documents
with editable equations and tables, embeds citation fields, assembles the complete
submission, and verifies the final files. It uses current LaTeX auxiliary files
for reference numbers and bibliography labels. The final scientific text is not
rewritten by the conversion.

To rebuild into a review directory while retaining the delivered files:

```sh
.venv-documents/bin/python src/documents/build.py --output-dir build/documents/reproduced
```

`--pdf-only` compiles PDFs; `--word-only` uses the current compiler cache;
`--verify-only` inspects existing Word files against current LaTeX labels. Cache
location is configurable with `--build-dir` and defaults to `build/documents/`.
Build caches are disposable and must not be committed. The command also exports
the cited CSL JSON and BibTeX records into `build/documents/citations/`.

| Module | Purpose |
| --- | --- |
| `build.py`, `paths.py` | One entry point and shared source/output/cache paths |
| `build_manuscript.py`, `build_supplementary.py` | LaTeX-to-Word conversion with current figure and table numbering |
| `build_complete.py` | Append supplement with a shared bibliography |
| `build_front_matter.py` | Cover letter and highlights from their Markdown sources |
| `citation_fields.py` | Self-contained editable Zotero fields using canonical BibTeX records |
| `format_word.py` | Double spacing, continuous line-number settings, table borders, equation alignment |
| `verify_citations.py` | Cited-key equality, all supplementary callouts, field completeness and identities |
| `verify_documents.py` | OOXML integrity, content fingerprints, fields, figures, editable tables and equations |
| `plot_graphical_abstract.py` | Final conceptual vector drawing and raster exports |

The verification reads document structure independently of obsolete revisions or
saved previews. It does not perform a new native Microsoft Word render or live
Zotero refresh. Word pagination and rendered line-number placement therefore
remain application-dependent. ZIP timestamps and generated package metadata can
change without changing scientific text, mathematics, citations or figures.

The complete DOCX contains 12 tables, 19 display equations, 16 figures including the
graphical abstract, 77 citation fields and one bibliography with 42 references.
Semantic fingerprints preserve the delivered main and supplementary document
content. Changing approved scientific content requires an intentional update of
those fingerprints after independent review.

```sh
.venv/bin/python src/documents/plot_graphical_abstract.py
```

PDF verification checks scientific text and page counts. Paragraph page breaks
and vertical placements may reflow during recompilation; binary PDF identity is
not required. [Final verification](../../paper/evidence/documents/final_verification.json)
records the current canonical PDF hashes and document checks.
