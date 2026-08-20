"""Soils erodibility and geology.

Soils    USDA SSURGO through Soil Data Access. Map unit polygons inside each
         watershed carry the surface horizon K factor (Kw) of the dominant
         component, a standard erodibility indicator.
Geology  USGS OFR 98-38 geologic map of Puerto Rico, island wide.

Outputs
  public/data/vectors/soils_k.geojson
  public/data/vectors/geology.geojson
"""

import json
import zipfile

import geopandas as gpd
import pandas as pd
import requests
from shapely import wkt as shapely_wkt

from common import CACHE, VECTORS, download_file, write_geojson

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
GEOLOGY_ZIP = "https://mrdata.usgs.gov/geology/pr/ofr-98-38.zip"


def sda_query(query: str) -> list[list]:
    response = requests.post(
        SDA_URL,
        json={"query": query, "format": "JSON"},
        timeout=600,
        headers={"User-Agent": "pr-dashboard-data-prep"},
    )
    response.raise_for_status()
    return response.json().get("Table", [])


def soils() -> None:
    sheds = gpd.read_file(CACHE / "watersheds_raw.gpkg", layer="watersheds")
    pieces = []
    for _, shed in sheds.iterrows():
        hull = shed.geometry.convex_hull.simplify(0.001)
        wkt_text = hull.wkt
        rows = sda_query(
            "SELECT mupolygon.mukey, mupolygon.mupolygongeo.STAsText() "
            "FROM mupolygon WHERE mupolygon.mupolygongeo.STIntersects("
            f"geometry::STPolyFromText('{wkt_text}', 4326)) = 1"
        )
        if not rows:
            print(f"  {shed['key']}: no SSURGO polygons returned")
            continue
        frame = gpd.GeoDataFrame(
            {"mukey": [row[0] for row in rows]},
            geometry=[shapely_wkt.loads(row[1]) for row in rows],
            crs="EPSG:4326",
        )
        frame = frame[frame.intersects(shed.geometry)]
        pieces.append(frame)
        print(f"  {shed['key']}: {len(frame)} map unit polygons")

    merged = gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), crs="EPSG:4326")
    merged = merged.dissolve(by="mukey", as_index=False)

    mukeys = ",".join(f"'{k}'" for k in merged["mukey"].unique())
    rows = sda_query(
        "SELECT mu.mukey, mu.musym, mu.muname, c.compname, c.comppct_r, "
        "ch.hzdept_r, ch.kwfact "
        "FROM mapunit mu "
        "JOIN component c ON c.mukey = mu.mukey "
        "LEFT JOIN chorizon ch ON ch.cokey = c.cokey "
        f"WHERE mu.mukey IN ({mukeys})"
    )
    attrs = pd.DataFrame(
        rows,
        columns=["mukey", "musym", "muname", "compname", "comppct", "hzdept", "kwfact"],
    )
    attrs["comppct"] = pd.to_numeric(attrs["comppct"], errors="coerce")
    attrs["hzdept"] = pd.to_numeric(attrs["hzdept"], errors="coerce")
    attrs["kw"] = pd.to_numeric(attrs["kwfact"], errors="coerce")

    def dominant(group: pd.DataFrame) -> pd.Series:
        best = group.sort_values(
            ["comppct", "hzdept"], ascending=[False, True]
        )
        with_k = best.dropna(subset=["kw"])
        top = with_k.iloc[0] if len(with_k) else best.iloc[0]
        return pd.Series(
            {
                "muname": top["muname"],
                "musym": top["musym"],
                "component": top["compname"],
                "kfactor": top["kw"] if pd.notna(top["kw"]) else None,
            }
        )

    summary = attrs.groupby("mukey").apply(dominant, include_groups=False).reset_index()
    merged = merged.merge(summary, on="mukey", how="left")
    merged["geometry"] = merged.geometry.simplify(0.00005, preserve_topology=True)
    write_geojson(merged, VECTORS / "soils_k.geojson")


def geology() -> None:
    zip_path = download_file(GEOLOGY_ZIP, CACHE / "geology_ofr9838.zip")
    extract = CACHE / "geology"
    if not extract.exists():
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract)
    shapefiles = list(extract.rglob("*.shp"))
    print("  shapefiles:", [s.name for s in shapefiles])
    polygons = None
    for shp in shapefiles:
        frame = gpd.read_file(shp)
        if frame.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).any():
            polygons = frame
            break
    if polygons is None:
        raise RuntimeError("No polygon layer in the geology download")
    print("  columns:", list(polygons.columns))
    if polygons.crs is None:
        polygons = polygons.set_crs("EPSG:4326")
    polygons = polygons.to_crs("EPSG:4326")
    polygons["geometry"] = polygons.geometry.simplify(0.0005, preserve_topology=True)
    write_geojson(polygons, VECTORS / "geology.geojson", precision=4)


def main() -> None:
    print("SSURGO soils K factor")
    soils()
    print("Geologic map")
    geology()


if __name__ == "__main__":
    main()
