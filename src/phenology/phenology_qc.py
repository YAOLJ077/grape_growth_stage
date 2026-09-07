"""Project-specific European phenology screening, policy v2 (root AGENTS.md).

These are review/quarantine rules, not universal physiological bounds.
"""
from collections import defaultdict
from datetime import date
from itertools import combinations

VERSION = "chronology-v2"
BUD = [1, 3, 5, 7, 9]
BRANCHES = [BUD + list(range(10, 20)),
            BUD + [53, 55, 57] + list(range(60, 70)) + [71, 73, 75, 77, 79, 81, 83, 85, 87, 89]]
ORDERED_PAIRS = sorted(set(pair for branch in BRANCHES for pair in combinations(branch, 2)))
INTERVALS = {(7, 65): (20, 100), (9, 65): (20, 100),
             (65, 81): (30, 120), (81, 89): (10, 90)}
WINDOWS = [(range(1, 10), "02-01", "06-15"),
           (range(10, 20), "03-01", "07-31"),
           (range(50, 60), "04-01", "07-15"),
           (range(60, 70), "05-01", "07-31"),
           (range(70, 80), "05-15", "09-15"),
           (range(80, 86), "07-01", "10-15"),
           (range(86, 90), "07-15", "11-15")]


def clean_records(records):
    """Return kept rows in input order and excluded row -> evidence list.

    Each row needs a compatible counterpart in every other observed ordered
    stage. Remove unsupported rows simultaneously, then recheck surviving stage
    pairs until stable. Empty stages no longer constrain other stages.
    """
    excluded = {}
    groups = defaultdict(list)
    ordinals = {}
    for row in records:
        stage, day = int(row[6]), date.fromisoformat(row[5])
        ordinals[row] = day.toordinal()
        window = next(((low, high) for stages, low, high in WINDOWS if stage in stages), None)
        if window and not window[0] <= row[5][5:] <= window[1]:
            excluded[row] = [dict(rule="seasonal_window", stage=stage,
                                  allowed_month_day=list(window), observed_date=row[5])]
        else:
            groups[(row[0], row[1], day.year)].append(row)
    for group in groups.values():
        active = set(group)
        iteration = 0
        while active:
            iteration += 1
            stages = defaultdict(list)
            for row in sorted(active):
                stages[int(row[6])].append(row)
            rejected = defaultdict(list)
            for early, late in ORDERED_PAIRS:
                left, right = stages.get(early), stages.get(late)
                if not left or not right:
                    continue
                low, high = INTERVALS.get((early, late), (0, 366))
                supported_left, supported_right = set(), set()
                for a in left:
                    for b in right:
                        if low <= ordinals[b] - ordinals[a] <= high:
                            supported_left.add(a)
                            supported_right.add(b)
                for rows, supported, others in [(left, supported_left, right), (right, supported_right, left)]:
                    for row in rows:
                        if row not in supported:
                            rejected[row].append(dict(
                                rule="phase_interval" if (early, late) in INTERVALS else "stage_order",
                                stages=[early, late], allowed_days=[low, high],
                                observed_date=row[5], counterpart_dates=sorted({other[5] for other in others}),
                                iteration=iteration,
                                variety_identity="reported_label" if row[1] else "unspecified_variety_pool"))
            if not rejected:
                break
            excluded.update(rejected)
            active.difference_update(rejected)
    return [row for row in records if row not in excluded], excluded
