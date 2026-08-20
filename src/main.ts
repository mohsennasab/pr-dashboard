import maplibregl, {
  type LayerSpecification,
  type Map as MapLibreMap,
  type MapLayerMouseEvent,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { cogProtocol, setColorFunction } from "@geomatico/maplibre-cog-protocol";
import { CrossSectionTool, type RasterExtent } from "./crosssection";
import "./style.css";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ISLAND_BOUNDS: [[number, number], [number, number]] = [
  [-67.32, 17.87],
  [-65.18, 18.58],
];
const BASEMAP_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
const TERRAIN_TILES = "https://tiles.mapterhorn.com/{z}/{x}/{y}.webp";
const TERRAIN_ATTRIBUTION =
  '<a href="https://mapterhorn.com/attribution" target="_blank" rel="noopener noreferrer">© Mapterhorn</a>';
const SATELLITE_TILES = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}";
const SATELLITE_ATTRIBUTION =
  '<a href="https://www.google.com/help/terms_maps/" target="_blank" rel="noopener noreferrer">Imagery © Google</a>';
const TOPO_TILES =
  "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}";
const TOPO_ATTRIBUTION = "USGS The National Map";

const DEM_ISLAND_URL = "./data/rasters/dem_island_30m.tif";
const SUSCEPTIBILITY_URL = "./data/rasters/landslide_susceptibility.tif";
const LANDCOVER_URL = "./data/rasters/landcover_30m.tif";

const NODATA = 65535;
const VALUE_SCALE = 0.1;

const RESERVOIRS = [
  { key: "guineo", name: "Lago El Guineo", river: "Rio Toro Negro", municipality: "Villalba / Orocovis" },
  { key: "matrullas", name: "Lago de Matrullas", river: "Rio Matrullas", municipality: "Orocovis" },
  { key: "guayabal", name: "Lago Guayabal", river: "Rio Jacaguas", municipality: "Juana Diaz / Villalba" },
  { key: "guayo", name: "Lago Guayo", river: "Rio Guayo", municipality: "Adjuntas / Lares" },
  { key: "loco", name: "Lago Loco", river: "Rio Loco", municipality: "Yauco" },
  { key: "lucchetti", name: "Lago Lucchetti", river: "Rio Yauco", municipality: "Yauco" },
];

// Saffir Simpson colors. Negative codes cover depressions, subtropical, and
// other systems below tropical storm strength.
const STORM_CATEGORIES: Array<{ value: number; label: string; color: string }> = [
  { value: -1, label: "Below storm strength", color: "#97a3ac" },
  { value: 0, label: "Tropical storm", color: "#5a86c0" },
  { value: 1, label: "Category 1", color: "#e6cd63" },
  { value: 2, label: "Category 2", color: "#e0a13e" },
  { value: 3, label: "Category 3", color: "#d2703a" },
  { value: 4, label: "Category 4", color: "#b8422f" },
  { value: 5, label: "Category 5", color: "#8a2a5e" },
];

const ELEVATION_STOPS: Array<[number, [number, number, number]]> = [
  [0, [62, 125, 86]],
  [400, [111, 162, 105]],
  [1000, [168, 189, 119]],
  [1800, [216, 196, 126]],
  [2600, [189, 146, 87]],
  [3400, [160, 111, 69]],
  [4400, [240, 231, 216]],
];

const SUSCEPTIBILITY_CLASSES: Array<{ value: number; label: string; color: string }> = [
  { value: 1, label: "Very low", color: "#f2ecd4" },
  { value: 2, label: "Low", color: "#e4cb79" },
  { value: 3, label: "Moderate", color: "#d69e46" },
  { value: 4, label: "High", color: "#bd6430" },
  { value: 5, label: "Very high", color: "#8f2b1e" },
];

const LANDCOVER_CLASSES: Record<number, { label: string; color: string }> = {
  2: { label: "Developed, high", color: "#9e3b33" },
  3: { label: "Developed, medium", color: "#c06657" },
  4: { label: "Developed, low", color: "#d99a83" },
  5: { label: "Developed, open", color: "#dfc2ba" },
  6: { label: "Cultivated", color: "#ab6c28" },
  7: { label: "Pasture and hay", color: "#cbb363" },
  8: { label: "Grassland", color: "#e5d99c" },
  9: { label: "Deciduous forest", color: "#7aa065" },
  10: { label: "Evergreen forest", color: "#3f7550" },
  11: { label: "Mixed forest", color: "#5c8a5a" },
  12: { label: "Scrub and shrub", color: "#b3a95f" },
  13: { label: "Wetland, forested", color: "#6c8f7f" },
  14: { label: "Wetland, scrub", color: "#82a58f" },
  15: { label: "Wetland, emergent", color: "#a3c3a3" },
  16: { label: "Estuarine forest", color: "#5d8a86" },
  17: { label: "Estuarine scrub", color: "#7ba39e" },
  18: { label: "Estuarine emergent", color: "#98bdb4" },
  19: { label: "Shore", color: "#d8cfae" },
  20: { label: "Barren", color: "#c9c1b1" },
  21: { label: "Open water", color: "#5f8fb8" },
  22: { label: "Aquatic bed", color: "#86a9c5" },
  23: { label: "Estuarine aquatic bed", color: "#a9c2d3" },
};

type LayerDefinition = {
  id: string;
  label: string;
  note: string;
  symbolCss: string;
  layers: string[];
  checked: boolean;
  onToggle?: (visible: boolean) => void;
};

type BasemapMode = "satellite" | "streets" | "topo" | "none";
type BasemapLayerGroups = { base: string[]; labels: string[] };

type StormIndexEntry = {
  sid: string;
  name: string;
  season: number;
  cat: number | null;
  wind: number | null;
  min_km: number;
};

type SurveyEntry = { year: number; mm3: number; acft: number };
type ReservoirFacts = {
  built: number;
  original_mm3: number;
  original_acft: number;
  surveys: SurveyEntry[];
  latest_year: number;
  pct_lost: number;
  note: string;
  report: string;
  report_url: string;
};

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function element<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (!found) {
    throw new Error(`Missing interface element: ${id}`);
  }
  return found as T;
}

function escapeHtml(value: unknown): string {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function interpolateColor(
  value: number,
  stops: Array<[number, [number, number, number]]>,
): [number, number, number] {
  if (value <= stops[0][0]) {
    return stops[0][1];
  }
  for (let index = 1; index < stops.length; index += 1) {
    const [upperValue, upperColor] = stops[index];
    if (value <= upperValue) {
      const [lowerValue, lowerColor] = stops[index - 1];
      const fraction = (value - lowerValue) / (upperValue - lowerValue);
      return lowerColor.map((channel, c) =>
        Math.round(channel + fraction * (upperColor[c] - channel)),
      ) as [number, number, number];
    }
  }
  return stops[stops.length - 1][1];
}

function hexToRgb(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.replace("#", ""), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function firstSymbolLayer(map: MapLibreMap): string | undefined {
  return map.getStyle().layers.find((layer) => layer.type === "symbol")?.id;
}

function setLayerVisibility(map: MapLibreMap, layerIds: string[], visible: boolean): void {
  for (const layerId of layerIds) {
    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
    }
  }
}

function showMapMessage(message: string): void {
  const panel = element<HTMLDivElement>("map-message");
  panel.textContent = message;
  panel.classList.remove("is-hidden");
  window.setTimeout(() => panel.classList.add("is-hidden"), 9000);
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Could not load ${url}: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Raster coloring
// ---------------------------------------------------------------------------

function registerRasterProtocol(): void {
  maplibregl.addProtocol("cog", cogProtocol);

  setColorFunction(DEM_ISLAND_URL, (pixel, color) => {
    const raw = Number(pixel[0]);
    if (!Number.isFinite(raw) || raw === NODATA) {
      color.set([0, 0, 0, 0]);
      return;
    }
    const feet = raw * VALUE_SCALE;
    const [red, green, blue] = interpolateColor(feet, ELEVATION_STOPS);
    color.set([red, green, blue, 255]);
  });

  setColorFunction(SUSCEPTIBILITY_URL, (pixel, color) => {
    const raw = Number(pixel[0]);
    const entry = SUSCEPTIBILITY_CLASSES.find((c) => c.value === raw);
    if (!entry) {
      color.set([0, 0, 0, 0]);
      return;
    }
    const [red, green, blue] = hexToRgb(entry.color);
    color.set([red, green, blue, 255]);
  });

  setColorFunction(LANDCOVER_URL, (pixel, color) => {
    const raw = Number(pixel[0]);
    const entry = LANDCOVER_CLASSES[raw];
    if (!entry) {
      color.set([0, 0, 0, 0]);
      return;
    }
    const [red, green, blue] = hexToRgb(entry.color);
    color.set([red, green, blue, 255]);
  });
}

// ---------------------------------------------------------------------------
// Basemap
// ---------------------------------------------------------------------------

const fallbackStyle: StyleSpecification = {
  version: 8,
  name: "Plain background",
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: {},
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#eef1ef" } },
  ],
};

async function loadBasemapStyle(): Promise<{ style: StyleSpecification; online: boolean }> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(BASEMAP_STYLE_URL, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`Basemap returned HTTP ${response.status}`);
    }
    return { style: (await response.json()) as StyleSpecification, online: true };
  } catch (error) {
    console.warn("Street basemap unavailable", error);
    return { style: fallbackStyle, online: false };
  } finally {
    window.clearTimeout(timeout);
  }
}

function layerIsVisible(layer: LayerSpecification): boolean {
  const visibility = "layout" in layer ? layer.layout?.visibility : undefined;
  return visibility !== "none";
}

function captureBasemapLayers(map: MapLibreMap): BasemapLayerGroups {
  const groups: BasemapLayerGroups = { base: [], labels: [] };
  for (const layer of map.getStyle().layers) {
    if (layer.type === "background" || !layerIsVisible(layer)) {
      continue;
    }
    (layer.type === "symbol" ? groups.labels : groups.base).push(layer.id);
  }
  return groups;
}

function addImageryLayers(map: MapLibreMap): void {
  const firstDrawnLayer = map.getStyle().layers.find((layer) => layer.type !== "background");
  map.addSource("satellite", {
    type: "raster",
    tiles: [SATELLITE_TILES],
    tileSize: 256,
    maxzoom: 20,
    attribution: SATELLITE_ATTRIBUTION,
  });
  map.addLayer(
    {
      id: "satellite-layer",
      type: "raster",
      source: "satellite",
      layout: { visibility: "none" },
      paint: { "raster-fade-duration": 0 },
    },
    firstDrawnLayer?.id,
  );
  map.addSource("usgs-topo", {
    type: "raster",
    tiles: [TOPO_TILES],
    tileSize: 256,
    maxzoom: 16,
    attribution: TOPO_ATTRIBUTION,
  });
  map.addLayer(
    {
      id: "topo-layer",
      type: "raster",
      source: "usgs-topo",
      layout: { visibility: "none" },
      paint: { "raster-fade-duration": 0 },
    },
    firstDrawnLayer?.id,
  );
}

function bindBasemapControls(map: MapLibreMap, groups: BasemapLayerGroups, online: boolean): void {
  const options = Array.from(
    element<HTMLDivElement>("basemap-options").querySelectorAll<HTMLInputElement>(
      'input[name="basemap"]',
    ),
  );
  const apply = (mode: BasemapMode): void => {
    setLayerVisibility(map, groups.base, mode === "streets");
    setLayerVisibility(map, groups.labels, mode === "streets" || mode === "satellite");
    setLayerVisibility(map, ["satellite-layer"], mode === "satellite");
    setLayerVisibility(map, ["topo-layer"], mode === "topo");
    for (const option of options) {
      option.closest(".basemap-option")?.classList.toggle("selected", option.checked);
    }
  };
  for (const option of options) {
    option.addEventListener("change", () => {
      if (option.checked) {
        apply(option.value as BasemapMode);
      }
    });
  }
  if (!online) {
    const streets = element<HTMLInputElement>("basemap-streets");
    streets.disabled = true;
    streets.closest(".basemap-option")?.classList.add("is-disabled");
  }
  apply((options.find((option) => option.checked)?.value as BasemapMode) ?? "streets");
}

// ---------------------------------------------------------------------------
// Terrain
// ---------------------------------------------------------------------------

function addTerrain(map: MapLibreMap): void {
  map.addSource("terrain-dem", {
    type: "raster-dem",
    tiles: [TERRAIN_TILES],
    tileSize: 512,
    maxzoom: 12,
    encoding: "terrarium",
    attribution: TERRAIN_ATTRIBUTION,
  });
  map.addSource("hillshade-dem", {
    type: "raster-dem",
    tiles: [TERRAIN_TILES],
    tileSize: 512,
    maxzoom: 12,
    encoding: "terrarium",
  });
  map.addLayer(
    {
      id: "hillshade-layer",
      type: "hillshade",
      source: "hillshade-dem",
      layout: { visibility: "none" },
      paint: {
        "hillshade-exaggeration": 0.35,
        "hillshade-shadow-color": "#2e3d38",
        "hillshade-highlight-color": "#fbf9ef",
        "hillshade-accent-color": "#6a7a6c",
      },
    },
    firstSymbolLayer(map),
  );
}

function bindTerrainControls(map: MapLibreMap): void {
  const terrainToggle = element<HTMLInputElement>("terrain-toggle");
  const hillshadeToggle = element<HTMLInputElement>("hillshade-toggle");
  const sceneToggle = element<HTMLButtonElement>("scene-toggle");
  const exaggerationInput = element<HTMLInputElement>("terrain-exaggeration");
  const exaggerationValue = element<HTMLOutputElement>("terrain-exaggeration-value");

  const applyTerrain = (): void => {
    const exaggeration = Number(exaggerationInput.value) || 1.4;
    if (terrainToggle.checked) {
      map.setTerrain({ source: "terrain-dem", exaggeration });
    } else {
      map.setTerrain(null);
    }
    exaggerationValue.value = `${exaggeration.toFixed(1)}×`;
    element("terrain-exaggeration-wrap").classList.toggle("is-hidden", !terrainToggle.checked);
  };

  terrainToggle.addEventListener("change", applyTerrain);
  exaggerationInput.addEventListener("input", applyTerrain);
  hillshadeToggle.addEventListener("change", () => {
    setLayerVisibility(map, ["hillshade-layer"], hillshadeToggle.checked);
  });

  const showSceneState = (tilted: boolean): void => {
    sceneToggle.textContent = tilted ? "Return to 2D view" : "Tilt to 3D view";
    sceneToggle.setAttribute("aria-pressed", String(tilted));
  };
  sceneToggle.addEventListener("click", () => {
    const shouldTilt = map.getPitch() <= 1;
    if (shouldTilt) {
      terrainToggle.checked = true;
      applyTerrain();
      map.easeTo({ pitch: 60, bearing: -15, duration: 900 });
    } else {
      map.easeTo({ pitch: 0, bearing: 0, duration: 700 });
    }
    showSceneState(shouldTilt);
  });
  map.on("pitchend", () => showSceneState(map.getPitch() > 1));
}

// ---------------------------------------------------------------------------
// Data layers
// ---------------------------------------------------------------------------

function addRasterOverlays(map: MapLibreMap): void {
  const before = firstSymbolLayer(map);
  const overlays: Array<{ source: string; layer: string; url: string; opacity: number }> = [
    { source: "elevation", layer: "elevation-layer", url: DEM_ISLAND_URL, opacity: 0.65 },
    { source: "landcover", layer: "landcover-layer", url: LANDCOVER_URL, opacity: 0.7 },
    {
      source: "susceptibility",
      layer: "susceptibility-layer",
      url: SUSCEPTIBILITY_URL,
      opacity: 0.7,
    },
  ];
  for (const overlay of overlays) {
    map.addSource(overlay.source, {
      type: "raster",
      url: `cog://${overlay.url}`,
      tileSize: 256,
    });
    map.addLayer(
      {
        id: overlay.layer,
        type: "raster",
        source: overlay.source,
        layout: { visibility: "none" },
        paint: {
          "raster-opacity": overlay.opacity,
          "raster-fade-duration": 0,
          "raster-resampling": "nearest",
        },
      },
      before,
    );
  }
}

function addVectorLayers(map: MapLibreMap): void {
  const before = firstSymbolLayer(map);
  const hidden = { visibility: "none" as const };

  // Soils sit under everything else.
  map.addSource("soils", { type: "geojson", data: "./data/vectors/soils_k.geojson" });
  map.addLayer(
    {
      id: "soils-fill",
      type: "fill",
      source: "soils",
      layout: hidden,
      paint: {
        "fill-color": [
          "case",
          ["!", ["to-boolean", ["get", "kfactor"]]],
          "#d7d7d3",
          [
            "interpolate",
            ["linear"],
            ["to-number", ["get", "kfactor"]],
            0.05,
            "#f3ede1",
            0.15,
            "#e3cf9d",
            0.25,
            "#cfa25c",
            0.35,
            "#a95f31",
            0.5,
            "#7c3116",
          ],
        ],
        "fill-opacity": 0.72,
        "fill-outline-color": "#9a8a70",
      },
    },
    before,
  );

  // Watershed framework.
  map.addSource("huc12", { type: "geojson", data: "./data/vectors/huc12.geojson" });
  map.addLayer(
    {
      id: "huc12-lines",
      type: "line",
      source: "huc12",
      layout: hidden,
      paint: {
        "line-color": "#6e7f7c",
        "line-width": 1,
        "line-dasharray": [3, 2],
        "line-opacity": 0.8,
      },
    },
    before,
  );

  map.addSource("watersheds", { type: "geojson", data: "./data/vectors/watersheds.geojson" });
  map.addLayer(
    {
      id: "watersheds-fill",
      type: "fill",
      source: "watersheds",
      paint: { "fill-color": "#1c4d52", "fill-opacity": 0.06 },
    },
    before,
  );
  map.addLayer(
    {
      id: "watersheds-outline",
      type: "line",
      source: "watersheds",
      paint: {
        "line-color": "#123c40",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.6, 13, 3.2],
        "line-opacity": 0.95,
      },
    },
    before,
  );

  // Rivers.
  map.addSource("rivers", { type: "geojson", data: "./data/vectors/rivers_island.geojson" });
  map.addLayer(
    {
      id: "rivers-lines",
      type: "line",
      source: "rivers",
      paint: {
        "line-color": "#2f7fae",
        "line-width": [
          "interpolate",
          ["linear"],
          ["zoom"],
          8,
          ["max", 0.4, ["*", 0.3, ["to-number", ["get", "streamorde"], 1]]],
          13,
          ["max", 1, ["*", 0.8, ["to-number", ["get", "streamorde"], 1]]],
        ],
        "line-opacity": 0.85,
      },
    },
    before,
  );

  map.addSource("streams", {
    type: "geojson",
    data: "./data/vectors/streams_watersheds.geojson",
  });
  map.addLayer(
    {
      id: "streams-lines",
      type: "line",
      source: "streams",
      layout: hidden,
      paint: {
        "line-color": "#5fa3c9",
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.5, 15, 1.6],
        "line-opacity": 0.8,
      },
    },
    before,
  );

  // Roads.
  map.addSource("roads-island", {
    type: "geojson",
    data: "./data/vectors/roads_island.geojson",
  });
  map.addLayer(
    {
      id: "roads-island-lines",
      type: "line",
      source: "roads-island",
      layout: hidden,
      paint: { "line-color": "#8a6d3b", "line-width": 1.6, "line-opacity": 0.9 },
    },
    before,
  );
  map.addSource("roads-watersheds", {
    type: "geojson",
    data: "./data/vectors/roads_watersheds.geojson",
  });
  map.addLayer(
    {
      id: "roads-watersheds-lines",
      type: "line",
      source: "roads-watersheds",
      layout: hidden,
      paint: {
        "line-color": "#a3762e",
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.7, 15, 2],
        "line-opacity": 0.9,
      },
    },
    before,
  );

  // Landslides: density at low zoom, individual points close in.
  map.addSource("landslides", {
    type: "geojson",
    data: "./data/vectors/landslides.geojson",
  });
  map.addLayer(
    {
      id: "landslides-heat",
      type: "heatmap",
      source: "landslides",
      maxzoom: 12.5,
      layout: hidden,
      paint: {
        "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 8, 4, 12, 14],
        "heatmap-intensity": 0.6,
        "heatmap-opacity": 0.75,
        "heatmap-color": [
          "interpolate",
          ["linear"],
          ["heatmap-density"],
          0,
          "rgba(143,43,30,0)",
          0.3,
          "rgba(214,158,70,0.55)",
          0.7,
          "rgba(189,100,48,0.8)",
          1,
          "rgba(143,43,30,0.95)",
        ],
      },
    },
    before,
  );
  map.addLayer(
    {
      id: "landslides-points",
      type: "circle",
      source: "landslides",
      minzoom: 12.5,
      layout: hidden,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 12.5, 2, 16, 4.5],
        "circle-color": "#8f2b1e",
        "circle-opacity": 0.8,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 0.5,
      },
    },
    before,
  );

  // Reservoirs and dams above the rest.
  map.addSource("reservoirs", { type: "geojson", data: "./data/vectors/reservoirs.geojson" });
  map.addLayer(
    {
      id: "reservoirs-fill",
      type: "fill",
      source: "reservoirs",
      paint: { "fill-color": "#2a7fb8", "fill-opacity": 0.55 },
    },
    before,
  );
  map.addLayer(
    {
      id: "reservoirs-outline",
      type: "line",
      source: "reservoirs",
      paint: { "line-color": "#155a86", "line-width": 1.4 },
    },
    before,
  );

  map.addSource("dams", { type: "geojson", data: "./data/vectors/dams.geojson" });
  map.addLayer(
    {
      id: "dams-points",
      type: "circle",
      source: "dams",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 4, 13, 7],
        "circle-color": "#123c40",
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1.6,
      },
    },
    before,
  );

  // Gauges on top of everything but labels.
  map.addSource("gauges-flow", {
    type: "geojson",
    data: "./data/vectors/gauges_streamflow.geojson",
  });
  map.addLayer(
    {
      id: "gauges-flow-points",
      type: "circle",
      source: "gauges-flow",
      layout: hidden,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 3.6, 13, 6.5],
        "circle-color": ["case", ["get", "active"], "#e0731d", "#cfae85"],
        "circle-opacity": ["case", ["get", "active"], 0.95, 0.7],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1.2,
      },
    },
    before,
  );
  map.addSource("gauges-rain", {
    type: "geojson",
    data: "./data/vectors/gauges_rain.geojson",
  });
  map.addLayer(
    {
      id: "gauges-rain-points",
      type: "circle",
      source: "gauges-rain",
      layout: hidden,
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 3.4, 13, 6],
        "circle-color": ["case", ["get", "active"], "#6db4e3", "#b6cfe0"],
        "circle-opacity": ["case", ["get", "active"], 0.95, 0.7],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1.2,
      },
    },
    before,
  );

  // Labels go above the basemap symbols.
  map.addLayer({
    id: "watersheds-labels",
    type: "symbol",
    source: "watersheds",
    layout: {
      "text-field": ["get", "name"],
      "text-font": ["Noto Sans Bold"],
      "text-size": 12,
      "text-transform": "uppercase",
      "text-letter-spacing": 0.06,
    },
    paint: {
      "text-color": "#0e3336",
      "text-halo-color": "rgba(255,255,255,0.92)",
      "text-halo-width": 1.6,
    },
  });
}

function addStormLayers(map: MapLibreMap): void {
  const before = firstSymbolLayer(map);
  const colorExpression: maplibregl.ExpressionSpecification = [
    "case",
    ["<", ["get", "cat"], 0],
    STORM_CATEGORIES[0].color,
    ["==", ["get", "cat"], 0],
    STORM_CATEGORIES[1].color,
    ["==", ["get", "cat"], 1],
    STORM_CATEGORIES[2].color,
    ["==", ["get", "cat"], 2],
    STORM_CATEGORIES[3].color,
    ["==", ["get", "cat"], 3],
    STORM_CATEGORIES[4].color,
    ["==", ["get", "cat"], 4],
    STORM_CATEGORIES[5].color,
    STORM_CATEGORIES[6].color,
  ];
  map.addSource("storms", { type: "geojson", data: "./data/vectors/storms.geojson" });
  map.addLayer(
    {
      id: "storms-lines",
      type: "line",
      source: "storms",
      layout: { visibility: "none", "line-cap": "round" },
      paint: {
        "line-color": colorExpression,
        "line-width": [
          "interpolate",
          ["linear"],
          ["zoom"],
          6,
          ["+", 1, ["*", 0.45, ["max", 0, ["get", "cat"]]]],
          10,
          ["+", 2, ["*", 0.8, ["max", 0, ["get", "cat"]]]],
        ],
        "line-opacity": 0.85,
      },
    },
    before,
  );
  map.addLayer({
    id: "storms-labels",
    type: "symbol",
    source: "storms",
    layout: {
      visibility: "none",
      "symbol-placement": "line",
      "text-field": ["concat", ["get", "name"], " ", ["to-string", ["get", "season"]]],
      "text-font": ["Noto Sans Regular"],
      "text-size": 11,
      "text-max-angle": 25,
      "symbol-spacing": 420,
    },
    paint: {
      "text-color": "#233240",
      "text-halo-color": "rgba(255,255,255,0.92)",
      "text-halo-width": 1.5,
    },
  });
}

// ---------------------------------------------------------------------------
// Storm controls
// ---------------------------------------------------------------------------

function bindStormControls(map: MapLibreMap, index: StormIndexEntry[]): void {
  const toggle = element<HTMLInputElement>("storms-toggle");
  const namesToggle = element<HTMLInputElement>("storm-names-toggle");
  const controls = element<HTMLDivElement>("storm-controls");
  const yearMin = element<HTMLInputElement>("storm-year-min");
  const yearMax = element<HTMLInputElement>("storm-year-max");
  const search = element<HTMLInputElement>("storm-search");
  const datalist = element<HTMLDataListElement>("storm-list");
  const clear = element<HTMLButtonElement>("storm-clear");
  const legend = element<HTMLDivElement>("storm-legend");

  legend.innerHTML = STORM_CATEGORIES.map(
    (category) =>
      `<span class="legend-item"><span class="legend-swatch" style="background:${category.color}"></span>${category.label}</span>`,
  ).join("");

  const labelFor = (entry: StormIndexEntry): string => `${entry.name} (${entry.season})`;
  for (const entry of index) {
    const option = document.createElement("option");
    option.value = labelFor(entry);
    const catText =
      entry.cat === null || entry.cat < 0
        ? "below hurricane strength near the island"
        : entry.cat === 0
          ? "tropical storm near the island"
          : `category ${entry.cat} near the island`;
    option.label = `${catText}, closest ${entry.min_km} km`;
    datalist.append(option);
  }

  let selectedSid: string | null = null;

  const applyFilter = (): void => {
    const low = Number(yearMin.value) || 1980;
    const high = Number(yearMax.value) || 2100;
    const clauses: unknown[] = [
      "all",
      [">=", ["get", "season"], low],
      ["<=", ["get", "season"], high],
    ];
    if (selectedSid) {
      clauses.push(["==", ["get", "sid"], selectedSid]);
    }
    const filter = clauses as maplibregl.FilterSpecification;
    map.setFilter("storms-lines", filter);
    map.setFilter("storms-labels", filter);
  };

  const applyVisibility = (): void => {
    setLayerVisibility(map, ["storms-lines"], toggle.checked);
    setLayerVisibility(map, ["storms-labels"], toggle.checked && namesToggle.checked);
    controls.classList.toggle("is-hidden", !toggle.checked);
  };

  toggle.addEventListener("change", applyVisibility);
  namesToggle.addEventListener("change", applyVisibility);
  yearMin.addEventListener("change", applyFilter);
  yearMax.addEventListener("change", applyFilter);

  search.addEventListener("change", () => {
    const text = search.value.trim().toLowerCase();
    if (!text) {
      selectedSid = null;
      applyFilter();
      return;
    }
    const exact = index.find((entry) => labelFor(entry).toLowerCase() === text);
    const partial =
      exact ??
      index.find((entry) => entry.name.toLowerCase() === text) ??
      index.find((entry) => labelFor(entry).toLowerCase().includes(text));
    if (partial) {
      selectedSid = partial.sid;
      search.value = labelFor(partial);
      if (!toggle.checked) {
        toggle.checked = true;
        applyVisibility();
      }
      namesToggle.checked = true;
      applyVisibility();
      applyFilter();
    }
  });
  clear.addEventListener("click", () => {
    selectedSid = null;
    search.value = "";
    applyFilter();
  });

  applyFilter();
  applyVisibility();
}

// ---------------------------------------------------------------------------
// Layer switch lists
// ---------------------------------------------------------------------------

function renderLayerGroup(
  map: MapLibreMap,
  containerId: string,
  definitions: LayerDefinition[],
): void {
  const container = element<HTMLDivElement>(containerId);
  container.replaceChildren();
  for (const definition of definitions) {
    const row = document.createElement("div");
    row.className = "layer-row";
    const inputId = `layer-${definition.id}`;
    row.innerHTML = `
      <label class="switch-label" for="${inputId}">
        <span class="layer-symbol" style="${definition.symbolCss}"></span>
        <span><strong>${definition.label}</strong><small>${definition.note}</small></span>
      </label>
      <input id="${inputId}" class="switch" type="checkbox" ${definition.checked ? "checked" : ""}>
    `;
    const checkbox = row.querySelector<HTMLInputElement>("input");
    checkbox?.addEventListener("change", () => {
      setLayerVisibility(map, definition.layers, checkbox.checked);
      definition.onToggle?.(checkbox.checked);
    });
    setLayerVisibility(map, definition.layers, definition.checked);
    container.append(row);
  }
}

function updateSedimentLegend(states: Record<string, boolean>): void {
  const legend = element<HTMLDivElement>("sediment-legend");
  const blocks: string[] = [];
  if (states.susceptibility) {
    blocks.push(
      `<span class="legend-item"><strong>Susceptibility</strong></span>` +
        SUSCEPTIBILITY_CLASSES.map(
          (entry) =>
            `<span class="legend-item"><span class="legend-swatch" style="background:${entry.color}"></span>${entry.label}</span>`,
        ).join(""),
    );
  }
  if (states.landcover) {
    const groups: Array<[string, string]> = [
      ["Developed", "#c06657"],
      ["Farm and pasture", "#cbb363"],
      ["Grass and shrub", "#e5d99c"],
      ["Forest", "#3f7550"],
      ["Wetland", "#82a58f"],
      ["Barren and shore", "#c9c1b1"],
      ["Water", "#5f8fb8"],
    ];
    blocks.push(
      `<span class="legend-item"><strong>Land cover</strong></span>` +
        groups
          .map(
            ([label, color]) =>
              `<span class="legend-item"><span class="legend-swatch" style="background:${color}"></span>${label}</span>`,
          )
          .join(""),
    );
  }
  if (states.soils) {
    blocks.push(
      `<span class="legend-item"><strong>Soil K factor</strong></span>` +
        `<span class="legend-item"><span class="legend-swatch" style="background:#f3ede1"></span>0.05</span>` +
        `<span class="legend-item"><span class="legend-swatch" style="background:#cfa25c"></span>0.25</span>` +
        `<span class="legend-item"><span class="legend-swatch" style="background:#7c3116"></span>0.5</span>`,
    );
  }
  legend.innerHTML = blocks.join("<br/>");
}

// ---------------------------------------------------------------------------
// Popups
// ---------------------------------------------------------------------------

function popup(map: MapLibreMap, event: MapLayerMouseEvent, html: string): void {
  new maplibregl.Popup({ closeButton: true, maxWidth: "300px" })
    .setLngLat(event.lngLat)
    .setHTML(`<div class="feature-popup">${html}</div>`)
    .addTo(map);
}

function gaugeHtml(properties: Record<string, unknown>, kind: string): string {
  const active = properties.active === true || properties.active === "true";
  const badge = active
    ? '<span class="status-pill-active">active</span>'
    : '<span class="status-pill-inactive">discontinued</span>';
  const drain = properties.drain_area_va
    ? `<div class="popup-row"><span>Drainage area</span><span>${escapeHtml(properties.drain_area_va)} sq mi</span></div>`
    : "";
  return `
    <div class="popup-title">${escapeHtml(properties.station)}${badge}</div>
    <div class="popup-sub">${escapeHtml(kind)} · ${escapeHtml(properties.network)}</div>
    <div class="popup-row"><span>Station</span><span>${escapeHtml(properties.site_no)}</span></div>
    <div class="popup-row"><span>Record</span><span>${escapeHtml(properties.begin)} to ${escapeHtml(properties.end)}</span></div>
    ${drain}
    <div class="popup-row"><a href="${escapeHtml(properties.url)}" target="_blank" rel="noopener noreferrer">Open the station page</a></div>
  `;
}

function bindPopups(map: MapLibreMap, openReservoirCard: (key: string) => void): void {
  const hoverable = [
    "gauges-flow-points",
    "gauges-rain-points",
    "rivers-lines",
    "streams-lines",
    "soils-fill",
    "roads-watersheds-lines",
    "watersheds-fill",
    "reservoirs-fill",
    "dams-points",
  ];
  for (const layerId of hoverable) {
    map.on("mouseenter", layerId, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", layerId, () => {
      map.getCanvas().style.cursor = "";
    });
  }

  map.on("click", "gauges-flow-points", (event) => {
    const properties = event.features?.[0]?.properties;
    if (properties) {
      popup(map, event, gaugeHtml(properties, "Streamflow gauge"));
    }
  });
  map.on("click", "gauges-rain-points", (event) => {
    const properties = event.features?.[0]?.properties;
    if (properties) {
      popup(map, event, gaugeHtml(properties, "Rain gauge"));
    }
  });
  map.on("click", "rivers-lines", (event) => {
    const properties = event.features?.[0]?.properties;
    if (!properties) {
      return;
    }
    const drainage = properties.totdasqkm
      ? `<div class="popup-row"><span>Drainage</span><span>${(Number(properties.totdasqkm) * 0.3861).toFixed(1)} sq mi</span></div>`
      : "";
    popup(
      map,
      event,
      `<div class="popup-title">${escapeHtml(properties.gnis_name || "Unnamed stream")}</div>
       <div class="popup-row"><span>Stream order</span><span>${escapeHtml(properties.streamorde ?? "n/a")}</span></div>
       ${drainage}`,
    );
  });
  map.on("click", "streams-lines", (event) => {
    const properties = event.features?.[0]?.properties;
    if (!properties) {
      return;
    }
    const slope = properties.slope
      ? `<div class="popup-row"><span>Slope</span><span>${(Number(properties.slope) * 100).toFixed(2)}%</span></div>`
      : "";
    popup(
      map,
      event,
      `<div class="popup-title">${escapeHtml(properties.gnis_name || "Unnamed stream")}</div>
       <div class="popup-row"><span>Stream order</span><span>${escapeHtml(properties.streamorde ?? "n/a")}</span></div>
       ${slope}`,
    );
  });
  map.on("click", "soils-fill", (event) => {
    const properties = event.features?.[0]?.properties;
    if (!properties) {
      return;
    }
    popup(
      map,
      event,
      `<div class="popup-title">${escapeHtml(properties.muname ?? "Soil map unit")}</div>
       <div class="popup-row"><span>Map unit</span><span>${escapeHtml(properties.musym ?? "")}</span></div>
       <div class="popup-row"><span>K factor</span><span>${escapeHtml(properties.kfactor ?? "not rated")}</span></div>`,
    );
  });
  map.on("click", "roads-watersheds-lines", (event) => {
    const properties = event.features?.[0]?.properties;
    if (!properties) {
      return;
    }
    popup(
      map,
      event,
      `<div class="popup-title">${escapeHtml(properties.name || "Unnamed road")}</div>`,
    );
  });

  const reservoirClick = (event: MapLayerMouseEvent): void => {
    const key = event.features?.[0]?.properties?.key as string | undefined;
    if (key) {
      openReservoirCard(key);
    }
  };
  map.on("click", "watersheds-fill", reservoirClick);
  map.on("click", "reservoirs-fill", reservoirClick);
  map.on("click", "dams-points", reservoirClick);
}

// ---------------------------------------------------------------------------
// Reservoir cards
// ---------------------------------------------------------------------------

function capacityChart(facts: ReservoirFacts): string {
  const points: Array<{ year: number; acft: number }> = [
    { year: facts.built, acft: facts.original_acft },
    ...facts.surveys.map((survey) => ({ year: survey.year, acft: survey.acft })),
  ];
  const width = 280;
  const height = 90;
  const margin = { top: 8, right: 10, bottom: 20, left: 44 };
  const years = points.map((point) => point.year);
  const [minYear, maxYear] = [Math.min(...years), Math.max(...years)];
  const maxCap = Math.max(...points.map((point) => point.acft));
  const xOf = (year: number): number =>
    margin.left +
    ((year - minYear) / Math.max(1, maxYear - minYear)) * (width - margin.left - margin.right);
  const yOf = (capacity: number): number =>
    margin.top + (1 - capacity / maxCap) * (height - margin.top - margin.bottom);
  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${xOf(point.year).toFixed(1)},${yOf(point.acft).toFixed(1)}`)
    .join("");
  const dots = points
    .map(
      (point) =>
        `<circle cx="${xOf(point.year).toFixed(1)}" cy="${yOf(point.acft).toFixed(1)}" r="3" fill="#1c4d52"/>` +
        `<text x="${xOf(point.year).toFixed(1)}" y="${height - 4}" text-anchor="middle" font-size="9" fill="#51625f">${point.year}</text>`,
    )
    .join("");
  return `
    <svg class="capacity-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Storage capacity over time">
      <text x="4" y="${margin.top + 6}" font-size="9" fill="#51625f">${Math.round(maxCap).toLocaleString()} ac-ft</text>
      <line x1="${margin.left}" y1="${yOf(0)}" x2="${width - margin.right}" y2="${yOf(0)}" stroke="#d9e1e0"/>
      <path d="${path}" fill="none" stroke="#1c4d52" stroke-width="2"/>
      ${dots}
    </svg>
  `;
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

async function initialize(): Promise<void> {
  registerRasterProtocol();
  element("loading-message").textContent = "Connecting to the basemap";
  const basemap = await loadBasemapStyle();

  const map = new maplibregl.Map({
    container: "map",
    style: basemap.style,
    center: [-66.4, 18.18],
    zoom: 8.6,
    minZoom: 6.5,
    maxZoom: 18.5,
    maxPitch: 75,
    attributionControl: false,
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  map.addControl(new maplibregl.FullscreenControl(), "top-right");
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "imperial" }), "bottom-left");
  map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");

  map.on("error", (event) => {
    console.warn("Map resource error", event.error?.message ?? event);
  });

  const [stormIndex, reservoirInfo, watershedData] = await Promise.all([
    fetchJson<StormIndexEntry[]>("./data/vectors/storm_index.json").catch(() => []),
    fetchJson<Record<string, ReservoirFacts>>("./data/vectors/reservoir_info.json").catch(
      () => ({}) as Record<string, ReservoirFacts>,
    ),
    fetchJson<GeoJSON.FeatureCollection>("./data/vectors/watersheds.geojson").catch(() => null),
  ]);

  // Bounds and areas per reservoir from the watershed polygons.
  const watershedBounds = new Map<string, [[number, number], [number, number]]>();
  const watershedAreas = new Map<string, number>();
  if (watershedData) {
    for (const feature of watershedData.features) {
      const key = (feature.properties as Record<string, unknown>)?.key as string;
      const area = (feature.properties as Record<string, unknown>)?.area_sqmi as number;
      let west = 180;
      let south = 90;
      let east = -180;
      let north = -90;
      const scan = (coordinates: unknown): void => {
        if (Array.isArray(coordinates) && typeof coordinates[0] === "number") {
          const [lng, lat] = coordinates as [number, number];
          west = Math.min(west, lng);
          east = Math.max(east, lng);
          south = Math.min(south, lat);
          north = Math.max(north, lat);
        } else if (Array.isArray(coordinates)) {
          for (const child of coordinates) {
            scan(child);
          }
        }
      };
      scan((feature.geometry as GeoJSON.Polygon).coordinates);
      watershedBounds.set(key, [
        [west, south],
        [east, north],
      ]);
      watershedAreas.set(key, area);
    }
  }

  // Reservoir card behavior.
  const card = element<HTMLElement>("reservoir-card");
  const openReservoirCard = (key: string): void => {
    const meta = RESERVOIRS.find((entry) => entry.key === key);
    const facts = reservoirInfo[key];
    if (!meta) {
      return;
    }
    element("reservoir-card-kicker").textContent = `${meta.river} · ${meta.municipality}`;
    element("reservoir-card-title").textContent = meta.name;
    const area = watershedAreas.get(key);
    const latest = facts?.surveys[facts.surveys.length - 1];
    const body = element<HTMLDivElement>("reservoir-card-body");
    body.innerHTML = facts
      ? `
        <dl>
          <div><dt>Built</dt><dd>${facts.built}</dd></div>
          <div><dt>Drainage area</dt><dd>${area ? `${area.toFixed(1)} sq mi` : "n/a"}</dd></div>
          <div><dt>Original storage</dt><dd>${facts.original_acft.toLocaleString()} ac-ft</dd></div>
          <div><dt>Storage in ${facts.latest_year}</dt><dd>${latest?.acft.toLocaleString()} ac-ft</dd></div>
          <div><dt>Capacity lost</dt><dd>${facts.pct_lost}%</dd></div>
        </dl>
        ${capacityChart(facts)}
        <p class="card-note">${escapeHtml(facts.note)}</p>
        <p><a class="card-link" href="${escapeHtml(facts.report_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(facts.report)}</a></p>
        <p class="card-note">Drainage area shown was delineated from the 3DEP terrain model for this map.</p>
      `
      : `<p class="card-note">No published survey figures loaded for this reservoir.</p>`;
    card.classList.remove("is-hidden");
    const bounds = watershedBounds.get(key);
    if (bounds) {
      map.fitBounds(bounds, { padding: 70, duration: 900, pitch: 0, bearing: 0 });
    }
  };
  element("reservoir-card-close").addEventListener("click", () =>
    card.classList.add("is-hidden"),
  );

  // Reservoir picker in the header.
  const picker = element<HTMLSelectElement>("reservoir-picker");
  for (const entry of RESERVOIRS) {
    const option = document.createElement("option");
    option.value = entry.key;
    option.textContent = entry.name;
    picker.append(option);
  }
  picker.addEventListener("change", () => {
    if (picker.value) {
      openReservoirCard(picker.value);
    } else {
      card.classList.add("is-hidden");
      map.fitBounds(ISLAND_BOUNDS, { padding: 30, duration: 900, pitch: 0, bearing: 0 });
    }
  });

  // Cross section tool.
  const crossSection = new CrossSectionTool(map, DEM_ISLAND_URL, {
    button: element<HTMLButtonElement>("crosssection-button"),
    hint: element<HTMLElement>("crosssection-hint"),
    panel: element<HTMLElement>("profile-panel"),
    stats: element<HTMLElement>("profile-stats"),
    chart: element<HTMLElement>("profile-chart"),
    download: element<HTMLButtonElement>("profile-download"),
    close: element<HTMLButtonElement>("profile-close"),
  });
  const extents: RasterExtent[] = [];
  for (const [key, bounds] of watershedBounds) {
    extents.push({
      url: `./data/rasters/dem_${key}_10m.tif`,
      bounds: [
        bounds[0][0] + 0.002,
        bounds[0][1] + 0.002,
        bounds[1][0] - 0.002,
        bounds[1][1] - 0.002,
      ],
    });
  }
  crossSection.setRasters(extents);

  map.once("load", () => {
    try {
      element("loading-message").textContent = "Adding data layers";
      const basemapGroups = captureBasemapLayers(map);
      addImageryLayers(map);
      addTerrain(map);
      addRasterOverlays(map);
      addVectorLayers(map);
      addStormLayers(map);
      crossSection.ensureLayers();

      const sedimentStates: Record<string, boolean> = {};
      const sedimentToggle = (name: string) => (visible: boolean) => {
        sedimentStates[name] = visible;
        updateSedimentLegend(sedimentStates);
        if (name === "susceptibility") {
          element("susceptibility-opacity-wrap").classList.toggle("is-hidden", !visible);
        }
        if (name === "landcover") {
          element("landcover-opacity-wrap").classList.toggle("is-hidden", !visible);
        }
      };

      renderLayerGroup(map, "water-context-layers", [
        {
          id: "watersheds",
          label: "Study watersheds",
          note: "Drainage areas above each dam",
          symbolCss: "background:#1c4d5218;border:2px solid #123c40",
          layers: ["watersheds-fill", "watersheds-outline", "watersheds-labels"],
          checked: true,
        },
        {
          id: "reservoirs",
          label: "Reservoirs and dams",
          note: "Lake extent and outlet point",
          symbolCss: "background:#2a7fb888;border:2px solid #155a86",
          layers: ["reservoirs-fill", "reservoirs-outline", "dams-points"],
          checked: true,
        },
        {
          id: "huc12",
          label: "HUC12 boundaries",
          note: "Federal subwatershed framework",
          symbolCss: "background:transparent;border:2px dashed #6e7f7c",
          layers: ["huc12-lines"],
          checked: false,
        },
      ]);

      renderLayerGroup(map, "water-layers", [
        {
          id: "rivers",
          label: "Rivers",
          note: "Named rivers island wide",
          symbolCss: "background:#2f7fae",
          layers: ["rivers-lines"],
          checked: false,
        },
        {
          id: "streams",
          label: "All streams in watersheds",
          note: "Every mapped channel",
          symbolCss: "background:#5fa3c9",
          layers: ["streams-lines"],
          checked: false,
        },
        {
          id: "gauges-flow",
          label: "Streamflow gauges",
          note: "USGS, orange when active",
          symbolCss: "background:#e0731d;border-radius:50%",
          layers: ["gauges-flow-points"],
          checked: false,
        },
        {
          id: "gauges-rain",
          label: "Rain gauges",
          note: "USGS and NOAA GHCN, light blue when active",
          symbolCss: "background:#6db4e3;border-radius:50%",
          layers: ["gauges-rain-points"],
          checked: false,
        },
      ]);

      renderLayerGroup(map, "sediment-layers", [
        {
          id: "landslides",
          label: "Landslides after Maria",
          note: "About 71,000 mapped slope failures",
          symbolCss: "background:#8f2b1e;border-radius:50%",
          layers: ["landslides-heat", "landslides-points"],
          checked: false,
        },
        {
          id: "susceptibility",
          label: "Landslide susceptibility",
          note: "USGS rainfall triggered classes",
          symbolCss: "background:linear-gradient(90deg,#f2ecd4,#8f2b1e)",
          layers: ["susceptibility-layer"],
          checked: false,
          onToggle: sedimentToggle("susceptibility"),
        },
        {
          id: "landcover",
          label: "Land cover",
          note: "NOAA C-CAP 2010, 30 m",
          symbolCss: "background:linear-gradient(90deg,#3f7550,#cbb363,#c06657)",
          layers: ["landcover-layer"],
          checked: false,
          onToggle: sedimentToggle("landcover"),
        },
        {
          id: "soils",
          label: "Soil erodibility",
          note: "SSURGO K factor in the watersheds",
          symbolCss: "background:linear-gradient(90deg,#f3ede1,#7c3116)",
          layers: ["soils-fill"],
          checked: false,
          onToggle: sedimentToggle("soils"),
        },
      ]);

      renderLayerGroup(map, "access-layers", [
        {
          id: "roads-island",
          label: "Primary and secondary roads",
          note: "Island wide context",
          symbolCss: "background:#8a6d3b",
          layers: ["roads-island-lines"],
          checked: false,
        },
        {
          id: "roads-watersheds",
          label: "All roads in watersheds",
          note: "Field access planning",
          symbolCss: "background:#a3762e",
          layers: ["roads-watersheds-lines"],
          checked: false,
        },
      ]);

      bindBasemapControls(map, basemapGroups, basemap.online);
      bindTerrainControls(map);
      bindStormControls(map, stormIndex);
      bindPopups(map, openReservoirCard);

      const elevationToggle = element<HTMLInputElement>("elevation-toggle");
      const elevationOpacity = element<HTMLInputElement>("elevation-opacity");
      // Color ramp legend matching the elevation color function.
      const rampSpan = ELEVATION_STOPS[ELEVATION_STOPS.length - 1][0];
      element<HTMLDivElement>("elevation-ramp-bar").style.background =
        `linear-gradient(90deg, ${ELEVATION_STOPS.map(
          ([feet, [red, green, blue]]) =>
            `rgb(${red},${green},${blue}) ${((feet / rampSpan) * 100).toFixed(1)}%`,
        ).join(", ")})`;
      elevationToggle.addEventListener("change", () => {
        setLayerVisibility(map, ["elevation-layer"], elevationToggle.checked);
        element("elevation-opacity-wrap").classList.toggle(
          "is-hidden",
          !elevationToggle.checked,
        );
        element("elevation-legend").classList.toggle("is-hidden", !elevationToggle.checked);
      });
      elevationOpacity.addEventListener("input", () => {
        map.setPaintProperty(
          "elevation-layer",
          "raster-opacity",
          Number(elevationOpacity.value) / 100,
        );
        element<HTMLOutputElement>("elevation-opacity-value").value =
          `${elevationOpacity.value}%`;
      });
      for (const [inputId, layerId] of [
        ["susceptibility-opacity", "susceptibility-layer"],
        ["landcover-opacity", "landcover-layer"],
      ] as const) {
        const input = element<HTMLInputElement>(inputId);
        input.addEventListener("input", () => {
          map.setPaintProperty(layerId, "raster-opacity", Number(input.value) / 100);
          element<HTMLOutputElement>(`${inputId}-value`).value = `${input.value}%`;
        });
      }

      element("about-button").addEventListener("click", () =>
        element<HTMLDialogElement>("about-dialog").showModal(),
      );
      element("reset-view").addEventListener("click", () => {
        picker.value = "";
        card.classList.add("is-hidden");
        map.fitBounds(ISLAND_BOUNDS, { padding: 30, duration: 850, pitch: 0, bearing: 0 });
      });

      const sidePanel = element<HTMLElement>("side-panel");
      const panelToggle = element<HTMLButtonElement>("panel-toggle");
      panelToggle.addEventListener("click", () => {
        const open = !sidePanel.classList.contains("is-open");
        sidePanel.classList.toggle("is-open", open);
        panelToggle.setAttribute("aria-expanded", String(open));
      });
      map.on("click", () => {
        if (window.innerWidth <= 840) {
          sidePanel.classList.remove("is-open");
        }
      });

      map.fitBounds(ISLAND_BOUNDS, { padding: 30, duration: 0 });
      element("loading-panel").classList.add("is-hidden");
      if (!basemap.online) {
        showMapMessage(
          "The street basemap could not be loaded. Satellite imagery and the data layers are still available.",
        );
      }
    } catch (error) {
      console.error("Initialization failed", error);
      element("loading-panel").classList.add("is-hidden");
      showMapMessage(`The map started but a layer failed to load. ${String(error)}`);
    }
  });
}

void initialize();
