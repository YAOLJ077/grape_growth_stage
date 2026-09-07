"""Select paper targets from the unchanged chronology-screened inventory.

Run from the repository root: python3 src/phenology/select_modeling_targets.py
Selection is observation-level; any one selected stage qualifies a site/year.
"""
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'data/phenology'
COLUMNS = ['site', 'variety', 'country', 'lat', 'lon', 'Date', 'BBCH']
TARGETS = ('07', '65', '81', '89')


def display_path(path):
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def build_subsets(source, source_quality, output_dir):
    """Export all four modelling stages in one observation CSV."""
    source, source_quality, output_dir = map(Path, (source, source_quality, output_dir))
    payload = source.read_bytes()
    source_hash = hashlib.sha256(payload).hexdigest()
    inherited = json.loads(source_quality.read_text())
    if source_hash != inherited['output_sha256']:
        raise ValueError('Inventory checksum does not match its quality report')
    reader = csv.reader(io.StringIO(payload.decode('utf-8'), newline=''))
    if next(reader) != COLUMNS:
        raise ValueError('Inventory must have the canonical seven-column schema')
    rows = [tuple(row) for row in reader]
    if any(len(row) != len(COLUMNS) for row in rows):
        raise ValueError('Invalid observation field count')
    if len(rows) != inherited['output_rows']:
        raise ValueError('Inventory row count does not match its quality report')
    if len(set(rows)) != len(rows):
        raise ValueError('Inventory contains exact duplicate observations')
    report = dict(
        policy='paper-targets-v3-four-stages', source=display_path(source),
        source_sha256=source_hash, source_rows=len(rows),
        source_quality=display_path(source_quality),
        inherited_qc=inherited['chronology_qc']['policy'],
        columns=COLUMNS, geography='All countries present in the cleaned inventory',
        eligibility='At least one observation of any selected stage; no complete site or site-year sequence required',
        preprocessing='Selection only; preserve source order, fields, missing varieties and repeated accepted observations',
        readiness='Phenology-eligible observations; weather matching, event preparation and calibration/test assignment remain separate',
    )
    target_codes = set(TARGETS)
    selected = [row for row in rows if row[6] in target_codes]
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / 'observations.csv'
    with output.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(COLUMNS)
        writer.writerows(selected)
    report['combined'] = summarize(selected, sorted(target_codes))
    report['combined'].update(file=display_path(output), sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    report['non_target_rows'] = len(rows) - len(selected)
    report['non_target_interpretation'] = 'Retained in the full inventory; not excluded as data-quality errors'
    (output_dir / 'quality.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def summarize(rows, stages):
    return dict(
        stages=list(stages), rows=len(rows),
        source_qualified_sites=len({row[0] for row in rows}),
        distinct_coordinate_pairs=len({(float(row[3]), float(row[4])) for row in rows}),
        countries=len({row[2] for row in rows}),
        counts_by_stage=dict(sorted(Counter(row[6] for row in rows).items())),
        counts_by_country=dict(sorted(Counter(row[2] for row in rows).items())),
        first_date=min((row[5] for row in rows), default=None),
        last_date=max((row[5] for row in rows), default=None),
    )


if __name__ == '__main__':
    summary = build_subsets(FOLDER / 'phenology_data.csv',
                            FOLDER / 'phenology_data_quality.json',
                            FOLDER / 'derived/paper_targets')
    subset = summary['combined']
    print(f"Four stages: {subset['rows']:,} observations; {subset['source_qualified_sites']:,} sites")
