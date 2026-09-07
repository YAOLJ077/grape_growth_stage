"""Rebuild the four-stage site map using Python stdlib and macOS Swift."""
import collections
import csv
import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "fig/study_area"
SOURCE = ROOT / "data/phenology/derived/paper_targets/observations.csv"
BOUNDARY = ROOT / "data/topography/metadata/countries.geojson"


def main():
    selection = json.loads(SOURCE.with_name('quality.json').read_text())
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert source_hash == selection['combined']['sha256'], 'Rebuild paper targets first'
    assert hashlib.sha256((ROOT / selection['source']).read_bytes()).hexdigest() == selection['source_sha256'], 'Paper targets are stale'
    sites = {}
    observed_years = collections.defaultdict(set)
    count = 0
    for row in csv.DictReader(SOURCE.open(newline="", encoding="utf-8")):
        assert row['BBCH'] in {'07', '65', '81', '89'}
        count += 1
        lat, lon = float(row["lat"]), float(row["lon"])
        assert math.isfinite(lat) and -90 <= lat <= 90
        assert math.isfinite(lon) and -180 <= lon <= 180
        date = datetime.date.fromisoformat(row["Date"]).isoformat()
        assert date >= "1951-01-01", "Rebuild the current 1951-onward phenology CSV first"
        key = row["site"]
        assert key
        observed_years[key].add(int(date[:4]))
        if key not in sites:
            sites[key] = dict(site=key, country=row["country"], lat=lat, lon=lon,
                              n_observations=0, first_date=date, last_date=date)
        site = sites[key]
        assert (site["country"], site["lat"], site["lon"]) == (row["country"], lat, lon), key
        site["n_observations"] += 1
        site["first_date"] = min(site["first_date"], date)
        site["last_date"] = max(site["last_date"], date)
    rows = sorted(sites.values(), key=lambda r: r["site"])
    for site in rows:
        years = sorted(observed_years[site["site"]])
        site["n_years"] = len(years)
        site["observed_years"] = ";".join(map(str, years))
        assert 1 <= site["n_years"] <= int(site["last_date"][:4]) - int(site["first_date"][:4]) + 1
    assert sum(r["n_observations"] for r in rows) == count
    assert count == selection['combined']['rows']
    assert rows
    with (OUT / "site_inventory.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    # Retain whole polygons intersecting the European rendering window.
    polygons = []
    for feature in json.loads(BOUNDARY.read_text())["features"]:
        geometry = feature["geometry"]
        if geometry is None:
            continue
        if geometry["type"] == "Polygon":
            parts = [geometry["coordinates"]]
        elif geometry["type"] == "MultiPolygon":
            parts = geometry["coordinates"]
        else:
            raise ValueError(geometry["type"])
        for rings in parts:
            outer = rings[0]
            xs, ys = zip(*[(p[0], p[1]) for p in outer])
            if min(xs) <= 38 and max(xs) >= -18 and min(ys) <= 70 and max(ys) >= 32:
                polygons.append(rings)
    quality = dict(
        source=str(SOURCE.relative_to(ROOT)),
        source_sha256=source_hash,
        inventory_source=selection['source'], inventory_sha256=selection['source_sha256'],
        target_policy=selection['policy'], stages=['07', '65', '81', '89'],
        boundaries=str(BOUNDARY.relative_to(ROOT)),
        boundaries_sha256=hashlib.sha256(BOUNDARY.read_bytes()).hexdigest(),
        records=count, source_qualified_sites=len(rows),
        distinct_coordinate_pairs=len({(r["lat"], r["lon"]) for r in rows}),
        sites_by_country=dict(sorted(collections.Counter(r["country"] or "unspecified" for r in rows).items())),
        first_date=min(r["first_date"] for r in rows),
        last_date=max(r["last_date"] for r in rows),
        bounds=dict(lat_min=min(r["lat"] for r in rows), lat_max=max(r["lat"] for r in rows),
                    lon_min=min(r["lon"] for r in rows), lon_max=max(r["lon"] for r in rows)),
        filters="All countries; BBCH07/65/81/89 after inherited direct-source BBCH, 1951-onward and chronology-v2 screening; any one selected stage qualifies a site or year",
        coordinate_conflicts=0, invalid_coordinates=0,
        year_availability_definition="Distinct calendar years with at least one BBCH07, 65, 81 or 89 observation per source-qualified site, pooled over varieties; not complete-stage or weather-year coverage",
        observed_years_min=min(r["n_years"] for r in rows),
        observed_years_max=max(r["n_years"] for r in rows),
        colour_classes=[dict(label=label, minimum=low, maximum=high,
                             sites=sum(low <= r["n_years"] <= high for r in rows))
                        for label, low, high in [("1–5", 1, 5), ("6–10", 6, 10),
                                                 ("11–20", 11, 20), ("21–40", 21, 40),
                                                 (">40", 41, 9999)]],
    )
    with tempfile.TemporaryDirectory(prefix="grape-study-area-") as tmp:
        payload = Path(tmp) / "map.json"
        payload.write_text(json.dumps(dict(sites=rows, polygons=polygons, quality=quality)))
        result = subprocess.run(
            ["swift", "-module-cache-path", "/tmp/grape-workflow-swift-cache",
             str(Path(__file__).with_name("draw_map.swift")), str(payload), str(OUT)],
            check=True, capture_output=True, text=True,
        )
        print(result.stdout, end="")
    quality["rendered_sites"] = len(rows)
    quality["sites_outside_map_frame"] = 0  # Enforced by renderer preconditions.
    (OUT / "map_quality.json").write_text(json.dumps(quality, indent=2) + "\n")
    print(json.dumps(quality, indent=2))


if __name__ == "__main__":
    main()
