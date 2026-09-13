# European Journal of Agronomy submission files

| Document | Files |
| --- | --- |
| Manuscript | [PDF](../manuscript.pdf), [LaTeX](../manuscript.tex) |
| Combined Word document | [Editable DOCX](../manuscript.docx), containing cover letter, highlights, graphical abstract and manuscript |
| Supplementary information | [PDF](../supplementary.pdf), [LaTeX](../supplementary.tex) |
| Graphical abstract | [Vector PDF](../../fig/graphical_abstract/graphical_abstract.pdf), [300-dpi TIFF](../../fig/graphical_abstract/graphical_abstract.tiff), [PNG](../../fig/graphical_abstract/graphical_abstract.png), [SVG](../../fig/graphical_abstract/graphical_abstract.svg) |
| Cover letter | [Editable Word](cover_letter.docx), [PDF](cover_letter.pdf), [Markdown](cover_letter.md) |
| Highlights | [Editable Word](highlights.docx), [Markdown](highlights.md) |
| Verification | [Checks and hashes](verification.json), [graphical-abstract evidence](../../fig/graphical_abstract/metadata.json) |

The manuscript concerns crop development and the joint predictive value of
process structure, elevation correction and residual learning. The scope remains
historical grapevine phenology; no GCM or climate-change projection analysis is
included. Administrative scoring dates and the need for independent confirmation
after model development remain explicit.

The graphical abstract is a separate portrait vector figure with 2,160 ×
3,120-pixel raster exports at 300 dpi. Botanical illustrations, terrain,
temperature adjustment, thermal accumulation and residual learning explain the
combined prediction pipeline. The final statements summarize the common-cohort
comparison and the zone-specific flowering gains from residual learning
(10.58 days in EZ05 and 1.44 days in EZ03), with sparse coverage identified
as a limit to regional inference. The portrait orientation follows the requested design; it differs
from the publisher's general landscape guidance. The five highlights each
contain at most 85 characters. The cover letter is addressed to the journal's
editors without naming an unverified handling editor.

Journal scope and general publisher guidance, consulted 13 September 2026:

- [European Journal of Agronomy scope](https://shop.elsevier.com/journals/european-journal-of-agronomy/1161-0301)
- [Elsevier graphical abstract specifications](https://www.elsevier.com/researcher/author/tools-and-resources/graphical-abstract)
- [Elsevier highlights specifications](https://www.elsevier.support/publishing/answer/how-do-i-include-highlights-with-my-manuscript)
- [Journal Guide for Authors](https://www.sciencedirect.com/journal/european-journal-of-agronomy/publish/guide-for-authors)

The journal-specific Guide for Authors returned HTTP 403 during verification;
complete compliance with its current submission checklist is therefore not
established. The abstract is below 250 words and has six keywords. Funding,
competing interests, author contributions, all-author approval and exclusive
submission declarations require author-supplied information. The cover letter
does not assert unverified declarations. No files have been submitted.

Reproduction from the repository root:

```sh
.venv/bin/python src/documents/plot_graphical_abstract.py
.venv-documents/bin/python src/documents/build.py
```

Dependencies, the compiler cache and complete reproduction commands are documented
in [document code](../../src/documents/README.md). The manuscript uses Times New
Roman and STIX Two Math; the graphical abstract uses Arial. Build intermediates
are written beneath ignored `build/documents/`.
