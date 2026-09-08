"""Reuse local ERA5-Land temperatures and fetch missing days into site-name CSVs."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from numbers import Number
from pathlib import Path
import re
import sys
import time
import unicodedata

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "data/phenology/derived/modeling/france_germany_four_stage/site_inventory.csv"
COLLECTION = "ECMWF/ERA5_LAND/DAILY_AGGR"


@dataclass(frozen=True)
class Site:
    uid: str
    name: str
    filename: str
    lat: float
    lon: float
    start: pd.Timestamp
    end: pd.Timestamp


def safe_filename(name):
    value = unicodedata.normalize("NFC", str(name)).strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).rstrip(". ")
    if not value or value in {".", ".."}:
        raise ValueError("Site names must produce nonempty safe filenames")
    if len(value.encode("utf-8")) > 230:
        suffix = "_" + hashlib.sha256(value.encode()).hexdigest()[:12]
        value = value.encode()[:210].decode("utf-8", errors="ignore") + suffix
    return value + ".csv"


def load_inventory(path):
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {"site_uid", "site_name", "lat", "lon", "first_year", "last_year"}
    if not required.issubset(frame) or frame.empty:
        raise ValueError(f"Inventory requires {sorted(required)}")
    sites, ids, filenames = [], set(), set()
    for row in frame.itertuples(index=False):
        filename = safe_filename(row.site_name)
        if not row.site_uid.strip() or row.site_uid in ids or filename.casefold() in filenames:
            raise ValueError("Duplicate site identity or ambiguous site-name filename")
        first, last = int(row.first_year), int(row.last_year)
        lat, lon = float(row.lat), float(row.lon)
        if not 1950 <= first <= last <= 2261:
            raise ValueError("Invalid observation year range")
        if not np.isfinite([lat, lon]).all() or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Invalid site coordinates")
        sites.append(Site(row.site_uid, row.site_name, filename, lat, lon,
                          pd.Timestamp(first - 1, 1, 1), pd.Timestamp(last, 12, 31)))
        ids.add(row.site_uid)
        filenames.add(filename.casefold())
    return sites


def empty_series():
    return pd.Series([], index=pd.DatetimeIndex([]), dtype=float)


def normalize(dates, temperatures, *, kelvin=False):
    if any(isinstance(v, Number) for v in dates):
        raise ValueError("Weather dates must be calendar dates, not numeric timestamps")
    parsed = pd.DatetimeIndex(pd.to_datetime(dates, format="mixed", errors="raise"))
    if parsed.tz is not None or parsed.hasnans or not parsed.equals(parsed.normalize()):
        raise ValueError("Weather dates must be nonmissing timezone-free calendar dates")
    values = pd.to_numeric(pd.Series(list(temperatures)).replace("", np.nan), errors="raise").to_numpy(dtype=float)
    if np.isinf(values).any():
        raise ValueError("Infinite temperatures are invalid")
    if kelvin:
        values -= 273.15
    finite = np.isfinite(values)
    if ((values[finite] < -100) | (values[finite] > 70)).any():
        raise ValueError("Temperature outside Celsius sanity bounds; verify units")
    return merge_values(empty_series(), pd.Series(values[finite], index=parsed[finite]))


def merge_values(existing, incoming):
    joined = pd.concat([existing, incoming])
    if joined.empty:
        return empty_series()
    grouped = joined.groupby(level=0)
    if ((grouped.max() - grouped.min()) > 1e-7).any():
        raise ValueError("Conflicting temperatures for the same site and date")
    return grouped.first().sort_index()


def missing_windows(values, start, end):
    """Inclusive missing intervals, split into at most one calendar year each."""
    missing = pd.date_range(start, end).difference(values.dropna().index)
    result = []
    for date in missing:
        if result and date == result[-1][1] + pd.Timedelta(days=1) and date.year == result[-1][1].year:
            result[-1] = (result[-1][0], date)
        else:
            result.append((date, date))
    return result


def read_local(directories, sites):
    """Recognize explicit Kelvin/Celsius schemas; index-only files are not weather."""
    by_uid = {site.uid: site for site in sites}
    by_name = {site.name: site.uid for site in sites}
    by_filename = {site.filename: site.uid for site in sites}
    parts = {site.uid: [] for site in sites}
    audit = {"used_files": [], "ignored_files": []}
    paths = set()
    for directory in directories:
        directory = Path(directory)
        if directory.is_file():
            paths.add(directory.resolve())
        elif directory.is_dir():
            paths.update(p.resolve() for p in directory.rglob("*.csv"))
            paths.update(p.resolve() for p in directory.rglob("*.csv.gz"))
    for path in sorted(paths):
        columns = pd.read_csv(path, nrows=0).columns
        date_col = next((c for c in ("Date", "weather_date", "date") if c in columns), None)
        temp_col = next((c for c in ("Tmean", "temperature_2m_c", "tmean_c", "temperature_2m") if c in columns), None)
        if date_col is None or temp_col is None:
            audit["ignored_files"].append({"path": str(path), "reason": "No daily date/temperature columns"})
            continue
        identity_available = ("site_uid" in columns or {"country", "source", "site_id"}.issubset(columns)
                              or "weather_id" in columns or "site_name" in columns)
        if not identity_available and path.name.removesuffix(".gz") not in by_filename:
            audit["ignored_files"].append({"path": str(path), "reason": "Filename does not match selected sites; no qualified ID"})
            continue
        matched = 0
        for chunk in pd.read_csv(path, dtype=str, keep_default_na=False, chunksize=100000):
            if "site_uid" in columns:
                identities = chunk.site_uid
            elif {"country", "source", "site_id"}.issubset(columns):
                identities = chunk.country + "|" + chunk.source + "|" + chunk.site_id
            elif "weather_id" in columns:
                identities = chunk.weather_id.str.rsplit("|", n=1).str[0]
            elif "site_name" in columns:
                identities = chunk.site_name.map(by_name)
            elif path.name.removesuffix(".gz") in by_filename:
                identities = pd.Series(by_filename[path.name.removesuffix(".gz")], index=chunk.index)
            else:
                raise ValueError(f"Daily weather lacks unambiguous site identity: {path}")
            chunk = chunk.assign(_uid=identities)
            for uid, group in chunk[chunk._uid.isin(by_uid)].groupby("_uid"):
                values = normalize(group[date_col], group[temp_col], kelvin=temp_col == "temperature_2m")
                site = by_uid[uid]
                values = values.loc[site.start:site.end]
                parts[uid].append(values)
                matched += len(values)
        audit["used_files"].append({"path": str(path), "n_matched": matched,
                                   "temperature_column": temp_col, "sha256": file_hash(path)})
    cache = {uid: merge_values(empty_series(), pd.concat(pieces)) if pieces else empty_series()
             for uid, pieces in parts.items()}
    return cache, audit


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parse_ee_rows(payload):
    if not payload:
        return empty_series()
    frame = pd.DataFrame(payload[1:], columns=payload[0])
    if not {"time", "temperature_2m"}.issubset(frame):
        raise ValueError("Unexpected Earth Engine response schema")
    dates = pd.to_datetime(frame.time, unit="ms", utc=True).dt.tz_localize(None)
    return normalize(dates, frame.temperature_2m, kelvin=True)


class EarthEngineProvider:
    """Authenticated, read-only daily point downloads on the native ERA5 grid."""
    def __init__(self, project):
        try:
            import ee
        except ImportError as exc:
            raise RuntimeError("Install earthengine-api; see data/weather/README.md") from exc
        try:
            ee.Initialize(project=project)
        except Exception as exc:
            raise RuntimeError("Earth Engine initialization failed. Authenticate with earthengine authenticate "
                               "and supply an enabled --project; see data/weather/README.md") from exc
        self.ee = ee
        self.collection = ee.ImageCollection(COLLECTION).select("temperature_2m")
        first = self.collection.aggregate_min("system:time_start").getInfo()
        last = self.collection.aggregate_max("system:time_start").getInfo()
        if first is None or last is None:
            raise RuntimeError("Earth Engine collection is empty or inaccessible")
        self.first_date = pd.to_datetime(first, unit="ms", utc=True).tz_localize(None).normalize()
        self.last_date = pd.to_datetime(last, unit="ms", utc=True).tz_localize(None).normalize()
        self.projection = self.collection.first().projection().getInfo()

    def fetch(self, site, start, end):
        end_exclusive = end + pd.Timedelta(days=1)
        selected = self.collection.filterDate(start.strftime("%Y-%m-%d"), end_exclusive.strftime("%Y-%m-%d"))
        point = self.ee.Geometry.Point([site.lon, site.lat])
        request = selected.getRegion(point, crs=self.projection["crs"],
                                     crsTransform=self.projection["transform"])
        for attempt in range(3):
            try:
                return parse_ee_rows(request.getInfo())
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)


def write_weather(values, path):
    """Only replace the destination after a complete valid two-column CSV exists."""
    path = Path(path)
    if path.exists():
        old = pd.read_csv(path, keep_default_na=False)
        if old.columns.tolist() != ["Date", "Tmean"]:
            raise ValueError(f"Existing destination does not have Date,Tmean columns: {path}")
        previous = normalize(old.Date, old.Tmean)
        if not previous.index.isin(values.index).all():
            raise ValueError(f"Refusing to truncate existing dates outside the requested window: {path}")
        merge_values(previous, values)  # Refuse changes to previously saved temperatures.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".csv.part")
    pd.DataFrame({"Date": values.index.strftime("%Y-%m-%d"), "Tmean": values.to_numpy()}).to_csv(temporary, index=False)
    temporary.replace(path)


def run(inventory, local_dirs, output, *, provider=None, site_uid=None, limit=None):
    sites = load_inventory(inventory)
    if site_uid:
        sites = [site for site in sites if site.uid == site_uid]
        if not sites:
            raise ValueError(f"Site is not in the inventory: {site_uid}")
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        sites = sites[:limit]
    output = Path(output)
    cached, audit = read_local([*local_dirs, output], sites)
    metadata = metadata_directory(output, sites, filtered=bool(site_uid) or limit is not None)
    metadata.mkdir(parents=True, exist_ok=True)
    summaries, gaps = [], []
    for index, site in enumerate(sites):
        values = cached[site.uid]
        n_reused = len(values)
        errors = []
        if provider is not None:
            start, end = max(site.start, provider.first_date), min(site.end, provider.last_date)
            for left, right in missing_windows(values, start, end):
                try:
                    incoming = provider.fetch(site, left, right)
                    if not incoming.index.isin(pd.date_range(left, right)).all():
                        raise ValueError("Downloaded dates are outside the requested interval")
                    values = merge_values(values, normalize(incoming.index, incoming.to_numpy()))
                    if len(values):
                        write_weather(values, output / site.filename)
                except Exception as exc:
                    errors.append({"start": str(left.date()), "end": str(right.date()), "error": str(exc)})
                    # Retain prior successes and stop this site's failed requests.
                    break
        if len(values):
            write_weather(values, output / site.filename)
        missing = missing_windows(values, site.start, site.end)
        n_expected = (site.end - site.start).days + 1
        for left, right in missing:
            gaps.append({"site_uid": site.uid, "filename": site.filename,
                         "start": str(left.date()), "end": str(right.date()),
                         "n_days": (right-left).days + 1})
        summaries.append({"site_uid": site.uid, "site_name": site.name, "filename": site.filename,
                          "lat": site.lat, "lon": site.lon,
                          "requested_start": str(site.start.date()), "requested_end": str(site.end.date()),
                          "first_available": str(values.index.min().date()) if len(values) else "",
                          "last_available": str(values.index.max().date()) if len(values) else "",
                          "n_expected": n_expected, "n_reused": n_reused, "n_downloaded": len(values)-n_reused,
                          "n_missing": n_expected-len(values),
                          "status": "complete" if not missing else "incomplete" if len(values) else "missing",
                          "download_errors": json.dumps(errors),
                          "sha256": file_hash(output / site.filename) if len(values) else ""})
        if provider is not None or (index + 1) % 250 == 0:
            print(f"{index + 1}/{len(sites)} {site.name}: {len(values)}/{n_expected} days", flush=True)
    pd.DataFrame(summaries).to_csv(metadata / "manifest.csv", index=False)
    pd.DataFrame(gaps, columns=["site_uid", "filename", "start", "end", "n_days"]).to_csv(metadata / "missing_periods.csv", index=False)
    details = {"inventory": str(Path(inventory).resolve()), "inventory_sha256": file_hash(inventory),
               "n_sites": len(sites), "collection": COLLECTION, "units": "degrees Celsius",
               "requested_window": "Jan 1 of first_year minus 1 through Dec 31 of last_year, inclusive",
               "created_utc": pd.Timestamp.now(tz="UTC").isoformat(), "local_audit": audit,
               "download_enabled": provider is not None,
               "collection_start": str(provider.first_date.date()) if provider else None,
               "collection_end": str(provider.last_date.date()) if provider else None,
               "download_sampling": "native ERA5-Land projection/transform; point; no spatial averaging",
               "download_projection": getattr(provider, "projection", None),
               "reused_sampling": "Inherited from source files, not reverified; consult local_audit hashes and original extraction metadata",
               "temporal_filling": "none"}
    (metadata / "run.json").write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    return summaries


def metadata_directory(output, sites, *, filtered):
    root = Path(output) / "metadata"
    if filtered:
        scope = hashlib.sha256(json.dumps([site.uid for site in sites]).encode()).hexdigest()[:16]
        return root / "subsets" / scope
    return root


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--local-dir", action="append", type=Path, help="Additional CSV directory or CSV file; repeatable")
    parser.add_argument("--output", type=Path, default=ROOT / "data/weather/sites")
    parser.add_argument("--download", action="store_true", help="Fetch missing periods from authenticated Earth Engine")
    parser.add_argument("--project", help="Earth Engine-enabled Google Cloud project")
    parser.add_argument("--site", help="Exact source-qualified site_uid to process")
    parser.add_argument("--limit", type=int, help="Process only the first N inventory sites")
    args = parser.parse_args(argv)
    if args.download and not args.project:
        parser.error("--download requires --project")
    try:
        # Always reuse and audit available local data before requesting credentials.
        directories = [ROOT / "data/gee", *(args.local_dir or [])]
        result = run(args.inventory, directories, args.output, site_uid=args.site, limit=args.limit)
        if args.download and any(row["n_missing"] for row in result):
            provider = EarthEngineProvider(args.project)
            result = run(args.inventory, directories, args.output, provider=provider, site_uid=args.site, limit=args.limit)
        counts = pd.Series([row["status"] for row in result]).value_counts().to_dict()
        print(json.dumps(counts))
        selected = [site for site in load_inventory(args.inventory) if site.uid in {row["site_uid"] for row in result}]
        metadata = metadata_directory(args.output, selected, filtered=bool(args.site) or args.limit is not None)
        print(f"Coverage audit: {metadata / 'manifest.csv'}")
        return 0 if all(row["status"] == "complete" for row in result) else 2
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
