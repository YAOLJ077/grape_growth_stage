"""Behavioural checks for approved chronology QC; no external packages."""
from datetime import date, timedelta
import unittest
import organize_phenology


def record(stage, day, variety="Riesling", site="DE:test:1"):
    return (site, variety, "DE", "49", "8", day, f"{stage:02d}")


class ChronologyTests(unittest.TestCase):
    def clean(self, rows):
        self.assertTrue(hasattr(organize_phenology, "clean_records"),
                        "The approved chronology filter has not been implemented")
        return organize_phenology.clean_records(rows)

    def test_seasonal_window_boundaries(self):
        for stage, start, end in [(7,"2000-02-01","2000-06-15"),
                                  (11,"2000-03-01","2000-07-31"),
                                  (53,"2000-04-01","2000-07-15"),
                                  (65,"2000-05-01","2000-07-31"),
                                  (75,"2000-05-15","2000-09-15"),
                                  (81,"2000-07-01","2000-10-15"),
                                  (89,"2000-07-15","2000-11-15")]:
            with self.subTest(stage=stage):
                good = [record(stage,start), record(stage,end)]
                bad = record(stage,(date.fromisoformat(end)+timedelta(days=1)).isoformat())
                kept, excluded = self.clean(good+[bad])
                self.assertEqual(kept,good)
                self.assertEqual(set(excluded),{bad})

    def test_reversed_stages_quarantine_both_endpoints(self):
        rows=[record(61,"2000-06-15"),record(69,"2000-06-01"),record(89,"2000-09-01")]
        kept,excluded=self.clean(rows)
        self.assertEqual(kept,rows[2:])
        self.assertEqual(set(excluded),set(rows[:2]))

    def test_intervals_are_inclusive(self):
        for early,late,start,minimum,maximum in [(7,65,"2000-04-15",20,100),
                                                (9,65,"2000-04-15",20,100),
                                                (65,81,"2000-06-15",30,120),
                                                (81,89,"2000-07-15",10,90)]:
            for lag in [minimum-1,minimum,maximum,maximum+1]:
                with self.subTest(pair=(early,late),lag=lag):
                    end=(date.fromisoformat(start)+timedelta(days=lag)).isoformat()
                    rows=[record(early,start),record(late,end)]
                    kept,excluded=self.clean(rows)
                    self.assertEqual(len(kept),2 if minimum<=lag<=maximum else 0)

    def test_leaf_inflorescence_overlap_allowed(self):
        rows=[record(19,"2000-06-01"),record(53,"2000-05-01")]
        self.assertEqual(self.clean(rows),(rows,{}))

    def test_groups_do_not_cross_varieties_sites_or_years(self):
        rows=[record(7,"2000-06-10"),record(65,"2000-06-01",variety=""),
              record(65,"2000-06-01",site="DE:other:1"),record(65,"2001-06-01")]
        self.assertEqual(self.clean(rows),(rows,{}))

    def test_feasible_pair_does_not_hide_an_unsupported_record(self):
        rows=[record(7,"2000-04-01"),record(7,"2000-06-10"),record(65,"2000-06-01")]
        kept,excluded=self.clean(rows)
        self.assertEqual(kept,[rows[0],rows[2]])
        self.assertEqual(set(excluded),{rows[1]})

    def test_seasonal_filter_precedes_pair_checks(self):
        rows=[record(7,"2000-04-01"),record(65,"2000-01-01")]
        kept,excluded=self.clean(rows)
        self.assertEqual(kept,rows[:1])
        self.assertEqual(set(excluded),{rows[1]})

    def test_no_dormancy_senescence_calendar_or_order_filter(self):
        rows=[record(0,"2000-12-01"),record(95,"2000-03-01"),record(97,"2000-01-01")]
        self.assertEqual(self.clean(rows),(rows,{}))

    def test_adjacent_stages_can_share_date(self):
        rows=[record(61,"2000-06-01"),record(65,"2000-06-01")]
        self.assertEqual(self.clean(rows),(rows,{}))

    def test_cleaning_is_order_independent_and_idempotent(self):
        rows=[record(7,"2000-06-01"),record(65,"2000-05-01"),record(89,"2000-09-01")]
        kept,excluded=self.clean(rows)
        reverse,reverse_excluded=self.clean(list(reversed(rows)))
        self.assertEqual(set(kept),set(reverse))
        self.assertEqual(excluded,reverse_excluded)
        self.assertEqual(self.clean(kept),(kept,{}))


if __name__ == "__main__":
    unittest.main()
