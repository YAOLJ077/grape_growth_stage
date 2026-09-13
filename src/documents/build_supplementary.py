"""Convert supplementary information to editable Word without revising content."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import zipfile
import sys

import pymupdf as fitz
import pypandoc
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

from paths import ROOT, PAPER, DELIVERY, CITATIONS, compiled, build_directory
BUILD = build_directory('supplementary')
OUT = DELIVERY / 'supplementary.docx'
ASSETS = BUILD / 'assets'
ASSETS.mkdir(parents=True, exist_ok=True)
PANDOC = pypandoc.get_pandoc_path()
sources = {PAPER / ('supplementary.' + ext) for ext in ('pdf', 'tex')} | {compiled('supplementary', ext) for ext in ('aux', 'bbl')}


def group(text, start):
    assert text[start] == '{'
    depth = 0
    for i in range(start, len(text)):
        if text[i] in '{}' and (i == 0 or text[i - 1] != '\\'):
            depth += 1 if text[i] == '{' else -1
            if depth == 0:
                return text[start + 1:i], i + 1
    raise ValueError('Unbalanced braces')


def groups(text):
    result, i = [], 0
    while i < len(text):
        if text[i] == '{':
            value, i = group(text, i)
            result.append(value)
        else:
            i += 1
    return result


def expand_inputs(text):
    def include(match):
        path = PAPER / match[1]
        if not path.suffix:
            path = path.with_suffix('.tex')
        sources.add(path)
        return expand_inputs(path.read_text())
    return re.sub(r'\\input\{([^}]+)\}', include, text)


tex = (PAPER / 'supplementary.tex').read_text()
aux = compiled('supplementary', 'aux').read_text()
labels = dict(re.findall(r'\\newlabel\{([^}]+)\}\{\{([^}]+)\}', aux))
cites = {}
for line in aux.splitlines():
    if line.startswith(r'\bibcite'):
        key, entry = groups(line)
        values = groups(entry)
        cites[key] = (values[2], values[1])


from citation_fields import CitationFields
citation_fields = CitationFields(cites, 'supplementary')
citation = citation_fields.replace


body = tex.split(r'\begin{document}', 1)[1].split(r'\end{document}', 1)[0]
body = expand_inputs(body)
body = re.sub(r'(?<!\\)%[^\n]*', '', body)
body = re.sub(r'\\(citep|citet|cite)\{([^}]+)\}', citation, body)
body = re.sub(r'\\ref\{([^}]+)\}', lambda m: labels[m[1]], body)
body = body.replace(r'\symbf', r'\boldsymbol')
title = 'Beyond thermal accumulation: improving cross-regional grapevine phenology prediction with terrain-aware forcing and residual learning'
body = re.sub(r'\\begin\{center\}.*?\\end\{center\}', lambda m: '\\section*{Supplementary information}\n\n' + title + '\n\nLinjia Yao, Qiang Yu and Gang Zhao\n\n', body, count=1, flags=re.S)
section_count = 0
def section(match):
    global section_count
    section_count += 1
    return r'\section*{S' + str(section_count) + '. ' + match[1] + '}'
body = re.sub(r'\\section\{([^}]+)\}', section, body)

figures = []
def figure(match):
    block = match[1]
    label = re.search(r'\\label\{([^}]+)\}', block)[1]
    path = ROOT / re.search(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}', block)[1]
    caption, _ = group(block, block.index(r'\caption{') + len(r'\caption'))
    number = labels[label]
    sources.add(path)
    pdf = fitz.open(path)
    assert len(pdf) == 1
    target = ASSETS / ('Fig_' + number + '.png')
    pdf[0].get_pixmap(dpi=300, alpha=False).save(target)
    figures.append({'number': number, 'source': str(path.relative_to(ROOT))})
    return '\n\n\\includegraphics[width=160mm]{' + str(target) + '}\n\n' + r'\textbf{Figure ' + number + ':} ' + caption + '\n\n'
body = re.sub(r'\\begin\{figure\}(?:\[[^]]*\])?(.*?)\\end\{figure\}', figure, body, flags=re.S)

tables = []
def table(match):
    kind, block = match[1], match[2]
    label = re.search(r'\\label\{([^}]+)\}', block)[1]
    start = block.index(r'\caption{')
    caption, end = group(block, start + len(r'\caption'))
    number = labels[label]
    block = block[:start] + block[end:]
    block = re.sub(r'\\label\{[^}]+\}', '', block)
    if kind == 'longtable':
        colspec, end = group(block, block.index('{'))
        tail = block[end:]
        header = tail[tail.index(r'\toprule'):tail.index(r'\endfirsthead')]
        rows = tail.split(r'\endhead', 1)[1]
        assert r'\endfoot' not in rows
        block = '\\begin{tabular}{' + colspec + '}\n' + header + rows + '\n\\end{tabular}'
    else:
        block = re.sub(r'^\[[^]]*\]', '', block)
    # Undo a print-only resize wrapper around a now-expanded input table.
    resize = re.search(r'\\resizebox\{[^}]*\}\{[^}]*\}', block)
    if resize:
        content, end = group(block, resize.end())
        block = block[:resize.start()] + content + block[end:]
    block = re.sub(r'\\addlinespace(?:\[[^]]*\])?', '', block)
    tables.append({'number': number})
    return '\n\n\\textbf{Table ' + number + ':} ' + caption + '\n\n' + block + '\n\n'
body = re.sub(r'\\begin\{(table|longtable)\}(.*?)\\end\{\1\}', table, body, flags=re.S)

equations = []
def equation(match):
    block = match[1]
    number = 'S' + str(len(equations) + 1)
    label = re.search(r'\\label\{([^}]+)\}', block)
    if label:
        assert labels[label[1]] == number
    equations.append(number)
    block = re.sub(r'\\label\{[^}]+\}', '', block)
    return '\n\\[' + block.strip() + '\\]\n'
body = re.sub(r'\\begin\{equation\}(.*?)\\end\{equation\}', equation, body, flags=re.S)
body = re.sub(r'\\label\{[^}]+\}', '', body)

bbl = compiled('supplementary', 'bbl').read_text()
parts = re.split(r'\\bibitem\[[\s\S]*?\]\{([^}]+)\}', bbl)[1:]
references = []
for key, entry in zip(parts[::2], parts[1::2]):
    entry = entry.split(r'\end{thebibliography}', 1)[0].strip()
    entry = entry.replace(r'\newblock', ' ').replace(r'\penalty0', '')
    entry = re.sub(r'\\doi\{([^}]+)\}', lambda m: r'doi: \url{https://doi.org/' + m[1] + '}', entry)
    entry = re.sub(r'\\natexlab\{([^}]+)\}', r'\1', entry)
    references.append({'key': key, 'latex': entry})
body = re.sub(r'\\bibliographystyle\{[^}]+\}', '', body)
body = re.sub(r'\\bibliography\{[^}]+\}', lambda m: '\\section*{References}\n\n' + '\n\n'.join(r['latex'] for r in references), body)
body = re.sub(r'\\setlength\{[^}]+\}\{[^}]*\}', '', body)
body = re.sub(r'\\(?:setstretch|fontsize)\{[^}]+\}(?:\{[^}]+\})?', '', body)
body = re.sub(r'\\renewcommand\{[^}]+\}\{[^}]*\}', '', body)
body = re.sub(r'\\vspace\{[^}]+\}', '', body)
body = re.sub(r'\\(?:begingroup|endgroup|clearpage|FloatBarrier|linenumbers|justifying|centering|selectfont|small|footnotesize|noindent|medskip)\b', '', body)
prepared = '\\documentclass{article}\n\\usepackage{amsmath,amssymb,graphicx,booktabs,tabularx}\n\\begin{document}\n' + body + '\n\\end{document}\n'
(BUILD / 'supplementary_word.tex').write_text(prepared)

reference_doc = Document()
sec = reference_doc.sections[0]
sec.page_width, sec.page_height = Mm(210), Mm(297)
sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Mm(25)
for name in ('Normal', 'Body Text', 'First Paragraph'):
    if name not in reference_doc.styles:
        reference_doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    style = reference_doc.styles[name]
    style.font.name, style.font.size = 'Times New Roman', Pt(11)
    style.paragraph_format.first_line_indent = Mm(0)
    style.paragraph_format.line_spacing = 1.3
    style.paragraph_format.space_after = Pt(6)
reference_doc.save(BUILD / 'reference.docx')
run = subprocess.run([PANDOC, str(BUILD / 'supplementary_word.tex'), '-f', 'latex', '-t', 'docx', '--reference-doc', str(BUILD / 'reference.docx'), '-o', str(OUT)], capture_output=True, text=True)
(BUILD / 'pandoc.log').write_text(run.stderr)
assert run.returncode == 0, run.stderr
doc = Document(OUT)
for name in ('Title', 'Subtitle', 'Heading 1', 'Heading 2', 'Heading 3', 'Heading 4', 'Heading 5', 'Caption'):
    style = doc.styles[name]
    style.font.name = 'Times New Roman'
    style.font.color.rgb = RGBColor(0, 0, 0)
    size = {'Title': 16, 'Subtitle': 12, 'Heading 1': 13, 'Caption': 10}.get(name, 11)
    style.font.size = Pt(size)
    style.font.bold = name not in ('Caption', 'Subtitle')
    style.paragraph_format.keep_with_next = name != 'Caption'
    style.paragraph_format.line_spacing = 1.1
    style.paragraph_format.space_before = Pt(12)
    style.paragraph_format.space_after = Pt(6)
    rfonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in list(rfonts.attrib):
        if 'theme' in attr.lower():
            del rfonts.attrib[attr]
    for attr in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
        rfonts.set(qn('w:' + attr), 'Times New Roman')
    for border in style.element.xpath('./w:pPr/w:pBdr'):
        border.getparent().remove(border)
doc.paragraphs[0].style = 'Title'
doc.paragraphs[1].style = 'Subtitle'
for p in doc.paragraphs[:3]:
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.line_spacing = 1.1
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(8)

in_refs = False
eqnum = 0
for p in doc.paragraphs:
    p.paragraph_format.widow_control = True
    if p.text == 'References':
        in_refs = True
        p.paragraph_format.page_break_before = True
    elif in_refs and p.text.strip():
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.left_indent = Mm(6)
        p.paragraph_format.first_line_indent = Mm(-6)
        p.paragraph_format.space_after = Pt(6)
    if re.match(r'^(Figure|Table) S\d+:', p.text):
        p.style = 'Caption'
        p.paragraph_format.line_spacing = 1.05
        p.paragraph_format.keep_together = True
        p.paragraph_format.keep_with_next = p.text.startswith('Table')
        p.paragraph_format.space_before = Pt(3)
        for r in p.runs:
            r.font.size = Pt(10)
    if p._p.xpath('.//w:drawing'):
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.space_after = Pt(5)
    if p._p.xpath('.//m:oMathPara'):
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.tab_stops.add_tab_stop(Mm(158), WD_TAB_ALIGNMENT.RIGHT)
        p.add_run('\t(' + equations[eqnum] + ')')
        p.paragraph_format.keep_together = True
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(6)
        eqnum += 1
for shape in doc.inline_shapes:
    factor = min(Mm(160) / shape.width, Mm(190) / shape.height, 1)
    shape.width, shape.height = int(shape.width * factor), int(shape.height * factor)

widths = [
    [38, 17, 20, 20, 17, 17, 16, 15],
    [36, 25, 16, 16, 17, 17, 17, 16],
    [27, 29, 17, 44, 43],
    [24, 28, 28, 43, 37],
    [34, 64, 14, 48],
    [42, 30, 30, 29, 29],
    [16, 15, 32, 24, 18, 55],
    [18, 17, 28, 40, 57],
]
assert len(doc.tables) == len(widths) == 8
for idx, tbl in enumerate(doc.tables):
    tbl.autofit = False
    for col, width in zip(tbl.columns, widths[idx]):
        col.width = Mm(width)
    for i, row in enumerate(tbl.rows):
        trpr = row._tr.get_or_add_trPr()
        trpr.append(OxmlElement('w:cantSplit'))
        if i == 0:
            trpr.append(OxmlElement('w:tblHeader'))
        for cell, width in zip(row.cells, widths[idx]):
            cell.width = Mm(width)
            for p in cell.paragraphs:
                p.paragraph_format.line_spacing = 1.05
                p.paragraph_format.space_before = Pt(3)
                p.paragraph_format.space_after = Pt(3)
                p.paragraph_format.keep_with_next = False
                for r in p.runs:
                    r.font.name, r.font.size = 'Times New Roman', Pt(10)
                    if i == 0:
                        r.bold = True

section = doc.sections[0]
section.footer_distance = Mm(12)
footer = section.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
field = OxmlElement('w:fldSimple')
field.set(qn('w:instr'), 'PAGE')
footer._p.append(field)
settings = doc.settings.element
for item in settings.xpath('./w:updateStyles | ./w:attachedTemplate'):
    settings.remove(item)
compat = settings.find(qn('w:compat'))
if compat is None:
    compat = OxmlElement('w:compat')
    settings.append(compat)
for item in list(compat):
    if item.get(qn('w:name')) == 'compatibilityMode':
        compat.remove(item)
mode = OxmlElement('w:compatSetting')
mode.set(qn('w:name'), 'compatibilityMode')
mode.set(qn('w:uri'), 'http://schemas.microsoft.com/office/word')
mode.set(qn('w:val'), '15')
compat.append(mode)
doc.core_properties.title = 'Supplementary information: ' + title
doc.core_properties.author = 'Linjia Yao; Qiang Yu; Gang Zhao'
doc.save(OUT)
from format_word import format_document
format_document(OUT, has_front_matter=False)
zotero_report = citation_fields.embed(OUT)
assert eqnum == 12 and section_count == 15 and len(figures) == 5 and len(references) == 11
assert [len(t.rows) for t in doc.tables] == [13, 3, 11, 5, 5, 8, 21, 21]
with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    xml = z.read('word/document.xml').decode()
    assert xml.count('<w:drawing>') == 5
    assert xml.count('<m:oMathPara>') == 12
    assert 'RMSE' in xml  # Preserve the supplementary diagnostics present in the source PDF.
pdf = fitz.open(PAPER / 'supplementary.pdf')
(BUILD / 'source_pdf.txt').write_text('\n'.join(p.get_text() for p in pdf))
manifest = {
    'built_utc': datetime.now(timezone.utc).isoformat(),
    'output': str(OUT.relative_to(ROOT)), 'source_pdf_pages': len(pdf),
    'sections': section_count, 'tables': tables, 'figures': figures,
    'equations': equations, 'references': len(references),
    'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)},
    'output_sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
    'output_bytes': OUT.stat().st_size, 'pandoc_warnings': run.stderr,
}
(BUILD / 'conversion.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({k: v for k, v in manifest.items() if k not in ('source_sha256', 'tables', 'figures')}, indent=2))
