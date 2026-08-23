"""Write the data catalog as markdown for the repo and HTML for the site."""

import datetime
import html
from pathlib import Path

from common import ROOT

RETRIEVED = datetime.date(2026, 8, 19).isoformat()

SOURCES = [
    {
        "layer": "Elevation and cross sections",
        "source": "USGS 3DEP seamless DEM",
        "details": "One third arc second (about 10 m) inside the study watersheds,"
        " one arc second (about 30 m) island wide. Elevations converted to feet.",
        "url": "https://www.usgs.gov/3d-elevation-program",
    },
    {
        "layer": "3D terrain and hillshade",
        "source": "Mapterhorn terrain tiles",
        "details": "Global terrain tiles streamed at view time for the 3D scene"
        " and shaded relief.",
        "url": "https://mapterhorn.com/attribution",
    },
    {
        "layer": "Study watersheds",
        "source": "USGS Watershed Boundary Dataset",
        "details": "The HUC12 subwatershed mapped at each dam. Its published"
        " area is the drainage area shown on the reservoir cards.",
        "url": "https://www.usgs.gov/national-hydrography/watershed-boundary-dataset",
    },
    {
        "layer": "HUC12 boundaries, rivers, waterbodies",
        "source": "USGS NHDPlus High Resolution",
        "details": "Flowlines, waterbody polygons, and the HUC12 framework from"
        " the National Hydrography Dataset Plus HR map service.",
        "url": "https://www.usgs.gov/national-hydrography/nhdplus-high-resolution",
    },
    {
        "layer": "Water transfers",
        "source": "USGS NHDPlus High Resolution",
        "details": "Tunnels, underground aqueducts, pipelines, siphons, canals,"
        " dams, and water intakes from the NHDPlus HR feature layers. Flow"
        " arrows are solid where NHD records the direction and faded where"
        " it was inferred downhill from the ground elevation at the ends.",
        "url": "https://www.usgs.gov/national-hydrography/nhdplus-high-resolution",
    },
    {
        "layer": "Reservoir storage figures",
        "source": "USGS sedimentation survey reports",
        "details": "Original and surveyed capacities from the published USGS"
        " report for each reservoir. Each reservoir card links to its report.",
        "url": "https://www.usgs.gov/centers/cfwsc/science/sedimentation-surveys-puerto-rico",
    },
    {
        "layer": "Streamflow gauges",
        "source": "USGS National Water Information System",
        "details": "Sites in Puerto Rico with discharge records, active and"
        " discontinued, with period of record and drainage area.",
        "url": "https://waterservices.usgs.gov/",
    },
    {
        "layer": "Rain gauges",
        "source": "USGS NWIS and NOAA GHCN Daily",
        "details": "USGS precipitation sites plus NOAA GHCN Daily stations with"
        " precipitation records.",
        "url": "https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily",
    },
    {
        "layer": "Hurricane tracks",
        "source": "NOAA NCEI IBTrACS v04r01",
        "details": "North Atlantic storms since 1980 passing within 500 km of"
        " Puerto Rico. Segments colored by the USA agency Saffir Simpson"
        " classification.",
        "url": "https://www.ncei.noaa.gov/products/international-best-track-archive",
    },
    {
        "layer": "Landslide points",
        "source": "USGS slope failure inventory after Hurricane Maria",
        "details": "About 71,000 headscarp points mapped from imagery after the"
        " September 2017 event.",
        "url": "https://www.sciencebase.gov/catalog/item/5d4c8b26e4b01d82ce8dfeb0",
    },
    {
        "layer": "Landslide susceptibility",
        "source": "USGS Open File Report 2020-1022",
        "details": "Susceptibility to rainfall triggered landslides, resampled"
        " from 5 m to about 15 m for the web.",
        "url": "https://www.sciencebase.gov/catalog/item/61087009d34ef8d70565c154",
    },
    {
        "layer": "Land cover",
        "source": "NOAA C-CAP 2010, Puerto Rico",
        "details": "Coastal Change Analysis Program land cover at 30 m.",
        "url": "https://coast.noaa.gov/digitalcoast/data/ccapregional.html",
    },
    {
        "layer": "Hydrologic soil group and K factor",
        "source": "gNATSGO on the Microsoft Planetary Computer",
        "details": "Island wide map unit raster (July 2020, 10 m, served at"
        " 20 m) joined to SSURGO attributes through Soil Data Access:"
        " dominant hydrologic group and surface horizon K factor.",
        "url": "https://planetarycomputer.microsoft.com/dataset/group/gnatsgo",
    },
    {
        "layer": "Geology and faults",
        "source": "USGS mrdata, Geologic Map of Puerto Rico (OFR 98-38)",
        "details": "Served by the USGS mrdata WFS with unit name, age, and"
        " lithology, colored by rock family. The 1:100,000 scale linework"
        " was shifted about 180 m south and 47 m east after comparison with"
        " the 3DEP and C-CAP coastlines to register it to the imagery.",
        "url": "https://mrdata.usgs.gov/geology/pr/",
    },
    {
        "layer": "Roads",
        "source": "US Census TIGER/Line 2024",
        "details": "Primary and secondary roads island wide plus all roads"
        " inside the study watersheds.",
        "url": "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html",
    },
    {
        "layer": "Satellite basemap",
        "source": "Google Maps tiles",
        "details": "Streamed at view time under the Google Maps terms.",
        "url": "https://www.google.com/help/terms_maps/",
    },
    {
        "layer": "Street basemap",
        "source": "OpenFreeMap, OpenStreetMap contributors",
        "details": "Drawn basemap style streamed at view time.",
        "url": "https://openfreemap.org/",
    },
    {
        "layer": "Topographic basemap",
        "source": "USGS The National Map",
        "details": "USGS Topo tile service streamed at view time.",
        "url": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer",
    },
    {
        "layer": "Rainfall frequency reference",
        "source": "NOAA Atlas 14, Volume 3, Puerto Rico",
        "details": "Not drawn on the map. Linked here as the standard rainfall"
        " frequency reference for the island.",
        "url": "https://hdsc.nws.noaa.gov/pfds/pfds_map_pr.html",
    },
]


def main() -> None:
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)

    lines = [
        "# Data catalog",
        "",
        f"Every layer in the dashboard with its source. Data retrieved {RETRIEVED}.",
        "",
        "| Layer | Source | Notes |",
        "|---|---|---|",
    ]
    for entry in SOURCES:
        lines.append(
            f"| {entry['layer']} | [{entry['source']}]({entry['url']}) |"
            f" {entry['details']} |"
        )
    lines += [
        "",
        "Land ownership is not shown. Puerto Rico parcel data (CRIM) is not"
        " openly distributed, so no parcel layer is included.",
        "",
    ]
    (docs / "DATA_CATALOG.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote docs/DATA_CATALOG.md")

    rows = "".join(
        "<tr><td>{layer}</td><td><a href='{url}' target='_blank'"
        " rel='noopener noreferrer'>{source}</a></td><td>{details}</td></tr>".format(
            layer=html.escape(entry["layer"]),
            url=html.escape(entry["url"]),
            source=html.escape(entry["source"]),
            details=html.escape(entry["details"]),
        )
        for entry in SOURCES
    )
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Data catalog, Puerto Rico Reservoir Watersheds</title>
<style>
body {{ font-family: Arial, Helvetica, sans-serif; color: #1d2b2d; margin: 0;
  background: #f4f7f6; }}
main {{ max-width: 900px; margin: 0 auto; padding: 28px 20px 60px; }}
h1 {{ font-size: 1.4rem; }}
p {{ line-height: 1.5; }}
table {{ border-collapse: collapse; width: 100%; background: #fff;
  border: 1px solid #d9e1e0; font-size: 0.88rem; }}
th, td {{ text-align: left; padding: 9px 12px; border-bottom: 1px solid #e6ecea;
  vertical-align: top; }}
th {{ background: #e3edee; }}
a {{ color: #1c4d52; }}
</style>
</head>
<body>
<main>
<h1>Data catalog</h1>
<p>Every layer in the <a href="../">Puerto Rico Reservoir Watersheds</a> map
with its source. Data retrieved {RETRIEVED}.</p>
<table>
<tr><th>Layer</th><th>Source</th><th>Notes</th></tr>
{rows}
</table>
<p>Land ownership is not shown. Puerto Rico parcel data (CRIM) is not openly
distributed, so no parcel layer is included.</p>
</main>
</body>
</html>
"""
    out = ROOT / "public" / "docs"
    out.mkdir(parents=True, exist_ok=True)
    (out / "DATA_CATALOG.html").write_text(page, encoding="utf-8")
    print("wrote public/docs/DATA_CATALOG.html")


if __name__ == "__main__":
    main()
