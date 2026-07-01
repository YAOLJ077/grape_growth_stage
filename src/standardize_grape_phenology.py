#!/usr/bin/env python
"""Standardize France TEMPO and Germany DWD grape phenology data.

The script reads source downloads from data/phenology_grape/raw, writes complete
country tables under data/phenology_grape/processed, and writes QA metadata under
data/phenology_grape/metadata/standardization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date as date_cls
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd


DWD_ANNUAL_STATIONS_URL = (
    "https://opendata.dwd.de/climate_environment/CDC/help/"
    "PH_Beschreibung_Phaenologie_Stationen_Jahresmelder.txt"
)
DWD_IMMEDIATE_STATIONS_URL = (
    "https://opendata.dwd.de/climate_environment/CDC/help/"
    "PH_Beschreibung_Phaenologie_Stationen_Sofortmelder.txt"
)
USER_AGENT = "growth-stage-grape-phenology-standardizer/1.0"

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

DWD_SELECTED_FILES = [
    (
        "annual",
        "early",
        "annual_reporters/vine/historical/"
        "PH_Jahresmelder_Weinrebe_Weinrebe_fruehe_Reife_1951_2024_hist.txt",
        20,
    ),
    (
        "annual",
        "late",
        "annual_reporters/vine/historical/"
        "PH_Jahresmelder_Weinrebe_Weinrebe_spaete_Reife_1951_2024_hist.txt",
        20,
    ),
    (
        "annual",
        "medium_late",
        "annual_reporters/vine/historical/"
        "PH_Jahresmelder_Weinrebe_Weinrebe_mittelspaete_Reife_1951_1990_hist.txt",
        20,
    ),
    (
        "annual",
        "early",
        "annual_reporters/vine/recent/PH_Jahresmelder_Weinrebe_Weinrebe_fruehe_Reife_akt.txt",
        30,
    ),
    (
        "annual",
        "late",
        "annual_reporters/vine/recent/PH_Jahresmelder_Weinrebe_Weinrebe_spaete_Reife_akt.txt",
        30,
    ),
    (
        "immediate",
        "mueller_thurgau",
        "immediate_reporters/vine/historical/PH_Sofortmelder_Wein_Mueller-Thurgau_2007_2012_hist.txt",
        10,
    ),
    (
        "immediate",
        "early",
        "immediate_reporters/vine/historical/"
        "PH_Sofortmelder_Weinrebe_Weinrebe_fruehe_Reife_1980_2006_hist.txt",
        10,
    ),
    (
        "immediate",
        "late",
        "immediate_reporters/vine/historical/"
        "PH_Sofortmelder_Weinrebe_Weinrebe_spaete_Reife_1980_2006_hist.txt",
        10,
    ),
]

DWD_OBJECT_NAMES = {
    410: "Weinrebe",
    411: "Weinrebe, frühe Reife",
    412: "Weinrebe, mittelspäte Reife",
    413: "Weinrebe, späte Reife",
    414: "Weinrebe, blaue Trauben",
    4111: "Müller-Thurgau",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def map_by_id(rows: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    return {row.get("id"): row for row in rows if row.get("id") is not None}


def clean_text(value: Any) -> Any:
    if value is None or pd.isna(value):
        return pd.NA
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if text else pd.NA


def to_int_string(value: Any, width: int | None = None) -> Any:
    if value is None or pd.isna(value):
        return pd.NA
    try:
        number = int(float(str(value).strip()))
    except ValueError:
        text = str(value).strip()
        return text.zfill(width) if width and text else text
    return f"{number:0{width}d}" if width else str(number)


def yyyymmdd_to_iso(value: Any) -> Any:
    text = str(value).strip()
    if not re.fullmatch(r"\d{8}", text):
        return pd.NA
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"


def add_date_parts(df: pd.DataFrame) -> pd.DataFrame:
    parts = df["date"].astype("string").str.extract(r"^(\d{4})-(\d{2})-(\d{2})$")
    df["year"] = pd.to_numeric(parts[0], errors="coerce").astype("Int64")
    df["month"] = pd.to_numeric(parts[1], errors="coerce").astype("Int64")
    df["day"] = pd.to_numeric(parts[2], errors="coerce").astype("Int64")
    if "doy" not in df.columns or df["doy"].isna().all():
        df["doy"] = [
            doy_from_parts(year, month, day)
            for year, month, day in zip(df["year"], df["month"], df["day"], strict=False)
        ]
        df["doy"] = pd.Series(df["doy"], index=df.index, dtype="Int64")
    else:
        df["doy"] = pd.to_numeric(df["doy"], errors="coerce").astype("Int64")
    return df


def doy_from_parts(year: Any, month: Any, day: Any) -> Any:
    if pd.isna(year) or pd.isna(month) or pd.isna(day):
        return pd.NA
    try:
        current = date_cls(int(year), int(month), int(day))
    except ValueError:
        return pd.NA
    return current.timetuple().tm_yday


def ensure_standard_columns(df: pd.DataFrame) -> pd.DataFrame:
    for column in STANDARD_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    return df[STANDARD_COLUMNS]


def stable_group_id(prefix: str, values: pd.Series) -> str:
    raw = "|".join("" if pd.isna(value) else str(value) for value in values)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def download_if_missing(url: str, path: Path, refresh: bool = False) -> bool:
    if path.exists() and path.stat().st_size > 0 and not refresh:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        path.write_bytes(response.read())
    return True


def load_france(base_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    france_raw_dir = base_dir / "raw" / "france_tempo"
    france_meta_dir = base_dir / "metadata" / "france_tempo"
    meta = json.loads((france_meta_dir / "metadata_snapshot.json").read_text(encoding="utf-8"))
    obs = pd.DataFrame(read_jsonl(france_raw_dir / "tempo_grape_cache_public_france.jsonl"))
    sites = pd.DataFrame(read_jsonl(france_meta_dir / "sites_france.jsonl"))
    additional = pd.DataFrame(read_jsonl(france_raw_dir / "tempo_grape_additionaldata_public_france.jsonl"))

    taxa = map_by_id(meta["taxa_all"])
    stages = map_by_id(meta["stages"])
    sources = map_by_id(meta["sources"])
    licenses = map_by_id(meta["licenses"])
    countries = map_by_id(meta["countries"])
    regions = map_by_id(meta["regions"])
    departments = map_by_id(meta["departments"])
    communes = map_by_id(meta["communes"])

    sites = sites.rename(
        columns={
            "id": "site",
            "name": "site_name",
            "country": "country",
            "region": "region_id",
            "department": "department_id",
            "commune": "commune_id",
        }
    )
    site_columns = [
        "site",
        "site_name",
        "latitude",
        "longitude",
        "altitude",
        "altitudeIgn",
        "country",
        "region_id",
        "department_id",
        "commune_id",
    ]
    sites = sites[[column for column in site_columns if column in sites.columns]]

    if not additional.empty:
        additional = additional.rename(columns={"id": "additionalData", "data": "additionalData_raw"})
    else:
        additional = pd.DataFrame(columns=["additionalData", "additionalData_raw"])

    df = obs.merge(sites, on="site", how="left").merge(additional, on="additionalData", how="left")

    df["source_system"] = "france_tempo"
    df["source_dataset"] = df["datasource"].map(lambda value: sources.get(value, {}).get("name"))
    df["observation_id"] = df["id"].map(to_int_string)
    df["date"] = df["date"].astype(str)
    df = add_date_parts(df)

    df["country_name"] = df["country"].map(lambda value: countries.get(value, {}).get("name"))
    df["region"] = df["region_id"].map(lambda value: regions.get(value, {}).get("name"))
    df["department"] = df["department_id"].map(lambda value: departments.get(value, {}).get("name"))
    df["commune"] = df["commune_id"].map(lambda value: communes.get(value, {}).get("name"))
    df["site_id"] = df["site"].map(to_int_string)

    df["taxon_id"] = df["taxon"].map(to_int_string)
    df["taxon_name"] = df["taxon"].map(lambda value: taxa.get(value, {}).get("name"))
    df["taxon_fullname"] = df["taxon"].map(lambda value: taxa.get(value, {}).get("fullname"))
    df["cultivar"] = df.apply(france_cultivar, axis=1)
    df["cultivar_group"] = df["cultivar"].fillna("species_or_unspecified")

    df["stage_id"] = df["stage"].map(to_int_string)
    df["stage_code"] = df["stage"].map(lambda value: stages.get(value, {}).get("code"))
    df["bbch_code"] = df["stage_code"]
    df["stage_eventcode"] = df["stage"].map(lambda value: stages.get(value, {}).get("eventcode"))
    df["stage_event"] = df["stage"].map(lambda value: stages.get(value, {}).get("event"))
    df["stage_description"] = df["stage"].map(lambda value: stages.get(value, {}).get("description"))

    df["datasource_id"] = df["datasource"].map(to_int_string)
    df["datasource_name"] = df["datasource"].map(lambda value: sources.get(value, {}).get("name"))
    df["license_id"] = df["license"].map(to_int_string)
    df["license_name"] = df["license"].map(lambda value: licenses.get(value, {}).get("name"))
    df["additionalData_id"] = df["additionalData"].map(to_int_string)
    df["country"] = df["country"].map(to_int_string)

    for column in ["site_name", "taxon_name", "taxon_fullname", "stage_event", "stage_description", "additionalData_raw"]:
        df[column] = df[column].map(clean_text)

    joined = ensure_standard_columns(df)

    train = joined[joined["taxon_fullname"].fillna("").str.contains(r"\bVitis\b", case=False, regex=True)].copy()
    train = assign_dedup(train, ["source_system", "country", "site_id", "date", "taxon_id", "stage_id", "datasource_id"], "fr")
    train["is_training_record"] = True
    train = train[~train["_duplicate"]].drop(columns=["_duplicate"])

    report = {
        "raw_rows": int(len(obs)),
        "joined_rows": int(len(joined)),
        "training_rows": int(len(train)),
        "excluded_non_vitis_rows": int(len(joined) - len(joined[joined["taxon_fullname"].fillna("").str.contains(r"\bVitis\b", case=False, regex=True)])),
        "training_duplicate_rows_removed": int(joined[joined["taxon_fullname"].fillna("").str.contains(r"\bVitis\b", case=False, regex=True)].shape[0] - train.shape[0]),
        "unique_sites": int(joined["site_id"].nunique(dropna=True)),
        "unique_stages": int(joined["stage_id"].nunique(dropna=True)),
        "date_min": str(joined["date"].min()),
        "date_max": str(joined["date"].max()),
    }
    return joined, ensure_standard_columns(train), report


def france_cultivar(row: pd.Series) -> Any:
    fullname = row.get("taxon_fullname")
    taxon_type = None
    if pd.notna(row.get("taxon")):
        # The caller also has a taxon map; this fallback is kept simple here.
        pass
    if isinstance(fullname, str) and " - " in fullname:
        return fullname.split(" - ", 1)[1].strip()
    return pd.NA


def read_dwd_table(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", encoding="latin1", skipinitialspace=True, dtype=str)
    df.columns = [column.strip() for column in df.columns]
    keep = [column for column in df.columns if column and column.lower() != "eor" and not column.startswith("Unnamed")]
    df = df[keep]
    for column in df.columns:
        df[column] = df[column].map(clean_text)
    return df


def load_dwd_phase_defs(dwd_raw_dir: Path) -> pd.DataFrame:
    annual_path = dwd_raw_dir / "annual_reporters/vine/recent/PH_Beschreibung_Phasendefinition_Jahresmelder_Weinrebe.txt"
    annual = read_dwd_table(annual_path)
    annual = annual.rename(
        columns={
            "Objekt_id": "object_id",
            "Objekt": "object_name",
            "Phasen_id": "phase_id",
            "Phase": "phase_name",
            "Phasendefinition": "phase_description",
            "BBCH_Code": "bbch_code",
            "Hinweis BBCH": "bbch_note",
        }
    )
    annual["object_id"] = pd.to_numeric(annual["object_id"], errors="coerce").astype("Int64")
    annual["phase_id"] = pd.to_numeric(annual["phase_id"], errors="coerce").astype("Int64")
    annual["bbch_code"] = pd.to_numeric(annual["bbch_code"], errors="coerce").astype("Int64").astype(str).replace("<NA>", pd.NA)
    annual["reporter_type"] = "annual"

    immediate_names = {
        2: ("Erstes Bluten", "first bleeding sap from grapevine branch"),
        3: ("Austrieb Beginn", "beginning of bud break"),
        4: ("Blattentfaltung Beginn", "beginning of unfolding of leaves"),
        5: ("Blüte Beginn", "beginning of flowering"),
        6: ("Vollblüte", "full flowering"),
        7: ("Blüte Ende", "end of flowering"),
        30: ("Lese", "harvest"),
        31: ("herbstliche Blattverfärbung", "autumn leaf colouring"),
        32: ("herbstlicher Blattfall", "autumn leaf fall"),
        40: ("allgemeine Fruchtreife", "general fruit maturity"),
        42: ("Reife Beginn Weinrebe", "beginning of ripening"),
    }
    immediate_rows = []
    for object_id in [410, 411, 413, 4111]:
        for phase_id, (name, description) in immediate_names.items():
            immediate_rows.append(
                {
                    "object_id": object_id,
                    "object_name": DWD_OBJECT_NAMES.get(object_id),
                    "phase_id": phase_id,
                    "phase_name": name,
                    "phase_description": description,
                    "bbch_code": dwd_bbch_code(phase_id),
                    "bbch_note": pd.NA,
                    "reporter_type": "immediate",
                }
            )
    return pd.concat([annual, pd.DataFrame(immediate_rows)], ignore_index=True)


def dwd_bbch_code(phase_id: int) -> Any:
    return {
        3: "07",
        5: "61",
        6: "65",
        7: "69",
        42: "81",
    }.get(int(phase_id), pd.NA)


def load_dwd_station_file(path: Path, reporter_type: str) -> pd.DataFrame:
    df = read_dwd_table(path)
    df = df.rename(
        columns={
            "Stations_id": "site_id",
            "Stationsname": "site_name",
            "geograph.Breite": "latitude",
            "geograph.Laenge": "longitude",
            "Stationshoehe": "altitude",
            "Naturraumgruppe_Code": "natural_region_group_code",
            "Naturraumgruppe": "natural_region_group",
            "Naturraum_Code": "natural_region_code",
            "Naturraum": "natural_region",
            "Datum Stationsaufloesung": "station_closed_date",
            "Bundesland": "federal_state",
        }
    )
    df["site_id"] = df["site_id"].map(lambda value: to_int_string(value, width=5))
    for column in ["latitude", "longitude", "altitude"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["reporter_type"] = reporter_type
    return df


def ensure_dwd_station_metadata(base_dir: Path, refresh: bool = False) -> dict[str, bool]:
    meta_dir = base_dir / "metadata" / "germany_dwd"
    annual_path = meta_dir / "PH_Beschreibung_Phaenologie_Stationen_Jahresmelder.txt"
    immediate_path = meta_dir / "PH_Beschreibung_Phaenologie_Stationen_Sofortmelder.txt"
    return {
        "annual_downloaded": download_if_missing(DWD_ANNUAL_STATIONS_URL, annual_path, refresh=refresh),
        "immediate_downloaded": download_if_missing(DWD_IMMEDIATE_STATIONS_URL, immediate_path, refresh=refresh),
    }


def load_germany(base_dir: Path, refresh_station_metadata: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    dwd_raw_dir = base_dir / "raw" / "germany_dwd"
    station_downloads = ensure_dwd_station_metadata(base_dir, refresh=refresh_station_metadata)
    phase_defs = load_dwd_phase_defs(dwd_raw_dir)

    station_dir = base_dir / "metadata" / "germany_dwd"
    annual_stations = load_dwd_station_file(station_dir / "PH_Beschreibung_Phaenologie_Stationen_Jahresmelder.txt", "annual")
    immediate_stations = load_dwd_station_file(station_dir / "PH_Beschreibung_Phaenologie_Stationen_Sofortmelder.txt", "immediate")
    stations = pd.concat([annual_stations, immediate_stations], ignore_index=True)

    frames = []
    for reporter_type, cultivar_group, relative_path, source_priority in DWD_SELECTED_FILES:
        path = dwd_raw_dir / relative_path
        raw = read_dwd_table(path)
        raw["reporter_type"] = reporter_type
        raw["cultivar_group"] = cultivar_group
        raw["source_file"] = path.name
        raw["source_priority"] = source_priority
        frames.append(raw)
    raw_df = pd.concat(frames, ignore_index=True)

    df = raw_df.rename(
        columns={
            "Stations_id": "site_id",
            "Referenzjahr": "reference_year",
            "Qualitaetsniveau": "quality_level",
            "Objekt_id": "object_id",
            "Phase_id": "phase_id",
            "Eintrittsdatum": "entry_date",
            "Eintrittsdatum_QB": "date_quality_flag",
            "Jultag": "doy",
        }
    )
    df["site_id"] = df["site_id"].map(lambda value: to_int_string(value, width=5))
    df["object_id"] = pd.to_numeric(df["object_id"], errors="coerce").astype("Int64")
    df["phase_id"] = pd.to_numeric(df["phase_id"], errors="coerce").astype("Int64")
    df["date"] = df["entry_date"].map(yyyymmdd_to_iso)
    df["doy"] = pd.to_numeric(df["doy"], errors="coerce").astype("Int64")
    df = add_date_parts(df)

    df = df.merge(
        phase_defs,
        on=["reporter_type", "object_id", "phase_id"],
        how="left",
    )
    df = df.merge(
        stations[
            [
                "reporter_type",
                "site_id",
                "site_name",
                "latitude",
                "longitude",
                "altitude",
                "natural_region",
                "federal_state",
            ]
        ],
        on=["reporter_type", "site_id"],
        how="left",
    )

    df["source_system"] = "germany_dwd"
    df["source_dataset"] = df["reporter_type"].map(
        {"annual": "DWD annual reporters vine", "immediate": "DWD immediate reporters vine"}
    )
    df["observation_id"] = df.apply(
        lambda row: "dwd:"
        + ":".join(
            [
                str(row["reporter_type"]),
                str(row["cultivar_group"]),
                str(row["site_id"]),
                str(row["year"]),
                str(row["object_id"]),
                str(row["phase_id"]),
                str(row["date"]),
            ]
        ),
        axis=1,
    )
    df["country"] = "DE"
    df["country_name"] = "Germany"
    df["taxon_id"] = df["object_id"].astype("Int64").astype(str).replace("<NA>", pd.NA)
    df["taxon_name"] = df["object_name"].fillna(df["object_id"].map(lambda value: DWD_OBJECT_NAMES.get(int(value)) if pd.notna(value) else pd.NA))
    df["taxon_fullname"] = "Plantae Vitis vinifera - " + df["taxon_name"].fillna(df["cultivar_group"])
    df["cultivar"] = df["taxon_name"]
    df["stage_id"] = df["phase_id"].astype("Int64").astype(str).replace("<NA>", pd.NA)
    df["stage_code"] = df["phase_id"].astype("Int64").astype(str).replace("<NA>", pd.NA)
    df["stage_event"] = df["phase_name"]
    df["stage_description"] = df["phase_description"]
    df["datasource_id"] = df["reporter_type"]
    df["datasource_name"] = df["source_dataset"]
    df["license_name"] = "DWD open data"
    df["is_training_record"] = True

    joined = ensure_standard_columns(df)

    train = joined.copy()
    train["_source_priority"] = df["source_priority"].to_numpy()
    train = assign_dedup(
        train,
        ["source_system", "reporter_type", "cultivar_group", "site_id", "year", "stage_id", "date"],
        "de",
        sort_column="_source_priority",
    )
    train["is_training_record"] = True
    train = train[~train["_duplicate"]].drop(columns=["_duplicate", "_source_priority"])

    report = {
        "station_metadata_downloads": station_downloads,
        "selected_raw_rows": int(len(raw_df)),
        "joined_rows": int(len(joined)),
        "training_rows": int(len(train)),
        "training_duplicate_rows_removed": int(len(joined) - len(train)),
        "unique_sites": int(joined["site_id"].nunique(dropna=True)),
        "unique_stages": int(joined["stage_id"].nunique(dropna=True)),
        "unmatched_station_rows": int(joined["latitude"].isna().sum()),
        "date_min": str(joined["date"].min()),
        "date_max": str(joined["date"].max()),
    }
    return joined, ensure_standard_columns(train), report


def assign_dedup(
    df: pd.DataFrame,
    keys: list[str],
    prefix: str,
    sort_column: str | None = None,
) -> pd.DataFrame:
    df = df.copy()
    work = df[keys].astype("string").fillna("")
    df["dedup_group_id"] = work.apply(lambda row: stable_group_id(prefix, row), axis=1)
    sort_cols = ["dedup_group_id"]
    ascending = [True]
    if sort_column:
        sort_cols.append(sort_column)
        ascending.append(False)
    df = df.sort_values(sort_cols, ascending=ascending, kind="mergesort")
    df["_duplicate"] = df.duplicated("dedup_group_id", keep="first")
    return df.sort_index(kind="mergesort")


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def table_summary(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": int(len(df)),
        "countries": df["country_name"].value_counts(dropna=False).head(20).to_dict(),
        "years": {
            "min": int(df["year"].min()) if df["year"].notna().any() else None,
            "max": int(df["year"].max()) if df["year"].notna().any() else None,
            "unique": int(df["year"].nunique(dropna=True)),
        },
        "unique_sites": int(df["site_id"].nunique(dropna=True)),
        "unique_stages": int(df["stage_id"].nunique(dropna=True)),
        "missing": {
            "latitude_pct": float(df["latitude"].isna().mean() * 100) if len(df) else 0.0,
            "longitude_pct": float(df["longitude"].isna().mean() * 100) if len(df) else 0.0,
            "bbch_code_pct": float(df["bbch_code"].isna().mean() * 100) if len(df) else 0.0,
            "stage_description_pct": float(df["stage_description"].isna().mean() * 100) if len(df) else 0.0,
        },
    }


def build_dedup_report(fr_train_pre: pd.DataFrame, de_train_pre: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, df in [("france_tempo", fr_train_pre), ("germany_dwd", de_train_pre)]:
        if "_duplicate" not in df.columns:
            continue
        dupes = df[df["_duplicate"]]
        for group_id, group in dupes.groupby("dedup_group_id"):
            rows.append(
                {
                    "source_system": name,
                    "dedup_group_id": group_id,
                    "duplicate_rows_removed": int(len(group)),
                    "example_observation_id": group["observation_id"].iloc[0],
                    "example_date": group["date"].iloc[0],
                    "example_site_id": group["site_id"].iloc[0],
                    "example_stage_id": group["stage_id"].iloc[0],
                }
            )
    return pd.DataFrame(rows)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", type=Path, default=Path("data") / "phenology_grape")
    parser.add_argument("--refresh-dwd-stations", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    base_dir = args.base_dir
    out_dir = base_dir / "processed"
    metadata_dir = base_dir / "metadata" / "standardization"
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    france_joined, france_training, france_report = load_france(base_dir)
    germany_joined, germany_training, germany_report = load_germany(
        base_dir,
        refresh_station_metadata=args.refresh_dwd_stations,
    )

    write_csv(france_joined, out_dir / "france_grape_phenology_complete.csv")
    write_csv(germany_joined, out_dir / "germany_grape_phenology_complete.csv")

    # Recompute duplicate reports on pre-drop copies for compact QA.
    fr_pre = assign_dedup(
        france_joined[france_joined["taxon_fullname"].fillna("").str.contains(r"\bVitis\b", case=False, regex=True)].copy(),
        ["source_system", "country", "site_id", "date", "taxon_id", "stage_id", "datasource_id"],
        "fr",
    )
    de_pre = germany_joined.copy()
    de_pre["_source_priority"] = de_pre["source_file"].map(lambda name: 30 if str(name).endswith("_akt.txt") else 20)
    de_pre = assign_dedup(
        de_pre,
        ["source_system", "reporter_type", "cultivar_group", "site_id", "year", "stage_id", "date"],
        "de",
        sort_column="_source_priority",
    )
    dedup_report = build_dedup_report(fr_pre, de_pre)
    write_csv(dedup_report, metadata_dir / "deduplication_report.csv")

    report = {
        "france_tempo": france_report,
        "germany_dwd": germany_report,
        "outputs": {
            "france_grape_phenology_complete": table_summary(france_joined),
            "germany_grape_phenology_complete": table_summary(germany_joined),
        },
    }
    (metadata_dir / "standardization_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(report["outputs"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
