"""Assemble the current manuscript and existing submission front matter as Word."""
from pathlib import Path
import copy
import hashlib
import json
import re
import subprocess
import zipfile
import sys

import fitz
import pypandoc
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from docxcompose.composer import Composer

from paths import ROOT, PAPER, DELIVERY, CITATIONS, compiled, build_directory
BUILD = build_directory('manuscript')
OUT = DELIVERY / 'manuscript.docx'
ASSETS = BUILD / 'assets'
ASSETS.mkdir(parents=True, exist_ok=True)
PANDOC = pypandoc.get_pandoc_path()


def group(text, start):
    assert text[start] == '{', text[start:start + 40]
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


def pdf_image(path, name, dpi=300):
    pdf = fitz.open(path)
    assert len(pdf) == 1
    pix = pdf[0].get_pixmap(dpi=dpi, alpha=False)
    target = ASSETS / (name + '.png')
    pix.save(target)
    return target


tex = (PAPER / 'manuscript.tex').read_text()
aux = compiled('manuscript', 'aux').read_text()
source_pdf = fitz.open(PAPER / 'manuscript.pdf')
pdf_text = '\n'.join(p.get_text() for p in source_pdf)
(BUILD / 'source_pdf.txt').write_text(pdf_text)
labels = dict(re.findall(r'\\newlabel\{([^}]+)\}\{\{([^}]+)\}', aux))
cites = {}
for line in aux.splitlines():
    if line.startswith(r'\bibcite'):
        key, entry = groups(line)
        values = groups(entry)
        cites[key] = (values[2], values[1])


from citation_fields import CitationFields
citation_fields = CitationFields(cites, 'manuscript')
citation = citation_fields.replace


title_start = tex.index(r'\title{') + len(r'\title')
title, _ = group(tex, title_start)
title = re.sub(r'\\fontsize\{[^}]+\}\{[^}]+\}\\selectfont', '', title)
body = tex.split(r'\maketitle', 1)[1].split(r'\end{document}', 1)[0]
body = r'\section*{' + title + '}\n' + body
body = re.sub(r'(?<!\\)%[^\n]*', '', body)
body = re.sub(r'\\(citep|citet|cite)\{([^}]+)\}', citation, body)
body = re.sub(r'\\ref\{([^}]+)\}', lambda m: labels[m[1]], body)
body = body.replace(r'\symbf', r'\boldsymbol')
body = body.replace(r'\begin{abstract}', r'\section*{Abstract}')
body = body.replace(r'\end{abstract}', '')

# Keep the exact numbering recorded by the typeset manuscript.
section_numbers = [0, 0, 0]
def number_section(match):
    level = {'section': 0, 'subsection': 1, 'subsubsection': 2}[match[1]]
    section_numbers[level] += 1
    for j in range(level + 1, 3):
        section_numbers[j] = 0
    number = '.'.join(str(n) for n in section_numbers[:level + 1])
    return '\\' + match[1] + '*{' + number + ' ' + match[2] + '}'
body = re.sub(r'\\(section|subsection|subsubsection)\{([^}]+)\}', number_section, body)

figure_records = []
def figure(match):
    block = match[1]
    label = re.search(r'\\label\{([^}]+)\}', block)[1]
    path = re.search(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}', block)[1]
    cap, _ = group(block, block.index(r'\caption{') + len(r'\caption'))
    number = labels[label]
    img = pdf_image(ROOT / path, 'Fig_' + number.zfill(2))
    figure_records.append({'number': int(number), 'source': path, 'caption': cap})
    return '\n\n\\includegraphics[width=160mm]{' + str(img) + '}\n\n' + r'\textit{\textbf{Fig. ' + number + '.} ' + cap + '}\n\n'
body = re.sub(r'\\begin\{figure\}(?:\[[^]]*\])?(.*?)\\end\{figure\}', figure, body, flags=re.S)

table_records = []
def table(match):
    kind, block = match[1], match[2]
    label = re.search(r'\\label\{([^}]+)\}', block)[1]
    cap_start = block.index(r'\caption{')
    cap, cap_end = group(block, cap_start + len(r'\caption'))
    number = labels[label]
    block = block[:cap_start] + block[cap_end:]
    block = re.sub(r'\\label\{[^}]+\}', '', block)
    if kind == 'longtable':
        # Use one editable table; Word repeats the header automatically.
        colspec, end = group(block, block.index('{'))
        tail = block[end:]
        first_header = tail[tail.index(r'\toprule'):tail.index(r'\endfirsthead')]
        rows = tail.split(r'\endlastfoot', 1)[1]
        block = '\\begin{tabular}{lllll}\n' + first_header + rows + '\n\\end{tabular}'
    else:
        block = re.sub(r'^\[[^]]*\]', '', block)
    block = re.sub(r'\\addlinespace(?:\[[^]]*\])?', '', block)
    table_records.append({'number': int(number), 'caption': cap})
    return '\n\n\\textit{\\textbf{Table ' + number + '.} ' + cap + '}\n\n' + block + '\n\n'
body = re.sub(r'\\begin\{(table|longtable)\}(.*?)\\end\{\1\}', table, body, flags=re.S)

equation_labels = []
def equation(match):
    block = match[1]
    label = re.search(r'\\label\{([^}]+)\}', block)[1]
    equation_labels.append(labels[label])
    block = re.sub(r'\\label\{[^}]+\}', '', block)
    return '\n\\[' + block.strip() + '\\]\n'
body = re.sub(r'\\begin\{equation\}(.*?)\\end\{equation\}', equation, body, flags=re.S)
body = re.sub(r'\\label\{[^}]+\}', '', body)

bbl = compiled('manuscript', 'bbl').read_text()
bibparts = re.split(r'\\bibitem\[[\s\S]*?\]\{([^}]+)\}', bbl)[1:]
references = []
for key, entry in zip(bibparts[::2], bibparts[1::2]):
    entry = entry.split(r'\end{thebibliography}', 1)[0].strip()
    entry = entry.replace(r'\newblock', ' ').replace(r'\penalty0', '')
    entry = re.sub(r'\\doi\{([^}]+)\}', lambda m: r'doi: \url{https://doi.org/' + m[1] + '}', entry)
    entry = re.sub(r'\\natexlab\{([^}]+)\}', r'\1', entry)
    references.append({'key': key, 'latex': entry})
body = re.sub(r'\\bibliographystyle\{[^}]+\}', '', body)
body = re.sub(r'\\bibliography\{[^}]+\}', lambda m: '\\section*{References}\n\n' + '\n\n'.join(r['latex'] for r in references), body)

# Discard print-only spacing controls, leaving all scientific content intact.
body = re.sub(r'\\setlength\{[^}]+\}\{[^}]*\}', '', body)
body = re.sub(r'\\(?:setstretch|fontsize)\{[^}]+\}(?:\{[^}]+\})?', '', body)
body = re.sub(r'\\renewcommand\{[^}]+\}\{[^}]*\}', '', body)
body = re.sub(r'\\vspace\{[^}]+\}', '', body)
body = re.sub(r'\\(?:begingroup|endgroup|clearpage|FloatBarrier|linenumbers|justifying|centering|selectfont|small|footnotesize|noindent|medskip)\b', '', body)
prepared = '\\documentclass{article}\n\\usepackage{amsmath,amssymb,graphicx,booktabs,tabularx}\n\\begin{document}\n' + body + '\n\\end{document}\n'
(BUILD / 'manuscript_word.tex').write_text(prepared)

reference_doc = Document()
sec = reference_doc.sections[0]
sec.page_width, sec.page_height = Mm(210), Mm(297)
sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Mm(25)
for style_name in ('Normal', 'Body Text', 'First Paragraph'):
    if style_name not in reference_doc.styles:
        reference_doc.styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
    s = reference_doc.styles[style_name]
    s.font.name, s.font.size = 'Times New Roman', Pt(12)
    s.paragraph_format.first_line_indent = Mm(0)
    s.paragraph_format.line_spacing = 1.5
    s.paragraph_format.space_after = Pt(6)
reference_doc.save(BUILD / 'reference.docx')
run = subprocess.run([PANDOC, str(BUILD / 'manuscript_word.tex'), '-f', 'latex', '-t', 'docx', '--reference-doc', str(BUILD / 'reference.docx'), '-o', str(BUILD / 'manuscript_body.docx')], capture_output=True, text=True)
(BUILD / 'pandoc.log').write_text(run.stderr)
if run.returncode:
    raise RuntimeError(run.stderr)

manuscript = Document(BUILD / 'manuscript_body.docx')
for name in ('Heading 1', 'Heading 2', 'Heading 3', 'Title', 'Caption'):
    style = manuscript.styles[name]
    style.font.name = 'Times New Roman'
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.paragraph_format.keep_with_next = name != 'Caption'
    style.font.size = Pt({'Heading 1': 14, 'Heading 2': 12, 'Heading 3': 12, 'Title': 16, 'Caption': 10}[name])
    if name != 'Caption':
        style.font.bold = True
    style.paragraph_format.space_before = Pt(12 if name != 'Title' else 0)
    style.paragraph_format.space_after = Pt(6)
manuscript.paragraphs[0].style = 'Title'
manuscript.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
manuscript.paragraphs[0].paragraph_format.line_spacing = 1.2
in_refs = False
eqnum = 0
for p in manuscript.paragraphs:
    p.paragraph_format.widow_control = True
    if p.text == 'References':
        in_refs = True
        p.paragraph_format.page_break_before = True
    elif in_refs and p.text.strip():
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.left_indent = Mm(6)
        p.paragraph_format.first_line_indent = Mm(-6)
        p.paragraph_format.space_after = Pt(6)
        for r in p.runs:
            r.font.size = Pt(11)
    if p.text.startswith(('Fig. ', 'Table ')):
        p.style = 'Caption'
        p.paragraph_format.line_spacing = 1.05
        p.paragraph_format.keep_together = True
        p.paragraph_format.keep_with_next = p.text.startswith('Table ')
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for r in p.runs:
            r.font.size = Pt(10)
    if p._p.xpath('.//w:drawing'):
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.space_after = Pt(5)
    if p._p.xpath('.//m:oMathPara'):
        eqnum += 1
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.tab_stops.add_tab_stop(Mm(158), WD_TAB_ALIGNMENT.RIGHT)
        p.add_run('\t(' + equation_labels[eqnum - 1] + ')')
        p.paragraph_format.keep_together = True
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(6)
assert eqnum == 7, eqnum

# High-resolution figures fit with their captions on portrait pages.
for shape in manuscript.inline_shapes:
    factor = min(Mm(160) / shape.width, Mm(182) / shape.height, 1)
    shape.width, shape.height = int(shape.width * factor), int(shape.height * factor)

widths = ([70, 27, 63], [17, 83, 60], [52, 52, 56], [21, 40, 29, 12, 58])
assert len(manuscript.tables) == 4, len(manuscript.tables)
for idx, tbl in enumerate(manuscript.tables):
    tbl.autofit = False
    for col, width in zip(tbl.columns, widths[idx]):
        col.width = Mm(width)
    for i, row in enumerate(tbl.rows):
        trpr = row._tr.get_or_add_trPr()
        no_split = OxmlElement('w:cantSplit')
        trpr.append(no_split)
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
                    r.font.name, r.font.size = 'Times New Roman', Pt(10 if idx == 3 else 11)
                    if i == 0:
                        r.bold = True
assert len(manuscript.tables[3].rows) == 21
manuscript.save(BUILD / 'manuscript_body.docx')

# A master document supplies shared styles; front matter has explicit local formatting.
combined = Document(BUILD / 'manuscript_body.docx')
for child in list(combined._element.body):
    if child.tag != qn('w:sectPr'):
        combined._element.body.remove(child)
section = combined.sections[0]
section.footer_distance = Mm(12)
footer = section.footer.paragraphs[0]
footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
field = OxmlElement('w:fldSimple')
field.set(qn('w:instr'), 'PAGE')
footer._p.append(field)

cover_blocks = (PAPER / 'afm_submission/cover_letter.md').read_text().strip().split('\n\n')
for block in cover_blocks:
    p = combined.add_paragraph(block)
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.space_after = Pt(5)
    for r in p.runs:
        r.font.name, r.font.size = 'Times New Roman', Pt(10.5)

p = combined.add_paragraph('Highlights', style='Heading 1')
p.paragraph_format.page_break_before = True
highlights = [line[2:] for line in (PAPER / 'afm_submission/highlights.md').read_text().splitlines() if line.startswith('- ')]
for text in highlights:
    p = combined.add_paragraph(text, style='List Bullet')
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.space_after = Pt(12)
    for r in p.runs:
        r.font.name, r.font.size = 'Times New Roman', Pt(12)

p = combined.add_paragraph('Graphical abstract', style='Heading 1')
p.paragraph_format.page_break_before = True
ga = pdf_image(ROOT / 'fig/paper_figures/graphical_abstract.pdf', 'graphical_abstract')
p = combined.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.line_spacing = 1
shape = p.add_run().add_picture(str(ga))
factor = min(Mm(160) / shape.width, Mm(218) / shape.height)
shape.width, shape.height = int(shape.width * factor), int(shape.height * factor)

manuscript.paragraphs[0].paragraph_format.page_break_before = True
composer = Composer(combined)
composer.append(manuscript)
for name in ('Title', 'Heading 1', 'Heading 2', 'Heading 3', 'Caption'):
    style = combined.styles[name]
    rfonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in list(rfonts.attrib):
        if 'theme' in attr.lower():
            del rfonts.attrib[attr]
    for attr in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
        rfonts.set(qn('w:' + attr), 'Times New Roman')
    for border in style.element.xpath('./w:pPr/w:pBdr'):
        border.getparent().remove(border)
combined.styles['Caption'].font.bold = False
settings = combined.settings.element
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
combined.core_properties.title = 'Beyond thermal accumulation: improving cross-regional grapevine phenology prediction with terrain-aware forcing and residual learning'
combined.core_properties.author = 'Linjia Yao; Qiang Yu; Gang Zhao'
combined.core_properties.subject = 'Cover letter, highlights, graphical abstract and manuscript'
composer.save(OUT)
from format_word import format_document
format_document(OUT, has_front_matter=True)
zotero_report = citation_fields.embed(OUT)

with zipfile.ZipFile(OUT) as z:
    xml = z.read('word/document.xml').decode()
    assert z.testzip() is None
    assert xml.count('<w:drawing>') == 11
    assert xml.count('<m:oMathPara>') == 7
    assert 'Supplementary Methods S7' in xml
    assert 'References' in xml
    assert 'RMSE' not in xml
    assert 'warmest zone (EZ05)' in xml
    assert 'Environmental-zone dependence of predictive performance' in xml

source_paths = [PAPER / 'manuscript.pdf', PAPER / 'manuscript.tex', compiled('manuscript', 'aux'), compiled('manuscript', 'bbl'), PAPER / 'afm_submission/cover_letter.md', PAPER / 'afm_submission/highlights.md', ROOT / 'fig/paper_figures/graphical_abstract.pdf'] + [ROOT / r['source'] for r in figure_records]
manifest = {
    'output': str(OUT.relative_to(ROOT)),
    'order': ['Cover letter', 'Highlights', 'Graphical abstract', 'Manuscript'],
    'supplementary_appended': False,
    'source_pdf_pages': len(source_pdf),
    'manuscript_figures': len(figure_records),
    'manuscript_tables': len(table_records),
    'display_equations': eqnum,
    'references': len(references),
    'highlights': len(highlights),
    'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
    'output_sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
    'output_bytes': OUT.stat().st_size,
    'pandoc_warnings': run.stderr,
}
(BUILD / 'conversion.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({k:v for k,v in manifest.items() if k != 'source_sha256'}, indent=2))
