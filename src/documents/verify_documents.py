"""Check final document content, editable fields and publication formatting.

Checks inspect OOXML directly. They do not claim a new Microsoft Word render
or live Zotero refresh. Semantic fingerprints ignore ZIP timestamps and layout
metadata while retaining text, equations, citations and embedded image bytes.
"""
from pathlib import Path
import hashlib
import json
import zipfile

from lxml import etree as E
from docx import Document
from docx.oxml.ns import qn

from paths import ROOT, PAPER, DELIVERY, build_directory
from format_word import TITLE

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def tree(node):
    return [node.tag, sorted(node.attrib.items()), node.text, [tree(c) for c in node]]


def fingerprint(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        root = E.fromstring(z.read('word/document.xml'))
        media = sorted(hashlib.sha256(z.read(k)).hexdigest() for k in z.namelist() if k.startswith('word/media/'))
        custom = E.fromstring(z.read('docProps/custom.xml'))
    preferences = ''.join(''.join(p.itertext()) for p in sorted(
        [p for p in custom if p.get('name', '').startswith('ZOTERO_PREF_')],
        key=lambda p: int(p.get('name').rsplit('_', 1)[1])))
    return {'text_sha256': digest(root.xpath('.//w:t/text()', namespaces=NS)),
            'math_sha256': digest([tree(m) for m in root.xpath('.//m:oMath', namespaces=NS)]),
            'field_sha256': digest(root.xpath('.//w:instrText/text()', namespaces=NS)),
            'image_sha256': digest(media), 'zotero_preferences_sha256': digest(preferences)}


def verify(name, expected_tables, expected_math, expected_fields, expected_figures):
    path = DELIVERY / (name + '.docx')
    document = Document(path)
    root = document._element
    instructions = root.xpath('.//w:instrText/text()')
    assert sum('ZOTERO_ITEM CSL_CITATION ' in s for s in instructions) == expected_fields
    assert sum('ZOTERO_BIBL ' in s for s in instructions) == 1
    assert len(document.tables) == expected_tables
    assert len(document.inline_shapes) == expected_figures
    for table in document.tables:
        borders = table._tbl.xpath('./w:tblPr/w:tblBorders')[0]
        assert {E.QName(e).localname for e in borders} == {'top', 'left', 'right', 'bottom', 'insideH', 'insideV'}
        assert all(e.get(qn('w:val')) == 'single' and e.get(qn('w:sz')) == '4' for e in borders)
    first = next(p for p in document.paragraphs if p.text == TITLE) if name != 'supplementary' else document.paragraphs[0]
    active = False
    paragraphs = 0
    for block in document._element.body:
        if block is first._p:
            active = True
        if not active:
            continue
        for node in ([block] if block.tag == qn('w:p') else list(block.iter(qn('w:p')))):
            spacing = node.find(qn('w:pPr')).find(qn('w:spacing'))
            assert spacing.get(qn('w:line')) == ('240' if node.xpath('.//w:drawing') else '480')
            assert spacing.get(qn('w:lineRule')) == 'auto'
            paragraphs += 1
    maths = root.xpath('.//m:oMathPara')
    assert len(maths) == expected_math
    for math in maths:
        p = math.getparent()
        tabs = p.xpath('./w:pPr/w:tabs/w:tab')
        assert [(t.get(qn('w:val')), int(t.get(qn('w:pos')))) for t in tabs] == [('center', 4535), ('right', 9071)]
        assert p[p.index(math)-1].find(qn('w:tab')) is not None
    for i, section in enumerate(document.sections):
        numbering = section._sectPr.find(qn('w:lnNumType'))
        if name != 'supplementary' and i == 0:
            assert numbering is None
        else:
            assert numbering is not None
            assert numbering.get(qn('w:restart')) == 'continuous'
            assert numbering.get(qn('w:start')) == '0'
            assert numbering.get(qn('w:countBy')) == '1'
    text = '\n'.join(p.text for p in document.paragraphs)
    if name == 'manuscript':
        assert 'RMSE' not in text
        assert 'warmest zone (EZ05)' in text
    if name == 'submission_complete':
        assert text.index('Supplementary information') > text.index('References')
    assert sum(p.text == 'References' for p in document.paragraphs) == 1
    signature = fingerprint(path)
    baseline = json.loads((PAPER / 'evidence/documents/content_fingerprints.json').read_text())
    if name in baseline:
        assert signature == baseline[name], (name, signature, baseline[name])
    return {'document': str(path.relative_to(ROOT)), 'status': 'passed',
            'tables': expected_tables, 'equations': expected_math, 'figures': expected_figures,
            'citation_fields': expected_fields, 'formatted_paragraphs': paragraphs,
            'continuous_numbering_configured': True, 'semantic_fingerprint': signature,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    reports = [verify(*spec) for spec in [('manuscript', 4, 7, 63, 11),
        ('supplementary', 8, 12, 14, 5), ('submission_complete', 12, 19, 77, 16)]]
    report = {'status': 'passed', 'scope': 'OOXML content and formatting; no new native Word rendering or live Zotero refresh', 'documents': reports}
    (build_directory('verification') / 'documents.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
