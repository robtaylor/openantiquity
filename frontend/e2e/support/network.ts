import type { Page, Route } from "@playwright/test";
import { NO_FINDINGS } from "../../src/features/findings/types.js";
import { pageFixture, suggestionsFixture } from "../../src/test/fixtures/findingPage.js";
import { solidPng } from "./png.js";

/**
 * Answer every request that would leave the dev server, so the tests need
 * neither a backend nor the internet. Tiles are recorded stand-ins: flat
 * colours for imagery, sea level for elevation, and nothing for vector data.
 * The API calls the app makes in fixture mode get stand-in answers too: no
 * findings (for the map and for the list), a fixed height for any spot,
 * one-metre elevation everywhere, nobody signed in, nothing waiting for a
 * second look, no help wanted, no mentions and no activity. A test can
 * answer any of them differently with a route of its own, which Playwright
 * tries first.
 */

/** The height every spot has, by these stubs. */
export const STUB_HEIGHT_M = 162.4;
/** The exact grid reference every spot has, by these stubs. */
export const STUB_GRID_REF = "SU 10235 69874";

const GREY_TILE = solidPng(256, 256, [128, 128, 128]);
const MAP_TILE = solidPng(256, 256, [222, 214, 196]);
// Terrarium encodes height as (red * 256 + green + blue / 256) - 32768, so this is 0 m.
const SEA_LEVEL_TILE = solidPng(256, 256, [128, 0, 0]);

/**
 * The vector layers in OpenFreeMap's TileJSON (https://tiles.openfreemap.org/planet,
 * OpenMapTiles schema 3.16), recorded in November 2026. MapLibre checks every
 * `source-layer` in the style against this list and reports any it cannot find,
 * so the tests catch a misnamed layer in the overlay styling.
 */
const OPENMAPTILES_LAYERS = [
  "aerodrome_label",
  "aeroway",
  "boundary",
  "building",
  "housenumber",
  "landcover",
  "landuse",
  "mountain_peak",
  "park",
  "place",
  "poi",
  "transportation",
  "transportation_name",
  "water",
  "water_name",
  "waterway",
];

const TILEJSON = {
  tilejson: "3.0.0",
  name: "stub",
  tiles: ["https://tiles.openfreemap.org/planet/stub/{z}/{x}/{y}.pbf"],
  minzoom: 0,
  maxzoom: 14,
  bounds: [-180, -85.05113, 180, 85.05113],
  vector_layers: OPENMAPTILES_LAYERS.map((id) => ({ id, fields: {} })),
};

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Requests to the dev server's backend paths, anchored to the start of the
 * path so that module URLs such as /src/api/client.ts are left alone.
 */
function backendRoute(prefix: string): RegExp {
  return new RegExp(`^https?://localhost(:\\d+)?${escapeRegExp(prefix)}`);
}

/** Requests to an API endpoint, such as `apiRoute("/findings")`, with or without a query. */
export function apiRoute(path: string): RegExp {
  return new RegExp(`${backendRoute(`/api/v1${path}`).source}(?:\\?|$)`);
}

/**
 * Requests for one finding's page or its parts, such as `/api/v1/findings/abc`,
 * `/api/v1/findings/abc/comments` or `/api/v1/findings/abc/observation/reveal`.
 * The id and the part are the first two groups.
 */
export const FINDING_PAGE_ROUTE =
  /^https?:\/\/localhost(?::\d+)?\/api\/v1\/findings\/([^/?#]+)(\/[a-z-]+(?:\/[a-z-]+)?)?(?:\?|$)/;

/** Requests under a backend tile path, such as `tilesRoute("/records/")`. */
export function tilesRoute(prefix = "/"): RegExp {
  return backendRoute(`/tiles${prefix}`);
}

export interface NetworkLog {
  /** Requests to hosts the stubs did not recognise. A passing test leaves this empty. */
  unexpected: string[];
  /** Count of stubbed requests by kind. */
  served: Record<string, number>;
}

function png(route: Route, body: Buffer): Promise<void> {
  return route.fulfill({ status: 200, contentType: "image/png", body });
}

function newLog(): NetworkLog {
  return { unexpected: [], served: {} };
}

function counter(log: NetworkLog): (kind: string) => void {
  return (kind) => {
    log.served[kind] = (log.served[kind] ?? 0) + 1;
  };
}

/**
 * `GET /terrain/coverage` as if one-metre elevation covered the whole box
 * asked about, so the map has no squares to shade unless a test says so.
 */
export function coverageEverywhere(url: URL): unknown {
  const [west, south, east, north] = (url.searchParams.get("bbox") ?? "-180,-85,180,85").split(",").map(Number);
  const ring = [
    [west, south],
    [east, south],
    [east, north],
    [west, north],
    [west, south],
  ];
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: "everywhere",
        geometry: { type: "Polygon", coordinates: [ring] },
        properties: { tile: "everywhere", capture: "Stand-in data", resolution_m: 1 },
      },
    ],
  };
}

/**
 * Stand in for the backend. Fixture mode answers /meta itself, the tile
 * endpoints answer "no data here", and the two API calls the map makes get
 * the stand-in answers described above.
 */
export async function stubBackend(page: Page, log: NetworkLog = newLog()): Promise<NetworkLog> {
  const count = counter(log);
  await page.route(tilesRoute(), (route) => {
    count("backend-tiles");
    return route.fulfill({ status: 204 });
  });
  await page.route(backendRoute("/api/"), (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/findings" && route.request().method() === "GET") {
      count("findings");
      // GeoJSON for the map, and an empty page for the Explore list.
      const geojson = new URL(route.request().url()).searchParams.get("format") === "geojson";
      const body = geojson ? NO_FINDINGS : { items: [], next_cursor: null };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    }
    const findingPage = FINDING_PAGE_ROUTE.exec(route.request().url());
    if (findingPage && route.request().method() === "GET" && findingPage[1] !== "export") {
      // Any finding asked for exists: a plain spotted one, with nothing said about it yet.
      count("finding-page");
      const publicId = decodeURIComponent(findingPage[1] ?? "");
      const part = findingPage[2];
      const body =
        part === undefined
          ? pageFixture({ public_id: publicId, title: `Finding ${publicId}` })
          : part === "/suggested-records"
            ? suggestionsFixture([])
            : { items: [], next_cursor: null };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    }
    if (path === "/api/v1/auth/me") {
      count("auth-me");
      const body = { error: { code: "unauthorised", message: "Sign in first." } };
      return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify(body) });
    }
    if (path === "/api/v1/review/next" || path === "/api/v1/review/tasks") {
      // Nothing waiting for a second look, and no help wanted.
      count("review");
      const body = path === "/api/v1/review/next" ? { items: [], next_cursor: null } : { groups: [] };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    }
    if (path === "/api/v1/mentions/recent" || path === "/api/v1/activity") {
      // Nobody has mentioned anything, and nothing has happened.
      count(path === "/api/v1/activity" ? "activity" : "mentions");
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], next_cursor: null }),
      });
    }
    if (path === "/api/v1/terrain/coverage") {
      count("coverage");
      const body = coverageEverywhere(new URL(route.request().url()));
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    }
    if (path === "/api/v1/geo/point") {
      count("geo-point");
      const body = { grid_ref: STUB_GRID_REF, nation: "england", elevation: STUB_HEIGHT_M };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    }
    log.unexpected.push(route.request().url());
    return route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "no_backend", message: "No backend in end-to-end tests." } }),
    });
  });
  return log;
}

/** Stand in for every outside tile service, with the recorded tiles described above. */
export async function stubUpstream(page: Page, log: NetworkLog = newLog()): Promise<NetworkLog> {
  const count = counter(log);
  await page.route(/^https?:\/\/(?!localhost[:/])/, (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "environment.data.gov.uk") {
      count("lidar");
      return png(route, GREY_TILE);
    }
    if (url.hostname === "tile.openstreetmap.org") {
      count("osm-raster");
      return png(route, MAP_TILE);
    }
    if (url.hostname === "s3.amazonaws.com") {
      count("dem");
      return png(route, SEA_LEVEL_TILE);
    }
    if (url.hostname === "tiles.openfreemap.org") {
      if (url.pathname === "/planet") {
        count("tilejson");
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(TILEJSON) });
      }
      count(url.pathname.startsWith("/fonts/") ? "glyphs" : "osm-vector");
      return route.fulfill({ status: 204 });
    }
    log.unexpected.push(url.href);
    return route.abort();
  });
  return log;
}

/** Stand in for the backend and every outside service. */
export async function stubNetwork(page: Page): Promise<NetworkLog> {
  const log = await stubBackend(page);
  return stubUpstream(page, log);
}
