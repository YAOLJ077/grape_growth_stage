"""Run with: python3 -m unittest discover -s src/phenology -p 'test_*.py'."""
import unittest
from organize_phenology import bbch_code, normalized_date, coordinate, transform, high_confidence, in_study_period


class NormalizationTests(unittest.TestCase):
    def test_inclusive_1951_cutoff(self):
        self.assertFalse(in_study_period("1950-12-31"))
        self.assertFalse(in_study_period("1349-09-19"))
        self.assertTrue(in_study_period("1951-01-01"))
        self.assertTrue(in_study_period("2026-06-24"))
        self.assertFalse(in_study_period(""))
        self.assertFalse(in_study_period("1951-02-29"))

    def test_only_direct_bbch_is_eligible(self):
        row = ("DE:dwd:1", "", "DE", "49", "8", "2001-09-01", "89")
        self.assertTrue(high_confidence(row, "direct"))
        self.assertFalse(high_confidence(row, "mapped_medium_confidence"))
        self.assertFalse(high_confidence(row, "unmapped"))
        self.assertFalse(high_confidence(row[:-1] + ("",), "direct"))
        self.assertFalse(high_confidence(row[:-1] + ("100",), "direct"))

    def test_direct_precedes_fallback(self):
        row = dict(taxon_fullname="Plantae Vitis vinifera", cultivar="",
                   site_id="07815", stage_id="30", bbch_code="89", latitude="49",
                   longitude="8", date="2001-09-01")
        result, mapping, _ = transform(row, "germany")
        self.assertTrue(high_confidence(result, mapping))
        row["bbch_code"] = ""
        result, mapping, _ = transform(row, "germany")
        self.assertFalse(high_confidence(result, mapping))

    def test_bbch_zero_and_fraction(self):
        self.assertEqual(bbch_code("0.0"), "00")
        self.assertEqual(bbch_code("7.0"), "07")
        for invalid in ("7.5", "100", "nan", "", "Infinity"):
            self.assertEqual(bbch_code(invalid), "")

    def test_dates_include_historical_and_leap_years(self):
        self.assertEqual(normalized_date("1349-09-19"), "1349-09-19")
        self.assertEqual(normalized_date("2000-02-29"), "2000-02-29")
        self.assertEqual(normalized_date("1900-02-29"), "")

    def test_coordinates(self):
        self.assertEqual(coordinate("48.3000", 90), "48.3")
        for value in ("-9999", "91", "inf", "nan"):
            self.assertEqual(coordinate(value, 90), "")

    def test_unmapped_pep_phase_and_species_prefix(self):
        row = dict(species="Vitis vinifera", provider_id="101", s_id="0012",
                   subspecies="Vitis vinifera Riesling", lat="49", lon="8",
                   phase_id="250", date="1960-03-01")
        result, status, stage = transform(row, "pep725")
        self.assertEqual(result, ("DE:pep725:101:0012", "Riesling", "DE", "49", "8", "1960-03-01", ""))
        self.assertEqual(status, "unmapped")
        row["phase_id"] = "100"
        self.assertEqual(transform(row, "pep725")[0][-1], "89")
        row["provider_id"] = "999"
        with self.assertRaises(ValueError):
            transform(row, "pep725")

    def test_species_filter_and_dwd_mapping(self):
        self.assertIsNone(transform({"taxon_fullname": "Plantae Prunus persica"}, "france"))
        row = dict(taxon_fullname="Plantae Vitis vinifera", cultivar="Weinrebe, frühe Reife",
                   site_id="07815", stage_id="30", bbch_code="", latitude="49",
                   longitude="8", date="2001-09-01")
        result, status, _ = transform(row, "germany")
        self.assertEqual(result[0], "DE:dwd:07815")
        self.assertEqual(result[-1], "89")
        self.assertEqual(status, "mapped_medium_confidence")


if __name__ == "__main__":
    unittest.main()
