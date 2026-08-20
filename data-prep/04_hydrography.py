"""Pull rivers, waterbodies, and HUC12 boundaries from NHDPlus HR.

Outputs
  public/data/vectors/rivers_island.geojson     named rivers, island wide
  public/data/vectors/streams_watersheds.geojson all flowlines inside the six
                                                 watersheds plus a small margin
  public/data/vectors/waterbodies.geojson       other lakes and ponds nearby
  public/data/vectors/huc12.geojson             HUC12 boundaries over the
                                                 study watersheds
"""

import geopandas as gpd
import pandas as pd

from common import CACHE, ISLAND_BBOX, VECTORS, http_get, write_geojson

SERVICE = "https://hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer"


def query_layer(layer: int, where: str, bbox, out_fields: str) -> gpd.GeoDataFrame:
    """Page through an ArcGIS query endpoint and return every feature."""
    frames = []
    offset = 0
    while True:
        response = http_get(
            f"{SERVICE}/{layer}/query",
            params={
                "where": where,
                "geometry": ",".join(str(v) for v in bbox),
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": out_fields,
                "returnGeometry": "true",
                "outSR": "4326",
                "resultOffset": offset,
                "resultRecordCount": 2000,
                "f": "geojson",
            },
            timeout=300,
        )
        payload = response.json()
        features = payload.get("features", [])
        if features:
            frames.append(gpd.GeoDataFrame.from_features(features, crs="EPSG:4326"))
        if payload.get("exceededTransferLimit") or len(features) == 2000:
            offset += len(features)
            print(f"    layer {layer}: {offset} features so far")
        else:
            break
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def main() -> None:
    sheds = gpd.read_file(CACHE / "watersheds_raw.gpkg", layer="watersheds")
    shed_union = sheds.union_all().buffer(0.01)
    shed_bbox = shed_union.bounds

    print("Named rivers island wide, stream order 3 and larger")
    rivers = query_layer(
        3,
        "streamorde >= 3",
        ISLAND_BBOX,
        "gnis_name,streamorde,lengthkm,totdasqkm",
    )
    rivers["geometry"] = rivers.geometry.simplify(0.0003, preserve_topology=True)
    write_geojson(rivers, VECTORS / "rivers_island.geojson", precision=4)

    print("All flowlines inside the study watersheds")
    streams = query_layer(
        3,
        "1=1",
        shed_bbox,
        "gnis_name,streamorde,lengthkm,totdasqkm,slope",
    )
    streams = streams[streams.intersects(shed_union)].copy()
    streams["geometry"] = streams.geometry.simplify(0.00005, preserve_topology=True)
    write_geojson(streams, VECTORS / "streams_watersheds.geojson")

    print("Nearby waterbodies")
    waterbodies = query_layer(
        9,
        "areasqkm > 0.01",
        shed_bbox,
        "gnis_name,areasqkm,ftype",
    )
    waterbodies = waterbodies[waterbodies.intersects(shed_union)].copy()
    write_geojson(waterbodies, VECTORS / "waterbodies.geojson")

    print("HUC12 boundaries over the study watersheds")
    huc12 = query_layer(
        12,
        "1=1",
        shed_bbox,
        "huc12,name,areasqkm",
    )
    huc12 = huc12[huc12.intersects(shed_union)].copy()
    huc12["geometry"] = huc12.geometry.simplify(0.0002, preserve_topology=True)
    write_geojson(huc12, VECTORS / "huc12.geojson")


if __name__ == "__main__":
    main()
