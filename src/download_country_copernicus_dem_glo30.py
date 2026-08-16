#!/usr/bin/env python
"""Download Copernicus GLO-30 DEM tiles for country-scale coverage."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

import requests
from shapely.geometry import box, shape
from shapely.ops import unary_union


COUNTRIES = {
    "france": {
        "iso3": "FRA",
        "name": "France",
        "label": "France metropolitan including Corsica",
        "europe_bbox": (-6.0, 41.0, 10.0, 52.0),
    },
    "germany": {
        "iso3": "DEU",
        "name": "Germany",
        "label": "Germany",
        "europe_bbox": (5.0, 47.0, 16.0, 56.0),
    },
    "austria": {
        "iso3": "AUT",
        "name": "Austria",
        "label": "Austria",
        "europe_bbox": (9.0, 46.0, 18.0, 50.0),
    },
    "slovakia": {
        "iso3": "SVK",
        "name": "Slovakia",
        "label": "Slovakia",
        "europe_bbox": (16.0, 47.0, 23.0, 50.0),
    },
    "switzerland": {
        "iso3": "CHE",
        "name": "Switzerland",
        "label": "Switzerland",
        "europe_bbox": (5.0, 45.0, 11.0, 48.0),
    },
    "spain": {
        "iso3": "ESP",
        "name": "Spain",
        "label": "Spain mainland and Balearic Islands",
        "europe_bbox": (-10.0, 35.0, 5.0, 44.0),
    },
}

BOUNDARY_URL = (
    "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
)


@dataclass(frozen=True)
class Tile:
    country: str
    tile_lat: int
    tile_lon: int

    @property
    def name(self) -> str:
        ns = "N" if self.tile_lat >= 0 else "S"
        ew = "E" if self.tile_lon >= 0 else "W"
        return (
            f"Copernicus_DSM_COG_10_{ns}{abs(self.tile_lat):02d}_00_"
            f"{ew}{abs(self.tile_lon):03d}_00_DEM"
        )

    @property
    def url(self) -> str:
        return f"https://copernicus-dem-30m.s3.amazonaws.com/{self.name}/{self.name}.tif"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--countries",
        nargs="+",
        default=["france", "germany", "austria", "slovakia", "switzerland", "spain"],
        choices=sorted(COUNTRIES),
        help="Countries to download.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/topography/raw/copernicus_dem_glo30/country_tiles"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/topography/metadata/copernicus_dem_glo30_country_tiles.csv"),
    )
    parser.add_argument(
        "--boundary-cache",
        type=Path,
        default=Path("data/topography/metadata/countries.geojson"),
    )
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the manifest without downloading tiles.",
    )
    return parser.parse_args()


def load_boundaries(cache_path: Path, timeout: int) -> dict:
    if not cache_path.exists() or cache_path.stat().st_size == 0:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(BOUNDARY_URL, timeout=timeout)
        response.raise_for_status()
        cache_path.write_bytes(response.content)
    return json.loads(cache_path.read_text(encoding="utf-8"))


def feature_iso3(feature: dict) -> str | None:
    props = feature.get("properties", {})
    for key in ("ISO_A3", "ISO3166-1-Alpha-3", "ADM0_A3", "iso_a3"):
        value = props.get(key)
        if isinstance(value, str) and len(value) == 3:
            return value.upper()
    return None


def country_geometry(boundaries: dict, country_key: str):
    config = COUNTRIES[country_key]
    parts = [
        shape(feature["geometry"])
        for feature in boundaries["features"]
        if feature_iso3(feature) == config["iso3"]
        or feature.get("properties", {}).get("name") == config["name"]
    ]
    if not parts:
        raise ValueError(f"No boundary found for {country_key} ({config['iso3']})")
    geometry = unary_union(parts)
    return geometry.intersection(box(*config["europe_bbox"]))


def country_tiles(geometry, country: str) -> list[Tile]:
    min_lon, min_lat, max_lon, max_lat = geometry.bounds
    tiles: list[Tile] = []
    for lat in range(math.floor(min_lat), math.ceil(max_lat)):
        for lon in range(math.floor(min_lon), math.ceil(max_lon)):
            tile_geom = box(lon, lat, lon + 1, lat + 1)
            if geometry.intersects(tile_geom):
                tiles.append(Tile(country=country, tile_lat=lat, tile_lon=lon))
    return tiles


def download_one(url: str, path: Path, timeout: int, retries: int) -> tuple[str, int]:
    if path.exists() and path.stat().st_size > 0:
        return "exists", path.stat().st_size
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.unlink(missing_ok=True)
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            with requests.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                with tmp.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            tmp.replace(path)
            return "downloaded", path.stat().st_size
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            tmp.unlink(missing_ok=True)
    raise RuntimeError(f"Failed to download {url}") from last_error


def write_manifest(manifest: Path, rows: list[dict]) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "country",
        "tile_lat",
        "tile_lon",
        "tile_name",
        "url",
        "local_path",
        "status",
        "size_mb",
    ]
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    boundaries = load_boundaries(args.boundary_cache, args.timeout)

    tiles: list[Tile] = []
    for country in args.countries:
        geometry = country_geometry(boundaries, country)
        selected = country_tiles(geometry, country)
        print(f"{country}: {len(selected):,} tiles")
        tiles.extend(selected)

    rows: list[dict] = []
    for i, tile in enumerate(tiles, start=1):
        country_dir = args.out_dir / tile.country
        country_dir.mkdir(parents=True, exist_ok=True)
        path = country_dir / f"{tile.name}.tif"
        if args.dry_run:
            status, size = "planned", path.stat().st_size if path.exists() else 0
        else:
            status, size = download_one(tile.url, path, args.timeout, args.retries)
        print(f"[{i:03d}/{len(tiles):03d}] {status:10s} {tile.country:7s} {path.name} {size / 1024 / 1024:.1f} MB")
        rows.append(
            {
                "country": tile.country,
                "tile_lat": tile.tile_lat,
                "tile_lon": tile.tile_lon,
                "tile_name": tile.name,
                "url": tile.url,
                "local_path": str(path),
                "status": status,
                "size_mb": size / 1024 / 1024,
            }
        )

    write_manifest(args.manifest, rows)
    total_mb = sum(float(row["size_mb"]) for row in rows)
    print(f"Manifest written to: {args.manifest}")
    print(f"Total listed size: {total_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
