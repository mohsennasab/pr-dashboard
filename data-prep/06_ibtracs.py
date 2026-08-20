"""Build the hurricane track layer from IBTrACS v04r01.

Keeps every North Atlantic storm since 1980 that passed within 500 km of
Puerto Rico. Tracks ship as one line segment per three hour step so the map
can color each piece by its Saffir Simpson category at that moment.

Outputs
  public/data/vectors/storms.geojson    track segments near the island
  public/data/vectors/storm_index.json  one row per storm for the search list
"""

import math

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString

from common import CACHE, VECTORS, download_file, save_json, write_geojson

IBTRACS_URL = (
    "https://www.ncei.noaa.gov/data/international-best-track-archive-for-"
    "climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.NA.list.v04r01.csv"
)
# Island rectangle used for the screening distance.
WEST, SOUTH, EAST, NORTH = -67.27, 17.88, -65.24, 18.57
SCREEN_KM = 500.0
DISPLAY_KM = 800.0


def distance_to_island_km(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Great circle distance from points to the nearest island bbox edge."""
    clamped_lon = np.clip(lon, WEST, EAST)
    clamped_lat = np.clip(lat, SOUTH, NORTH)
    lat1 = np.radians(lat)
    lat2 = np.radians(clamped_lat)
    dlat = lat2 - lat1
    dlon = np.radians(clamped_lon - lon)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def main() -> None:
    path = download_file(IBTRACS_URL, CACHE / "ibtracs_na.csv")
    frame = pd.read_csv(
        path,
        skiprows=[1],
        usecols=["SID", "SEASON", "NAME", "ISO_TIME", "LAT", "LON", "USA_WIND", "USA_SSHS"],
        dtype=str,
        na_values=[" ", ""],
        keep_default_na=True,
        low_memory=False,
    )
    frame["SEASON"] = pd.to_numeric(frame["SEASON"], errors="coerce")
    frame = frame[frame["SEASON"] >= 1980].copy()
    for column in ("LAT", "LON", "USA_WIND", "USA_SSHS"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["LAT", "LON"])
    frame["time"] = pd.to_datetime(frame["ISO_TIME"], errors="coerce")
    frame["dist_km"] = distance_to_island_km(frame["LON"].values, frame["LAT"].values)

    near = frame.groupby("SID")["dist_km"].min()
    keep_ids = near[near <= SCREEN_KM].index
    frame = frame[frame["SID"].isin(keep_ids)].copy()
    print(f"{len(keep_ids)} storms within {SCREEN_KM:.0f} km since 1980")

    segments = []
    index_rows = []
    for sid, track in frame.groupby("SID", sort=False):
        track = track.sort_values("time")
        name = str(track["NAME"].iloc[0] or "Unnamed").title()
        season = int(track["SEASON"].iloc[0])
        within = track[track["dist_km"] <= SCREEN_KM]
        peak_cat = within["USA_SSHS"].max()
        peak_wind = within["USA_WIND"].max()
        index_rows.append(
            {
                "sid": sid,
                "name": name,
                "season": season,
                "cat": None if pd.isna(peak_cat) else int(peak_cat),
                "wind": None if pd.isna(peak_wind) else int(peak_wind),
                "min_km": int(track["dist_km"].min()),
            }
        )
        rows = track.to_dict("records")
        for start, end in zip(rows[:-1], rows[1:]):
            if start["dist_km"] > DISPLAY_KM and end["dist_km"] > DISPLAY_KM:
                continue
            gap = (end["time"] - start["time"]).total_seconds() if start["time"] and end["time"] else None
            if gap is None or gap > 12 * 3600:
                continue
            cat = start["USA_SSHS"]
            wind = start["USA_WIND"]
            segments.append(
                {
                    "sid": sid,
                    "name": name,
                    "season": season,
                    "cat": -9 if pd.isna(cat) else int(cat),
                    "wind": None if pd.isna(wind) else int(wind),
                    "geometry": LineString(
                        [(start["LON"], start["LAT"]), (end["LON"], end["LAT"])]
                    ),
                }
            )

    gdf = gpd.GeoDataFrame(segments, crs="EPSG:4326")
    write_geojson(gdf, VECTORS / "storms.geojson", precision=3)
    index_rows.sort(key=lambda row: (-row["season"], row["name"]))
    save_json(index_rows, VECTORS / "storm_index.json")


if __name__ == "__main__":
    main()
