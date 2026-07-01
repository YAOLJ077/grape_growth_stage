# Topography Data

Processed files are derived from Copernicus DEM GLO-30 public Cloud Optimized GeoTIFF tiles.

- Source: Copernicus DEM GLO-30
- Resolution of source tiles: about 30 m
- Remote COG bucket pattern: `https://copernicus-dem-30m.s3.amazonaws.com/...`
- This repository caches only a coarse plotting background (`*.csv`) and site-level terrain variables, not the full 30 m tile archive.
