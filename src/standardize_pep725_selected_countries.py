#!/usr/bin/env python
"""Standardize selected PEP725 grape phenology countries.

This script extracts Austria, Slovakia, Switzerland, and Spain from the
PEP725 grape extract and writes a standardized table compatible with the existing
France TEMPO and Germany DWD processed tables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd


STANDARD_COLUMNS = [
    "source_system",
    "source_dataset",
    "observation_id",
    "date",
    "year",
    "month",
    "day",
    "doy",
    "country",
    "country_name",
    "site_id",
    "site_name",
    "latitude",
    "longitude",
    "altitude",
    "altitude_reported",
    "altitude_ign",
    "altitude_source",
    "region",
    "department",
    "commune",
    "natural_region",
    "federal_state",
    "taxon_id",
    "taxon_name",
    "taxon_fullname",
    "cultivar",
    "cultivar_group",
    "stage_id",
    "stage_code",
    "bbch_code",
    "stage_eventcode",
    "stage_event",
    "stage_description",
    "datasource_id",
    "datasource_name",
    "license_id",
    "license_name",
    "quality_level",
    "date_quality_flag",
    "reporter_type",
    "additionalData_id",
    "additionalData_raw",
    "source_file",
    "dedup_group_id",
    "is_training_record",
]

EXTRA_COLUMNS = [
    "analysis_tier",
    "analysis_tier_note",
]

PROVIDERS = {
    14: {
        "country": "ES",
        "country_name": "Spain",
        "provider_name": "COST725 member Spain",
        "tier": 2,
    },
    201: {
        "country": "SI",
        "country_name": "Slovenia",
        "provider_name": "PEP725 member meteo.si",
        "tier": None,
    },
    301: {
        "country": "AT",
        "country_name": "Austria",
        "provider_name": "PEP725 member ZAMG / GeoSphere Austria",
        "tier": 1,
    },
    501: {
        "country": "CH",
        "country_name": "Switzerland",
        "provider_name": "PEP725 member METEOSCHWEIZ",
        "tier": 2,
    },
    601: {
        "country": "SK",
        "country_name": "Slovakia",
        "provider_name": "PEP725 member SHMU Slovakia",
        "tier": 2,
    },
    1401: {
        "country": "ES",
        "country_name": "Spain",
        "provider_name": "PEP725 member SMC-Meteocat",
        "tier": 2,
    },
    1402: {
        "country": "ES",
        "country_name": "Spain",
        "provider_name": "PEP725 member AEMET",
        "tier": 2,
    },
}

SELECTED_PROVIDER_IDS = [14, 301, 501, 601, 1401, 1402]

TIER_NOTES = {
    1: "Core extension country: high station count and long time coverage.",
    2: "Supplementary extension country: useful for extended or sensitivity analyses.",
}

COUNTRY_TIER_NOTES = {
    "Austria": TIER_NOTES[1],
    "Slovakia": TIER_NOTES[2],
    "Switzerland": TIER_NOTES[2],
    "Spain": TIER_NOTES[2],
}

PHASE_SECTION_MARKER = "Definition of growing stages:"


def clean_text(value: Any) -> Any:
    if value is None or pd.isna(value):
        return pd.NA
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if text else pd.NA


def to_int_string(value: Any) -> Any:
    if value is None or pd.isna(value):
        return pd.NA
    try:
        return str(int(float(str(value).strip())))
    except ValueError:
        text = str(value).strip()
        return text if text else pd.NA


def ensure_standard_columns(df: pd.DataFrame) -> pd.DataFrame:
    for column in STANDARD_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    return df[STANDARD_COLUMNS + EXTRA_COLUMNS]


def stable_group_id(prefix: str, values: pd.Series) -> str:
    raw = "|".join("" if pd.isna(value) else str(value) for value in values)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def parse_pep725_phase_descriptions(readme_path: Path) -> dict[int, str]:
    text = readme_path.read_text(encoding="utf-8", errors="replace")
    if PHASE_SECTION_MARKER in text:
        text = text.split(PHASE_SECTION_MARKER, 1)[1]

    descriptions: dict[int, str] = {}
    current_id: int | None = None
    current_lines: list[str] = []
    row_pattern = re.compile(r"^\s*(\d{1,3})\s+(.*)$")

    for line in text.splitlines():
        match = row_pattern.match(line)
        if match:
            if current_id is not None:
                descriptions[current_id] = clean_phase_description(current_lines)
            current_id = int(match.group(1))
            current_lines = [match.group(2)]
            continue
        if current_id is not None and (line.startswith(" ") or line.startswith("\t")):
            current_lines.append(line.strip())
        elif current_id is not None and line.strip() == "":
            continue
        elif current_id is not None:
            descriptions[current_id] = clean_phase_description(current_lines)
            current_id = None
            current_lines = []

    if current_id is not None:
        descriptions[current_id] = clean_phase_description(current_lines)
    return descriptions


def clean_phase_description(lines: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def stage_event_from_description(description: Any) -> Any:
    if pd.isna(description):
        return pd.NA
    text = str(description).strip()
    if not text:
        return pd.NA
    for separator in [":", ","]:
        if separator in text:
            return text.split(separator, 1)[0].strip()
    return text[:80]


def build_standardized_table(base_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    raw_path = base_dir / "raw" / "pep725" / "pep725_20260701_0.csv"
    readme_path = base_dir / "raw" / "pep725" / "README.txt"
    phase_descriptions = parse_pep725_phase_descriptions(readme_path)

    raw = pd.read_csv(raw_path, sep=";")
    selected = raw[raw["provider_id"].isin(SELECTED_PROVIDER_IDS)].copy()

    provider_info = selected["provider_id"].map(PROVIDERS)
    selected["country"] = provider_info.map(lambda value: value["country"])
    selected["country_name"] = provider_info.map(lambda value: value["country_name"])
    selected["provider_name"] = provider_info.map(lambda value: value["provider_name"])
    selected["analysis_tier"] = provider_info.map(lambda value: value["tier"]).astype("Int64")
    selected["analysis_tier_note"] = selected["country_name"].map(COUNTRY_TIER_NOTES)

    df = pd.DataFrame(index=selected.index)
    df["source_system"] = "pep725"
    df["source_dataset"] = selected["provider_name"]
    df["observation_id"] = selected.apply(
        lambda row: "pep725:"
        + ":".join(
            [
                to_int_string(row["provider_id"]),
                to_int_string(row["s_id"]),
                to_int_string(row["year"]),
                to_int_string(row["phase_id"]),
                str(row["date"]),
            ]
        ),
        axis=1,
    )
    df["date"] = selected["date"].astype(str)
    date_parts = df["date"].str.extract(r"^(\d{4})-(\d{2})-(\d{2})$")
    df["year"] = pd.to_numeric(date_parts[0], errors="coerce").astype("Int64")
    df["month"] = pd.to_numeric(date_parts[1], errors="coerce").astype("Int64")
    df["day"] = pd.to_numeric(date_parts[2], errors="coerce").astype("Int64")
    df["doy"] = pd.to_numeric(selected["day"], errors="coerce").astype("Int64")

    df["country"] = selected["country"]
    df["country_name"] = selected["country_name"]
    df["site_id"] = selected["s_id"].map(to_int_string)
    df["latitude"] = pd.to_numeric(selected["lat"], errors="coerce")
    df["longitude"] = pd.to_numeric(selected["lon"], errors="coerce")
    df["altitude"] = pd.to_numeric(selected["alt"], errors="coerce").replace(-9999, pd.NA)
    df["altitude_reported"] = df["altitude"]
    df["altitude_ign"] = pd.NA
    df["altitude_source"] = df["altitude"].notna().map(
        {True: "pep725_reported", False: pd.NA}
    )

    df["taxon_id"] = selected["gss_id"].map(to_int_string)
    df["taxon_name"] = selected["species"].fillna(selected["genus"]).map(clean_text)
    df["taxon_fullname"] = selected.apply(pep725_taxon_fullname, axis=1).map(clean_text)
    df["cultivar"] = selected["subspecies"].map(clean_text)
    df["cultivar_group"] = df["cultivar"].fillna("species_or_unspecified")

    df["stage_id"] = selected["phase_id"].map(to_int_string)
    df["stage_code"] = df["stage_id"]
    phase_numeric = pd.to_numeric(selected["phase_id"], errors="coerce")
    df["bbch_code"] = phase_numeric.where(phase_numeric <= 99).map(to_int_string)
    df["stage_description"] = phase_numeric.map(lambda value: phase_descriptions.get(int(value)) if pd.notna(value) else pd.NA)
    df["stage_event"] = df["stage_description"].map(stage_event_from_description)

    df["datasource_id"] = selected["provider_id"].map(to_int_string)
    df["datasource_name"] = selected["provider_name"]
    df["license_id"] = selected["license_short"]
    df["license_name"] = selected["license_short"]
    df["reporter_type"] = "pep725_network"
    df["source_file"] = raw_path.name
    df["additionalData_raw"] = selected.apply(
        lambda row: json.dumps(
            {
                "provider_id": int(row["provider_id"]),
                "alt_dem": None if pd.isna(row["alt_dem"]) else int(row["alt_dem"]),
                "cult_season": None if pd.isna(row["cult_season"]) else int(row["cult_season"]),
                "gss_id": None if pd.isna(row["gss_id"]) else int(row["gss_id"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        axis=1,
    )
    df["analysis_tier"] = selected["analysis_tier"]
    df["analysis_tier_note"] = selected["analysis_tier_note"]

    dedup_keys = ["source_system", "datasource_id", "site_id", "date", "taxon_id", "stage_id"]
    work = df[dedup_keys].astype("string").fillna("")
    df["dedup_group_id"] = work.apply(lambda row: stable_group_id("pep725", row), axis=1)
    df["is_training_record"] = ~df.duplicated("dedup_group_id", keep="first")

    standardized = ensure_standard_columns(df)
    report = {
        "source_file": str(raw_path),
        "selected_provider_ids": SELECTED_PROVIDER_IDS,
        "raw_rows": int(len(raw)),
        "selected_rows": int(len(selected)),
        "training_rows": int(standardized["is_training_record"].sum()),
        "duplicate_rows_removed": int(len(standardized) - standardized["is_training_record"].sum()),
        "countries": {
            country: {
                "rows": int(len(group)),
                "training_rows": int(group["is_training_record"].sum()),
                "unique_sites": int(group["site_id"].nunique(dropna=True)),
                "unique_stages": int(group["stage_id"].nunique(dropna=True)),
                "first_year": int(group["year"].min()),
                "last_year": int(group["year"].max()),
                "analysis_tier": int(group["analysis_tier"].dropna().iloc[0]),
            }
            for country, group in standardized.groupby("country_name", sort=True)
        },
        "missing": {
            "latitude_pct": float(standardized["latitude"].isna().mean() * 100),
            "longitude_pct": float(standardized["longitude"].isna().mean() * 100),
            "altitude_pct": float(standardized["altitude"].isna().mean() * 100),
            "bbch_code_pct": float(standardized["bbch_code"].isna().mean() * 100),
            "stage_description_pct": float(standardized["stage_description"].isna().mean() * 100),
        },
    }
    return standardized, report


def write_readme(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# PEP725 selected grape phenology countries",
        "",
        "Generated by `src/standardize_pep725_selected_countries.py` from `data/phenology/raw/pep725/pep725_20260701_0.csv`.",
        "",
        "Output table:",
        "",
        "- `pep725_selected_countries_grape_phenology_complete.csv`",
        "",
        "Country analysis tiers:",
        "",
        "- Tier 1: Austria. Core extension country with high station count and long time coverage.",
        "- Tier 2: Slovakia, Switzerland, and Spain. Supplementary countries for extended or sensitivity analyses.",
        "",
        "The table follows the France/Germany standardized column layout and appends:",
        "",
        "- `analysis_tier`: numeric analysis tier.",
        "- `analysis_tier_note`: short interpretation of the tier.",
        "",
        "Country summary:",
        "",
        "| Country | Tier | Rows | Training rows | Sites | Stages | Years |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for country, summary in sorted(report["countries"].items()):
        lines.append(
            f"| {country} | {summary['analysis_tier']} | {summary['rows']} | "
            f"{summary['training_rows']} | {summary['unique_sites']} | "
            f"{summary['unique_stages']} | {summary['first_year']}-{summary['last_year']} |"
        )
    lines.extend(
        [
            "",
            "Notes:",
            "",
            "- `bbch_code` is filled only for PEP725 `phase_id <= 99`; additional PEP725 phases such as harvest and leaf colouring remain in `stage_code` and `stage_id`.",
            "- `datasource_id` preserves the PEP725 `provider_id`; this is especially important for Spain, which combines provider IDs 14, 1401, and 1402.",
            "- `additionalData_raw` preserves selected PEP725 fields not present in the shared France/Germany schema, including `alt_dem`, `cult_season`, and `gss_id`.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def pep725_taxon_fullname(row: pd.Series) -> Any:
    genus = clean_text(row.get("genus"))
    species = clean_text(row.get("species"))
    if pd.isna(species):
        return genus
    if pd.isna(genus):
        return species
    genus_text = str(genus)
    species_text = str(species)
    if species_text.lower().startswith(genus_text.lower() + " "):
        return species_text
    return f"{genus_text} {species_text}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, default=Path("data") / "phenology")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    base_dir = args.base_dir
    out_dir = base_dir / "processed"
    metadata_dir = base_dir / "metadata" / "standardization"
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    standardized, report = build_standardized_table(base_dir)
    standardized.to_csv(out_dir / "pep725_selected_countries_grape_phenology_complete.csv", index=False)
    write_readme(out_dir / "README_pep725_selected_countries.md", report)
    (metadata_dir / "pep725_selected_countries_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
