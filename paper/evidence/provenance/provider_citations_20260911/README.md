# Dataset citation evidence

Metadata checked on 11 September 2026, Europe/Berlin. Raw registry responses
and hashes preserve the bibliographic evidence used in the active manuscript.

| Dataset | Registered citation metadata | Registry evidence |
| --- | --- | --- |
| Copernicus DEM | European Space Agency and Airbus; 2022; DOI `10.5270/ESA-c5d3d65` | [Crossref response](copernicus_dem_crossref.json) and [official product page](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) |
| ERA5-Land hourly | Copernicus Climate Change Service; 2019; hourly data from 1950 to present; DOI `10.24381/cds.e2161bac` | [DataCite response](era5_land_hourly.json) |
| ERA5-Land monthly | Copernicus Climate Change Service; 2019; monthly averaged data from 1950 to present; DOI `10.24381/cds.68d2bb30` | [DataCite response](era5_land_monthly.json) |

The Copernicus DEM DOI is registered with Crossref, not DataCite. The DOI
content-negotiation BibTeX response omitted the corporate author names; the
underlying Crossref JSON identifies European Space Agency and Airbus. The
registered year 2022 is the dataset citation year, not an assertion that the
sampled AWS COG tiles belong to the 2022 release. Distribution and sample
provenance remain in the terrain metadata and source register.

The main Methods and Supplement S2 cite these datasets and the ERA5-Land
reanalysis paper. The supplement separately identifies the actual Earth Engine
daily and monthly aggregation collections. Copernicus GLO-30 is identified as
a digital surface model, consistent with the official product description.

Source acknowledgements use the [TEMPO data-access guidance](https://tempo.pheno.fr/eng/data)
and the [Earth Engine ERA5-Land attribution guidance](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR#terms-of-use).
They concern data access and derived weather products, not research funding.
The existing PEP725 source acknowledgement and access date remain in Methods.
Exact DEM reuse notices and redistribution conditions remain governed by the
[source/licence register](../data_source_register.md); adding a dataset citation
does not itself establish that a proposed public data deposit satisfies them.

The archived manuscript has empty CRediT and acknowledgements sections and a
generic competing-interest statement. It does not establish author-approved
contributions, funding or current declarations for this submission. Those
author-dependent facts remain pending.
