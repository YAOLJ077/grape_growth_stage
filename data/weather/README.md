# Per-site ERA5-Land mean temperature

The active download inventory is
`data/phenology/derived/modeling/france_germany_four_stage/site_inventory.csv`.
It contains 2,324 sites in France and Germany. This explicitly selected historical
inventory is distinct from the all-country inventory in `data/site_inventory.csv`.

## Output

Each site with available temperature values has one file:
`data/weather/sites/<site_name>.csv`, with exactly:

```csv
Date,Tmean
```

`Date` is an ISO calendar date; `Tmean` is daily mean 2-m air temperature in
degrees Celsius. The requested interval is **January 1 of `first_year - 1`
through December 31 of `last_year`, inclusive**, including years without
phenology observations. For example, first_year=2019 and last_year=2022 gives
2018-01-01 through 2022-12-31. The inventory supplies years, not exact starting
observation dates.

Names retain spaces and Unicode. Characters unsafe in paths are replaced by
underscores. Very long names are shortened and receive a stable hash suffix;
the complete name and source-qualified identity remain in the manifest.
Case-insensitive or sanitization-induced filename collisions stop processing.

Only actual finite temperatures are written. Missing, masked, pre-collection
and not-yet-published dates remain gaps, without interpolation or invented
values. A site with no available values has a manifest record but no empty
weather CSV. Incomplete files must not be treated as model-ready inputs.

## Reuse local files

From the repository root, using Python 3.12 with `model/requirements.txt`:

```sh
python src/weather_processing/site_weather.py
```

The script scans `data/gee/` and existing output files. Additional files or
directories can be supplied without moving the originals:

```sh
python src/weather_processing/site_weather.py \
  --local-dir /path/to/downloaded/gee/exports
```

Recognized date columns are `Date`, `weather_date` and `date`. Recognized
temperature columns are `Tmean`, `temperature_2m_c` and `tmean_c` in Celsius,
or raw GEE `temperature_2m` in Kelvin, converted by subtracting 273.15.
Units are inferred from these explicit column contracts, not from magnitude.
CSV and gzip-compressed CSV files are supported. Index-only tables are listed
as ignored, not counted as downloaded weather.

Site matching uses `site_uid`, or `country|source|site_id`, or the qualified
prefix of `weather_id`. Unique `site_name` or a matching per-site filename is
used only when those qualified fields are absent. Bare numeric IDs are not
matched across sources. An unrelated named two-column file is ignored and
recorded in the audit.

Repeated identical site/date values are deduplicated. Conflicts exceeding
1e-7 °C stop local reuse; no source is silently selected. Original export
files remain unchanged. Existing destination values cannot be replaced by
different temperatures or truncated to a shorter inventory window.

## Download missing periods

Earth Engine requires an authenticated account and an Earth Engine-enabled
Google Cloud project. Authentication is interactive and is not performed
automatically by the processing script.

```sh
python -m pip install -r src/weather_processing/site_weather_requirements.txt
earthengine authenticate
python src/weather_processing/site_weather.py \
  --download --project YOUR_EARTH_ENGINE_PROJECT
```

The verified project for the current download is `smart-soil-erosion`.
The historical export script names `glossy-essence-477012-s7`, which the
authenticated account cannot currently use.
No new cloud project or paid resource is created by this script.

Local reuse and its coverage audit run first. Only remaining missing days
within the live collection's available interval are requested. Requests are
split at calendar-year boundaries and use a point at the inventory coordinates
on the collection's native projection and transform. No buffering, spatial
averaging or DEM correction is applied to new downloads. Raw Kelvin means
are converted to Celsius. Successful intervals are saved immediately so a
subsequent run can reuse them. Failed requests are retried three times; a
repeated failure stops further requests for that site and is recorded.

A small initial run is supported:

```sh
python src/weather_processing/site_weather.py \
  --download --project YOUR_EARTH_ENGINE_PROJECT --limit 1
```

Use `--site 'France|france_tempo|100354'` to select an exact inventory identity.
`--inventory` and `--output` are configurable. The default output is
`data/weather/sites/`. Separate processes must not write to the same output
directory concurrently.

## Coverage and provenance

`sites/metadata/` contains:

- `manifest.csv`: full site names, identities, filenames, coordinates, requested
  and actual dates, reused/downloaded/missing counts, status, errors and hashes.
- `missing_periods.csv`: inclusive missing date intervals per site.
- `run.json`: inventory fingerprint, used/ignored local files, input fingerprints,
  collection, units, execution time and available collection dates when queried.

Filtered runs use `metadata/subsets/<selection-hash>/` and do not replace the
all-site audit. An all-site rerun refreshes the main manifest. Each audit
describes that run; input source files preserve detailed legacy provenance.
Reused temperatures inherit their original extraction and any buffer-fill
methods; the native-grid sampling statement applies only to new downloads.

Exit status is 0 only when every requested site is complete, or 2 when coverage
is incomplete or processing fails. Inspect the manifest and terminal message
to distinguish those outcomes. Requests through 2026-12-31 remain incomplete
until all required daily values are published. The GEE catalogue begins at
1950-01-02, so requested 1950-01-01 is explicitly missing rather than synthesized.

The initial local audit on 2026-09-07 found three GEE extraction-index CSVs but no daily
temperature values: 2,324 sites and 8,455,301 requested site-days remain missing.
That audit preceded live downloading. Authentication and live extraction were
subsequently verified using `smart-soil-erosion`: the first site,
`France|france_tempo|100354`, has all 1,096 requested days from 2018-01-01 through
2020-12-31 in `sites/16369-27875-2852-36032-2505.csv`. The complete inventory
download was started in the background, with progress in
`sites/metadata/download-20260907.log`. Per-site CSVs are updated after each
successful interval; the main manifest is refreshed when the full run finishes.
An in-progress log or populated subset of files is not evidence that every site
has completed. Do not start another writer in the same output directory while
this run is active.

## References and checks

- [ERA5-Land daily aggregate catalogue and units](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR)
- [Earth Engine authentication](https://developers.google.com/earth-engine/guides/auth)
- [Point time-series extraction with getRegion](https://developers.google.com/earth-engine/apidocs/ee-imagecollection-getregion)

Tests run with `python -m pytest tests/test_site_weather.py -q`. Synthetic
fixtures test reuse, unit conversion, identity matching, missing periods,
filename safety and resumability; they do not validate live GEE access.

For a one-site process run, add the manifest's `site_uid` as the `site` column
when loading a weather CSV, and pass `temperature_column="Tmean"` to the
shared model API. The on-disk weather file remains exactly two columns.
