"""Supporting layers: landslides, land cover, and roads.

Landslide points   USGS map of slope failure locations after Hurricane Maria
                   (ScienceBase 5d4c8b26e4b01d82ce8dfeb0, about 71,000 points)
Susceptibility     USGS OFR 2020-1022 companion raster, 5 m classes
                   (ScienceBase 61087009d34ef8d70565c154)
Land cover         NOAA C-CAP 2010 Puerto Rico, 30 m
Roads              Census TIGER/Line 2024, primary and secondary island wide
                   plus every road inside the study watersheds

Outputs
  public/data/vectors/landslides.geojson
  public/data/rasters/landslide_susceptibility.tif
  public/data/rasters/landcover_30m.tif
  public/data/vectors/roads_island.geojson
  public/data/vectors/roads_watersheds.geojson
"""

import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from common import CACHE, RASTERS, VECTORS, download_file, http_get, write_geojson

LANDSLIDES_ZIP = (
    "https://www.sciencebase.gov/catalog/file/get/5d4c8b26e4b01d82ce8dfeb0"
    "?f=__disk__c9%2Fe9%2F25%2Fc9e925899f8ad6b000ca1178cb2333bef7ccc802"
)
SUSCEPTIBILITY_TIF = (
    "https://www.sciencebase.gov/catalog/file/get/61087009d34ef8d70565c154"
    "?f=__disk__18%2Fba%2F51%2F18ba51d1483f53e10890019147a259a885e0c9db"
)
CCAP_TIF = (
    "https://chs.coast.noaa.gov/htdata/raster1/landcover/bulkdownload/30m_lc/"
    "pr_2010_ccap_hr_land_cover20170214_30m.tif"
)
PRISEC_ZIP = (
    "https://www2.census.gov/geo/tiger/TIGER2024/PRISECROADS/"
    "tl_2024_72_prisecroads.zip"
)
COUNTY_QUERY = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "State_County/MapServer/1/query"
)


def landslide_points() -> None:
    zip_path = download_file(LANDSLIDES_ZIP, CACHE / "landslides.zip")
    extract_dir = CACHE / "landslides"
    if not extract_dir.exists():
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_dir)
    shp = next(extract_dir.rglob("*.shp"))
    points = gpd.read_file(shp).to_crs("EPSG:4326")
    print(f"  {len(points)} slope failure points, columns {list(points.columns)[:8]}")
    slim = gpd.GeoDataFrame(geometry=points.geometry, crs="EPSG:4326")
    write_geojson(slim, VECTORS / "landslides.geojson", precision=4)


def downsample_categorical(src_path, out_path, factor_note, target_res_m) -> None:
    """Warp a categorical raster to EPSG:3857 at a coarser resolution.

    The browser COG reader only handles Web Mercator. Nearest resampling
    keeps class values intact and runs fast on these large rasters.
    """
    with rasterio.open(src_path) as src:
        print(f"  source {src.width}x{src.height} {src.crs} res {src.res}")
        nodata = src.nodata if src.nodata is not None else 0
        with WarpedVRT(
            src,
            crs="EPSG:3857",
            resampling=Resampling.nearest,
            nodata=nodata,
        ) as vrt:
            scale = target_res_m / abs(vrt.transform.a)
            out_width = max(1, int(vrt.width / scale))
            out_height = max(1, int(vrt.height / scale))
            data = vrt.read(
                1,
                out_shape=(out_height, out_width),
                resampling=Resampling.nearest,
            )
            transform = vrt.transform * vrt.transform.scale(
                vrt.width / out_width, vrt.height / out_height
            )
    data = np.where(data == nodata, 0, data)
    profile = {
        "driver": "COG",
        "dtype": "uint8",
        "count": 1,
        "crs": "EPSG:3857",
        "transform": transform,
        "width": out_width,
        "height": out_height,
        "nodata": 0,
        "compress": "deflate",
        "blocksize": 256,
        "overview_resampling": "nearest",
    }
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data.astype(np.uint8), 1)
    values, counts = np.unique(data, return_counts=True)
    summary = dict(list(zip(values.tolist(), counts.tolist()))[:20])
    print(f"  {factor_note}: values {summary}")
    print(f"  wrote {out_path.name} ({out_path.stat().st_size / (1 << 20):.1f} MB)")


def susceptibility() -> None:
    tif = download_file(SUSCEPTIBILITY_TIF, CACHE / "landslide_susceptibility_5m.tif")
    downsample_categorical(
        tif, RASTERS / "landslide_susceptibility.tif", "susceptibility 15 m", 15
    )


def landcover() -> None:
    tif = download_file(CCAP_TIF, CACHE / "ccap_pr_2010_30m.tif")
    downsample_categorical(tif, RASTERS / "landcover_30m.tif", "C-CAP 30 m", 30)


def watershed_counties(shed_bbox) -> list[str]:
    response = http_get(
        COUNTY_QUERY,
        params={
            "where": "STATE = '72'",
            "geometry": ",".join(str(v) for v in shed_bbox),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "GEOID,NAME",
            "returnGeometry": "false",
            "f": "json",
        },
        timeout=120,
    )
    rows = response.json().get("features", [])
    codes = sorted({row["attributes"]["GEOID"] for row in rows})
    names = sorted({row["attributes"]["NAME"] for row in rows})
    print(f"  {len(codes)} municipios intersect the watersheds: {names}")
    return codes


def roads() -> None:
    sheds = gpd.read_file(CACHE / "watersheds_raw.gpkg", layer="watersheds")
    shed_union = sheds.union_all().buffer(0.02)

    prisec_zip = download_file(PRISEC_ZIP, CACHE / "tl_2024_72_prisecroads.zip")
    prisec = gpd.read_file(f"zip://{prisec_zip}")
    prisec = prisec.to_crs("EPSG:4326")[["FULLNAME", "RTTYP", "geometry"]]
    prisec["geometry"] = prisec.geometry.simplify(0.0002, preserve_topology=True)
    prisec = prisec.rename(columns={"FULLNAME": "name", "RTTYP": "route_type"})
    write_geojson(prisec, VECTORS / "roads_island.geojson", precision=4)

    frames = []
    for geoid in watershed_counties(shed_union.bounds):
        url = (
            "https://www2.census.gov/geo/tiger/TIGER2024/ROADS/"
            f"tl_2024_{geoid}_roads.zip"
        )
        local = download_file(url, CACHE / f"tl_2024_{geoid}_roads.zip")
        county_roads = gpd.read_file(f"zip://{local}").to_crs("EPSG:4326")
        county_roads = county_roads[county_roads.intersects(shed_union)]
        frames.append(county_roads[["FULLNAME", "MTFCC", "geometry"]])
    merged = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    merged = merged.rename(columns={"FULLNAME": "name", "MTFCC": "road_class"})
    write_geojson(merged, VECTORS / "roads_watersheds.geojson")


def main() -> None:
    print("Landslide points")
    landslide_points()
    print("Landslide susceptibility raster")
    susceptibility()
    print("C-CAP land cover")
    landcover()
    print("Roads")
    roads()


if __name__ == "__main__":
    main()
