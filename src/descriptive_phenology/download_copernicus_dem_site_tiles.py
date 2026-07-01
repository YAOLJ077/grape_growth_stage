#!/usr/bin/env python
"""Download Copernicus GLO-30 DEM tiles covering phenology sites."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd
import requests


COUNTRY_TABLES = [
    Path("data/phenology_grape/processed/france_grape_phenology_complete.csv"),
    Path("data/phenology_grape/processed/germany_grape_phenology_complete.csv"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, nargs="+", default=COUNTRY_TABLES)
    parser.add_argument("--out-dir", type=Path, default=Path("data/topography/raw/copernicus_dem_glo30/site_tiles"))
    parser.add_argument("--manifest", type=Path, default=Path("data/topography/metadata/copernicus_dem_glo30_site_tiles.csv"))
    parser.add_argument("--max-tiles", type=int, default=0, help="Download top N site-dense tiles; 0 downloads all site tiles.")
    parser.add_argument("--timeout", type=int, default=180)
    return parser.parse_args()


def tile_name(lat_floor: int, lon_floor: int) -> str:
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat_floor):02d}_00_{ew}{abs(lon_floor):03d}_00_DEM"


def tile_url(lat_floor: int, lon_floor: int) -> str:
    name = tile_name(lat_floor, lon_floor)
    return f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"


def tile_path(out_dir: Path, lat_floor: int, lon_floor: int) -> Path:
    return out_dir / f"{tile_name(lat_floor, lon_floor)}.tif"


def site_tiles(paths: list[Path], max_tiles: int) -> pd.DataFrame:
    columns = ["country_name", "site_id", "latitude", "longitude", "doy"]
    df = pd.concat(
        [pd.read_csv(path, usecols=columns, low_memory=False) for path in paths],
        ignore_index=True,
    )
    df = df.dropna(subset=["country_name", "site_id", "latitude", "longitude"])
    sites = (
        df.groupby(["country_name", "site_id"], dropna=False)
        .agg(latitude=("latitude", "first"), longitude=("longitude", "first"), n_observations=("doy", "size"))
        .reset_index()
    )
    sites["tile_lat"] = sites["latitude"].map(math.floor)
    sites["tile_lon"] = sites["longitude"].map(math.floor)
    tiles = (
        sites.groupby(["tile_lat", "tile_lon"], dropna=False)
        .agg(n_sites=("site_id", "nunique"), n_observations=("n_observations", "sum"))
        .reset_index()
        .sort_values(["n_sites", "n_observations"], ascending=False)
        .reset_index(drop=True)
    )
    if max_tiles > 0:
        tiles = tiles.head(max_tiles).copy()
    tiles["tile_name"] = [tile_name(int(row.tile_lat), int(row.tile_lon)) for row in tiles.itertuples()]
    tiles["url"] = [tile_url(int(row.tile_lat), int(row.tile_lon)) for row in tiles.itertuples()]
    return tiles


def download_one(url: str, path: Path, timeout: int) -> tuple[str, int]:
    if path.exists() and path.stat().st_size > 0:
        return "exists", path.stat().st_size
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.unlink(missing_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with tmp.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    tmp.replace(path)
    return "downloaded", path.stat().st_size


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    tiles = site_tiles(args.input, args.max_tiles)
    statuses = []
    for i, row in enumerate(tiles.itertuples(index=False), start=1):
        path = tile_path(args.out_dir, int(row.tile_lat), int(row.tile_lon))
        status, size = download_one(row.url, path, args.timeout)
        statuses.append(status)
        print(f"[{i:03d}/{len(tiles):03d}] {status:10s} {path.name} {size / 1024 / 1024:.1f} MB")
    tiles["local_path"] = [str(tile_path(args.out_dir, int(row.tile_lat), int(row.tile_lon))) for row in tiles.itertuples()]
    tiles["status"] = statuses
    tiles["size_mb"] = [Path(path).stat().st_size / 1024 / 1024 for path in tiles["local_path"]]
    tiles.to_csv(args.manifest, index=False)
    print(f"Tiles: {len(tiles):,}")
    print(f"Total size: {tiles['size_mb'].sum():.1f} MB")
    print(f"Manifest written to: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
