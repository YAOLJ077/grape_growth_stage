"""Checks for combined target selection without complete-sequence filtering."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

try:
    from select_modeling_targets import build_subsets
except ImportError:
    build_subsets = None


COLUMNS = ['site', 'variety', 'country', 'lat', 'lon', 'Date', 'BBCH']
ROWS = [
    ['AT:one', '', 'AT', '48', '15', '2000-04-20', '07'],
    ['AT:one', '', 'AT', '48', '15', '2000-04-21', '07'],
    ['FR:two', 'Chardonnay', 'FR', '46', '3', '2000-06-15', '65'],
    ['FR:two', 'Chardonnay', 'FR', '46', '3', '2000-08-20', '81'],
    ['FR:two', 'Chardonnay', 'FR', '46', '3', '2002-08-20', '81'],
    ['SE:three', '', 'SE', '59', '18', '2001-08-20', '81'],
    ['FR:maturity', '', 'FR', '45', '2', '2000-09-20', '89'],
    ['FR:bud09', '', 'FR', '45', '2', '2000-04-20', '09'],
    ['DE:leaf', '', 'DE', '49', '9', '2000-04-25', '13'],
]


class TargetSelectionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build_subsets, 'The target-selection implementation is missing')
        self.temporary = tempfile.TemporaryDirectory(prefix='grape-target-test-')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.source = self.folder / 'inventory.csv'
        self.report = self.folder / 'inventory_quality.json'
        self.output = self.folder / 'selected'
        self.write_input(ROWS)

    def write_input(self, rows):
        with self.source.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(COLUMNS)
            writer.writerows(rows)
        self.report.write_text(json.dumps({
            'output_sha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
            'output_rows': len(rows), 'chronology_qc': {'policy': 'chronology-v2'},
        }))

    def read_output(self, name):
        self.assertTrue((self.output / name).is_file(), 'Combined observation export is missing')
        with (self.output / name).open(newline='') as stream:
            reader = csv.reader(stream)
            self.assertEqual(next(reader), COLUMNS)
            return list(reader)

    def test_keeps_single_stage_sites_all_countries_and_partial_years(self):
        build_subsets(self.source, self.report, self.output)
        self.assertEqual(self.read_output('observations.csv'), ROWS[:7])

    def test_all_four_stages_in_same_file_other_codes_excluded_and_no_split_csvs(self):
        build_subsets(self.source, self.report, self.output)
        selected = self.read_output('observations.csv')
        self.assertIn(ROWS[6], selected)
        self.assertNotIn(ROWS[7], selected)
        self.assertNotIn(ROWS[8], selected)
        self.assertEqual(sorted(p.name for p in self.output.glob('*.csv')), ['observations.csv'])

    def test_preserves_source_bytes_and_reports_exact_counts(self):
        before = self.source.read_bytes()
        build_subsets(self.source, self.report, self.output)
        self.assertEqual(self.source.read_bytes(), before)
        report = json.loads((self.output / 'quality.json').read_text())
        self.assertNotIn('roles', report)
        self.assertNotIn('role_definition', report)
        combined = report['combined']
        self.assertEqual(combined['rows'], 7)
        self.assertEqual(combined['source_qualified_sites'], 4)
        self.assertEqual(combined['counts_by_stage'], {'07': 2, '65': 1, '81': 3, '89': 1})
        self.assertEqual(combined['counts_by_country'], {'AT': 2, 'FR': 4, 'SE': 1})
        self.assertEqual(report['non_target_rows'], 2)
        self.assertEqual(report['combined']['rows'], 7)
        self.assertEqual(report['combined']['sha256'], hashlib.sha256((self.output / 'observations.csv').read_bytes()).hexdigest())

    def test_stale_source_hash_fails_before_creating_outputs(self):
        self.source.write_bytes(self.source.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            build_subsets(self.source, self.report, self.output)
        self.assertFalse(self.output.exists())

    def test_duplicate_source_records_are_rejected_not_silently_removed(self):
        self.write_input(ROWS + [ROWS[0]])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            build_subsets(self.source, self.report, self.output)
        self.assertFalse(self.output.exists())

    def test_rebuilding_is_deterministic(self):
        build_subsets(self.source, self.report, self.output)
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        build_subsets(self.source, self.report, self.output)
        self.assertEqual({p.name: p.read_bytes() for p in self.output.iterdir()}, before)


if __name__ == '__main__':
    unittest.main()
