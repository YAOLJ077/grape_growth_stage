"""Embed editable Zotero citation/bibliography fields using source citation keys.

The document carries self-contained CSL records, without inventing a Zotero
library identity. Field and preference formats follow the official Zotero
integration field and preference formats. Embedded records are self-contained;
no live Zotero library connection is assumed.
"""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import re
import uuid
import zipfile

from lxml import etree as E
import pypandoc

from paths import ROOT, PAPER, DELIVERY, CITATIONS, compiled, build_directory
BUILD = build_directory('citations')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
STYLE = 'http://www.zotero.org/styles/european-journal-of-agronomy'


def element(name, **attrs):
    node = E.Element('{%s}%s' % (W, name))
    for key, value in attrs.items():
        node.set('{%s}%s' % (W, key), value)
    return node


def run_text(node):
    return ''.join(node.xpath('.//w:t/text()', namespaces=NS))


def slice_run(node, start, end):
    """Clone a textual run while preserving its font properties."""
    assert node.tag == '{%s}r' % W
    result = deepcopy(node)
    offset = 0
    for child in list(result):
        if child.tag == '{%s}rPr' % W:
            continue
        assert child.tag == '{%s}t' % W, child.tag
        text = child.text or ''
        child.text = text[max(0, start-offset):max(0, min(len(text), end-offset))]
        child.set(XML_SPACE, 'preserve')
        offset += len(text)
    return result


def field_runs(code, results):
    begin = element('r')
    begin.append(element('fldChar', fldCharType='begin', fldLock='false', dirty='false'))
    instruction = element('r')
    text = element('instrText')
    text.set(XML_SPACE, 'preserve')
    text.text = code
    instruction.append(text)
    separate = element('r')
    separate.append(element('fldChar', fldCharType='separate'))
    end = element('r')
    end.append(element('fldChar', fldCharType='end'))
    return [begin, instruction, separate, *results, end]


class CitationFields:
    def __init__(self, labels, document):
        self.labels = labels
        self.document = document
        self.records = []

    def replace(self, match):
        command, keys = match.groups()
        keys = [k.strip() for k in keys.split(',')]
        labels = [self.labels[k] for k in keys]
        if command == 'citep':
            display = '(' + '; '.join(f'{author}, {year}' for author, year in labels) + ')'
            prefix = ''
        else:
            assert len(keys) == 1, 'Narrative multi-item citations require separate year fields'
            author, year = labels[0]
            prefix, display = author + ' ', '(' + year + ')'
        index = len(self.records) + 1
        self.records.append({'index': index, 'command': command, 'keys': keys})
        return prefix + f'ZOTEROSTART{index:04d}' + display + f'ZOTEROEND{index:04d}'

    def embed(self, path):
        path = Path(path)
        raw = json.loads(pypandoc.convert_file(str(ROOT / 'paper/references/Phenological.bib'), format='biblatex', to='csljson'))
        wanted = {key for r in self.records for key in r['keys']}
        metadata = {}
        allowed = {'id', 'type', 'title', 'title-short', 'author', 'editor', 'issued', 'accessed', 'container-title', 'container-title-short', 'collection-title', 'volume', 'issue', 'page', 'publisher', 'publisher-place', 'edition', 'DOI', 'URL', 'ISBN', 'ISSN', 'event-title', 'event-place', 'language', 'note'}
        dataset_keys = {'mauryTempoDataPortal2023', 'copernicusClimateChangeServiceERA5LandHourly2019', 'copernicusClimateChangeServiceERA5LandMonthly2019', 'esaAirbusCopernicusDEM2022'}
        for item in raw:
            if item['id'] not in wanted:
                continue
            item = {k: v for k, v in item.items() if k in allowed}
            if item['id'] in dataset_keys:
                item['type'] = 'dataset'
            if item['id'] == 'mauryTempoDataPortal2023':
                item['publisher'] = 'Recherche Data Gouv'
            assert item['type'] and item.get('title') and item.get('author') and item.get('issued'), item['id']
            metadata[item['id']] = item
        assert set(metadata) == wanted
        exported = [metadata[key] for key in sorted(metadata)]
        export_path = BUILD / f'{self.document}_references.json'
        export_path.write_text(json.dumps(exported, ensure_ascii=False, indent=2) + '\n')
        (BUILD / f'{self.document}_references.bib').write_text(pypandoc.convert_text(json.dumps(exported, ensure_ascii=False), format='csljson', to='biblatex'))

        with zipfile.ZipFile(path) as z:
            files = {name: z.read(name) for name in z.namelist()}
        root = E.fromstring(files['word/document.xml'])
        session = uuid.uuid5(uuid.NAMESPACE_URL, 'grape-phenology/' + self.document).hex[:8]
        item_ids = {key: session + '/' + uuid.uuid5(uuid.NAMESPACE_URL, key).hex[:8] for key in wanted}
        uris = {key: 'urn:uuid:' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'grape-phenology/reference/' + key)) for key in wanted}
        seen = []
        for paragraph in root.xpath('.//w:p', namespaces=NS):
            while True:
                visible = run_text(paragraph)
                marker = re.search(r'ZOTEROSTART(\d{4})', visible)
                if not marker:
                    break
                index = int(marker[1])
                end_token = f'ZOTEROEND{index:04d}'
                end_start = visible.index(end_token, marker.end())
                end = end_start + len(end_token)
                record = self.records[index - 1]
                display = visible[marker.end():end_start]
                items = []
                for key in record['keys']:
                    item = {'id': item_ids[key], 'uris': [uris[key]], 'itemData': dict(metadata[key], id=item_ids[key])}
                    if record['command'] != 'citep':
                        item['suppress-author'] = True
                    items.append(item)
                data = {'citationID': uuid.uuid5(uuid.NAMESPACE_URL, f'{session}/citation/{index}').hex[:8], 'properties': {'plainCitation': display, 'noteIndex': 0}, 'citationItems': items, 'schema': 'https://github.com/citation-style-language/schema/raw/master/csl-citation.json'}
                affected, results = [], []
                offset = 0
                before = after = None
                for child in list(paragraph):
                    child_text = run_text(child)
                    length = len(child_text)
                    left, right = offset, offset + length
                    if left < end and right > marker.start():
                        assert child.tag == '{%s}r' % W, child.tag
                        affected.append(child)
                        if left < marker.start():
                            before = slice_run(child, 0, marker.start()-left)
                        a, b = max(left, marker.end()), min(right, end_start)
                        if a < b:
                            results.append(slice_run(child, a-left, b-left))
                        if right > end:
                            after = slice_run(child, end-left, length)
                    offset = right
                assert affected and ''.join(run_text(r) for r in results) == display
                position = paragraph.index(affected[0])
                for child in affected:
                    paragraph.remove(child)
                replacement = ([] if before is None else [before]) + field_runs(' ADDIN ZOTERO_ITEM CSL_CITATION ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ' ', results) + ([] if after is None else [after])
                for child in reversed(replacement):
                    paragraph.insert(position, child)
                record.update({'display': display, 'citationID': data['citationID']})
                seen.append(index)
        assert sorted(seen) == list(range(1, len(self.records) + 1))
        assert 'ZOTEROSTART' not in run_text(root) and 'ZOTEROEND' not in run_text(root)

        paragraphs = root.xpath('./w:body/w:p', namespaces=NS)
        heading = next(i for i, p in enumerate(paragraphs) if run_text(p) == 'References')
        references = [p for p in paragraphs[heading+1:] if run_text(p).strip()]
        assert len(references) == len(wanted), (len(references), len(wanted))
        bib_field = field_runs(' ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} CSL_BIBLIOGRAPHY ', [])
        position = 1 if len(references[0]) and references[0][0].tag == '{%s}pPr' % W else 0
        for child in reversed(bib_field[:-1]):
            references[0].insert(position, child)
        references[-1].append(bib_field[-1])
        files['word/document.xml'] = E.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)

        data = E.Element('data', {'data-version': '3', 'zotero-version': '7.0'})
        E.SubElement(data, 'session', id=session)
        E.SubElement(data, 'style', id=STYLE, locale='en-US', hasBibliography='1', bibliographyStyleHasBeenSet='1')
        prefs = E.SubElement(data, 'prefs')
        for key, value in {'fieldType': 'Field', 'storeReferences': 'true', 'noteType': '0', 'automaticJournalAbbreviations': 'false'}.items():
            E.SubElement(prefs, 'pref', name=key, value=value)
        prefs_text = E.tostring(data, encoding='unicode')
        cp = 'http://schemas.openxmlformats.org/officeDocument/2006/custom-properties'
        vt = 'http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes'
        custom = E.fromstring(files['docProps/custom.xml']) if 'docProps/custom.xml' in files else E.Element('{%s}Properties' % cp, nsmap={None: cp, 'vt': vt})
        for prop in list(custom):
            if prop.get('name', '').startswith('ZOTERO_PREF_'):
                custom.remove(prop)
        pid = max([1] + [int(p.get('pid')) for p in custom]) + 1
        for i, start in enumerate(range(0, len(prefs_text), 255), 1):
            prop = E.SubElement(custom, '{%s}property' % cp, fmtid='{D5CDD505-2E9C-101B-9397-08002B2CF9AE}', pid=str(pid+i-1), name=f'ZOTERO_PREF_{i}')
            E.SubElement(prop, '{%s}lpwstr' % vt).text = prefs_text[start:start+255]
        files['docProps/custom.xml'] = E.tostring(custom, xml_declaration=True, encoding='UTF-8', standalone=True)
        relationships = E.fromstring(files['_rels/.rels'])
        reltype = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties'
        if not any(r.get('Type') == reltype for r in relationships):
            ids = {r.get('Id') for r in relationships}
            rid = next(f'rId{i}' for i in range(1, 1000) if f'rId{i}' not in ids)
            E.SubElement(relationships, '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship', Id=rid, Type=reltype, Target='docProps/custom.xml')
        files['_rels/.rels'] = E.tostring(relationships, xml_declaration=True, encoding='UTF-8', standalone=True)
        types = E.fromstring(files['[Content_Types].xml'])
        if not any(t.get('PartName') == '/docProps/custom.xml' for t in types):
            E.SubElement(types, '{http://schemas.openxmlformats.org/package/2006/content-types}Override', PartName='/docProps/custom.xml', ContentType='application/vnd.openxmlformats-officedocument.custom-properties+xml')
        files['[Content_Types].xml'] = E.tostring(types, xml_declaration=True, encoding='UTF-8', standalone=True)
        temp = path.with_suffix('.zotero.tmp')
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, value in files.items():
                z.writestr(name, value)
        temp.replace(path)
        report = {'document': str(path.relative_to(ROOT)), 'citation_fields': len(seen), 'references': len(wanted), 'bibliography_fields': 1, 'style': STYLE, 'identity': 'Self-contained embedded references with document-generated URNs; no linked Zotero library', 'live_zotero_refresh_tested': False, 'source_bib_sha256': hashlib.sha256((ROOT / 'paper/references/Phenological.bib').read_bytes()).hexdigest(), 'output_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'citations': self.records, 'reference_ids': item_ids}
        (BUILD / f'{self.document}_fields.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        return report
