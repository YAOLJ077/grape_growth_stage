#!/usr/bin/env python3
"""Build editable AFM submission documents and cover-letter LaTeX from Markdown.

Requires python-docx. Compile the generated cover_letter.tex with Tectonic.
"""
from pathlib import Path
from docx import Document
from docx.shared import Mm, Pt

from paths import PAPER, DELIVERY, build_directory
SOURCE = PAPER / "afm_submission"
OUT = DELIVERY / "afm_submission"
OUT.mkdir(parents=True, exist_ok=True)


def document():
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.top_margin = section.bottom_margin = Mm(22)
    section.left_margin = section.right_margin = Mm(22)
    style = doc.styles["Normal"]
    style.font.name, style.font.size = "Times New Roman", Pt(11)
    style.paragraph_format.space_after = Pt(7)
    style.paragraph_format.line_spacing = 1.05
    return doc


def escape_tex(text):
    table = {"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#", "$": r"\$"}
    return "".join(table.get(c, c) for c in text)


def main():
    cover = (SOURCE / "cover_letter.md").read_text().strip().split("\n\n")
    doc = document()
    for block in cover:
        doc.add_paragraph(block)
    doc.save(OUT / "cover_letter.docx")
    preamble = r"""\documentclass[a4paper,11pt]{article}
\usepackage{fontspec}
\setmainfont{Times New Roman}
\usepackage[margin=22mm]{geometry}
\usepackage{setspace}
\setstretch{1.05}
\setlength{\parindent}{0pt}
\setlength{\parskip}{7pt}
\pagestyle{empty}
\begin{document}
"""
    body = "\n\n".join(escape_tex(block).replace("\n", "\\\\\n") for block in cover)
    (build_directory("front_matter") / "cover_letter.tex").write_text(preamble + body + "\n\\end{document}\n")
    highlights = [(s[2:]) for s in (SOURCE / "highlights.md").read_text().splitlines() if s.startswith("- ")]
    assert 3 <= len(highlights) <= 5
    assert all(len(s) <= 85 for s in highlights), [(len(s), s) for s in highlights]
    doc = document()
    doc.add_heading("Highlights", level=1)
    for text in highlights:
        doc.add_paragraph(text, style="List Bullet")
    doc.save(OUT / "highlights.docx")
    print({"cover_letter_paragraphs": len(cover), "highlight_characters": [len(s) for s in highlights]})


if __name__ == "__main__":
    main()
