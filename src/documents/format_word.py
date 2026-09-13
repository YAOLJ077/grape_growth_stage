"""Apply publication formatting without changing text or Zotero field payloads."""
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt
from docx.text.paragraph import Paragraph

from paths import ROOT, PAPER, DELIVERY, CITATIONS, compiled, build_directory
BUILD = build_directory('formatting')
TITLE = 'Beyond thermal accumulation: improving cross-regional grapevine phenology prediction with terrain-aware forcing and residual learning'


def format_document(path, has_front_matter=True):
    path = Path(path)
    document = Document(path)
    body = document._element.body
    paragraphs = document.paragraphs
    start = next(i for i, p in enumerate(paragraphs) if p.text == TITLE) if has_front_matter else 0
    first = paragraphs[start]

    # A section boundary excludes the submission front matter from line numbers.
    if has_front_matter and len(document.sections) == 1:
        previous = paragraphs[start - 1]
        previous._p.get_or_add_pPr().append(deepcopy(document.sections[0]._sectPr))
    if has_front_matter:
        first.paragraph_format.page_break_before = False
    for index, section in enumerate(document.sections):
        properties = section._sectPr
        for node in properties.findall(qn('w:lnNumType')):
            properties.remove(node)
        if has_front_matter and index == 0:
            continue
        numbering = OxmlElement('w:lnNumType')
        # Word stores the starting number as a zero-based value.
        for key, value in {'countBy': '1', 'start': '0', 'restart': 'continuous', 'distance': '240'}.items():
            numbering.set(qn('w:' + key), value)
        # Insert in the section-property schema order, before page numbering/columns.
        successors = {qn('w:' + n) for n in ('pgNumType', 'cols', 'formProt', 'vAlign', 'noEndnote', 'titlePg', 'textDirection', 'bidi', 'rtlGutter', 'docGrid', 'printerSettings', 'sectPrChange')}
        position = next((i for i, node in enumerate(properties) if node.tag in successors), len(properties))
        properties.insert(position, numbering)
    if 'Line Number' not in document.styles:
        document.styles.add_style('Line Number', WD_STYLE_TYPE.CHARACTER)
    document.styles['Line Number'].font.name = 'Times New Roman'
    document.styles['Line Number'].font.size = Pt(8)

    # Double space text, captions, references and table cells. Inline figures
    # retain single image-line height so Word does not double their physical height.
    active = not has_front_matter
    text_paragraphs = equations = 0
    for block in body:
        if block is first._p:
            active = True
        if not active:
            continue
        nodes = [block] if block.tag == qn('w:p') else list(block.iter(qn('w:p')))
        for node in nodes:
            paragraph = Paragraph(node, document)
            paragraph.paragraph_format.line_spacing = 2.0
            paragraph.paragraph_format.widow_control = True
            for suppress in node.xpath('./w:pPr/w:suppressLineNumbers'):
                suppress.getparent().remove(suppress)
            text_paragraphs += 1
            if node.xpath('.//w:drawing'):
                paragraph.paragraph_format.line_spacing = 1.0
                paragraph.paragraph_format.keep_with_next = True
                suppress = OxmlElement('w:suppressLineNumbers')
                node.get_or_add_pPr().append(suppress)
            if paragraph.style.name.endswith('Caption'):
                paragraph.paragraph_format.keep_together = False
            math = node.find(qn('m:oMathPara'))
            if math is not None:
                equations += 1
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                paragraph.paragraph_format.left_indent = Mm(0)
                paragraph.paragraph_format.right_indent = Mm(0)
                paragraph.paragraph_format.first_line_indent = Mm(0)
                paragraph.paragraph_format.tab_stops.clear_all()
                paragraph.paragraph_format.tab_stops.add_tab_stop(Mm(80), WD_TAB_ALIGNMENT.CENTER)
                paragraph.paragraph_format.tab_stops.add_tab_stop(Mm(160), WD_TAB_ALIGNMENT.RIGHT)
                before_math = list(node)[:node.index(math)]
                # Idempotent: create just one leading centre tab.
                for child in before_math:
                    if child.tag == qn('w:r') and child.find(qn('w:tab')) is not None and not child.findall(qn('w:t')):
                        node.remove(child)
                leading = OxmlElement('w:r')
                leading.append(OxmlElement('w:tab'))
                node.insert(node.index(math), leading)
                paragraph.paragraph_format.keep_together = True

    for table in document.tables:
        properties = table._tbl.tblPr
        old = properties.find(qn('w:tblBorders'))
        if old is not None:
            properties.remove(old)
        borders = OxmlElement('w:tblBorders')
        for name in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
            edge = OxmlElement('w:' + name)
            for key, value in {'val': 'single', 'sz': '4', 'space': '0', 'color': '000000'}.items():
                edge.set(qn('w:' + key), value)
            borders.append(edge)
        properties.append(borders)
        for row in table.rows:
            for cell in row.cells:
                for local in cell._tc.xpath('./w:tcPr/w:tcBorders'):
                    local.getparent().remove(local)
        margins = properties.find(qn('w:tblCellMar'))
        if margins is None:
            margins = OxmlElement('w:tblCellMar')
            properties.append(margins)
        for name in ('left', 'right'):
            side = margins.find(qn('w:' + name))
            if side is None:
                side = OxmlElement('w:' + name)
                margins.append(side)
            side.set(qn('w:w'), '60')
            side.set(qn('w:type'), 'dxa')
    document.save(path)
    return {'document': str(path.relative_to(ROOT)), 'formatted_content_paragraphs': text_paragraphs, 'equations_centred': equations, 'bordered_tables': len(document.tables), 'numbered_sections': len(document.sections) - int(has_front_matter), 'front_matter_unnumbered': has_front_matter, 'output_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='*')
    args = parser.parse_args()
    paths = [Path(p) for p in args.files] or [DELIVERY / (name + '.docx') for name in ('manuscript', 'supplementary', 'submission_complete')]
    reports = [format_document(p.resolve(), p.stem != 'supplementary') for p in paths]
    (BUILD / 'formatting.json').write_text(json.dumps(reports, indent=2) + '\n')
    print(json.dumps(reports, indent=2))
