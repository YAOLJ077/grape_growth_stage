#!/usr/bin/env python3
"""Collect the current figure PDFs and optionally synchronize the edited manuscript."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / 'fig/paper_figures'
ORDER = ['graphical_abstract'] + [f'Fig_{i:02d}' for i in range(1, 11)] + [f'Fig_S{i:02d}' for i in range(1, 6)]


def main(update_manuscript=False):
    writer = PdfWriter()
    records = []
    for index, stem in enumerate(ORDER):
        source = FIGURES / f'{stem}.pdf'
        reader = PdfReader(source)
        assert len(reader.pages) == 1, source
        page = reader.pages[0]
        assert page.extract_text().strip(), source
        writer.add_page(page)
        writer.add_outline_item(stem.replace('_', ' '), index)
        records.append({'id': stem, 'merged_page': index + 1,
                        'width_points': float(page.mediabox.width),
                        'height_points': float(page.mediabox.height),
                        'assets': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in FIGURES.glob(stem + '.*')
                                   if p.suffix in {'.pdf', '.png', '.svg', '.tiff'}}})
    target = FIGURES / 'All_figures.pdf'
    temporary = target.with_suffix('.tmp.pdf')
    with temporary.open('wb') as stream:
        writer.write(stream)
    merged = PdfReader(temporary)
    assert len(merged.pages) == len(ORDER)
    for i, stem in enumerate(ORDER):
        original = PdfReader(FIGURES / f'{stem}.pdf').pages[0]
        assert merged.pages[i].extract_text() == original.extract_text(), stem
    temporary.replace(target)
    report = {'order': ORDER, 'figures': records, 'merged_pages': len(ORDER),
              'merged_pdf_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    if update_manuscript:
        path = ROOT / 'paper/grape_pheno_manuscript_ylj.docx'
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            original = {entry.filename: archive.read(entry.filename) for entry in entries}
        replacement = dict(original)
        keys = []
        for number in range(1, 11):
            key = f'word/media/image{number}.png'
            assert key in original, key
            replacement[key] = (FIGURES / f'Fig_{number:02d}.png').read_bytes()
            keys.append(key)
        temporary = path.with_suffix('.tmp.docx')
        with zipfile.ZipFile(temporary, 'w') as archive:
            for entry in entries:
                archive.writestr(entry, replacement[entry.filename])
        with zipfile.ZipFile(temporary) as archive:
            assert archive.testzip() is None
            assert all(archive.read(k) == v for k, v in original.items() if k not in keys)
            assert all(archive.read(k) == replacement[k] for k in keys)
        temporary.replace(path)
        report['manuscript'] = str(path.relative_to(ROOT))
        report['manuscript_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        report['manuscript_text_and_xml_unchanged'] = True
    (FIGURES / 'figure_manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Consolidated {len(ORDER)} current figures into {target.relative_to(ROOT)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--update-manuscript', action='store_true')
    main(parser.parse_args().update_manuscript)
