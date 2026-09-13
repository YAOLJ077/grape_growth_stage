"""Check source callouts, bibliography completeness, and editable Word fields."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
import re
import zipfile
import uuid

from lxml import etree as E
from docx import Document

from paths import ROOT, PAPER, DELIVERY, CITATIONS, compiled, build_directory
BUILD = build_directory('verification')
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'


def expand(source):
    return re.sub(r'\\input\{([^}]+)\}', lambda m: expand((PAPER / m[1]).read_text()), source)


def source_audit(name):
    source = expand((PAPER / (name + '.tex')).read_text())
    source = re.sub(r'(?<!\\)%[^\n]*', '', source)
    occurrences = re.findall(r'\\cite[pt]?\{([^}]+)\}', source)
    keys = {key.strip() for item in occurrences for key in item.split(',')}
    bbl = compiled(name, 'bbl').read_text()
    bibliography = re.findall(r'\\bibitem\[.*?\]\{([^}]+)\}', bbl, re.S)
    assert len(bibliography) == len(set(bibliography))
    assert keys == set(bibliography), (keys-set(bibliography), set(bibliography)-keys)
    labels = dict(re.findall(r'\\newlabel\{([^}]+)\}\{\{([^}]+)\}', compiled(name, 'aux').read_text()))
    blocks = list(re.finditer(r'\\begin\{(figure|table|longtable)\}(.*?)\\end\{\1\}', source, re.S))
    narrative = source
    for block in reversed(blocks):
        narrative = narrative[:block.start()] + narrative[block.end():]
    rows = []
    for block in blocks:
        label = re.search(r'\\label\{([^}]+)\}', block[2])[1]
        count = len(re.findall(r'\\ref\{' + re.escape(label) + r'\}', narrative))
        assert count > 0, (name, label)
        rows.append({'document': name, 'kind': 'figure' if block[1] == 'figure' else 'table', 'number': labels[label], 'label': label, 'narrative_callouts': count})
    assert set(re.findall(r'\\ref\{([^}]+)\}', source)) <= set(labels)
    log = compiled(name, 'log').read_text()
    assert not re.search(r'Overfull \\[hv]box|undefined|LaTeX Error|Float too large', log, re.I)
    commands = [{'command': m[1], 'keys': [k.strip() for k in m[2].split(',')]} for m in re.finditer(r'\\(citep|citet|cite)\{([^}]+)\}', source)]
    return {'citation_commands': commands, 'citation_occurrences': len(occurrences), 'reference_count': len(keys), 'missing_references': [], 'uncited_references': [], 'source_keys': sorted(keys), 'elements': rows}, narrative


def field_audit(name, source):
    path = DELIVERY / (name + '.docx')
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        root = E.fromstring(z.read('word/document.xml'))
        custom = E.fromstring(z.read('docProps/custom.xml'))
    prefs = ''.join(''.join(p.itertext()) for p in sorted([p for p in custom if p.get('name', '').startswith('ZOTERO_PREF_')], key=lambda p: int(p.get('name').rsplit('_', 1)[1])))
    data = E.fromstring(prefs.encode())
    assert data.get('data-version') == '3'
    assert data.find('style').get('id').endswith('/european-journal-of-agronomy')
    assert any(p.get('name') == 'fieldType' and p.get('value') == 'Field' for p in data.find('prefs'))
    fields, stack = [], []
    for node in root.iter():
        if node.tag == W + 'fldChar':
            kind = node.get(W + 'fldCharType')
            if kind == 'begin':
                assert node.get(W + 'fldLock', 'false') in ('false', '0')
                stack.append({'code': '', 'result': '', 'separated': False})
            elif kind == 'separate':
                stack[-1]['separated'] = True
            elif kind == 'end':
                fields.append(stack.pop())
        elif node.tag == W + 'instrText':
            stack[-1]['code'] += node.text or ''
        elif node.tag == W + 't' and stack and stack[-1]['separated']:
            stack[-1]['result'] += node.text or ''
    assert not stack
    citations = []
    for field in fields:
        if 'ZOTERO_ITEM CSL_CITATION ' not in field['code']:
            continue
        item = json.loads(field['code'].split('CSL_CITATION ', 1)[1])
        assert item['properties']['plainCitation'] == field['result']
        assert not item['properties'].get('dontUpdate') and not item['properties'].get('custom')
        for ref in item['citationItems']:
            assert ref['uris'] and ref['uris'][0].startswith('urn:uuid:')
            assert ref['itemData']['id'] == ref['id']
            assert all(ref['itemData'].get(k) for k in ['title', 'type', 'author', 'issued'])
        citations.append(item)
    assert len(citations) == source['citation_occurrences']
    assert len({c['citationID'] for c in citations}) == len(citations)
    session = uuid.uuid5(uuid.NAMESPACE_URL, 'grape-phenology/' + name).hex[:8]
    inverse = {session + '/' + uuid.uuid5(uuid.NAMESPACE_URL, key).hex[:8]: key for key in source['source_keys']}
    assert {inverse[r['id']] for c in citations for r in c['citationItems']} == set(source['source_keys'])
    for index, (citation, record) in enumerate(zip(citations, source['citation_commands']), 1):
        assert citation['citationID'] == uuid.uuid5(uuid.NAMESPACE_URL, f'{session}/citation/{index}').hex[:8]
        assert [inverse[i['id']] for i in citation['citationItems']] == record['keys']
        assert all(bool(i.get('suppress-author')) == (record['command'] != 'citep') for i in citation['citationItems'])
    assert len([f for f in fields if 'ZOTERO_BIBL ' in f['code']]) == 1
    document = Document(path)
    index = next(i for i, p in enumerate(document.paragraphs) if p.text == 'References')
    assert len([p for p in document.paragraphs[index+1:] if p.text.strip()]) == source['reference_count']
    visible = '\n'.join(p.text for p in document.paragraphs)
    assert 'ZOTEROSTART' not in visible and 'ZOTEROEND' not in visible
    output_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    build_directory('citations')
    (CITATIONS / f'{name}_citation_data.json').write_text(json.dumps(citations, ensure_ascii=False, indent=2) + '\n')
    return {'citation_fields': len(citations), 'bibliography_fields': 1, 'embedded_reference_records': len(inverse), 'unlocked': True, 'complete_metadata': True, 'style': data.find('style').get('id'), 'output_sha256': output_hash}


main, narrative = source_audit('manuscript')
supp, _ = source_audit('supplementary')
plain = narrative.replace('~', ' ')
patterns = {'section': r'(?:Section|Methods)\s+(S\d+)', 'figure': r'Fig\.\s+(S\d+)', 'table': r'Tables?\s+(S\d+(?:(?:,\s*|\s+and\s+|,\s+and\s+)S\d+)*)'}
rows = []
sections = re.findall(r'\\section\{([^}]+)\}', (PAPER / 'supplementary.tex').read_text())
supplementary = [{'kind': 'section', 'number': f'S{i}', 'title': title} for i, title in enumerate(sections, 1)] + supp['elements']
for element in supplementary:
    count = sum(element['number'] in re.findall(r'S\d+', m[1]) for m in re.finditer(patterns[element['kind']], plain))
    assert count > 0, element
    rows.append({'kind': element['kind'], 'number': element['number'], 'title_or_label': element.get('title', element.get('label')), 'main_narrative_callouts': count, 'retained': True})
assert len(rows) == 28
with open(BUILD / 'supplementary_callouts.csv', 'w') as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
for name, source in [('manuscript', main), ('supplementary', supp)]:
    source['word_fields'] = field_audit(name, source)
result = {'verified_utc': datetime.now(timezone.utc).isoformat(), 'status': 'passed', 'manuscript': main, 'supplementary': supp, 'all_28_supplementary_objects_cited_in_main_narrative': True, 'all_figures_and_tables_cited_in_own_document_narrative': True, 'all_reference_lists_equal_cited_sets': True, 'removed_material': [], 'live_zotero_refresh_tested': False, 'zotero_identity': 'Self-contained document records; no linked library or live refresh test'}
(BUILD / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: result[k] for k in ['status', 'all_28_supplementary_objects_cited_in_main_narrative', 'all_figures_and_tables_cited_in_own_document_narrative', 'all_reference_lists_equal_cited_sets']}, indent=2))
