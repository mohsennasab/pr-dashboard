"""Engineered water conveyance features around the study watersheds.

Everything comes from the NHDPlus HR map service, split into separate files
so each footprint type can be switched on its own in the map.

Outputs
  public/data/vectors/transfers_tunnels.geojson     NHDLine tunnels plus
                                                    underground aqueducts,
                                                    penstocks, and pipelines
  public/data/vectors/transfers_pipelines.geojson   surface and elevated
                                                    pipelines and siphons
  public/data/vectors/transfers_canals.geojson      canal and ditch lines and
                                                    canal polygons
  public/data/vectors/transfers_structures.geojson  dam and weir lines and
                                                    polygons, water intake and
                                                    outflow polygons

Flow direction comes from NHD where the flowdir flag is "with digitized".
For the rest, these are gravity systems, so direction is inferred from the
ground elevation at the two ends of each line (high end to low end) using
the one arc second DEM. Each feature carries direction = recorded,
inferred, or unknown, and the map draws arrows for the first two.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from shapely.geometry import LineString, MultiLineString

from common import CACHE, VECTORS, http_get, write_geojson

MIN_DROP_M = 3.0

SERVICE = "https://hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer"

# Official NHD feature codes, labeled in plain words.
LABELS = {
    33400: "Connector",
    33600: "Canal or ditch",
    33601: "Canal or ditch, aqueduct",
    33603: "Canal or ditch, stormwater",
    34305: "Dam or weir, earthen",
    34306: "Dam or weir, nonearthen",
    42800: "Pipeline",
    42801: "Aqueduct at or near surface",
    42802: "Aqueduct, elevated",
    42803: "Aqueduct, underground",
    42804: "Aqueduct, underwater",
    42805: "Pipeline at or near surface",
    42806: "Pipeline, elevated",
    42807: "Pipeline, underground",
    42808: "Pipeline, underwater",
    42809: "Penstock at or near surface",
    42810: "Penstock, elevated",
    42811: "Penstock, underground",
    42812: "Penstock, underwater",
    42813: "Siphon",
    47800: "Tunnel",
    48500: "Water intake or outflow",
}
UNDERGROUND = {42803, 42804, 42807, 42808, 42811, 42812, 47800}
SURFACE_PIPES = {42800, 42801, 42802, 42805, 42806, 42809, 42810, 42813}
CANALS = {33600, 33601}
STRUCTURES = {34305, 34306, 48500}

def search_box():
    sheds = gpd.read_file(CACHE / "watersheds_raw.gpkg", layer="watersheds")
    minx, miny, maxx, maxy = sheds.total_bounds
    # Stretch west and south so the Lajas Valley canal is captured in full.
    return (minx - 0.30, miny - 0.08, maxx + 0.06, maxy + 0.10)


def query(layer: int, where: str, bbox, fields: str) -> gpd.GeoDataFrame:
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
                "outFields": fields,
                "returnGeometry": "true",
                "outSR": "4326",
                "resultOffset": offset,
                "resultRecordCount": 2000,
                "f": "geojson",
            },
            timeout=300,
        )
        features = response.json().get("features", [])
        if features:
            frames.append(gpd.GeoDataFrame.from_features(features, crs="EPSG:4326"))
        if len(features) < 2000:
            break
        offset += len(features)
    if not frames:
        return gpd.GeoDataFrame(columns=["fcode", "gnis_name", "geometry"], crs="EPSG:4326")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def tidy(frame: gpd.GeoDataFrame, source: str, directed_ok: bool = False) -> gpd.GeoDataFrame:
    frame = frame.copy()
    frame["fcode"] = pd.to_numeric(frame["fcode"], errors="coerce").astype("Int64")
    frame["label"] = frame["fcode"].map(LABELS).fillna("Other")
    frame["name"] = frame.get("gnis_name")
    frame["source"] = source
    if "lengthkm" in frame.columns:
        frame["length_mi"] = (pd.to_numeric(frame["lengthkm"], errors="coerce") * 0.621371).round(2)
    else:
        frame["length_mi"] = None
    # NHD flowdir 1 means flow follows the digitized direction of the line.
    if directed_ok and "flowdir" in frame.columns:
        frame["directed"] = pd.to_numeric(frame["flowdir"], errors="coerce").eq(1)
    else:
        frame["directed"] = False
    return frame[["fcode", "label", "name", "source", "length_mi", "directed", "geometry"]]


def end_points(geom):
    if isinstance(geom, LineString):
        coords = list(geom.coords)
    elif isinstance(geom, MultiLineString):
        coords = list(geom.geoms[0].coords)[:1] + list(geom.geoms[-1].coords)[-1:]
    else:
        return None
    return coords[0], coords[-1]


def infer_direction(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Point every undirected line downhill and record how direction was set."""
    frame = frame.copy()
    frame["direction"] = np.where(frame["directed"], "recorded", "unknown")
    undirected = frame.index[~frame["directed"]]
    if len(undirected) == 0:
        return frame
    with rasterio.open(CACHE / "dem_island_30m.tif") as dem:
        for index in undirected:
            ends = end_points(frame.at[index, "geometry"])
            if ends is None:
                continue
            samples = list(dem.sample([ends[0], ends[1]]))
            start_z, end_z = float(samples[0][0]), float(samples[1][0])
            if not np.isfinite(start_z) or not np.isfinite(end_z):
                continue
            drop = start_z - end_z
            if abs(drop) < MIN_DROP_M:
                continue
            if drop < 0:
                frame.at[index, "geometry"] = shapely.reverse(frame.at[index, "geometry"])
            frame.at[index, "direction"] = "inferred"
    frame["directed"] = frame["direction"] != "unknown"
    return frame


def main() -> None:
    bbox = search_box()
    print("Search box", [round(v, 3) for v in bbox])

    codes = sorted(UNDERGROUND | SURFACE_PIPES | CANALS)
    where = "fcode IN (" + ",".join(str(c) for c in codes) + ")"
    network = tidy(
        query(3, where, bbox, "fcode,gnis_name,lengthkm,flowdir"),
        "NHDPlus HR network flowline",
        directed_ok=True,
    )
    nonnetwork = tidy(
        query(4, where, bbox, "fcode,gnis_name,lengthkm,flowdir"),
        "NHDPlus HR non network flowline",
        directed_ok=True,
    )
    flowlines = gpd.GeoDataFrame(pd.concat([network, nonnetwork], ignore_index=True), crs="EPSG:4326")

    lines = tidy(
        query(7, "fcode IN (47800,34305,34306)", bbox, "fcode,gnis_name"), "NHDPlus HR line feature"
    )
    areas = tidy(
        query(8, "fcode IN (33600,34305,34306,48500)", bbox, "fcode,gnis_name"), "NHDPlus HR area feature"
    )

    tunnels = pd.concat(
        [flowlines[flowlines["fcode"].isin(UNDERGROUND)], lines[lines["fcode"] == 47800]],
        ignore_index=True,
    )
    pipelines = flowlines[flowlines["fcode"].isin(SURFACE_PIPES)]
    canals = pd.concat(
        [flowlines[flowlines["fcode"].isin(CANALS)], areas[areas["fcode"] == 33600]],
        ignore_index=True,
    )
    structures = pd.concat(
        [lines[lines["fcode"].isin({34305, 34306})], areas[areas["fcode"].isin(STRUCTURES)]],
        ignore_index=True,
    )

    for name, frame in (
        ("transfers_tunnels", tunnels),
        ("transfers_pipelines", pipelines),
        ("transfers_canals", canals),
        ("transfers_structures", structures),
    ):
        frame = gpd.GeoDataFrame(frame, crs="EPSG:4326")
        if name != "transfers_structures":
            frame = infer_direction(frame)
        else:
            frame["direction"] = "unknown"
        summary = frame.groupby("label").size().to_dict()
        print(f"{name}: {summary}, direction {frame['direction'].value_counts().to_dict()}")
        write_geojson(frame, VECTORS / f"{name}.geojson")


if __name__ == "__main__":
    main()
