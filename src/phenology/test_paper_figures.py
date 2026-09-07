"""Integration checks for the four-stage figure inventories."""
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


class PaperFigureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.targets = [r for r in read_csv(ROOT / 'data/phenology/phenology_data.csv')
                       if r['BBCH'] in {'07', '65', '81', '89'}]

    def test_map_has_every_target_site_and_all_observed_years(self):
        expected = defaultdict(set)
        counts = Counter()
        for row in self.targets:
            expected[row['site']].add(row['Date'][:4])
            counts[row['site']] += 1
        mapped = read_csv(ROOT / 'fig/study_area/site_inventory.csv')
        self.assertEqual(len(mapped), len(expected))
        self.assertEqual({r['site'] for r in mapped}, set(expected))
        for row in mapped:
            self.assertEqual(set(row['observed_years'].split(';')), expected[row['site']])
            self.assertEqual(int(row['n_years']), len(expected[row['site']]))
            self.assertEqual(int(row['n_observations']), counts[row['site']])

    def test_bar_counts_are_all_target_observations_in_sequence(self):
        bars = read_csv(ROOT / 'fig/phen_data/stage_counts.csv')
        self.assertEqual([r['BBCH'] for r in bars], ['07', '65', '81', '89'])
        self.assertEqual({r['BBCH']: int(r['count']) for r in bars},
                         dict(Counter(r['BBCH'] for r in self.targets)))

    def test_both_figures_trace_to_combined_file(self):
        source = ROOT / 'data/phenology/derived/paper_targets/observations.csv'
        expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        for path in ['fig/study_area/map_quality.json', 'fig/phen_data/plot_quality.json']:
            report = json.loads((ROOT / path).read_text())
            self.assertEqual(report['source'], str(source.relative_to(ROOT)))
            self.assertEqual(report['source_sha256'], expected_hash)


if __name__ == '__main__':
    unittest.main()
