"""Delineate the drainage area upstream of each reservoir dam.

Steps per reservoir
  1. Pull the reservoir polygon from the NHDPlus HR waterbody layer.
  2. Condition the one third arc second DEM with pysheds.
  3. Take the flow accumulation maximum inside the lake as the outlet.
  4. Delineate the upstream catchment and polygonize it.

Outputs
  public/data/vectors/reservoirs.geojson    six lake polygons with names
  public/data/vectors/watersheds.geojson    six drainage area polygons
  public/data/vectors/dams.geojson          outlet points at each dam
  cache/watersheds_raw.gpkg                 unsimplified copies for later clips
"""

import geopandas as gpd
import numpy as np
import pandas as pd
from pysheds.grid import Grid
from shapely.geometry import Point, shape

from common import CACHE, RESERVOIRS, VECTORS, http_get, write_geojson

WATERBODY_QUERY = (
    "https://hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer/9/query"
)
EQUAL_AREA = "EPSG:6566"  # Puerto Rico State Plane meters


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
    chosen = contains if len(contains) else frame.iloc[
        [frame.distance(point).idxmin()]
    ]
    chosen = chosen.iloc[[0]].copy()
    chosen["key"] = key
    chosen["name"] = info["name"]
    chosen["river"] = info["river"]
    chosen["municipality"] = info["municipality"]
    return chosen[["key", "name", "river", "municipality", "areasqkm", "geometry"]]


def delineate(key: str, info: dict, lake: gpd.GeoDataFrame):
    dem_path = CACHE / f"dem_{key}_10m.tif"
    grid = Grid.from_raster(str(dem_path))
    dem = grid.read_raster(str(dem_path))

    pit_filled = grid.fill_pits(dem)
    flooded = grid.fill_depressions(pit_filled)
    inflated = grid.resolve_flats(flooded)
    fdir = grid.flowdir(inflated)
    acc = grid.accumulation(fdir)

    # The DEM is flat across the lake surface, so accumulation only
    # concentrates in the channel just below the dam. Searching a 200 m
    # buffer around the lake finds that cell, which carries the full
    # upstream drainage area.
    lake_geom = lake.geometry.iloc[0].buffer(0.002)
    acc_array = np.asarray(acc)
    rows, cols = acc_array.shape
    from rasterio.transform import xy

    transform = acc.affine
    import rasterio.features

    lake_mask = rasterio.features.geometry_mask(
        [lake_geom], out_shape=(rows, cols), transform=transform, invert=True
    )
    masked = np.where(lake_mask, acc_array, -1)
    outlet_row, outlet_col = np.unravel_index(np.argmax(masked), masked.shape)
    outlet_x, outlet_y = xy(transform, outlet_row, outlet_col)

    # Index addressing avoids a coordinate snapping artifact that returned
    # near empty catchments for some outlets.
    catchment = grid.catchment(
        x=outlet_col, y=outlet_row, fdir=fdir, xytype="index"
    )
    grid.clip_to(catchment)
    shapes = list(grid.polygonize())
    polygons = [shape(geom) for geom, value in shapes if value == 1]
    if not polygons:
        raise RuntimeError(f"Empty catchment for {info['name']}")
    from shapely.ops import unary_union

    merged = unary_union(polygons)
    frame = gpd.GeoDataFrame(
        {
            "key": [key],
            "name": [info["name"]],
            "river": [info["river"]],
        },
        geometry=[merged],
        crs="EPSG:4326",
    )
    area_sqkm = frame.to_crs(EQUAL_AREA).area.iloc[0] / 1e6
    frame["area_sqmi"] = round(area_sqkm / 2.58999, 2)
    frame["area_sqkm"] = round(area_sqkm, 2)
    outlet = gpd.GeoDataFrame(
        {"key": [key], "name": [f"{info['name']} Dam"]},
        geometry=[Point(outlet_x, outlet_y)],
        crs="EPSG:4326",
    )
    return frame, outlet


def main() -> None:
    lakes = []
    sheds = []
    dams = []
    for key, info in RESERVOIRS.items():
        print(f"{info['short']}")
        lake = reservoir_polygon(key, info)
        print(f"  lake polygon {lake['areasqkm'].iloc[0]:.3f} sqkm")
        shed, dam = delineate(key, info, lake)
        print(
            f"  watershed {shed['area_sqmi'].iloc[0]} sqmi"
            f" ({shed['area_sqkm'].iloc[0]} sqkm)"
        )
        lakes.append(lake)
        sheds.append(shed)
        dams.append(dam)

    lakes_frame = pd.concat(lakes, ignore_index=True)
    sheds_frame = pd.concat(sheds, ignore_index=True)
    dams_frame = pd.concat(dams, ignore_index=True)

    raw = CACHE / "watersheds_raw.gpkg"
    if raw.exists():
        raw.unlink()
    sheds_frame.to_file(raw, layer="watersheds", driver="GPKG")
    lakes_frame.to_file(raw, layer="reservoirs", driver="GPKG")

    display = sheds_frame.copy()
    display["geometry"] = display.geometry.simplify(0.0002, preserve_topology=True)
    write_geojson(lakes_frame, VECTORS / "reservoirs.geojson")
    write_geojson(display, VECTORS / "watersheds.geojson")
    write_geojson(dams_frame, VECTORS / "dams.geojson")


if __name__ == "__main__":
    main()
