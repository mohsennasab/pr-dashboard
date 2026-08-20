# Data catalog

Every layer in the dashboard with its source. Data retrieved 2026-08-19.

| Layer | Source | Notes |
|---|---|---|
| Elevation and cross sections | [USGS 3DEP seamless DEM](https://www.usgs.gov/3d-elevation-program) | One third arc second (about 10 m) inside the study watersheds, one arc second (about 30 m) island wide. Elevations converted to feet. |
| 3D terrain and hillshade | [Mapterhorn terrain tiles](https://mapterhorn.com/attribution) | Global terrain tiles streamed at view time for the 3D scene and shaded relief. |
| Watershed boundaries | [Delineated from USGS 3DEP](https://www.usgs.gov/3d-elevation-program) | Drainage area upstream of each dam, delineated with pysheds from the 10 m DEM. Reconnaissance level boundaries. |
| HUC12 boundaries, rivers, waterbodies | [USGS NHDPlus High Resolution](https://www.usgs.gov/national-hydrography/nhdplus-high-resolution) | Flowlines, waterbody polygons, and the HUC12 framework from the National Hydrography Dataset Plus HR map service. |
| Reservoir storage figures | [USGS sedimentation survey reports](https://www.usgs.gov/centers/cfwsc/science/sedimentation-surveys-puerto-rico) | Original and surveyed capacities from the published USGS report for each reservoir. Each reservoir card links to its report. |
| Streamflow gauges | [USGS National Water Information System](https://waterservices.usgs.gov/) | Sites in Puerto Rico with discharge records, active and discontinued, with period of record and drainage area. |
| Rain gauges | [USGS NWIS and NOAA GHCN Daily](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily) | USGS precipitation sites plus NOAA GHCN Daily stations with precipitation records. |
| Hurricane tracks | [NOAA NCEI IBTrACS v04r01](https://www.ncei.noaa.gov/products/international-best-track-archive) | North Atlantic storms since 1980 passing within 500 km of Puerto Rico. Segments colored by the USA agency Saffir Simpson classification. |
| Landslide points | [USGS slope failure inventory after Hurricane Maria](https://www.sciencebase.gov/catalog/item/5d4c8b26e4b01d82ce8dfeb0) | About 71,000 headscarp points mapped from imagery after the September 2017 event. |
| Landslide susceptibility | [USGS Open File Report 2020-1022](https://www.sciencebase.gov/catalog/item/61087009d34ef8d70565c154) | Susceptibility to rainfall triggered landslides, resampled from 5 m to about 15 m for the web. |
| Land cover | [NOAA C-CAP 2010, Puerto Rico](https://coast.noaa.gov/digitalcoast/data/ccapregional.html) | Coastal Change Analysis Program land cover at 30 m. |
| Soils | [USDA SSURGO through Soil Data Access](https://sdmdataaccess.sc.egov.usda.gov/) | Map units inside the study watersheds with the surface horizon K factor of the dominant component. |
| Roads | [US Census TIGER/Line 2024](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) | Primary and secondary roads island wide plus all roads inside the study watersheds. |
| Satellite basemap | [Google Maps tiles](https://www.google.com/help/terms_maps/) | Streamed at view time under the Google Maps terms. |
| Street basemap | [OpenFreeMap, OpenStreetMap contributors](https://openfreemap.org/) | Drawn basemap style streamed at view time. |
| Topographic basemap | [USGS The National Map](https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer) | USGS Topo tile service streamed at view time. |
| Rainfall frequency reference | [NOAA Atlas 14, Volume 3, Puerto Rico](https://hdsc.nws.noaa.gov/pfds/pfds_map_pr.html) | Not drawn on the map. Linked here as the standard rainfall frequency reference for the island. |

Land ownership is not shown. Puerto Rico parcel data (CRIM) is not openly distributed, so no parcel layer is included.
