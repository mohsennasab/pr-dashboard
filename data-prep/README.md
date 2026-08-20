# Data preparation

Numbered scripts that download public data and write the web ready layers
into `public/data`. Raw downloads land in `cache/`, which stays out of git.
Run them in order from this folder:

```
python 01_dem.py                        # 3DEP elevation, island and watersheds
python 02_watersheds.py                 # HUC12 study watersheds and dam points
python 03_dem_products.py               # clip watershed DEMs to COGs
python 04_hydrography.py                # rivers, streams, waterbodies, HUC12
python 05_gauges.py                     # USGS and GHCN gauges
python 06_ibtracs.py                    # hurricane tracks since 1980
python 07_landslides_landcover_roads.py # landslides, C-CAP, TIGER roads
python 08_soils.py                      # SSURGO K factor
python 09_reservoir_info.py             # USGS sedimentation survey figures
python 10_catalog.py                    # data catalog page
```

Requirements: Python 3.11 or newer with `geopandas`, `rasterio`, `pyogrio`,
`shapely`, `pandas`, `numpy`, `requests`, and `pysheds`.

```
pip install -r requirements.txt
```

Each script skips downloads that already sit in `cache/`, so a rerun is
cheap. To refresh a layer from the source, delete its cache file first.
