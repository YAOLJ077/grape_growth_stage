#!/usr/bin/env python3
"""Consolidate direct-BBCH grapevine records from all available countries.

Only Python's standard library is required. Source files are never modified.
Rebuild: python3 src/phenology/organize_phenology.py
"""
from collections import Counter, defaultdict
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
from pathlib import Path
import re
from phenology_qc import clean_records, VERSION as QC_VERSION

ROOT = Path(__file__).resolve().parents[2] / 'data/phenology'
COLUMNS = ["site", "variety", "country", "lat", "lon", "Date", "BBCH"]
MIN_DATE = "1951-01-01"
INPUTS = [
    ("france", "processed/france_grape_phenology_complete.csv", ","),
    ("germany", "processed/germany_grape_phenology_complete.csv", ","),
    ("tempo_other", "raw/france_tempo/tempo_other_countries_observations_joined.csv", ","),
    ("pep725", "raw/pep725/pep725_20260701_0.csv", ";"),
]
# Country attribution follows the provider list in raw/pep725/README.txt.
PEP_COUNTRIES = {"7": "LU", "13": "FR", "14": "ES", "101": "DE", "201": "SI",
                 "301": "AT", "501": "CH", "601": "SK", "1401": "ES", "1402": "ES",
                 "1802": "SE", "2101": "HR", "2201": "CZ", "2601": "BA", "2701": "ME"}
TEMPO_COUNTRIES = {"France": "FR", "Allemagne": "DE", "Suisse": "CH", "Espagne": "ES",
                   "Italie": "IT", "Belgique": "BE", "Grèce": "GR", "Andorre": "AD",
                   "Inconnu": ""}
# Existing repository mapping, with medium-confidence adaptations kept explicit.
DWD_BBCH = {"3": "07", "4": "11", "5": "61", "6": "65", "7": "69",
            "30": "89", "31": "92", "32": "95", "40": "89", "42": "81"}
PEP_BBCH = {"100": "89", "201": "92", "205": "95"}
MISSING = {"", "nan", "na", "n/a", "null", "none", "<na>", "-9999", "-9999.0"}


def clean(value):
    result = re.sub(r"\s+", " ", str(value or "")).strip()
    return "" if result.casefold() in MISSING else result


def integer_code(value):
    text = clean(value)
    if not text:
        return ""
    try:
        number = Decimal(text)
        if not number.is_finite() or number != number.to_integral_value():
            return ""
        return str(int(number))
    except InvalidOperation:
        return ""


def bbch_code(value):
    number = integer_code(value)
    return f"{int(number):02d}" if number and 0 <= int(number) <= 99 else ""


def normalized_date(value):
    text = clean(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def coordinate(value, limit):
    text = clean(value)
    if not text:
        return ""
    try:
        number = Decimal(text)
        if not number.is_finite() or abs(number) > limit:
            return ""
        return "0" if number == 0 else format(number.normalize(), "f")
    except InvalidOperation:
        return ""


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_input(relative):
    original = ROOT / relative
    with original.open("rb") as stream:
        header = stream.read(512)
    if not header.startswith(b"version https://git-lfs.github.com/spec/v1"):
        return original
    lines = header.decode("ascii").splitlines()
    expected_hash = next(line.split("sha256:")[1] for line in lines if line.startswith("oid "))
    expected_size = int(next(line.split()[1] for line in lines if line.startswith("size ")))
    cached = ROOT / ".source_cache" / original.name
    if not cached.exists() or cached.stat().st_size != expected_size or sha256(cached) != expected_hash:
        raise RuntimeError(f"Missing verified LFS input: {relative}; run fetch_phenology_inputs.py first")
    return cached


def transform(row, kind):
    """Return the seven fields, mapping provenance and raw stage, or None for non-grape taxa."""
    taxon = row.get("species", "") if kind == "pep725" else row.get("taxon_fullname", "")
    if not re.search(r"\bVitis\s+vinifera\b", taxon, flags=re.I):
        return None
    if kind == "pep725":
        provider = integer_code(row["provider_id"])
        if provider not in PEP_COUNTRIES:
            raise ValueError(f"Unmapped PEP725 provider: {provider}")
        country, namespace = PEP_COUNTRIES[provider], f"pep725:{provider}"
        site_id = clean(row["s_id"])
        variety = re.sub(r"^Vitis\s+vinifera\s*", "", clean(row["subspecies"]), flags=re.I).strip()
        latitude, longitude = row["lat"], row["lon"]
        stage = integer_code(row["phase_id"])
        direct = bbch_code(stage)
        mapped = direct or PEP_BBCH.get(stage, "")
    else:
        if kind == "germany":
            country, namespace = "DE", "dwd"
        else:
            name = row["country_name"]
            if name not in TEMPO_COUNTRIES:
                raise ValueError(f"Unmapped TEMPO country: {name}")
            country, namespace = TEMPO_COUNTRIES[name], "tempo"
        site_id = clean(row["site_id"])
        variety = clean(row.get("cultivar"))
        if kind == "tempo_other" and " - " in taxon:
            variety = clean(taxon.split(" - ", 1)[1])
        latitude, longitude = row["latitude"], row["longitude"]
        stage = integer_code(row["stage_id"])
        direct = bbch_code(row.get("bbch_code", row.get("stage_code", "")))
        mapped = direct or (DWD_BBCH.get(stage, "") if kind == "germany" else "")
    if not site_id:
        raise ValueError(f"Missing source site identifier in {kind}; no invented site is permitted")
    site = f"{country or 'XX'}:{namespace}:{site_id}"
    status = "direct" if direct else ("mapped_medium_confidence" if mapped else "unmapped")
    result = (site, variety, country, coordinate(latitude, 90), coordinate(longitude, 180),
              normalized_date(row["date"]), mapped)
    return result, status, stage


def event_id(row):
    return hashlib.sha256(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def high_confidence(row, mapping):
    """High conversion confidence means a valid direct source BBCH code only."""
    return mapping == "direct" and bool(re.fullmatch(r"[0-9]{2}", row[-1]))


def in_study_period(value):
    """Include 1951 onward; invalid or missing dates never qualify."""
    normalized = normalized_date(value)
    return bool(normalized) and normalized >= MIN_DATE


def build():
    resolved = [(kind, relative, delimiter, resolve_input(relative)) for kind, relative, delimiter in INPUTS]
    unique = set()
    stats = {"columns": COLUMNS, "as_of_date": date.today().isoformat(), "inputs": [],
             "bbch_confidence_policy": "direct source BBCH only; exclude inferred mappings and unmapped phases before deduplication",
             "minimum_date_inclusive": MIN_DATE,
             "date_policy": "retain observations from 1951 onward; date exclusions follow BBCH confidence filtering and precede deduplication",
             "mapping_counts_before_deduplication": Counter(), "unmapped_source_stages": Counter(),
             "licenses_by_source": {}, "invalid_fields_before_deduplication": Counter()}
    provenance_path = ROOT / "phenology_data_provenance.jsonl.gz"
    provenance_temp = provenance_path.with_suffix(".gz.part")
    # One provenance entry for every input row, including excluded and merged rows.
    with provenance_temp.open("wb") as raw_provenance:
        with gzip.GzipFile(filename="", fileobj=raw_provenance, mode="wb", mtime=0) as provenance:
            for kind, relative, delimiter, path in resolved:
                counts = Counter()
                licenses = Counter()
                with path.open(encoding="utf-8-sig", newline="") as stream:
                    reader = csv.DictReader(stream, delimiter=delimiter)
                    for record_number, row in enumerate(reader, start=1):
                        counts["input_rows"] += 1
                        transformed = transform(row, kind)
                        audit = {"source": relative, "record_number": record_number,
                                 "observation_id": row.get("observation_id", "")}
                        if transformed is None:
                            counts["excluded_non_grape"] += 1
                            audit.update(status="excluded_non_grape", taxon=row.get("taxon_fullname", row.get("species", "")))
                        else:
                            result, mapping, stage = transformed
                            license_name = row.get("license_short", row.get("license_name", ""))
                            licenses[license_name or "unspecified"] += 1
                            counts["grape_rows"] += 1
                            stats["mapping_counts_before_deduplication"][mapping] += 1
                            if mapping == "unmapped":
                                stats["unmapped_source_stages"][f"{kind}:{stage}"] += 1
                            for field, raw_value, normalized in [("Date", row["date"], result[5]),
                                ("lat", row.get("latitude", row.get("lat")), result[3]),
                                ("lon", row.get("longitude", row.get("lon")), result[4])]:
                                if clean(raw_value) and not normalized:
                                    stats["invalid_fields_before_deduplication"][field] += 1
                            audit.update(source_stage=stage, bbch_mapping=mapping, license=license_name,
                                         source_provider=row.get("provider_id", row.get("datasource_id", "")))
                            if not high_confidence(result, mapping):
                                reason = "excluded_inferred_bbch" if mapping == "mapped_medium_confidence" else "excluded_unmapped_bbch"
                                counts[reason] += 1
                                audit.update(status=reason, candidate_event_id=event_id(result))
                            elif not in_study_period(result[5]):
                                reason = "excluded_before_1951" if result[5] else "excluded_missing_or_invalid_date"
                                counts[reason] += 1
                                audit.update(status=reason, candidate_event_id=event_id(result), source_date=row["date"])
                            else:
                                duplicate = result in unique
                                counts["duplicate_rows" if duplicate else "output_rows"] += 1
                                unique.add(result)
                                audit.update(status="duplicate" if duplicate else "retained", event_id=event_id(result))
                        provenance.write((json.dumps(audit, ensure_ascii=False, separators=(",", ":")) + "\n").encode())
                for key in ("input_rows", "grape_rows", "excluded_non_grape", "excluded_inferred_bbch",
                            "excluded_unmapped_bbch", "excluded_before_1951", "excluded_missing_or_invalid_date",
                            "duplicate_rows", "output_rows"):
                    counts.setdefault(key, 0)
                assert counts["input_rows"] == sum(counts[k] for k in (
                    "excluded_non_grape", "excluded_inferred_bbch", "excluded_unmapped_bbch",
                    "excluded_before_1951", "excluded_missing_or_invalid_date", "duplicate_rows", "output_rows"))
                stats["inputs"].append({"path": relative, "sha256": sha256(path), "bytes": path.stat().st_size, **counts})
                stats["licenses_by_source"][kind] = dict(licenses)
                print(f"{kind}: {counts['input_rows']:,} input → {counts['output_rows']:,} unique grape records", flush=True)
    records = sorted(unique, key=lambda r: (r[2], r[0], r[5], r[6], r[1], r[3], r[4]))
    before_qc = records
    records, exclusions = clean_records(records)
    excluded_hashes = {event_id(row): evidence for row, evidence in exclusions.items()}
    quarantine_path = ROOT / "phenology_data_quarantine.jsonl.gz"
    quarantine_temp = quarantine_path.with_suffix(".gz.part")
    with quarantine_temp.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream:
            for row in before_qc:
                if row in exclusions:
                    item = dict(event_id=event_id(row), record=dict(zip(COLUMNS, row)),
                                policy=QC_VERSION, evidence=exclusions[row])
                    stream.write((json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode())
    # Reconcile every source occurrence, including duplicates, to final QC status.
    sources = {source["path"]: source for source in stats["inputs"]}
    for source in sources.values():
        source["output_rows_before_chronology_qc"] = source["output_rows"]
        source["duplicate_rows_before_chronology_qc"] = source["duplicate_rows"]
        source["excluded_chronology_qc"] = 0
    revised_provenance = ROOT / "phenology_data_provenance.qc.part"
    with gzip.open(provenance_temp, "rt", encoding="utf-8") as reader, revised_provenance.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as writer:
            for line in reader:
                item = json.loads(line)
                if item["status"] in {"retained", "duplicate"} and item["event_id"] in excluded_hashes:
                    source = sources[item["source"]]
                    source["output_rows" if item["status"] == "retained" else "duplicate_rows"] -= 1
                    source["excluded_chronology_qc"] += 1
                    item["pre_qc_status"] = item["status"]
                    item["status"] = "excluded_chronology_qc"
                    item["candidate_event_id"] = item.pop("event_id")
                    item["qc_rules"] = sorted({e["rule"] for e in excluded_hashes[item["candidate_event_id"]]})
                writer.write((json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n").encode())
    revised_provenance.replace(provenance_temp)
    quarantine_temp.replace(quarantine_path)
    rules = Counter(e["rule"] for evidence in exclusions.values() for e in {v["rule"]: v for v in evidence}.values())
    stats["chronology_qc"] = dict(
        policy=QC_VERSION, rows_before=len(before_qc), rows_quarantined=len(exclusions), rows_after=len(records),
        sites_before=len({r[0] for r in before_qc}), sites_after=len({r[0] for r in records}),
        rules=dict(sorted(rules.items())),
        excluded_by_country=dict(sorted(Counter(r[2] for r in exclusions).items())),
        excluded_by_source=dict(sorted(Counter(r[0].split(":")[1] for r in exclusions).items())),
        excluded_by_bbch=dict(sorted(Counter(r[6] for r in exclusions).items())),
        excluded_by_year=dict(sorted(Counter(r[5][:4] for r in exclusions).items())),
        quarantine_sha256=sha256(quarantine_path),
        pre_qc_rows_sha256=hashlib.sha256(json.dumps(before_qc, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest())
    assert len(records) + len(exclusions) == len(before_qc)
    assert clean_records(records)[1] == {}, "QC result is not stable"
    for source in sources.values():
        assert source["input_rows"] == sum(source[k] for k in (
            "excluded_non_grape", "excluded_inferred_bbch", "excluded_unmapped_bbch",
            "excluded_before_1951", "excluded_missing_or_invalid_date", "excluded_chronology_qc",
            "duplicate_rows", "output_rows"))
    output = ROOT / "phenology_data.csv"
    temporary = output.with_suffix(".csv.part")
    by_country = defaultdict(list)
    by_site_coords = defaultdict(set)
    possible_overlap = defaultdict(set)
    missing = Counter()
    for record in records:
        site, variety, country, latitude, longitude, event_date, bbch = record
        by_country[country or "unknown"].append(record)
        by_site_coords[site].add((latitude, longitude))
        missing.update(column for column, value in zip(COLUMNS, record) if not value)
        if country and latitude and longitude and event_date and bbch:
            key = (country, round(float(latitude), 4), round(float(longitude), 4), event_date, bbch)
            possible_overlap[key].add(site.split(":")[1])
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(records)
    temporary.replace(output)
    provenance_temp.replace(provenance_path)
    stats.update(output_rows=len(records), source_qualified_sites=len(by_site_coords),
                 output_sha256=sha256(output), provenance_sha256=sha256(provenance_path),
                 exact_duplicates_after_export=0,
                 missing_fields={column: missing[column] for column in COLUMNS},
                 date_min=min(r[5] for r in records if r[5]), date_max=max(r[5] for r in records if r[5]),
                 future_dated_rows=sum(r[5] > stats["as_of_date"] for r in records),
                 sites_with_multiple_coordinate_pairs=sum(len(v) > 1 for v in by_site_coords.values()),
                 possible_cross_source_coincidence_keys=sum(len(v) > 1 for v in possible_overlap.values()),
                 dwd_maturity_group_rows=sum(r[0].split(":")[1] == "dwd" and r[1].startswith("Weinrebe,") for r in records),
                 countries={})
    for country, group in sorted(by_country.items()):
        stats["countries"][country] = {
            "rows": len(group), "sites": len({r[0] for r in group}),
            "date_min": min((r[5] for r in group if r[5]), default=""),
            "date_max": max((r[5] for r in group if r[5]), default=""),
            "missing_variety": sum(not r[1] for r in group), "missing_BBCH": sum(not r[6] for r in group),
        }
    assert len(records) == sum(source["output_rows"] for source in stats["inputs"])
    assert missing["BBCH"] == 0
    assert all(in_study_period(r[5]) for r in records)
    (ROOT / "phenology_data_quality.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output.name}: {len(records):,} rows; {len(by_site_coords):,} source-qualified sites", flush=True)
    return stats


if __name__ == "__main__":
    build()
