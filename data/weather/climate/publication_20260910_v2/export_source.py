"""Export common-period ERA5-Land temperature profiles and historical warm years.

Monthly temperature averages are in kelvin in Earth Engine. April–September
means weight months by their calendar-day counts. All six months and all 30
normal-period values per calendar month are required at each sampled grid.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from src.base_table.build_site_era5_grid_crosswalk import nearest_grid_center, grid_id

COLLECTION = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
MONTHS = [f"tmean_month_{m:02d}_c" for m in range(1, 13)]
YEARS = list(range(1951, 2026))


def make_grids(sites, native_assignments=None):
    coordinates = sites[["lat", "lon"]].apply(lambda s: s.map(float))
    if not np.isfinite(coordinates).all().all():
        raise ValueError("Nonfinite site coordinates")
    if not coordinates.lat.between(-90, 90).all() or not coordinates.lon.between(-180, 180).all():
        raise ValueError("Out-of-range site coordinates")
    if native_assignments is not None:
        native = native_assignments.copy()
        if (sites.site.duplicated().any() or native.site.duplicated().any()
                or set(sites.site) != set(native.site)):
            raise ValueError("Native grid identities differ from requested sites")
        native = native.set_index('site').loc[sites.site].reset_index()
        matched = native[['lat', 'lon']].apply(lambda s: s.map(float)).to_numpy()
        if not np.array_equal(coordinates.to_numpy(), matched):
            raise ValueError("Native grid source coordinates differ")
        result = native[['era5_grid_lat', 'era5_grid_lon']].rename(
            columns={'era5_grid_lat': 'lat', 'era5_grid_lon': 'lon'}).astype(float)
        ids = [grid_id(r.lat, r.lon) for r in result.itertuples()]
        if ids != native.era5_grid_id.tolist():
            raise ValueError("Native grid identities disagree with grid centres")
        if not np.isfinite(result).all().all():
            raise ValueError("Nonfinite native grid centres")
        result = result.drop_duplicates()
    else:
        result = coordinates.apply(lambda s: s.map(nearest_grid_center)).drop_duplicates()
    result["era5_grid_id"] = [grid_id(r.lat, r.lon) for r in result.itertuples()]
    return result.sort_values("era5_grid_id").reset_index(drop=True)


def publish_tables(frame, grids, output):
    """Require every requested grid and band before publishing usable climate."""
    if frame.era5_grid_id.duplicated().any() or set(frame.era5_grid_id) != set(grids.era5_grid_id):
        raise ValueError("Climate export grid identities do not match requested grids")
    columns = MONTHS + [f"summer_{year}" for year in YEARS]
    numeric = frame[columns].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(numeric).all().all():
        raise ValueError("Climate export has masked or incomplete temperature profiles")
    normals = pd.concat([frame[["era5_grid_id"]], numeric[MONTHS]], axis=1)
    annual = pd.concat([
        pd.DataFrame(dict(era5_grid_id=frame.era5_grid_id, year=y,
                          tmean_apr_sep_c=numeric[f"summer_{y}"])) for y in YEARS
    ], ignore_index=True)
    for name, table in [("monthly_normals.csv", normals), ("annual_summer.csv", annual)]:
        with (output / name).open("x") as stream:
            table.sort_values(list(table.columns[:2]) if name.startswith("annual") else ["era5_grid_id"]).to_csv(stream, index=False)


def submit(sites_path, output, project, native_grids=None):
    import ee
    import httplib2

    if output.exists():
        raise FileExistsError("Choose a new climate export directory")
    if native_grids is None:
        raise ValueError("Submission requires --native-grids verified at actual weather sampling points")
    grids = make_grids(pd.read_csv(sites_path, dtype=str), pd.read_csv(native_grids, dtype=str))
    ee.Initialize(project=project, http_transport=httplib2.Http(timeout=60))
    source = ee.ImageCollection(COLLECTION).select("temperature_2m")
    projection = source.first().projection().getInfo()
    images = []
    normal = source.filterDate("1991-01-01", "2021-01-01")
    for month, name in enumerate(MONTHS, 1):
        subset = normal.filter(ee.Filter.calendarRange(month, month, "month"))
        images.append(subset.mean().subtract(273.15).updateMask(subset.count().eq(30)).rename(name))
    for year in YEARS:
        subset = source.filterDate(f"{year}-04-01", f"{year}-10-01")
        total_days = sum(calendar.monthrange(year, month)[1] for month in range(4, 10))
        def weighted(image):
            date = image.date()
            days = date.advance(1, "month").difference(date, "day")
            return image.subtract(273.15).multiply(days)
        images.append(subset.map(weighted).sum().divide(total_days)
                      .updateMask(subset.count().eq(6)).rename(f"summer_{year}"))
    image = ee.Image.cat(images)
    points = ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([row.lon, row.lat]), {"era5_grid_id": row.era5_grid_id})
        for row in grids.itertuples()
    ])
    sampled = image.reduceRegions(collection=points, reducer=ee.Reducer.first(),
        crs=projection["crs"], crsTransform=projection["transform"], tileScale=4)
    description = "grape_climate_" + output.name
    task = ee.batch.Export.table.toDrive(collection=sampled, description=description,
        folder="grape_phenology_climate", fileNamePrefix=description, fileFormat="CSV",
        selectors=["era5_grid_id", *MONTHS, *[f"summer_{y}" for y in YEARS]])
    output.mkdir(parents=True)
    grids.to_csv(output / "grids.csv", index=False)
    (output / "export_source.py").write_bytes(Path(__file__).read_bytes())
    metadata = dict(project=project, collection=COLLECTION, band="temperature_2m",
        normal_period=[1991, 2020], annual_years=YEARS, projection=projection,
        units="degrees Celsius", seasonal_mean="calendar-day-weighted April–September monthly means",
        normal_mean="equal-year calendar-month means; 30 finite values required",
        grid_sampling="native transform at official 0.1 degree grid centre; no interpolation",
        temperature_input="RAW",
        native_grid_source=str(native_grids.resolve()),
        native_grid_sha256=hashlib.sha256(native_grids.read_bytes()).hexdigest(),
        sites_source=str(sites_path.resolve()), source_sha256=hashlib.sha256(sites_path.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        n_grids=len(grids), task_id=task.id, description=description)
    (output / "request.json").write_text(json.dumps(metadata, indent=2) + "\n")
    task.start()
    metadata["task_id"] = task.id
    (output / "request.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["submit", "status", "collect"])
    parser.add_argument("--sites", type=Path, default=ROOT / "data/site_inventory.csv")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--project", default="smart-soil-erosion")
    parser.add_argument("--native-grids", type=Path)
    args = parser.parse_args()
    if args.command == "submit":
        return submit(args.sites, args.output, args.project, args.native_grids)
    import ee
    import httplib2
    request = json.loads((args.output / "request.json").read_text())
    ee.Initialize(project=request["project"], http_transport=httplib2.Http(timeout=60))
    status = ee.data.getTaskStatus(request["task_id"])
    (args.output / "task_status.json").write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps(status, indent=2))
    if args.command == "status":
        return
    if status[0]["state"] != "COMPLETED":
        raise RuntimeError("Climate export is not completed")
    from googleapiclient.discovery import build
    from io import BytesIO
    drive = build("drive", "v3", credentials=ee.data.get_persistent_credentials(), cache_discovery=False)
    name = request["description"] + ".csv"
    files = drive.files().list(q=f"name = '{name}' and trashed = false",
        fields="files(id,name,size,md5Checksum)", pageSize=100).execute()["files"]
    if len(files) != 1:
        raise ValueError("Expected one uniquely named climate export")
    payload = drive.files().get_media(fileId=files[0]["id"]).execute()
    if hashlib.md5(payload).hexdigest() != files[0]["md5Checksum"]:
        raise ValueError("Drive export checksum mismatch")
    with (args.output / "export.csv").open("xb") as stream:
        stream.write(payload)
    (args.output / "export_provenance.json").write_text(json.dumps({**files[0],
        "sha256": hashlib.sha256(payload).hexdigest()}, indent=2) + "\n")
    publish_tables(pd.read_csv(BytesIO(payload)), pd.read_csv(args.output / "grids.csv"), args.output)


if __name__ == "__main__":
    main()
