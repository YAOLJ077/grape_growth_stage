"""Independent inventory, provenance, quarantine and combined-target audit.

Replaces the archived five-cell inventory notebook; uses only Python stdlib.
The chronology constants are intentionally independent of the QC implementation.
"""
from collections import Counter, defaultdict
import csv
from datetime import date
import gzip
import hashlib
from itertools import combinations
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / 'data/phenology'
COLUMNS = ['site', 'variety', 'country', 'lat', 'lon', 'Date', 'BBCH']


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def read_records(path):
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.reader(stream)
        assert next(reader) == COLUMNS
        return [tuple(row) for row in reader]


def main():
    records = read_records(DATA / 'phenology_data.csv')
    quality = json.loads((DATA / 'phenology_data_quality.json').read_text())
    assert len(records) == quality['output_rows'] == len(set(records))
    assert hashlib.sha256((DATA / 'phenology_data.csv').read_bytes()).hexdigest() == quality['output_sha256']
    missing, countries, sites = Counter(), Counter(), set()
    for row in records:
        site, variety, country, lat, lon, day, bbch = row
        assert site and re.fullmatch('[A-Z]{2}', country)
        assert country == site.split(':')[0]
        assert -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180
        assert date.fromisoformat(day).isoformat() == day and day >= '1951-01-01'
        assert re.fullmatch('[0-9]{2}', bbch)
        missing.update(c for c, v in zip(COLUMNS, row) if not v)
        countries[country] += 1
        sites.add(site)
    assert len(sites) == quality['source_qualified_sites']
    assert dict(missing) == {k: v for k, v in quality['missing_fields'].items() if v}
    assert dict(countries) == {k: v['rows'] for k, v in quality['countries'].items()}
    print(f'Inventory: {len(records):,} unique rows; schema, values and checksum verified.')

    event_hashes = {digest(row) for row in records}
    retained_hashes, qc_hashes = set(), set()
    statuses, per_source = Counter(), Counter()
    with gzip.open(DATA / 'phenology_data_provenance.jsonl.gz', 'rt', encoding='utf-8') as stream:
        for line in stream:
            item = json.loads(line)
            statuses[item['status']] += 1
            per_source[(item['source'], item['status'])] += 1
            if item['status'] == 'excluded_chronology_qc':
                qc_hashes.add(item['candidate_event_id'])
            if item['status'] in {'retained', 'duplicate'}:
                assert item['event_id'] in event_hashes and item['bbch_mapping'] == 'direct'
            if item['status'] == 'retained':
                assert item['event_id'] not in retained_hashes
                retained_hashes.add(item['event_id'])
    assert retained_hashes == event_hashes
    assert sum(statuses.values()) == sum(s['input_rows'] for s in quality['inputs'])
    for source in quality['inputs']:
        for status, field in [('retained', 'output_rows'), ('duplicate', 'duplicate_rows')]:
            assert per_source[(source['path'], status)] == source[field]
        for status in ['excluded_non_grape', 'excluded_inferred_bbch', 'excluded_unmapped_bbch',
                       'excluded_before_1951', 'excluded_missing_or_invalid_date', 'excluded_chronology_qc']:
            assert per_source[(source['path'], status)] == source[status]
    assert hashlib.sha256((DATA / 'phenology_data_provenance.jsonl.gz').read_bytes()).hexdigest() == quality['provenance_sha256']
    print(f'Provenance: all {sum(statuses.values()):,} source occurrences reconcile.')

    stage_groups = defaultdict(lambda: defaultdict(list))
    windows = [(range(1, 10), '02-01', '06-15'), (range(10, 20), '03-01', '07-31'),
               (range(50, 60), '04-01', '07-15'), (range(60, 70), '05-01', '07-31'),
               (range(70, 80), '05-15', '09-15'), (range(80, 86), '07-01', '10-15'),
               (range(86, 90), '07-15', '11-15')]
    for row in records:
        b, d = int(row[6]), date.fromisoformat(row[5])
        for codes, low, high in windows:
            if b in codes:
                assert low <= row[5][5:] <= high
        stage_groups[(row[0], row[1], d.year)][b].append(d.toordinal())
    branches = [[1,3,5,7,9,10,11,12,13,14,15,16,17,18,19],
                [1,3,5,7,9,53,55,57,60,61,62,63,64,65,66,67,68,69,71,73,75,77,79,81,83,85,87,89]]
    pairs = set(pair for branch in branches for pair in combinations(branch, 2))
    bounds = {(7,65):(20,100), (9,65):(20,100), (65,81):(30,120), (81,89):(10,90)}
    for stages in stage_groups.values():
        for a, b in pairs:
            if a not in stages or b not in stages:
                continue
            low, high = bounds.get((a, b), (0, 366))
            assert all(any(low <= y-x <= high for y in stages[b]) for x in stages[a])
            assert all(any(low <= y-x <= high for x in stages[a]) for y in stages[b])
    with gzip.open(DATA / 'phenology_data_quarantine.jsonl.gz', 'rt', encoding='utf-8') as stream:
        quarantine = [json.loads(line) for line in stream]
    assert {q['event_id'] for q in quarantine} == qc_hashes
    assert qc_hashes.isdisjoint(event_hashes)
    excluded = [tuple(q['record'][c] for c in COLUMNS) for q in quarantine]
    for q, row in zip(quarantine, excluded):
        assert q['evidence'] and q['policy'] == 'chronology-v2' and digest(row) == q['event_id']
    assert len(quarantine) == len(qc_hashes) == quality['chronology_qc']['rows_quarantined']
    restored = sorted(records + excluded, key=lambda r: (r[2],r[0],r[5],r[6],r[1],r[3],r[4]))
    assert len(restored) == len(set(restored)) == quality['chronology_qc']['rows_before']
    assert digest(restored) == quality['chronology_qc']['pre_qc_rows_sha256']
    assert hashlib.sha256((DATA / 'phenology_data_quarantine.jsonl.gz').read_bytes()).hexdigest() == quality['chronology_qc']['quarantine_sha256']
    print(f'Chronology: independent checks pass; {len(excluded):,} quarantined rows restore the pre-QC inventory.')

    targets = DATA / 'derived/paper_targets'
    actual = read_records(targets / 'observations.csv')
    assert actual == [r for r in records if r[6] in {'07', '65', '81', '89'}]
    report = json.loads((targets / 'quality.json').read_text())
    assert report['source_sha256'] == quality['output_sha256']
    assert len(actual) == report['combined']['rows']
    assert hashlib.sha256((targets / 'observations.csv').read_bytes()).hexdigest() == report['combined']['sha256']
    assert 'roles' not in report and 'role_definition' not in report
    assert dict(Counter(r[6] for r in actual)) == report['combined']['counts_by_stage']
    assert len({r[0] for r in actual}) == report['combined']['source_qualified_sites']
    print(f'Targets: {len(actual):,} unchanged source rows in one combined CSV.')
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(Path(__file__).parent), '-p', 'test_*.py'], check=True)


if __name__ == '__main__':
    main()
