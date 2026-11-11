import { GeoJSONVT } from "@maplibre/geojson-vt";
import { fromGeojsonVt } from "@maplibre/vt-pbf";
import type { Page } from "@playwright/test";
import type { FindingCollection } from "../../src/features/findings/types.js";
import { FINDINGS_CENTRE, findingsData, offset } from "../../src/test/fixtures/findings.js";
import { apiRoute } from "./network.js";

/**
 * Stand-in markers, so the marker styling can be seen and tested before the
 * backend serves real ones. Records come as vector tiles built from a few
 * points, with `category` as the contract says. Findings come from a
 * stand-in for `GET /findings?bbox=&format=geojson`, from the shared fixture
 * or from a test's own collection.
 */

export interface MarkerPoint {
  lon: number;
  lat: number;
  properties: Record<string, string | number | boolean>;
}

/** The centre of the fixture's opening view, at Avebury. */
export const CENTRE = FINDINGS_CENTRE;
export { offset };

const TILE_OPTIONS = { maxZoom: 14, indexMaxZoom: 14, extent: 4096, buffer: 64, tolerance: 0 };

type GeoJsonInput = ConstructorParameters<typeof GeoJSONVT>[0];

function collection(points: MarkerPoint[]): GeoJsonInput {
  return {
    type: "FeatureCollection",
    features: points.map((point, index) => ({
      type: "Feature",
      id: index + 1,
      geometry: { type: "Point", coordinates: [point.lon, point.lat] },
      properties: point.properties,
    })),
  };
}

/**
 * Serve `points` as the records vector tile layer for every records tile, or
 * as the counts layer (`record_counts`) a busy or low-zoom tile carries.
 */
export async function serveRecordTiles(
  page: Page,
  points: MarkerPoint[],
  layer: "records" | "record_counts" = "records",
): Promise<void> {
  const index = new GeoJSONVT(collection(points), TILE_OPTIONS);
  const pattern = /^https?:\/\/localhost(:\d+)?\/tiles\/records\/(\d+)\/(\d+)\/(\d+)\.mvt(\?.*)?$/;
  await page.route(pattern, (route) => {
    const match = pattern.exec(route.request().url());
    if (!match) return route.fulfill({ status: 404 });
    const tile = index.getTile(Number(match[2]), Number(match[3]), Number(match[4]));
    if (!tile) return route.fulfill({ status: 204 });
    const body = Buffer.from(fromGeojsonVt({ [layer]: tile }, { version: 2, extent: TILE_OPTIONS.extent }));
    return route.fulfill({ status: 200, contentType: "application/vnd.mapbox-vector-tile", body });
  });
}

export interface FindingsLog {
  /** The `bbox` of each request, as west, south, east, north. */
  boxes: Array<[number, number, number, number]>;
}

/**
 * Answer `GET /api/v1/findings` with the findings of `findings` that fall in
 * the box asked for, as the server would. Records each box.
 */
export async function serveFindings(page: Page, findings: FindingCollection = findingsData): Promise<FindingsLog> {
  const log: FindingsLog = { boxes: [] };
  await page.route(apiRoute("/findings"), (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("format") !== "geojson") return route.fulfill({ status: 400 });
    const box = (url.searchParams.get("bbox") ?? "").split(",").map(Number);
    if (box.length !== 4 || box.some((n) => !Number.isFinite(n))) return route.fulfill({ status: 422 });
    const [west, south, east, north] = box as [number, number, number, number];
    log.boxes.push([west, south, east, north]);
    const features = findings.features.filter((feature) => {
      const [lon, lat] = feature.geometry.coordinates;
      return lon >= west && lon <= east && lat >= south && lat <= north;
    });
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ type: "FeatureCollection", features }),
    });
  });
  return log;
}

const CATEGORIES = ["designation", "monument", "find", "event", "document", "community", "map_label"];

/** One record per category in a row. */
export const SAMPLE_RECORDS: MarkerPoint[] = CATEGORIES.map((category, i) => ({
  ...offset(-600 + i * 200, -150),
  properties: { id: i + 1, category },
}));
