#!/usr/bin/env python
"""Build a six-country analysis layer with standardized BBCH and phenophase fields."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_INPUTS = [
    Path("data/phenology/processed/france_grape_phenology_complete.csv"),
    Path("data/phenology/processed/germany_grape_phenology_complete.csv"),
    Path("data/phenology/processed/pep725_selected_countries_grape_phenology_complete.csv"),
]
COUNTRY_ORDER = ["France", "Germany", "Austria", "Switzerland", "Slovakia", "Spain"]
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
EXTRA_PEP_COLUMNS = ["analysis_tier", "analysis_tier_note"]

DWD_STAGE_BBCH = {
    "3": ("07", "high", "DWD stage 3 Austrieb Beginn mapped to BBCH 07"),
    "4": ("11", "medium", "DWD stage 4 Blattentfaltung Beginn mapped to BBCH 11"),
    "5": ("61", "high", "DWD stage 5 Bluete Beginn mapped to BBCH 61"),
    "6": ("65", "high", "DWD stage 6 Vollbluete mapped to BBCH 65"),
    "7": ("69", "high", "DWD stage 7 Bluete Ende mapped to BBCH 69"),
    "30": ("89", "medium", "DWD stage 30 Lese mapped to BBCH 89"),
    "31": ("92", "medium", "DWD stage 31 autumn leaf colouring mapped to BBCH 92"),
    "32": ("95", "medium", "DWD stage 32 autumn leaf fall mapped to BBCH 95"),
    "40": ("89", "medium", "DWD stage 40 general fruit maturity mapped to BBCH 89"),
    "42": ("81", "high", "DWD stage 42 Reife Beginn mapped to BBCH 81"),
}
PEP_EXTENDED_STAGE_BBCH = {
    "100": ("89", "medium", "PEP725 phase 100 start of harvest mapped to BBCH 89"),
    "201": ("92", "medium", "PEP725 phase 201 autumnal leaf colouring mapped to BBCH 92"),
    "205": ("95", "medium", "PEP725 phase 205 autumnal leaf colouring >=50% mapped to BBCH 95"),
}
UNMAPPED_STAGE_NOTES = {
    ("germany_dwd", "2"): "DWD bleeding phase has no cross-source BBCH mapping in this layer",
    ("pep725", "250"): "PEP725 grapevine bleeding phase has no cross-source BBCH mapping in this layer",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", default=DEFAULT_INPUTS)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/phenology/derived/standardized_bbch"),
    )
    return parser.parse_args()


def normalize_int_string(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    try:
        return str(int(float(text)))
    except ValueError:
        return text


def normalize_bbch(value: object) -> str:
    text = normalize_int_string(value)
    if not text:
        return ""
    try:
        number = int(text)
    except ValueError:
        return text
    if 0 <= number <= 99:
        return f"{number:02d}"
    return ""


def load_inputs(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        header = pd.read_csv(path, nrows=0)
        columns = STANDARD_COLUMNS + [column for column in EXTRA_PEP_COLUMNS if column in header.columns]
        usecols = [column for column in columns if column in header.columns]
        frame = pd.read_csv(path, usecols=usecols, low_memory=False)
        for column in STANDARD_COLUMNS + EXTRA_PEP_COLUMNS:
            if column not in frame.columns:
                frame[column] = pd.NA
        frames.append(frame[STANDARD_COLUMNS + EXTRA_PEP_COLUMNS])
    df = pd.concat(frames, ignore_index=True)
    df = df[df["country_name"].isin(COUNTRY_ORDER)].copy()
    return df


def standardize_bbch(row: pd.Series) -> tuple[str, str, str]:
    source = str(row.get("source_system", ""))
    stage_id = normalize_int_string(row.get("stage_id"))
    direct = normalize_bbch(row.get("bbch_code"))
    if direct:
        return direct, "high", "direct normalized source bbch_code"
    if source == "germany_dwd" and stage_id in DWD_STAGE_BBCH:
        return DWD_STAGE_BBCH[stage_id]
    if source == "pep725" and stage_id in PEP_EXTENDED_STAGE_BBCH:
        return PEP_EXTENDED_STAGE_BBCH[stage_id]
    note = UNMAPPED_STAGE_NOTES.get((source, stage_id), "no reliable cross-source BBCH mapping")
    return "", "unmapped", note


def major_stage(bbch: str) -> str:
    if not bbch:
        return ""
    try:
        return str(int(bbch) // 10)
    except ValueError:
        return ""


def phenophase_from_bbch(bbch: str, source: str, stage_id: str) -> tuple[str, int | None]:
    if not bbch:
        if (source, stage_id) in {("germany_dwd", "2"), ("pep725", "250")}:
            return "bleeding", 0
        return "", None
    number = int(bbch)
    if number == 0:
        return "dormancy", 0
    if number == 7:
        return "budburst", 1
    if 10 <= number <= 19:
        return "leaf_development", 2
    if 50 <= number <= 59:
        return "inflorescence_emergence", 3
    if 60 <= number <= 69:
        return "flowering", 4
    if 70 <= number <= 79:
        return "fruit_development", 5
    if 80 <= number <= 87:
        return "veraison", 6
    if number in {88, 89}:
        return "maturity_or_harvest", 7
    if 90 <= number <= 99:
        return "senescence_or_dormancy", 8
    return "", None


def add_standard_fields(df: pd.DataFrame) -> pd.DataFrame:
    results = df.apply(standardize_bbch, axis=1, result_type="expand")
    df["bbch_standard"] = results[0]
    df["bbch_mapping_confidence"] = results[1]
    df["bbch_mapping_note"] = results[2]
    df["bbch_major"] = df["bbch_standard"].map(major_stage)
    source_stage = [
        phenophase_from_bbch(bbch, str(source), normalize_int_string(stage_id))
        for bbch, source, stage_id in zip(df["bbch_standard"], df["source_system"], df["stage_id"], strict=False)
    ]
    df["phenophase_standard"] = [value[0] for value in source_stage]
    df["phenophase_order"] = [value[1] for value in source_stage]
    return df


def write_audit_tables(df: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stage_audit = (
        df.groupby(
            [
                "source_system",
                "country_name",
                "stage_id",
                "stage_event",
                "bbch_code",
                "bbch_standard",
                "bbch_mapping_confidence",
                "phenophase_standard",
                "bbch_mapping_note",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="n_observations")
        .sort_values(["country_name", "source_system", "stage_id"])
    )
    stage_audit.to_csv(out_dir / "bbch_stage_mapping_audit.csv", index=False)

    country_summary = (
        df.groupby("country_name", dropna=False)
        .agg(
            n_observations=("site_id", "size"),
            n_sites=("site_id", "nunique"),
            n_source_bbch=("bbch_code", lambda value: value.map(normalize_bbch).loc[lambda s: s.ne("")].nunique()),
            n_standard_bbch=("bbch_standard", lambda value: value[value.ne("")].nunique()),
            n_standard_phenophases=("phenophase_standard", lambda value: value[value.ne("")].nunique()),
            unmapped_records=("bbch_mapping_confidence", lambda value: value.eq("unmapped").sum()),
        )
        .reindex(COUNTRY_ORDER)
        .reset_index()
    )
    country_summary.to_csv(out_dir / "bbch_country_mapping_summary.csv", index=False)

    bbch_summary = (
        df[df["bbch_standard"].ne("")]
        .groupby(["country_name", "bbch_standard", "phenophase_standard"], dropna=False)
        .agg(n_observations=("site_id", "size"), n_sites=("site_id", "nunique"))
        .reset_index()
        .sort_values(["country_name", "bbch_standard"])
    )
    bbch_summary.to_csv(out_dir / "bbch_standard_distribution.csv", index=False)


def main() -> int:
    args = parse_args()
    df = load_inputs(args.input)
    df = add_standard_fields(df)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / "six_country_phenology_bbch_standardized.csv"
    df.to_csv(out_path, index=False)
    write_audit_tables(df, args.out_dir)
    print(f"Rows written: {len(df):,}")
    print(f"Standardized table: {out_path}")
    print(f"Audit tables written to: {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
