"""Clip the one third arc second DEMs to each watershed and write COGs.

The browser samples these rasters for cross section profiles, so each one
covers its watershed plus a one kilometer margin. Elevations ship as uint16
tenths of feet, matching the island wide raster.
"""

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.mask

from common import (
    CACHE,
    FEET_PER_METER,
    NODATA,
    RASTERS,
    RESERVOIRS,
    VALUE_SCALE,
    fetch_3dep_dem,
)


def main() -> None:
    sheds = gpd.read_file(CACHE / "watersheds_raw.gpkg", layer="watersheds")
    for key, info in RESERVOIRS.items():
        shed = sheds[sheds["key"] == key]
        clip_shape = shed.geometry.iloc[0].buffer(0.01)
        from rasterio.enums import Resampling
        from rasterio.io import MemoryFile
        from rasterio.vrt import WarpedVRT

        # The HUC12 study watershed can extend past the original download
        # boxes, so fetch a DEM sized to this boundary. Cached after the
        # first run.
        bounds = clip_shape.bounds
        dem_path = fetch_3dep_dem(
            (bounds[0] - 0.005, bounds[1] - 0.005, bounds[2] + 0.005, bounds[3] + 0.005),
            1.0 / 3.0,
            f"dem_{key}_h12_10m",
        )
        with rasterio.open(dem_path) as src:
            data, transform = rasterio.mask.mask(
                src, [clip_shape], crop=True, nodata=-9999.0
            )
            clipped_profile = src.profile.copy()
        clipped_profile.update(
            height=data.shape[1],
            width=data.shape[2],
            transform=transform,
            nodata=-9999.0,
        )
        # Warp the clipped piece to Web Mercator for the browser COG reader.
        with MemoryFile() as memory:
            with memory.open(**clipped_profile) as temp:
                temp.write(data)
            with memory.open() as temp:
                with WarpedVRT(
                    temp,
                    crs="EPSG:3857",
                    resampling=Resampling.bilinear,
                    nodata=-9999.0,
                ) as vrt:
                    data = vrt.read()
                    transform = vrt.transform
                    profile = vrt.profile.copy()
        band = data[0]
        invalid = ~np.isfinite(band) | (band == -9999.0) | (band < -100)
        feet_tenths = np.round(band * FEET_PER_METER / VALUE_SCALE)
        feet_tenths = np.clip(feet_tenths, 0, NODATA - 1).astype(np.uint16)
        feet_tenths[invalid] = NODATA
        profile.update(
            driver="COG",
            dtype="uint16",
            nodata=NODATA,
            compress="deflate",
            blocksize=256,
            overview_resampling="average",
            height=band.shape[0],
            width=band.shape[1],
            transform=transform,
        )
        for stale in ("blockxsize", "blockysize", "tiled"):
            profile.pop(stale, None)
        out_path = RASTERS / f"dem_{key}_10m.tif"
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(feet_tenths, 1)
        print(f"{info['short']}: {out_path.name} {out_path.stat().st_size / (1 << 20):.1f} MB")


if __name__ == "__main__":
    main()
