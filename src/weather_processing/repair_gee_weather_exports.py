from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEATHER_DIR = REPO_ROOT / "data" / "weather"
DEFAULT_INDEX = REPO_ROOT / "data" / "gee" / "weather_download_index_1951_gee_20parts.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "weather" / "processed" / "era5_land_daily_with_coords"
DEFAULT_SUMMARY = REPO_ROOT / "data" / "weather" / "processed" / "weather_export_repair_summary.json"
DEFAULT_MISSING_INDEX = REPO_ROOT / "data" / "weather" / "processed" / "france_missing_era5_land_site_years.csv"
DEFAULT_GEE_SCRIPT = REPO_ROOT / "data" / "weather" / "processed" / "gee_france_missing_era5_land_buffer_fill.js"

WEATHER_COLUMNS = [
    "temperature_2m",
    "temperature_2m_min",
    "temperature_2m_max",
    "dewpoint_temperature_2m",
    "total_precipitation_sum",
    "surface_pressure",
    "surface_solar_radiation_downwards_sum",
    "u_component_of_wind_10m",
    "v_component_of_wind_10m",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair GEE ERA5-Land CSV exports with coordinates from the local index.")
    parser.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER_DIR)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--missing-index", type=Path, default=DEFAULT_MISSING_INDEX)
    parser.add_argument("--gee-script", type=Path, default=DEFAULT_GEE_SCRIPT)
    parser.add_argument("--chunksize", type=int, default=200_000)
    return parser.parse_args()


def load_index(path: Path) -> pd.DataFrame:
    usecols = [
        "weather_id",
        "gee_part",
        "gee_part_key",
        "country",
        "source",
        "site_id",
        "site_name",
        "lat",
        "lon",
        "alt_m",
        "year",
        "weather_start_date",
        "weather_end_date",
        "n_events",
        "bbch_list",
        "phenophase_list",
        "model_tier",
        "first_event_date",
        "last_event_date",
        "first_event_doy",
        "last_event_doy",
    ]
    index = pd.read_csv(path, usecols=usecols)
    if index["weather_id"].duplicated().any():
        duplicated = index.loc[index["weather_id"].duplicated(), "weather_id"].head().tolist()
        raise ValueError(f"Duplicate weather_id values in index: {duplicated}")
    return index


def repair_weather_files(args: argparse.Namespace, index: pd.DataFrame) -> dict:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    weather_files = sorted(args.weather_dir.glob("era5_land_daily_grape_1951_part_*_of_20.csv"))
    if not weather_files:
        raise FileNotFoundError(f"No weather CSV files found in {args.weather_dir}")

    coord_lookup = index[["weather_id", "lat", "lon", "alt_m"]].rename(
        columns={"lat": "lat_index", "lon": "lon_index", "alt_m": "alt_m_index"}
    )

    total_rows = 0
    missing_weather_ids: set[str] = set()
    output_files = []
    missing_counts = {column: 0 for column in WEATHER_COLUMNS}
    lat_missing_before = 0
    lon_missing_before = 0
    lat_missing_after = 0
    lon_missing_after = 0

    for source_path in weather_files:
        out_path = args.out_dir / source_path.name
        if out_path.exists():
            out_path.unlink()

        first_chunk = True
        file_rows = 0
        for chunk in pd.read_csv(source_path, chunksize=args.chunksize):
            file_rows += len(chunk)
            total_rows += len(chunk)
            lat_missing_before += int(chunk["lat"].isna().sum()) if "lat" in chunk else len(chunk)
            lon_missing_before += int(chunk["lon"].isna().sum()) if "lon" in chunk else len(chunk)

            original_columns = list(chunk.columns)
            chunk = chunk.drop(columns=[c for c in ["lat", "lon", "alt_m"] if c in chunk.columns])
            chunk = chunk.merge(coord_lookup, on="weather_id", how="left", validate="many_to_one")
            chunk = chunk.rename(columns={"lat_index": "lat", "lon_index": "lon", "alt_m_index": "alt_m"})

            for col in WEATHER_COLUMNS:
                if col in chunk.columns:
                    mask = chunk[col].isna()
                    missing_counts[col] += int(mask.sum())
                    if mask.any():
                        missing_weather_ids.update(chunk.loc[mask, "weather_id"].dropna().astype(str).unique())

            lat_missing_after += int(chunk["lat"].isna().sum())
            lon_missing_after += int(chunk["lon"].isna().sum())

            ordered_columns = [c for c in original_columns if c not in {"lat", "lon", "alt_m"}]
            insert_at = ordered_columns.index("site_name") + 1 if "site_name" in ordered_columns else 7
            ordered_columns[insert_at:insert_at] = ["lat", "lon", "alt_m"]
            chunk = chunk[[c for c in ordered_columns if c in chunk.columns]]
            chunk.to_csv(out_path, mode="w" if first_chunk else "a", header=first_chunk, index=False)
            first_chunk = False

        output_files.append({"file": str(out_path.relative_to(REPO_ROOT)), "rows": file_rows})
        print(f"written {out_path.relative_to(REPO_ROOT)} rows={file_rows:,}")

    missing_index = index[index["weather_id"].isin(missing_weather_ids)].copy()
    missing_index = missing_index.sort_values(["country", "site_id", "year"])
    args.missing_index.parent.mkdir(parents=True, exist_ok=True)
    missing_index.to_csv(args.missing_index, index=False)

    summary = {
        "input_weather_dir": str(args.weather_dir.relative_to(REPO_ROOT)),
        "output_weather_dir": str(args.out_dir.relative_to(REPO_ROOT)),
        "n_input_files": len(weather_files),
        "n_total_daily_rows": total_rows,
        "lat_missing_before": lat_missing_before,
        "lon_missing_before": lon_missing_before,
        "lat_missing_after": lat_missing_after,
        "lon_missing_after": lon_missing_after,
        "missing_weather_value_counts": missing_counts,
        "n_missing_site_years": int(len(missing_index)),
        "missing_site_years_by_country": missing_index["country"].value_counts().to_dict(),
        "missing_index": str(args.missing_index.relative_to(REPO_ROOT)),
        "output_files": output_files,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def write_gee_buffer_fill_script(path: Path, missing_weather_ids: list[str]) -> None:
    id_lines = ",\n".join(f"  '{weather_id}'" for weather_id in missing_weather_ids)
    script = """var INDEX_ASSET = 'projects/glossy-essence-477012-s7/assets/weather_download_index_1951_gee_20parts';
var OUT_FOLDER = 'grape_phenology_era5_land_daily';
var BUFFER_METERS = 30000;
var MISSING_WEATHER_IDS = [
__MISSING_WEATHER_IDS__
];

var ERA5 = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR');

var BANDS = [
  'temperature_2m',
  'temperature_2m_min',
  'temperature_2m_max',
  'dewpoint_temperature_2m',
  'total_precipitation_sum',
  'surface_pressure',
  'surface_solar_radiation_downwards_sum',
  'u_component_of_wind_10m',
  'v_component_of_wind_10m'
];

var index = ee.FeatureCollection(INDEX_ASSET)
  .filter(ee.Filter.inList('weather_id', MISSING_WEATHER_IDS));
print('Missing site-year rows', index.size());
print('Example input row', index.first());

var metaFields = [
  'weather_id',
  'gee_part',
  'gee_part_key',
  'country',
  'source',
  'site_id',
  'site_name',
  'lat',
  'lon',
  'alt_m',
  'year',
  'weather_start_date',
  'weather_end_date',
  'n_events',
  'bbch_list',
  'phenophase_list',
  'model_tier',
  'first_event_date',
  'last_event_date',
  'first_event_doy',
  'last_event_doy'
];

function oneSiteYearToDaily(row) {
  row = ee.Feature(row);
  var point = row.geometry();
  var buffer = point.buffer(BUFFER_METERS);
  var start = ee.Date(ee.String(row.get('weather_start_date')));
  var end = ee.Date(ee.String(row.get('weather_end_date'))).advance(1, 'day');
  var meta = row.toDictionary(metaFields);

  return ERA5
    .select(BANDS)
    .filterDate(start, end)
    .map(function(image) {
      var values = image.reduceRegion({
        reducer: ee.Reducer.mean(),
        geometry: buffer,
        scale: 11132,
        bestEffort: true,
        tileScale: 4,
        maxPixels: 1000000
      });

      return ee.Feature(null, meta.combine(values).combine({
        weather_date: image.date().format('YYYY-MM-dd'),
        weather_year: image.date().get('year'),
        weather_month: image.date().get('month'),
        weather_doy: image.date().getRelative('day', 'year').add(1),
        fill_method: 'era5_land_buffer_mean',
        fill_buffer_m: BUFFER_METERS
      }));
    });
}

var rowList = index.toList(index.size());
var nestedDaily = ee.List.sequence(0, index.size().subtract(1)).map(function(i) {
  return oneSiteYearToDaily(ee.Feature(rowList.get(i)));
});
var dailyWeather = ee.FeatureCollection(nestedDaily).flatten();

print('Example output row', dailyWeather.first());
print('Output rows', dailyWeather.size());

Export.table.toDrive({
  collection: dailyWeather,
  description: 'era5_land_daily_grape_1951_france_missing_buffer_fill',
  folder: OUT_FOLDER,
  fileNamePrefix: 'era5_land_daily_grape_1951_france_missing_buffer_fill',
  fileFormat: 'CSV',
  selectors: metaFields.concat([
    'weather_date',
    'weather_year',
    'weather_month',
    'weather_doy',
    'fill_method',
    'fill_buffer_m'
  ]).concat(BANDS)
});
""".replace("__MISSING_WEATHER_IDS__", id_lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script, encoding="utf-8")


def main() -> None:
    args = parse_args()
    index = load_index(args.index)
    summary = repair_weather_files(args, index)
    missing_ids = pd.read_csv(args.missing_index, usecols=["weather_id"])["weather_id"].astype(str).tolist()
    write_gee_buffer_fill_script(args.gee_script, missing_ids)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"GEE buffer-fill script written: {args.gee_script.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
