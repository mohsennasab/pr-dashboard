import type { GeoJSONSource, Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import { locationValues } from "@geomatico/maplibre-cog-protocol";

// Elevation rasters store tenths of feet as uint16 with 65535 as nodata.
const NODATA = 65535;
const VALUE_SCALE = 0.1;
const MILES_PER_KM = 0.621371;

export type RasterExtent = {
  url: string;
  bounds: [number, number, number, number];
};

type SamplePoint = {
  distanceMiles: number;
  lng: number;
  lat: number;
  elevationFeet: number | null;
};

type CrossSectionElements = {
  button: HTMLButtonElement;
  hint: HTMLElement;
  panel: HTMLElement;
  stats: HTMLElement;
  chart: HTMLElement;
  download: HTMLButtonElement;
  close: HTMLButtonElement;
};

const SOURCE_ID = "crosssection-line";
const LAYER_LINE = "crosssection-line-layer";
const LAYER_POINTS = "crosssection-point-layer";

function haversineKm(a: [number, number], b: [number, number]): number {
  const radius = 6371;
  const dLat = ((b[1] - a[1]) * Math.PI) / 180;
  const dLon = ((b[0] - a[0]) * Math.PI) / 180;
  const lat1 = (a[1] * Math.PI) / 180;
  const lat2 = (b[1] * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * radius * Math.asin(Math.sqrt(Math.min(1, h)));
}

function decode(raw: number | undefined): number | null {
  if (raw === undefined || !Number.isFinite(raw) || raw === NODATA) {
    return null;
  }
  return raw * VALUE_SCALE;
}

function inBounds(lng: number, lat: number, bounds: [number, number, number, number]): boolean {
  return lng >= bounds[0] && lat >= bounds[1] && lng <= bounds[2] && lat <= bounds[3];
}

export class CrossSectionTool {
  private map: MapLibreMap;
  private rasters: RasterExtent[] = [];
  private fallbackUrl: string;
  private elements: CrossSectionElements;
  private active = false;
  private vertices: [number, number][] = [];
  private cursor: [number, number] | null = null;
  private samples: SamplePoint[] = [];
  private clickHandler: (event: MapMouseEvent) => void;
  private moveHandler: (event: MapMouseEvent) => void;
  private dblclickHandler: (event: MapMouseEvent) => void;
  private keyHandler: (event: KeyboardEvent) => void;

  constructor(map: MapLibreMap, fallbackUrl: string, elements: CrossSectionElements) {
    this.map = map;
    this.fallbackUrl = fallbackUrl;
    this.elements = elements;
    this.clickHandler = (event) => this.addVertex(event);
    this.moveHandler = (event) => {
      if (!this.active || this.vertices.length === 0) {
        return;
      }
      this.cursor = [event.lngLat.lng, event.lngLat.lat];
      this.renderLine();
    };
    this.dblclickHandler = (event) => {
      event.preventDefault();
      void this.finish();
    };
    this.keyHandler = (event) => {
      if (!this.active) {
        return;
      }
      if (event.key === "Escape") {
        this.cancel();
      } else if (event.key === "Enter") {
        void this.finish();
      }
    };

    elements.button.addEventListener("click", () => {
      if (this.active) {
        this.cancel();
      } else {
        this.start();
      }
    });
    elements.close.addEventListener("click", () => this.clearAll());
    elements.download.addEventListener("click", () => this.downloadCsv());
  }

  setRasters(rasters: RasterExtent[]): void {
    this.rasters = rasters;
  }

  ensureLayers(): void {
    if (this.map.getSource(SOURCE_ID)) {
      return;
    }
    this.map.addSource(SOURCE_ID, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    this.map.addLayer({
      id: LAYER_LINE,
      type: "line",
      source: SOURCE_ID,
      filter: ["==", ["geometry-type"], "LineString"],
      paint: {
        "line-color": "#d8452c",
        "line-width": 2.5,
        "line-dasharray": [1.5, 1.2],
      },
    });
    this.map.addLayer({
      id: LAYER_POINTS,
      type: "circle",
      source: SOURCE_ID,
      filter: ["==", ["geometry-type"], "Point"],
      paint: {
        "circle-radius": 4.5,
        "circle-color": "#ffffff",
        "circle-stroke-color": "#d8452c",
        "circle-stroke-width": 2,
      },
    });
  }

  private start(): void {
    this.ensureLayers();
    this.active = true;
    this.vertices = [];
    this.cursor = null;
    this.elements.button.textContent = "Cancel cross section";
    this.elements.button.setAttribute("aria-pressed", "true");
    this.elements.hint.classList.remove("is-hidden");
    this.elements.panel.classList.add("is-hidden");
    this.map.getCanvas().style.cursor = "crosshair";
    this.map.doubleClickZoom.disable();
    this.map.on("click", this.clickHandler);
    this.map.on("mousemove", this.moveHandler);
    this.map.on("dblclick", this.dblclickHandler);
    window.addEventListener("keydown", this.keyHandler);
  }

  private stopDrawing(): void {
    this.active = false;
    this.elements.button.textContent = "Draw a cross section";
    this.elements.button.setAttribute("aria-pressed", "false");
    this.elements.hint.classList.add("is-hidden");
    this.map.getCanvas().style.cursor = "";
    this.map.doubleClickZoom.enable();
    this.map.off("click", this.clickHandler);
    this.map.off("mousemove", this.moveHandler);
    this.map.off("dblclick", this.dblclickHandler);
    window.removeEventListener("keydown", this.keyHandler);
  }

  private cancel(): void {
    this.stopDrawing();
    this.vertices = [];
    this.cursor = null;
    this.renderLine();
  }

  private clearAll(): void {
    this.vertices = [];
    this.cursor = null;
    this.samples = [];
    this.renderLine();
    this.elements.panel.classList.add("is-hidden");
  }

  private addVertex(event: MapMouseEvent): void {
    this.vertices.push([event.lngLat.lng, event.lngLat.lat]);
    this.renderLine();
  }

  private renderLine(): void {
    const source = this.map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
    if (!source) {
      return;
    }
    const line =
      this.vertices.length > 0
        ? [...this.vertices, ...(this.active && this.cursor ? [this.cursor] : [])]
        : [];
    const features: GeoJSON.Feature[] = this.vertices.map((vertex) => ({
      type: "Feature",
      properties: {},
      geometry: { type: "Point", coordinates: vertex },
    }));
    if (line.length >= 2) {
      features.push({
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: line },
      });
    }
    source.setData({ type: "FeatureCollection", features });
  }

  private async finish(): Promise<void> {
    if (!this.active) {
      return;
    }
    if (this.vertices.length < 2) {
      this.cancel();
      return;
    }
    this.stopDrawing();
    this.cursor = null;
    this.renderLine();
    this.elements.stats.textContent = "Reading elevations from the terrain model";
    this.elements.chart.innerHTML = "";
    this.elements.panel.classList.remove("is-hidden");

    const line = this.vertices;
    const legsKm: number[] = [];
    let totalKm = 0;
    for (let index = 1; index < line.length; index += 1) {
      const leg = haversineKm(line[index - 1], line[index]);
      legsKm.push(leg);
      totalKm += leg;
    }
    const sampleCount = Math.min(400, Math.max(80, Math.round((totalKm * 1000) / 20)));
    const targets: { lng: number; lat: number; distanceKm: number }[] = [];
    for (let step = 0; step <= sampleCount; step += 1) {
      const distance = (totalKm * step) / sampleCount;
      let remaining = distance;
      let position: [number, number] = line[0];
      for (let leg = 0; leg < legsKm.length; leg += 1) {
        if (remaining <= legsKm[leg] || leg === legsKm.length - 1) {
          const fraction = legsKm[leg] === 0 ? 0 : Math.min(1, remaining / legsKm[leg]);
          position = [
            line[leg][0] + (line[leg + 1][0] - line[leg][0]) * fraction,
            line[leg][1] + (line[leg + 1][1] - line[leg][1]) * fraction,
          ];
          break;
        }
        remaining -= legsKm[leg];
      }
      targets.push({ lng: position[0], lat: position[1], distanceKm: distance });
    }

    const samples: SamplePoint[] = [];
    const chunkSize = 24;
    for (let start = 0; start < targets.length; start += chunkSize) {
      const chunk = targets.slice(start, start + chunkSize);
      const values = await Promise.all(
        chunk.map(async (target) => {
          const raster =
            this.rasters.find((candidate) =>
              inBounds(target.lng, target.lat, candidate.bounds),
            )?.url ?? this.fallbackUrl;
          try {
            const result = await locationValues(raster, {
              latitude: target.lat,
              longitude: target.lng,
            });
            return decode(result?.[0]);
          } catch (error) {
            console.warn("Elevation sample failed", error);
            return null;
          }
        }),
      );
      chunk.forEach((target, index) => {
        samples.push({
          distanceMiles: target.distanceKm * MILES_PER_KM,
          lng: target.lng,
          lat: target.lat,
          elevationFeet: values[index],
        });
      });
    }

    this.samples = samples;
    this.renderProfile(totalKm * MILES_PER_KM);
  }

  private renderProfile(totalMiles: number): void {
    const valid = this.samples.filter((sample) => sample.elevationFeet !== null);
    if (valid.length < 2) {
      this.elements.stats.textContent =
        "No elevation data along this line. Draw the line over land in Puerto Rico.";
      return;
    }
    const elevations = valid.map((sample) => sample.elevationFeet as number);
    const minElev = Math.min(...elevations);
    const maxElev = Math.max(...elevations);
    this.elements.stats.textContent =
      `Length ${totalMiles.toFixed(2)} miles. ` +
      `Elevation ${Math.round(minElev).toLocaleString()} to ` +
      `${Math.round(maxElev).toLocaleString()} feet. ` +
      `Relief ${Math.round(maxElev - minElev).toLocaleString()} feet.`;

    const width = 900;
    const height = 170;
    const margin = { top: 10, right: 12, bottom: 24, left: 52 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const elevPad = Math.max(10, (maxElev - minElev) * 0.08);
    const yMin = Math.max(0, minElev - elevPad);
    const yMax = maxElev + elevPad;

    const xOf = (miles: number): number =>
      margin.left + (miles / Math.max(totalMiles, 0.0001)) * plotWidth;
    const yOf = (feet: number): number =>
      margin.top + plotHeight - ((feet - yMin) / (yMax - yMin)) * plotHeight;

    let path = "";
    let area = "";
    for (const sample of this.samples) {
      if (sample.elevationFeet === null) {
        continue;
      }
      const x = xOf(sample.distanceMiles).toFixed(1);
      const y = yOf(sample.elevationFeet).toFixed(1);
      path += path === "" ? `M${x},${y}` : `L${x},${y}`;
    }
    const first = this.samples.find((sample) => sample.elevationFeet !== null);
    const last = [...this.samples].reverse().find((sample) => sample.elevationFeet !== null);
    if (first && last) {
      area =
        path +
        `L${xOf(last.distanceMiles).toFixed(1)},${(margin.top + plotHeight).toFixed(1)}` +
        `L${xOf(first.distanceMiles).toFixed(1)},${(margin.top + plotHeight).toFixed(1)}Z`;
    }

    const yTicks = 4;
    let grid = "";
    let labels = "";
    for (let tick = 0; tick <= yTicks; tick += 1) {
      const feet = yMin + ((yMax - yMin) * tick) / yTicks;
      const y = yOf(feet).toFixed(1);
      grid += `<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#e3e8e7" stroke-width="1"/>`;
      labels += `<text x="${margin.left - 8}" y="${y}" text-anchor="end" dominant-baseline="middle" font-size="11" fill="#51625f">${Math.round(feet).toLocaleString()}</text>`;
    }
    const xTicks = 6;
    for (let tick = 0; tick <= xTicks; tick += 1) {
      const miles = (totalMiles * tick) / xTicks;
      const x = xOf(miles).toFixed(1);
      labels += `<text x="${x}" y="${height - 6}" text-anchor="middle" font-size="11" fill="#51625f">${miles.toFixed(1)} mi</text>`;
    }
    labels += `<text x="14" y="${margin.top + plotHeight / 2}" transform="rotate(-90 14 ${margin.top + plotHeight / 2})" text-anchor="middle" font-size="11" fill="#51625f">feet</text>`;

    this.elements.chart.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Elevation profile along the drawn line" preserveAspectRatio="none">
        ${grid}
        <path d="${area}" fill="#1c4d52" fill-opacity="0.12"/>
        <path d="${path}" fill="none" stroke="#1c4d52" stroke-width="2"/>
        ${labels}
      </svg>
    `;
  }

  private downloadCsv(): void {
    if (this.samples.length === 0) {
      return;
    }
    const rows = ["distance_miles,longitude,latitude,elevation_feet"];
    for (const sample of this.samples) {
      rows.push(
        `${sample.distanceMiles.toFixed(4)},${sample.lng.toFixed(6)},` +
          `${sample.lat.toFixed(6)},` +
          `${sample.elevationFeet === null ? "" : sample.elevationFeet.toFixed(1)}`,
      );
    }
    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "cross_section_profile.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }
}
