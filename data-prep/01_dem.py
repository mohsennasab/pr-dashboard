"""Download 3DEP elevation for the island and for each reservoir box.

Produces
  cache/dem_island_30m.tif          float32 meters, one arc second
  cache/dem_<reservoir>_10m.tif     float32 meters, one third arc second
  public/data/rasters/dem_island_30m.tif   uint16 tenths of feet COG

The per reservoir COGs are written by 03_dem_products.py after the
watershed boundaries exist, so they can be clipped to the drainage area.
"""

from common import ISLAND_BBOX, RASTERS, RESERVOIRS, fetch_3dep_dem, write_elevation_cog


def main() -> None:
    print("Island DEM at one arc second")
    island = fetch_3dep_dem(ISLAND_BBOX, 1.0, "dem_island_30m")
    write_elevation_cog(island, RASTERS / "dem_island_30m.tif")

    for key, info in RESERVOIRS.items():
        print(f"{info['short']} DEM at one third arc second")
        fetch_3dep_dem(info["dem_bbox"], 1.0 / 3.0, f"dem_{key}_10m")


if __name__ == "__main__":
    main()
