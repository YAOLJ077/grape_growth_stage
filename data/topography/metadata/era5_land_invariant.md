# ERA5-Land invariant fields

The untracked raw files in `data/topography/raw/era5_land_invariant/` are the
official ECMWF ERA5-Land invariant fields on the CDS regular 0.1° grid. They
were downloaded on 2026-08-03 from the attachments to the ECMWF ERA5-Land data
documentation page.

| Local file | ECMWF attachment | SHA-256 |
|---|---|---|
| `geopotential_0p1deg.nc` | `geo_1279l4_0.1x0.1.grib2_v4_unpack.nc` | `6fe9d064e7eae98bfe20348430bc4290bc94daa838b560c355999cd85cb1a559` |
| `land_sea_mask_0p1deg.nc` | `lsm_1279l4_0.1x0.1.grb_v4_unpack.nc` | `9df65151d1608990851e2aa8d0e1e4ca063b5181b0568493c42676d2572b202c` |

Model-grid elevation is calculated as geopotential divided by standard gravity
(`9.80665 m s-2`). It is kept distinct from Copernicus GLO-30 site elevation
and from GLO-30 terrain statistics aggregated inside the same nominal cell.

Source: <https://confluence.ecmwf.int/pages/viewpage.action?pageId=197699521>
