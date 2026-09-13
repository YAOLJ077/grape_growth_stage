"""Append the supplement, retaining one Zotero bibliography for the whole file."""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import zipfile
import sys
from docx import Document
from docx.oxml.ns import qn
from docxcompose.composer import Composer

from paths import ROOT, PAPER, DELIVERY, CITATIONS, compiled, build_directory
BUILD = build_directory('complete')
main = Document(DELIVERY / 'manuscript.docx')
supp = Document(DELIVERY / 'supplementary.docx')
main_refs = json.loads((CITATIONS / 'manuscript_references.json').read_text())
supp_refs = json.loads((CITATIONS / 'supplementary_references.json').read_text())
assert {r['id'] for r in supp_refs} <= {r['id'] for r in main_refs}

# All supplementary sources already occur in the main bibliography. A single
# document-wide Zotero bibliography avoids two lists changing on refresh.
heading = next(i for i, p in enumerate(supp.paragraphs) if p.text == 'References')
for paragraph in supp.paragraphs[heading:]:
    paragraph._p.getparent().remove(paragraph._p)

# Distinct source styles preserve the supplement's typography.
mapping = {s.style_id: 'Supplement_' + s.style_id for s in supp.styles}
for style in supp.styles:
    old_id = style.style_id
    style.element.set(qn('w:styleId'), mapping[old_id])
    style.element.attrib.pop(qn('w:default'), None)
    name = style.element.find(qn('w:name'))
    if name is not None:
        name.set(qn('w:val'), 'Supplement ' + name.get(qn('w:val')))
for root in [supp.styles.element, supp._element]:
    for node in root.iter():
        if node.tag in {qn('w:basedOn'), qn('w:link'), qn('w:next'), qn('w:pStyle'), qn('w:rStyle'), qn('w:tblStyle')}:
            value = node.get(qn('w:val'))
            if value in mapping:
                node.set(qn('w:val'), mapping[value])
for paragraph in supp._element.xpath('.//w:p'):
    if paragraph.pPr is None or paragraph.pPr.pStyle is None:
        paragraph.get_or_add_pPr().get_or_add_pStyle().val = mapping['Normal']
supp.paragraphs[0].paragraph_format.page_break_before = True
composer = Composer(main)
composer.append(supp)
main.core_properties.subject = 'Cover letter, highlights, graphical abstract, manuscript and supplementary information'
output = DELIVERY / 'submission_complete.docx'
composer.save(output)
from format_word import format_document
format_document(output, has_front_matter=True)

final = Document(output)
assert len(final.tables) == 12
assert len(final.inline_shapes) == 16
assert len(final._element.xpath('.//m:oMathPara')) == 19
assert sum(p.text == 'References' for p in final.paragraphs) == 1
assert next(i for i, p in enumerate(final.paragraphs) if p.text == 'Supplementary information') > next(i for i, p in enumerate(final.paragraphs) if p.text == 'References')
with zipfile.ZipFile(output) as z:
    assert z.testzip() is None
    xml = z.read('word/document.xml').decode()
    assert xml.count('ZOTERO_ITEM CSL_CITATION') == 77
    assert xml.count('ZOTERO_BIBL ') == 1
    assert b'ZOTERO_PREF_1' in z.read('docProps/custom.xml')
report = {'output': str(output.relative_to(ROOT)), 'order': ['Cover letter', 'Highlights', 'Graphical abstract', 'Manuscript including shared references', 'Supplementary information'], 'citations': 77, 'unique_references': 42, 'bibliography_fields': 1, 'tables': 12, 'figures_including_graphical_abstract': 16, 'editable_display_equations': 19, 'all_supplementary_references_in_shared_bibliography': True, 'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [DELIVERY/'manuscript.docx', DELIVERY/'supplementary.docx']}, 'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
(BUILD / 'complete_conversion.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
