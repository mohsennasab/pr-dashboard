"""Shared configuration and helpers for the data preparation scripts.

Every script in this folder writes web ready files into public/data.
Raw downloads land in data-prep/cache, which stays out of git.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.merge import merge as rio_merge

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data-prep" / "cache"
VECTORS = ROOT / "public" / "data" / "vectors"
RASTERS = ROOT / "public" / "data" / "rasters"
for folder in (CACHE, VECTORS, RASTERS):
    folder.mkdir(parents=True, exist_ok=True)

# Island wide bounding box with a small margin, WGS84 lon and lat.
ISLAND_BBOX = (-67.35, 17.85, -65.15, 18.60)

# Elevation rasters ship as uint16 tenths of feet so the browser can decode
# them the same way for every raster. 65535 marks nodata.
NODATA = 65535
FEET_PER_METER = 3.28084
VALUE_SCALE = 0.1

# The six study reservoirs. Lake points sit inside each NHD waterbody polygon
# and were checked against published dam coordinates. Each DEM box is drawn
# generously so the full upstream drainage area fits inside it.
RESERVOIRS = {
    "guineo": {
        "name": "Lago El Guineo",
        "short": "Guineo",
        "river": "Rio Toro Negro",
        "municipality": "Villalba / Orocovis",
        "lake_point": (-66.5294, 18.1592),
        "dem_bbox": (-66.62, 18.10, -66.46, 18.24),
    },
    "matrullas": {
        "name": "Lago de Matrullas",
        "short": "Matrullas",
        "river": "Rio Matrullas",
        "municipality": "Orocovis",
        "lake_point": (-66.4795, 18.2041),
        "dem_bbox": (-66.57, 18.15, -66.40, 18.30),
    },
    "guayabal": {
        "name": "Lago Guayabal",
        "short": "Guayabal",
        "river": "Rio Jacaguas",
        "municipality": "Juana Diaz / Villalba",
        "lake_point": (-66.5010, 18.0963),
        "dem_bbox": (-66.62, 18.03, -66.40, 18.24),
    },
    "guayo": {
        "name": "Lago Guayo",
        "short": "Guayo",
        "river": "Rio Guayo",
        "municipality": "Adjuntas / Lares",
        "lake_point": (-66.8336, 18.1994),
        "dem_bbox": (-66.96, 18.13, -66.72, 18.36),
    },
    "loco": {
        "name": "Lago Loco",
        "short": "Loco",
        "river": "Rio Loco",
        "municipality": "Yauco",
        "lake_point": (-66.8838, 18.0479),
        "dem_bbox": (-67.00, 17.99, -66.78, 18.20),
    },
    "lucchetti": {
        "name": "Lago Lucchetti",
        "short": "Lucchetti",
        "river": "Rio Yauco",
        "municipality": "Yauco",
        "lake_point": (-66.8671, 18.0985),
        "dem_bbox": (-67.00, 18.04, -66.76, 18.26),
    },
}

THREEDEP_EXPORT = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/"
    "ImageServer/exportImage"
)

USER_AGENT = "pr-dashboard-data-prep (github.com/mohsennasab/pr-dashboard)"


def http_get(url: str, *, params=None, timeout: int = 300, tries: int = 4) -> requests.Response:
    """GET with simple retries so long downloads survive a flaky connection."""
    last = None
    for attempt in range(tries):
        try:
            response = requests.get(
                url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT}
            )
            if response.status_code == 200:
                return response
            last = RuntimeError(f"HTTP {response.status_code} for {response.url[:200]}")
        except requests.RequestException as error:
            last = error
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Download failed after {tries} tries: {url}") from last


def download_file(url: str, dest: Path, *, params=None, timeout: int = 900) -> Path:
    """Download to cache once. A finished file is trusted and reused."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    with requests.get(
        url, params=params, timeout=timeout, stream=True, headers={"User-Agent": USER_AGENT}
    ) as response:
        response.raise_for_status()
        with open(partial, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                handle.write(chunk)
    partial.replace(dest)
    return dest


def fetch_3dep_dem(bbox, resolution_arcsec: float, cache_name: str) -> Path:
    """Download a 3DEP DEM for a lon lat box, tiling requests under the
    service size limit and mosaicking the pieces into one float32 GeoTIFF."""
    out_path = CACHE / f"{cache_name}.tif"
    if out_path.exists():
        return out_path

    step = resolution_arcsec / 3600.0
    west, south, east, north = bbox
    width = math.ceil((east - west) / step)
    height = math.ceil((north - south) / step)
    max_pixels = 4000

    pieces = []
    piece_index = 0
    for row_start in range(0, height, max_pixels):
        rows = min(max_pixels, height - row_start)
        tile_north = north - row_start * step
        tile_south = tile_north - rows * step
        for col_start in range(0, width, max_pixels):
            cols = min(max_pixels, width - col_start)
            tile_west = west + col_start * step
            tile_east = tile_west + cols * step
            piece_path = CACHE / f"{cache_name}_piece{piece_index}.tif"
            piece_index += 1
            if not piece_path.exists():
                meta = http_get(
                    THREEDEP_EXPORT,
                    params={
                        "bbox": f"{tile_west},{tile_south},{tile_east},{tile_north}",
                        "bboxSR": "4326",
                        "imageSR": "4326",
                        "size": f"{cols},{rows}",
                        "format": "tiff",
                        "pixelType": "F32",
                        "interpolation": "RSP_BilinearInterpolation",
                        "f": "json",
                    },
                    timeout=600,
                ).json()
                if "href" not in meta:
                    raise RuntimeError(f"3DEP export failed: {meta}")
                download_file(meta["href"], piece_path)
                print(f"  downloaded {piece_path.name} ({cols}x{rows})")
            pieces.append(piece_path)

    if len(pieces) == 1:
        pieces[0].replace(out_path)
        return out_path

    sources = [rasterio.open(piece) for piece in pieces]
    mosaic, transform = rio_merge(sources)
    profile = sources[0].profile.copy()
    profile.update(
        height=mosaic.shape[1], width=mosaic.shape[2], transform=transform, count=1
    )
    for source in sources:
        source.close()
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(mosaic[0], 1)
    for piece in pieces:
        piece.unlink()
    return out_path


def write_elevation_cog(dem_path: Path, out_path: Path) -> None:
    """Convert a float32 meter DEM into a uint16 tenth of a foot COG.

    The browser COG reader only handles Web Mercator, so the raster is
    warped to EPSG:3857 on the way out.
    """
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    with rasterio.open(dem_path) as src:
        with WarpedVRT(
            src,
            crs="EPSG:3857",
            resampling=Resampling.bilinear,
            src_nodata=src.nodata if src.nodata is not None else -9999.0,
            nodata=-9999.0,
        ) as vrt:
            data = vrt.read(1)
            profile = vrt.profile.copy()
    src_nodata = -9999.0

    invalid = ~np.isfinite(data)
    invalid |= data == src_nodata
    invalid |= data < -100
    # The seamless DEM reports open water as zero. Masking it keeps the
    # elevation color ramp on land only.
    invalid |= data <= 0.05

    feet_tenths = np.round(data * FEET_PER_METER / VALUE_SCALE)
    feet_tenths = np.clip(feet_tenths, 0, NODATA - 1).astype(np.uint16)
    feet_tenths[invalid] = NODATA

    profile.update(
        driver="COG",
        dtype="uint16",
        nodata=NODATA,
        compress="deflate",
        blocksize=256,
        overview_resampling="average",
    )
    profile.pop("blockxsize", None)
    profile.pop("blockysize", None)
    profile.pop("tiled", None)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(feet_tenths, 1)
    size_mb = out_path.stat().st_size / (1 << 20)
    print(f"  wrote {out_path.name} ({size_mb:.1f} MB)")


def write_geojson(gdf, path: Path, precision: int = 5) -> None:
    """Write GeoJSON with trimmed coordinate precision to keep files small."""
    import pyogrio

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    pyogrio.write_dataframe(
        gdf, path, driver="GeoJSON", COORDINATE_PRECISION=str(precision)
    )
    size_mb = path.stat().st_size / (1 << 20)
    print(f"  wrote {path.name} ({size_mb:.2f} MB, {len(gdf)} features)")


def save_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
    print(f"  wrote {path.name} ({path.stat().st_size / 1024:.0f} KB)")
