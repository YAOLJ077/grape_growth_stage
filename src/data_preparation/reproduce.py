#!/usr/bin/env python3
"""Reconstruct the final observation population and its frozen primary split.

Uses only prepared observations, weather eligibility and frozen site assignments.
No predictions, fitted models, residuals or outcome-based selection are read.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
import gzip
import hashlib
import io
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIELDS = ["site", "variety", "country", "lat", "lon", "Date", "BBCH"]
ASSIGNMENTS = ["partition", "inner_fold", "temperature_zone_id"]
FINAL_FIELDS = FIELDS + ["observation_id", "season"] + ASSIGNMENTS
QC = ROOT / "data/phenology/derived/target_qc_v3_20260912"
COHORT = ROOT / "model_run/results/publication_cohort_20260910"
PROTOCOL = ROOT / "model_run/results/publication_factorial_20260911_v3/protocols.csv"
REFERENCE = ROOT / "model_run/results/cleaned_reevaluation_20260912/observations.csv"
PARTITIONS = ROOT / "model_run/results/pooled_calibration_20260912"
EXPECTED = {"calibration": (59472, 2534, 1434), "test": (15146, 635, 357)}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read_table(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError(f"Malformed CSV: {path}")
        return reader.fieldnames, rows


def identity(row):
    fields = [row[name] for name in FIELDS]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def relative(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(Path(path).resolve())


def require_hash(path, expected):
    if digest(path) != expected:
        raise ValueError(f"Frozen input hash differs: {path}")


def reconstruct(qc_dir=QC, cohort_dir=COHORT, protocols_path=PROTOCOL):
    """Preserve QC row order, exact field strings and surviving site assignments."""
    qc_dir, cohort_dir, protocols_path = map(Path, (qc_dir, cohort_dir, protocols_path))
    source_paths = [qc_dir / "summary.json", qc_dir / "observations.csv",
                    cohort_dir / "manifest.json", cohort_dir / "observations.csv",
                    cohort_dir / "sites.csv", protocols_path]
    hashes = {path: digest(path) for path in source_paths}
    qc_meta = json.loads((qc_dir / "summary.json").read_text())
    if qc_meta["policy"] != "four_target_qc_v3_20260912":
        raise ValueError("Require the frozen four-target QC-v3 policy")
    require_hash(qc_dir / "observations.csv", qc_meta["output_hashes"]["observations.csv"])
    cohort_meta = json.loads((cohort_dir / "manifest.json").read_text())
    for name in ["observations.csv", "sites.csv"]:
        require_hash(cohort_dir / name, cohort_meta["files"][name])

    columns, clean = read_table(qc_dir / "observations.csv")
    if columns != FIELDS or len(clean) != 75738:
        raise ValueError("Revised QC inventory differs from the frozen 75,738-row population")
    _, original = read_table(cohort_dir / "observations.csv")
    _, sites = read_table(cohort_dir / "sites.csv")
    _, all_protocols = read_table(protocols_path)
    coordinates, eligible_years = {}, set()
    for row in original:
        coordinate = (row["country"], row["lat"], row["lon"])
        if row["site"] in coordinates and coordinates[row["site"]] != coordinate:
            raise ValueError("An original frozen site has conflicting coordinates or country")
        coordinates[row["site"]] = coordinate
        eligible_years.add((row["site"], row["season"]))
    groups = {row["site"]: row["group_id"] for row in sites}
    if len(groups) != len(sites) or any(not value for value in groups.values()):
        raise ValueError("Duplicate site or missing original independence group")
    protocol = {}
    for row in all_protocols:
        if row["experiment"] != "site_holdout":
            continue
        key = (row["site"], row["season"])
        if key in protocol:
            raise ValueError("Duplicate frozen primary site-year assignment")
        protocol[key] = row

    final, eligibility, observed_ids = [], [], set()
    for row in clean:
        event_id = identity(row)
        if event_id in observed_ids:
            raise ValueError("Duplicate canonical QC observation")
        observed_ids.add(event_id)
        observed = date.fromisoformat(row["Date"])
        if observed.isoformat() != row["Date"] or row["BBCH"] not in {"07", "65", "81", "89"}:
            raise ValueError("Noncanonical date or nontarget stage")
        season = str(observed.year)
        source = coordinates.get(row["site"])
        actual = [float(row[name]) for name in ("lat", "lon")]
        matching = source is not None and row["country"] == source[0]
        matching = matching and all(math.isfinite(value) for value in actual)
        matching = matching and actual == [float(source[1]), float(source[2])]
        status = ("outside_frozen_site_or_coordinates" if not matching else
                  "outside_frozen_site_year" if (row["site"], season) not in eligible_years else
                  "eligible")
        eligibility.append(dict(row, observation_id=event_id, season=season, match_status=status))
        if status != "eligible":
            continue
        assignment = protocol.get((row["site"], season))
        if assignment is None or assignment["partition"] not in EXPECTED:
            raise ValueError("An eligible observation has no frozen primary assignment")
        final.append(dict(row, observation_id=event_id, season=season,
                          **{name: assignment[name] for name in ASSIGNMENTS}))

    if len(final) != 74618 or len({row["site"] for row in final}) != 3169:
        raise ValueError("Final observation or site count differs from the published population")
    partitions = {part: [row for row in final if row["partition"] == part] for part in EXPECTED}
    site_assignments, group_assignments = {}, {}
    for row in final:
        value = tuple(row[name] for name in ASSIGNMENTS)
        site, group = row["site"], groups[row["site"]]
        for key, mapping in [(site, site_assignments), (group, group_assignments)]:
            if key in mapping and mapping[key] != value:
                raise ValueError("An original site/group crosses partitions, folds or zones")
            mapping[key] = value
    summary = {}
    for part, rows in partitions.items():
        actual = (len(rows), len({row["site"] for row in rows}), len({groups[row["site"]] for row in rows}))
        if actual != EXPECTED[part]:
            raise ValueError(f"Frozen {part} population differs: {actual}")
        folds = {row["inner_fold"] for row in rows}
        if folds != ({"0", "1", "2", "3"} if part == "calibration" else {"-1"}):
            raise ValueError(f"Unexpected frozen folds in {part}")
        summary[part] = dict(zip(["observations", "reported_sites", "independence_groups"], actual))
    for path, expected in hashes.items():
        require_hash(path, expected)
    report = dict(scope="QC-v3 observations matched to original frozen site-year eligibility and primary assignments",
                  observations=len(final), reported_sites=len(site_assignments),
                  independence_groups=len(group_assignments), partitions=summary,
                  stage_counts=dict(sorted(Counter(row["BBCH"] for row in final).items())),
                  eligibility_counts=dict(sorted(Counter(row["match_status"] for row in eligibility).items())),
                  input_hashes={relative(path): value for path, value in hashes.items()},
                  code_sha256=digest(__file__), model_predictions_read=False,
                  weather_downloaded=False, models_refitted=False)
    return final, partitions, eligibility, report


def verify(final, partitions, report):
    references = [(REFERENCE, FIELDS, final)] + [
        (PARTITIONS / f"{part}_observations.csv.gz", FINAL_FIELDS, rows)
        for part, rows in partitions.items()]
    verified = {}
    for path, columns, rows in references:
        fields, expected = read_table(path)
        actual = [{name: row[name] for name in columns} for row in rows]
        if fields != columns or actual != expected:
            raise ValueError(f"Reconstructed fields, values or row order differ: {path}")
        verified[relative(path)] = digest(path)
    report["verified_against_frozen_tables"] = True
    report["reference_hashes"] = verified


def write_table(path, columns, rows):
    # Deterministic gzip metadata; decompressed CSV retains original field strings.
    if path.suffix == ".gz":
        with path.open("xb") as raw:
            with gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as zipped:
                with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(rows)
    else:
        with path.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Compare every field and row order against all three final frozen tables")
    parser.add_argument("--output", type=Path, help="Write reconstructed tables to a new directory; existing directories are refused")
    parser.add_argument("--qc-dir", type=Path, default=QC, help="QC-v3 directory, including observations.csv and summary.json")
    parser.add_argument("--cohort-dir", type=Path, default=COHORT, help="Original frozen weather-eligible cohort")
    parser.add_argument("--protocols", type=Path, default=PROTOCOL, help="Original frozen protocols.csv")
    args = parser.parse_args(argv)
    if args.output is not None and args.output.exists():
        parser.error("--output must be a new directory")
    final, partitions, eligibility, report = reconstruct(args.qc_dir, args.cohort_dir, args.protocols)
    if args.verify or args.output is None:
        verify(final, partitions, report)
    if args.output is not None:
        args.output.mkdir(parents=True, exist_ok=False)
        write_table(args.output / "observations.csv", FIELDS, final)
        for part, rows in partitions.items():
            write_table(args.output / f"{part}_observations.csv.gz", FINAL_FIELDS, rows)
        write_table(args.output / "eligibility.csv.gz", FIELDS + ["observation_id", "season", "match_status"], eligibility)
        report["output_hashes"] = {path.name: digest(path) for path in sorted(args.output.iterdir())}
        (args.output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
