"""Geology and island wide soils.

Geology  USGS mrdata WFS for the Geologic Map of Puerto Rico (OFR 98-38),
         served in WGS84 with unit name, age, and lithology. Faults come
         from the same service.
Soils    gNATSGO map unit raster from the Microsoft Planetary Computer,
         joined to SSURGO attributes through Soil Data Access. Produces
         island wide hydrologic soil group and surface K factor rasters.

Outputs
  public/data/vectors/geology.geojson
  public/data/vectors/geology_faults.geojson
  public/data/rasters/soils_hsg.tif        uint8 classes, 0 nodata
  public/data/rasters/soils_kfactor.tif    uint8 K times 100, 255 nodata
  public/data/vectors/soils_lookup.json    class tables for the legend
"""

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer
import rasterio
import rasterio.merge
import requests
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from shapely.geometry import box

from common import CACHE, ISLAND_BBOX, RASTERS, VECTORS, save_json, write_geojson

WFS = "https://mrdata.usgs.gov/services/wfs/pr"
STAC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
HEADERS = {"User-Agent": "Mozilla/5.0 pr-dashboard-data-prep"}

HSG_CODES = {"A": 1, "B": 2, "C": 3, "D": 4, "A/D": 5, "B/D": 6, "C/D": 7}

# Registration correction for the geologic map, in Web Mercator meters.
# Found by maximizing the overlap between the map's land area and two
# independent land masks (3DEP elevation and NOAA C-CAP) over a grid of
# trial shifts. About 47 m east and 180 m south on the ground.
GEOLOGY_SHIFT_M = (50.0, -190.0)
TARGET_RES_M = 20


# --------------------------------------------------------------------------
# Geology
# --------------------------------------------------------------------------

def fetch_wfs(type_name: str) -> gpd.GeoDataFrame:
    path = CACHE / f"mrdata_{type_name}.gml"
    if not path.exists():
        response = requests.get(
            WFS,
            params={
                "request": "GetFeature",
                "service": "WFS",
                "version": "1.1.0",
                "typeName": type_name,
                "maxFeatures": "50000",
            },
            headers=HEADERS,
            timeout=600,
        )
        response.raise_for_status()
        path.write_bytes(response.content)
    frame = gpd.read_file(path)
    # WFS 1.1.0 returns EPSG:4326 with latitude first. Swap to lon, lat.
    from shapely.ops import transform as shapely_transform

    frame["geometry"] = frame.geometry.map(
        lambda geom: shapely_transform(lambda x, y, z=None: (y, x), geom)
    )
    frame = frame.set_crs("EPSG:4326", allow_override=True)
    # Apply the registration correction in a metric projection.
    from shapely.affinity import translate

    mercator = frame.to_crs("EPSG:3857")
    mercator["geometry"] = mercator.geometry.map(
        lambda geom: translate(geom, GEOLOGY_SHIFT_M[0], GEOLOGY_SHIFT_M[1])
    )
    return mercator.to_crs("EPSG:4326")


def geology() -> None:
    units = fetch_wfs("geol")
    print(f"  {len(units)} geology polygons, columns {list(units.columns)}")
    keep = [c for c in ("fmatn", "name", "age", "lith62name", "url") if c in units.columns]
    units = units[keep + ["geometry"]].copy()
    units["geometry"] = units.geometry.simplify(0.00015, preserve_topology=True)
    write_geojson(units, VECTORS / "geology.geojson", precision=5)
    print("  lithology classes:", units["lith62name"].value_counts().to_dict())
    print("  ages:", units["age"].value_counts().head(12).to_dict())

    # Two fault layers. Line type codes come from the OFR 98-38 metadata.
    thrust = fetch_wfs("fault")
    thrust["kind"] = thrust["lntype"].map({"7": "Thrust fault", "27": "Concealed thrust fault"})
    normal = fetch_wfs("faultn")
    normal["kind"] = normal["lntype"].map({"25": "Normal fault", "0": "Fault, type not recorded"})
    faults = pd.concat([thrust, normal], ignore_index=True)
    faults["kind"] = faults["kind"].fillna("Fault")
    faults = gpd.GeoDataFrame(faults[["lntype", "kind", "geometry"]], crs="EPSG:4326")
    faults["geometry"] = faults.geometry.simplify(0.00015, preserve_topology=True)
    print(f"  {len(faults)} fault lines: {faults['kind'].value_counts().to_dict()}")
    write_geojson(faults, VECTORS / "geology_faults.geojson", precision=5)


# --------------------------------------------------------------------------
# Soils
# --------------------------------------------------------------------------

def sda_query(query: str) -> list[list]:
    response = requests.post(
        SDA_URL, json={"query": query, "format": "JSON"}, timeout=600, headers=HEADERS
    )
    response.raise_for_status()
    return response.json().get("Table", [])


def mukey_raster() -> tuple[np.ndarray, dict]:
    """Mosaic the gNATSGO map unit key raster over the island at 20 m."""
    mosaic_path = CACHE / "gnatsgo_mukey_pr_20m.tif"
    if not mosaic_path.exists():
        search = requests.post(
            STAC_SEARCH,
            json={"collections": ["gnatsgo-rasters"], "bbox": list(ISLAND_BBOX), "limit": 10},
            timeout=120,
        ).json()
        pieces = []
        for item in search.get("features", []):
            href = planetary_computer.sign(item["assets"]["mukey"]["href"])
            piece_path = CACHE / f"gnatsgo_mukey_{item['id']}.tif"
            if not piece_path.exists():
                with rasterio.open(href) as src:
                    island = gpd.GeoSeries([box(*ISLAND_BBOX)], crs="EPSG:4326").to_crs(src.crs)
                    bounds = island.total_bounds
                    window = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
                    window = window.intersection(
                        rasterio.windows.Window(0, 0, src.width, src.height)
                    )
                    factor = TARGET_RES_M / src.res[0]
                    out_shape = (
                        max(1, int(window.height / factor)),
                        max(1, int(window.width / factor)),
                    )
                    data = src.read(
                        1, window=window, out_shape=out_shape, resampling=Resampling.nearest
                    )
                    transform = src.window_transform(window) * rasterio.Affine.scale(
                        window.width / out_shape[1], window.height / out_shape[0]
                    )
                    profile = {
                        "driver": "GTiff",
                        "dtype": "int32",
                        "count": 1,
                        "crs": src.crs,
                        "transform": transform,
                        "width": out_shape[1],
                        "height": out_shape[0],
                        "nodata": src.nodata,
                        "compress": "deflate",
                    }
                with rasterio.open(piece_path, "w", **profile) as dst:
                    dst.write(data, 1)
                print(f"  fetched {piece_path.name} {out_shape[1]}x{out_shape[0]}")
            pieces.append(rasterio.open(piece_path))
        mosaic, transform = rasterio.merge.merge(pieces, method="first")
        profile = pieces[0].profile.copy()
        profile.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform)
        for piece in pieces:
            piece.close()
        with rasterio.open(mosaic_path, "w", **profile) as dst:
            dst.write(mosaic[0], 1)
    with rasterio.open(mosaic_path) as src:
        return src.read(1), src.profile.copy()


def soil_attributes(mukeys: list[int]) -> pd.DataFrame:
    rows = []
    for start in range(0, len(mukeys), 400):
        chunk = ",".join(str(k) for k in mukeys[start : start + 400])
        rows += sda_query(
            "SELECT mukey, muname, hydgrpdcd, drclassdcd FROM muaggatt "
            f"WHERE mukey IN ({chunk})"
        )
    attrs = pd.DataFrame(rows, columns=["mukey", "muname", "hsg", "drainage"])
    attrs["mukey"] = pd.to_numeric(attrs["mukey"])

    krows = []
    for start in range(0, len(mukeys), 400):
        chunk = ",".join(str(k) for k in mukeys[start : start + 400])
        krows += sda_query(
            "SELECT mu.mukey, c.comppct_r, ch.hzdept_r, ch.kwfact "
            "FROM mapunit mu JOIN component c ON c.mukey = mu.mukey "
            "LEFT JOIN chorizon ch ON ch.cokey = c.cokey "
            f"WHERE mu.mukey IN ({chunk})"
        )
    kframe = pd.DataFrame(krows, columns=["mukey", "comppct", "hzdept", "kw"])
    for column in ("mukey", "comppct", "hzdept", "kw"):
        kframe[column] = pd.to_numeric(kframe[column], errors="coerce")
    kframe = kframe.dropna(subset=["kw"]).sort_values(["mukey", "comppct", "hzdept"], ascending=[True, False, True])
    kfactor = kframe.groupby("mukey").first()["kw"].rename("kfactor")
    return attrs.merge(kfactor, on="mukey", how="left")


def write_class_cog(data: np.ndarray, profile: dict, out_path, nodata: int) -> None:
    from rasterio.io import MemoryFile

    source_profile = profile.copy()
    source_profile.update(dtype="uint8", nodata=nodata, driver="GTiff")
    with MemoryFile() as memory:
        with memory.open(**source_profile) as temp:
            temp.write(data.astype(np.uint8), 1)
        with memory.open() as temp:
            with WarpedVRT(temp, crs="EPSG:3857", resampling=Resampling.nearest, nodata=nodata) as vrt:
                warped = vrt.read(1)
                out_profile = {
                    "driver": "COG",
                    "dtype": "uint8",
                    "count": 1,
                    "crs": "EPSG:3857",
                    "transform": vrt.transform,
                    "width": vrt.width,
                    "height": vrt.height,
                    "nodata": nodata,
                    "compress": "deflate",
                    "blocksize": 256,
                    "overview_resampling": "nearest",
                }
    with rasterio.open(out_path, "w", **out_profile) as dst:
        dst.write(warped, 1)
    print(f"  wrote {out_path.name} ({out_path.stat().st_size / (1 << 20):.1f} MB)")


def soils() -> None:
    mukeys_raster, profile = mukey_raster()
    nodata = profile.get("nodata")
    valid = mukeys_raster != nodata
    mukeys = sorted(int(k) for k in np.unique(mukeys_raster[valid]))
    print(f"  {len(mukeys)} map units on the island")
    attrs = soil_attributes(mukeys)
    print("  hydrologic groups:", attrs["hsg"].value_counts(dropna=False).to_dict())
    print(f"  K factor known for {attrs['kfactor'].notna().sum()} map units")

    hsg_lookup = {row.mukey: HSG_CODES.get(str(row.hsg).strip(), 0) for row in attrs.itertuples()}
    k_lookup = {
        row.mukey: (255 if pd.isna(row.kfactor) else int(round(float(row.kfactor) * 100)))
        for row in attrs.itertuples()
    }

    # Map every mukey to its class value with a vectorized lookup.
    keys = np.array(list(hsg_lookup.keys()), dtype=np.int64)
    hsg_values = np.array([hsg_lookup[k] for k in keys], dtype=np.uint8)
    k_values = np.array([k_lookup[k] for k in keys], dtype=np.uint8)
    order = np.argsort(keys)
    keys, hsg_values, k_values = keys[order], hsg_values[order], k_values[order]
    flat = mukeys_raster.astype(np.int64).ravel()
    positions = np.searchsorted(keys, flat)
    positions = np.clip(positions, 0, len(keys) - 1)
    matched = keys[positions] == flat

    hsg = np.where(matched, hsg_values[positions], 0).reshape(mukeys_raster.shape)
    hsg[~valid] = 0
    kfac = np.where(matched, k_values[positions], 255).reshape(mukeys_raster.shape)
    kfac[~valid] = 255

    write_class_cog(hsg, profile, RASTERS / "soils_hsg.tif", 0)
    write_class_cog(kfac, profile, RASTERS / "soils_kfactor.tif", 255)

    save_json(
        {
            "hsg": {str(v): k for k, v in HSG_CODES.items()},
            "units": len(mukeys),
            "source": "gNATSGO July 2020 map unit raster with SSURGO attributes from Soil Data Access",
        },
        VECTORS / "soils_lookup.json",
    )


def main() -> None:
    print("Geology from mrdata WFS")
    geology()
    print("Soils from gNATSGO")
    soils()


if __name__ == "__main__":
    main()
