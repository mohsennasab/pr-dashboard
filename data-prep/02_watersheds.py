"""Build the study watershed layer and dam points.

The study watershed for each reservoir is the HUC12 subwatershed that
contains it, taken from the USGS Watershed Boundary Dataset as served by
the NHDPlus HR map service. The HUC12 area attribute becomes the drainage
area shown on the reservoir cards.

Dam outlet points come from a flow accumulation analysis of the one third
arc second DEM with pysheds, snapped to the highest accumulation cell in a
200 meter buffer around each lake.

Outputs
  public/data/vectors/reservoirs.geojson    six lake polygons with names
  public/data/vectors/watersheds.geojson    six HUC12 study watersheds
  public/data/vectors/dams.geojson          outlet points at each dam
  cache/watersheds_raw.gpkg                 unsimplified copies for later clips
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio.features
from pysheds.grid import Grid
from rasterio.transform import xy
from shapely.geometry import Point

from common import CACHE, RESERVOIRS, VECTORS, http_get, write_geojson

SERVICE = "https://hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer"
WATERBODY_QUERY = f"{SERVICE}/9/query"
HUC12_QUERY = f"{SERVICE}/12/query"
SQMI_PER_SQKM = 0.386102


def reservoir_polygon(key: str, info: dict) -> gpd.GeoDataFrame:
    lon, lat = info["lake_point"]
    margin = 0.03
    response = http_get(
        WATERBODY_QUERY,
        params={
            "where": "areasqkm > 0.03",
            "geometry": f"{lon - margin},{lat - margin},{lon + margin},{lat + margin}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "gnis_name,areasqkm,nhdplusid",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        },
        timeout=120,
    )
    features = response.json().get("features", [])
    if not features:
        raise RuntimeError(f"No waterbody found near {info['name']}")
    frame = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    point = Point(lon, lat)
    contains = frame[frame.contains(point)]
    if len(contains):
        chosen = contains
    else:
        meters = frame.to_crs("EPSG:6566")
        chosen = frame.iloc[[meters.distance(
            gpd.GeoSeries([point], crs="EPSG:4326").to_crs("EPSG:6566").iloc[0]
        ).idxmin()]]
    chosen = chosen.iloc[[0]].copy()
    chosen["key"] = key
    chosen["name"] = info["name"]
    chosen["river"] = info["river"]
    chosen["municipality"] = info["municipality"]
    return chosen[["key", "name", "river", "municipality", "areasqkm", "geometry"]]


def containing_huc12(key: str, info: dict) -> gpd.GeoDataFrame:
    """The HUC12 subwatershed polygon that contains the reservoir."""
    lon, lat = info["lake_point"]
    response = http_get(
        HUC12_QUERY,
        params={
            "where": "1=1",
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "huc12,name,areasqkm",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        },
        timeout=120,
    )
    features = response.json().get("features", [])
    if not features:
        raise RuntimeError(f"No HUC12 found for {info['name']}")
    frame = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    frame = frame.iloc[[0]].copy()
    frame = frame.rename(columns={"name": "huc12_name"})
    area_sqkm = float(frame["areasqkm"].iloc[0] or 0)
    if not np.isfinite(area_sqkm) or area_sqkm <= 0:
        area_sqkm = frame.to_crs("EPSG:6566").area.iloc[0] / 1e6
    frame["key"] = key
    frame["name"] = info["name"]
    frame["river"] = info["river"]
    frame["area_sqkm"] = round(area_sqkm, 2)
    frame["area_sqmi"] = round(area_sqkm * SQMI_PER_SQKM, 2)
    return frame[
        ["key", "name", "river", "huc12", "huc12_name", "area_sqmi", "area_sqkm", "geometry"]
    ]


def dam_point(key: str, info: dict, lake: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    dem_path = CACHE / f"dem_{key}_10m.tif"
    grid = Grid.from_raster(str(dem_path))
    dem = grid.read_raster(str(dem_path))
    inflated = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(dem)))
    fdir = grid.flowdir(inflated)
    acc = grid.accumulation(fdir)
    acc_array = np.asarray(acc)

    lake_geom = lake.geometry.iloc[0].buffer(0.002)
    lake_mask = rasterio.features.geometry_mask(
        [lake_geom], out_shape=acc_array.shape, transform=acc.affine, invert=True
    )
    masked = np.where(lake_mask, acc_array, -1)
    outlet_row, outlet_col = np.unravel_index(np.argmax(masked), masked.shape)
    outlet_x, outlet_y = xy(acc.affine, outlet_row, outlet_col)
    return gpd.GeoDataFrame(
        {"key": [key], "name": [f"{info['name']} Dam"]},
        geometry=[Point(outlet_x, outlet_y)],
        crs="EPSG:4326",
    )


def main() -> None:
    lakes = []
    sheds = []
    dams = []
    for key, info in RESERVOIRS.items():
        print(f"{info['short']}")
        lake = reservoir_polygon(key, info)
        print(f"  lake polygon {lake['areasqkm'].iloc[0]:.3f} sqkm")
        shed = containing_huc12(key, info)
        print(
            f"  HUC12 {shed['huc12'].iloc[0]} {shed['huc12_name'].iloc[0]}"
            f" {shed['area_sqmi'].iloc[0]} sqmi"
        )
        dam = dam_point(key, info, lake)
        lakes.append(lake)
        sheds.append(shed)
        dams.append(dam)

    lakes_frame = gpd.GeoDataFrame(pd.concat(lakes, ignore_index=True), crs="EPSG:4326")
    sheds_frame = gpd.GeoDataFrame(pd.concat(sheds, ignore_index=True), crs="EPSG:4326")
    dams_frame = gpd.GeoDataFrame(pd.concat(dams, ignore_index=True), crs="EPSG:4326")

    raw = CACHE / "watersheds_raw.gpkg"
    if raw.exists():
        raw.unlink()
    sheds_frame.to_file(raw, layer="watersheds", driver="GPKG")
    lakes_frame.to_file(raw, layer="reservoirs", driver="GPKG")

    display = sheds_frame.copy()
    display["geometry"] = display.geometry.simplify(0.0001, preserve_topology=True)
    write_geojson(lakes_frame, VECTORS / "reservoirs.geojson")
    write_geojson(display, VECTORS / "watersheds.geojson")
    write_geojson(dams_frame, VECTORS / "dams.geojson")


if __name__ == "__main__":
    main()
