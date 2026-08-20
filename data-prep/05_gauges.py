"""Build the gauge layers.

Streamflow gauges come from the USGS NWIS site service. Rain gauges come
from the same service plus NOAA GHCN Daily stations. Each feature keeps its
period of record, an active flag, and a link to the agency station page.

Outputs
  public/data/vectors/gauges_streamflow.geojson
  public/data/vectors/gauges_rain.geojson
"""

import io

import geopandas as gpd
import pandas as pd

from common import CACHE, VECTORS, download_file, http_get, write_geojson

NWIS_SITE = "https://waterservices.usgs.gov/nwis/site/"
GHCN_STATIONS = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt"
GHCN_INVENTORY = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-inventory.txt"
ACTIVE_AFTER = "2024-06-01"


def read_rdb(text: str) -> pd.DataFrame:
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    header = lines[0].split("\t")
    rows = [line.split("\t") for line in lines[2:] if line.strip()]
    return pd.DataFrame(rows, columns=header)


def nwis_series(parameter: str) -> pd.DataFrame:
    response = http_get(
        NWIS_SITE,
        params={
            "format": "rdb",
            "stateCd": "PR",
            "parameterCd": parameter,
            "seriesCatalogOutput": "true",
            "siteStatus": "all",
        },
        timeout=300,
    )
    frame = read_rdb(response.text)
    frame = frame[frame["parm_cd"] == parameter]
    frame = frame[frame["data_type_cd"].isin(["dv", "uv", "id"])]
    grouped = (
        frame.groupby("site_no")
        .agg(
            station=("station_nm", "first"),
            lat=("dec_lat_va", "first"),
            lon=("dec_long_va", "first"),
            begin=("begin_date", "min"),
            end=("end_date", "max"),
        )
        .reset_index()
    )
    grouped["lat"] = pd.to_numeric(grouped["lat"], errors="coerce")
    grouped["lon"] = pd.to_numeric(grouped["lon"], errors="coerce")
    grouped = grouped.dropna(subset=["lat", "lon"])
    grouped["active"] = grouped["end"] >= ACTIVE_AFTER
    grouped["url"] = (
        "https://waterdata.usgs.gov/monitoring-location/" + grouped["site_no"]
    )
    return grouped


def nwis_drainage() -> pd.DataFrame:
    response = http_get(
        NWIS_SITE,
        params={
            "format": "rdb",
            "stateCd": "PR",
            "parameterCd": "00060",
            "siteOutput": "expanded",
            "siteStatus": "all",
        },
        timeout=300,
    )
    frame = read_rdb(response.text)
    frame = frame[["site_no", "drain_area_va"]].copy()
    frame["drain_area_va"] = pd.to_numeric(frame["drain_area_va"], errors="coerce")
    return frame


def to_geojson(frame: pd.DataFrame, path, columns) -> None:
    gdf = gpd.GeoDataFrame(
        frame[columns],
        geometry=gpd.points_from_xy(frame["lon"], frame["lat"]),
        crs="EPSG:4326",
    )
    write_geojson(gdf, path)


def ghcn_rain() -> pd.DataFrame:
    stations_path = download_file(GHCN_STATIONS, CACHE / "ghcnd-stations.txt")
    inventory_path = download_file(GHCN_INVENTORY, CACHE / "ghcnd-inventory.txt")

    stations = pd.read_fwf(
        stations_path,
        colspecs=[(0, 11), (12, 20), (21, 30), (31, 37), (38, 40), (41, 71)],
        names=["id", "lat", "lon", "elev", "state", "name"],
        dtype={"id": str},
    )
    stations = stations[stations["id"].str.startswith("RQ")]

    inventory = pd.read_fwf(
        inventory_path,
        colspecs=[(0, 11), (31, 35), (36, 45), (41, 45)],
        names=["id", "element", "firstyear", "lastyear"],
        dtype={"id": str},
    )
    inventory = inventory[inventory["id"].str.startswith("RQ")]
    inventory = inventory[inventory["element"] == "PRCP"]
    inventory["firstyear"] = pd.to_numeric(inventory["firstyear"], errors="coerce")
    inventory["lastyear"] = pd.to_numeric(inventory["lastyear"], errors="coerce")

    merged = stations.merge(inventory[["id", "firstyear", "lastyear"]], on="id")
    merged["station"] = merged["name"].str.title()
    merged["begin"] = merged["firstyear"].astype("Int64").astype(str)
    merged["end"] = merged["lastyear"].astype("Int64").astype(str)
    merged["active"] = merged["lastyear"] >= 2024
    merged["network"] = "GHCN Daily"
    merged["url"] = (
        "https://www.ncei.noaa.gov/cdo-web/datasets/GHCND/stations/GHCND:"
        + merged["id"]
        + "/detail"
    )
    merged = merged.rename(columns={"id": "site_no"})
    return merged


def main() -> None:
    print("USGS streamflow gauges")
    flow = nwis_series("00060")
    drainage = nwis_drainage()
    flow = flow.merge(drainage, on="site_no", how="left")
    flow["network"] = "USGS NWIS"
    to_geojson(
        flow,
        VECTORS / "gauges_streamflow.geojson",
        ["site_no", "station", "begin", "end", "active", "drain_area_va", "network", "url"],
    )

    print("USGS rain gauges")
    usgs_rain = nwis_series("00045")
    usgs_rain["network"] = "USGS NWIS"

    print("GHCN Daily rain gauges")
    ghcn = ghcn_rain()

    columns = ["site_no", "station", "begin", "end", "active", "network", "url"]
    rain = pd.concat([usgs_rain[columns + ["lat", "lon"]], ghcn[columns + ["lat", "lon"]]])
    to_geojson(rain, VECTORS / "gauges_rain.geojson", columns)


if __name__ == "__main__":
    main()
