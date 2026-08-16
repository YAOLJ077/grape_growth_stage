# Topography Data

Processed files are derived from Copernicus DEM GLO-30 public Cloud Optimized GeoTIFF tiles.

- Source: Copernicus DEM GLO-30
- Resolution of source tiles: about 30 m
- Remote COG bucket pattern: `https://copernicus-dem-30m.s3.amazonaws.com/...`
- The repository currently contains the downloaded country-scale 30 m tile archive locally; Git continues to ignore these raw tiles because of their size.

Country-scale raw tile archive:

- Download script: `src/download_country_copernicus_dem_glo30.py`
- Boundary source used for tile selection: `data/topography/metadata/countries.geojson`
- Tile manifest: `data/topography/metadata/copernicus_dem_glo30_country_tiles.csv`
- Raw tiles: `data/topography/raw/copernicus_dem_glo30/country_tiles/{france,germany,austria,slovakia,switzerland,spain}/`
- Coverage: metropolitan France including Corsica, Germany, Austria, Slovakia, Switzerland, and Spain mainland plus the Balearic Islands. Tiles are selected by intersection between country boundaries and Copernicus 1-degree GLO-30 tiles.

Site extraction:

- Script: `src/base_table/build_site_topography.py`
- Input population: sites retained in the 1951+ standardized BBCH base table.
- Output: `data/phenology/derived/descriptive_phenology/site_topography.csv`
- The extraction uses local tiles, samples elevation at every site, and retains source elevation separately for quality auditing.
