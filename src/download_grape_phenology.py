#!/usr/bin/env python
"""Download public grape phenology data from TEMPO France and DWD Germany.

The script is intentionally dependency-free. It writes raw source files/data,
manifest rows, failure logs, and run configuration under data/phenology_grape.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html.parser
import json
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


DWD_BASE = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/phenology/"
DWD_VINE_DIRS = (
    "annual_reporters/vine/historical/",
    "annual_reporters/vine/recent/",
    "immediate_reporters/vine/historical/",
)
TEMPO_API = "https://data.pheno.fr/api/"
TEMPO_WEBSERVICES = "https://data.pheno.fr/webservices"
MAX_WORKERS = 32
DEFAULT_WORKERS = 8
MAX_TEMPO_PAGE_SIZE = 200_000
HTTP_TIMEOUT = 120
RETRIES = 3
USER_AGENT = "growth-stage-grape-phenology-downloader/1.0"

GRAPE_TERMS = (
    "grape",
    "vine",
    "vigne",
    "vignes",
    "vitis",
    "vinifera",
    "wein",
    "weinrebe",
    "weintraube",
    "raisin",
)
FRANCE_TERMS = ("france", "frankreich")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_workers(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--workers must be an integer") from exc
    if parsed < 1 or parsed > MAX_WORKERS:
        raise argparse.ArgumentTypeError(f"--workers must be between 1 and {MAX_WORKERS}")
    return parsed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_bytes(url: str, *, params: dict[str, Any] | None = None) -> tuple[bytes, int, str]:
    if params:
        clean: list[tuple[str, str]] = []
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                clean.extend((key, str(item)) for item in value)
            else:
                clean.append((key, str(value)))
        url = f"{url}?{urlencode(clean)}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=HTTP_TIMEOUT) as response:
        return response.read(), response.status, response.geturl()


def request_json(url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    body, status, final_url = request_bytes(url, params=params)
    if status >= 400:
        raise RuntimeError(f"HTTP {status} for {final_url}")
    return json.loads(body.decode("utf-8"))


def retry_call(fn, *args, **kwargs):
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            return fn(*args, **kwargs), attempt
        except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == RETRIES:
                break
            delay = min(60, 2**attempt)
            if isinstance(exc, HTTPError) and exc.code == 429:
                delay = max(delay, 30)
            time.sleep(delay)
    assert last_error is not None
    raise last_error


class LinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


@dataclass(frozen=True)
class DownloadTask:
    source: str
    url: str
    output_path: Path
    source_group: str


class RunLogger:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.manifest_path = out_dir / "manifest.csv"
        self.failed_path = out_dir / "failed_downloads.csv"
        self.skipped_path = out_dir / "skipped_authorized_sources.csv"
        self._lock = threading.Lock()
        out_dir.mkdir(parents=True, exist_ok=True)
        self._init_csv(
            self.manifest_path,
            [
                "timestamp_utc",
                "source",
                "source_group",
                "url",
                "path",
                "bytes",
                "sha256",
                "status",
                "attempts",
                "note",
            ],
        )
        self._init_csv(
            self.failed_path,
            [
                "timestamp_utc",
                "source",
                "source_group",
                "url",
                "path",
                "attempts",
                "error",
            ],
        )
        self._init_csv(
            self.skipped_path,
            ["timestamp_utc", "source", "id", "name", "reason", "url"],
        )

    @staticmethod
    def _init_csv(path: Path, headers: list[str]) -> None:
        if path.exists():
            return
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(headers)

    def manifest(self, row: dict[str, Any]) -> None:
        fields = [
            "timestamp_utc",
            "source",
            "source_group",
            "url",
            "path",
            "bytes",
            "sha256",
            "status",
            "attempts",
            "note",
        ]
        self._append(self.manifest_path, fields, row)

    def failed(self, row: dict[str, Any]) -> None:
        fields = ["timestamp_utc", "source", "source_group", "url", "path", "attempts", "error"]
        self._append(self.failed_path, fields, row)

    def skipped(self, row: dict[str, Any]) -> None:
        fields = ["timestamp_utc", "source", "id", "name", "reason", "url"]
        self._append(self.skipped_path, fields, row)

    def _append(self, path: Path, fields: list[str], row: dict[str, Any]) -> None:
        with self._lock:
            with path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writerow({field: row.get(field, "") for field in fields})


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, data: Any) -> None:
    raw = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    atomic_write_bytes(path, raw)


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def reset_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def list_dwd_tasks(out_dir: Path) -> list[DownloadTask]:
    tasks: list[DownloadTask] = []
    for rel_dir in DWD_VINE_DIRS:
        index_url = urljoin(DWD_BASE, rel_dir)
        (content, _status, _final_url), _attempts = retry_call(request_bytes, index_url)
        parser = LinkParser()
        parser.feed(content.decode("utf-8", errors="replace"))
        for href in parser.hrefs:
            if href.startswith("../") or href.endswith("/"):
                continue
            if not (href.lower().endswith(".txt") or href.lower().endswith(".pdf")):
                continue
            url = urljoin(index_url, href)
            local = out_dir / "germany_dwd" / rel_dir / href
            tasks.append(DownloadTask("germany_dwd", url, local, rel_dir.rstrip("/")))
    return tasks


def download_one(task: DownloadTask, logger: RunLogger, resume: bool) -> str:
    if resume and task.output_path.exists() and task.output_path.stat().st_size > 0:
        logger.manifest(
            {
                "timestamp_utc": utc_now(),
                "source": task.source,
                "source_group": task.source_group,
                "url": task.url,
                "path": str(task.output_path),
                "bytes": task.output_path.stat().st_size,
                "sha256": sha256_file(task.output_path),
                "status": "skipped_existing",
                "attempts": 0,
                "note": "resume",
            }
        )
        return "skipped"
    attempts = 0
    try:
        (body, status, final_url), attempts = retry_call(request_bytes, task.url)
        atomic_write_bytes(task.output_path, body)
        logger.manifest(
            {
                "timestamp_utc": utc_now(),
                "source": task.source,
                "source_group": task.source_group,
                "url": final_url,
                "path": str(task.output_path),
                "bytes": task.output_path.stat().st_size,
                "sha256": sha256_file(task.output_path),
                "status": status,
                "attempts": attempts,
                "note": "downloaded",
            }
        )
        return "downloaded"
    except Exception as exc:
        logger.failed(
            {
                "timestamp_utc": utc_now(),
                "source": task.source,
                "source_group": task.source_group,
                "url": task.url,
                "path": str(task.output_path),
                "attempts": attempts or RETRIES,
                "error": repr(exc),
            }
        )
        return "failed"


def run_dwd(out_dir: Path, workers: int, dry_run: bool, resume: bool, logger: RunLogger) -> None:
    tasks = list_dwd_tasks(out_dir)
    atomic_write_json(out_dir / "germany_dwd" / "download_plan.json", [task.__dict__ | {"output_path": str(task.output_path)} for task in tasks])
    print(f"DWD Germany: found {len(tasks)} vine files.")
    if dry_run:
        return
    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(download_one, task, logger, resume) for task in tasks]
        for future in as_completed(futures):
            counts[future.result()] += 1
    print(f"DWD Germany: {counts}")


def tempo_endpoint(path: str) -> str:
    return urljoin(TEMPO_API, path.lstrip("/"))


def tempo_fetch_page(path: str, **params: Any) -> dict[str, Any]:
    (payload, _attempts) = retry_call(request_json, tempo_endpoint(path), params=params)
    status = payload.get("status") or {}
    code = status.get("code")
    if code not in (None, 0, 200):
        raise RuntimeError(f"TEMPO status {code}: {status.get('message')}")
    return payload


def tempo_fetch_all(path: str, *, page_size: int = MAX_TEMPO_PAGE_SIZE, **params: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor: int | None = None
    seen: set[int] = set()
    while True:
        page_params = dict(params)
        page_params["pagesize"] = page_size
        if cursor is not None:
            page_params["cursor"] = cursor
        payload = tempo_fetch_page(path, **page_params)
        data = payload.get("data") or []
        rows.extend(data)
        pagination = payload.get("pagination") or {}
        last_cursor = pagination.get("lastCursor")
        total = pagination.get("totalCount")
        if not data or last_cursor in (None, cursor) or last_cursor in seen:
            break
        if total is not None and len(rows) >= int(total):
            break
        seen.add(int(last_cursor))
        cursor = int(last_cursor) + 1
    return rows


def text_contains_any(value: Any, terms: tuple[str, ...]) -> bool:
    if value is None:
        return False
    text = str(value).casefold()
    return any(term.casefold() in text for term in terms)


def row_text(row: dict[str, Any]) -> str:
    return " ".join(str(value) for value in row.values() if value is not None)


def find_grape_taxa(taxa: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [taxon for taxon in taxa if text_contains_any(row_text(taxon), GRAPE_TERMS)]


def find_france_country_ids(countries: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for country in countries:
        if text_contains_any(row_text(country), FRANCE_TERMS):
            ids.append(int(country["id"]))
    return ids


def batch(values: list[int], size: int) -> list[list[int]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def write_jsonl_artifact(path: Path, rows: list[dict[str, Any]], logger: RunLogger, source_group: str, note: str) -> None:
    reset_file(path)
    append_jsonl(path, rows)
    logger.manifest(
        {
            "timestamp_utc": utc_now(),
            "source": "france_tempo",
            "source_group": source_group,
            "url": TEMPO_API,
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "status": "generated",
            "attempts": 1,
            "note": note,
        }
    )


def run_tempo(out_dir: Path, workers: int, dry_run: bool, logger: RunLogger) -> None:
    france_dir = out_dir / "france_tempo"
    raw_dir = france_dir / "raw"
    meta_dir = france_dir / "metadata"
    france_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        france_dir / "api_reference.json",
        {
            "api_base": TEMPO_API,
            "documentation": TEMPO_WEBSERVICES,
            "access_scope": "public unauthenticated data only",
            "query_terms": GRAPE_TERMS,
        },
    )

    sources = tempo_fetch_all("/pheno/source")
    taxa = tempo_fetch_all("/pheno/taxon")
    countries = tempo_fetch_all("/pheno/site/country")
    regions = tempo_fetch_all("/pheno/site/region")
    departments = tempo_fetch_all("/pheno/site/department")
    communes = tempo_fetch_all("/pheno/site/commune")
    licenses = tempo_fetch_all("/pheno/license")
    stages = tempo_fetch_all("/pheno/stage")

    grape_taxa = find_grape_taxa(taxa)
    grape_taxon_ids = sorted({int(row["id"]) for row in grape_taxa})
    france_country_ids = find_france_country_ids(countries)
    print(f"TEMPO France: found {len(grape_taxon_ids)} grape-like taxon IDs and {len(france_country_ids)} France country IDs.")

    metadata = {
        "sources": sources,
        "taxa_all": taxa,
        "taxa_grape_candidates": grape_taxa,
        "countries": countries,
        "regions": regions,
        "departments": departments,
        "communes": communes,
        "france_country_ids": france_country_ids,
        "licenses": licenses,
        "stages": stages,
    }
    atomic_write_json(meta_dir / "metadata_snapshot.json", metadata)

    for source in sources:
        licenses_text = " ".join(row_text(license_row) for license_row in source.get("licenses") or [])
        if text_contains_any(row_text(source), ("subject to", "authorization", "autorisation", "pro", "vitadapt")):
            logger.skipped(
                {
                    "timestamp_utc": utc_now(),
                    "source": "france_tempo",
                    "id": source.get("id"),
                    "name": source.get("name"),
                    "reason": f"source may require authorization; public API only. licenses={licenses_text}",
                    "url": source.get("website"),
                }
            )

    if dry_run:
        atomic_write_json(
            france_dir / "download_plan.json",
            {
                "grape_taxon_ids": grape_taxon_ids,
                "france_country_ids": france_country_ids,
                "planned_endpoints": ["/pheno/cache", "/pheno/additionaldata"],
            },
        )
        return

    if not grape_taxon_ids:
        logger.failed(
            {
                "timestamp_utc": utc_now(),
                "source": "france_tempo",
                "source_group": "taxon_discovery",
                "url": tempo_endpoint("/pheno/taxon"),
                "path": "",
                "attempts": RETRIES,
                "error": "No grape-like taxon IDs found.",
            }
        )
        return

    site_ids_france: set[int] | None = None
    if france_country_ids:
        site_rows: list[dict[str, Any]] = []
        for country_id in france_country_ids:
            site_rows.extend(tempo_fetch_all("/pheno/site", country=[country_id]))
        site_ids_france = {int(row["id"]) for row in site_rows if row.get("id") is not None}
        write_jsonl_artifact(meta_dir / "sites_france.jsonl", site_rows, logger, "metadata/sites", "France sites from TEMPO")

    cache_rows: list[dict[str, Any]] = []
    for taxon_id in grape_taxon_ids:
        rows = tempo_fetch_all("/pheno/cache", taxon=[taxon_id])
        if site_ids_france is not None:
            rows = [row for row in rows if row.get("site") in site_ids_france]
        cache_rows.extend(rows)
        print(f"TEMPO France: taxon {taxon_id} yielded {len(rows)} France/public cache rows.")

    dedup_cache: dict[int, dict[str, Any]] = {}
    for row in cache_rows:
        row_id = row.get("id")
        if row_id is not None:
            dedup_cache[int(row_id)] = row
    cache_rows = [dedup_cache[key] for key in sorted(dedup_cache)]
    write_jsonl_artifact(raw_dir / "tempo_grape_cache_public_france.jsonl", cache_rows, logger, "raw/cache", "public grape cache rows")

    additional_ids = sorted({int(row["additionalData"]) for row in cache_rows if row.get("additionalData") is not None})
    atomic_write_json(raw_dir / "additionaldata_ids.json", additional_ids)
    additional_rows: list[dict[str, Any]] = []
    failures: list[tuple[list[int], Exception]] = []

    def fetch_additional(ids: list[int]) -> list[dict[str, Any]]:
        payload = tempo_fetch_page("/pheno/additionaldata", id=ids, pagesize=min(MAX_TEMPO_PAGE_SIZE, max(1, len(ids))))
        return payload.get("data") or []

    with ThreadPoolExecutor(max_workers=min(workers, 8)) as executor:
        future_to_ids = {executor.submit(fetch_additional, ids): ids for ids in batch(additional_ids, 500)}
        for future in as_completed(future_to_ids):
            ids = future_to_ids[future]
            try:
                additional_rows.extend(future.result())
            except Exception as exc:
                failures.append((ids, exc))

    for ids, exc in failures:
        logger.failed(
            {
                "timestamp_utc": utc_now(),
                "source": "france_tempo",
                "source_group": "raw/additionaldata",
                "url": tempo_endpoint("/pheno/additionaldata"),
                "path": str(raw_dir / "tempo_grape_additionaldata_public_france.jsonl"),
                "attempts": RETRIES,
                "error": f"{repr(exc)} for id batch {ids[:5]}... ({len(ids)} ids)",
            }
        )
    additional_rows.sort(key=lambda row: int(row.get("id", 0)))
    write_jsonl_artifact(
        raw_dir / "tempo_grape_additionaldata_public_france.jsonl",
        additional_rows,
        logger,
        "raw/additionaldata",
        "public grape additional data rows",
    )


def write_run_config(out_dir: Path, args: argparse.Namespace) -> None:
    atomic_write_json(
        out_dir / "run_config.json",
        {
            "timestamp_utc": utc_now(),
            "source": args.source,
            "workers": args.workers,
            "dry_run": args.dry_run,
            "resume": args.resume,
            "dwd_base": DWD_BASE,
            "dwd_vine_dirs": DWD_VINE_DIRS,
            "tempo_api": TEMPO_API,
            "tempo_webservices": TEMPO_WEBSERVICES,
            "max_workers": MAX_WORKERS,
            "retries": RETRIES,
        },
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("all", "france", "germany"), default="all")
    parser.add_argument("--workers", type=ensure_workers, default=DEFAULT_WORKERS)
    parser.add_argument("--out", type=Path, default=Path("data") / "phenology_grape")
    parser.add_argument("--dry-run", action="store_true", help="Build plans and metadata without downloading raw data files.")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    write_run_config(out_dir, args)
    logger = RunLogger(out_dir)

    if args.source in ("all", "germany"):
        run_dwd(out_dir, args.workers, args.dry_run, args.resume, logger)
    if args.source in ("all", "france"):
        run_tempo(out_dir, args.workers, args.dry_run, logger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
