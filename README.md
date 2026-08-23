# Puerto Rico Reservoir Watersheds

An interactive map of six reservoirs in the mountains of Puerto Rico and the
watersheds that drain to them: Guineo, Matrullas, Guayabal, Guayo, Loco, and
Lucchetti. Everything on the map comes from public federal data.

The map runs entirely in the browser. There is no server and nothing to
install. Open the site, turn layers on and off, and click features for
details.

## What you can do

- See each reservoir, its dam, and the drainage area above it
- Read the published USGS storage and sedimentation figures for each reservoir
- Turn on hurricane tracks since 1980 and search for a single storm by name
- Check stream and rain gauges, active and discontinued, with links to the
  agency station pages
- View terrain as hillshade, an elevation color ramp, or a full 3D scene
- Draw a cross section anywhere and download the elevation profile as CSV
- See the tunnels, canals, pipelines, dams, and intakes that move water
  between basins, each as its own layer
- Explore landslides, landslide susceptibility, land cover, hydrologic soil
  groups, soil erodibility, geology, faults, and roads

## Data

Every layer and its source is listed in [docs/DATA_CATALOG.md](docs/DATA_CATALOG.md)
and on the data catalog page inside the app. Elevation figures are in feet
and distances in miles.

The `data-prep` folder holds the Python scripts that download and prepare
every layer. They are numbered in run order and write their outputs into
`public/data`. See [data-prep/README.md](data-prep/README.md).

## Development

```
npm install
npm run dev      # local development server
npm run build    # production build in dist/
```

Built with MapLibre GL JS, Vite, and TypeScript. Elevation rasters are Cloud
Optimized GeoTIFFs read directly in the browser.

## Notes

Study watersheds are the HUC12 subwatersheds mapped at each dam in the USGS
Watershed Boundary Dataset. Confirm any measurement against the original
sources before using it in an engineering decision.
