import { existsSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { GeoJSONVT } from "@maplibre/geojson-vt";
import { fromGeojsonVt } from "@maplibre/vt-pbf";
import { expect, type Page, type Route, test } from "@playwright/test";
import type { FindingFeature, FindingShape } from "../../src/features/findings/types.js";
import { FINDINGS_CENTRE, findingSummary, offset } from "../../src/test/fixtures/findings.js";
import { apiRoute, stubBackend, tilesRoute } from "../support/network.js";

/**
 * Findings beside heritage records at zooms 7, 9, 11, 13 and 15, over
 * several kinds of ground, for checking that a glance finds the findings
 * first. The same picture is laid out in screen pixels at every zoom: a
 * finding of each tier, two known findings, a line, an area and records
 * beside them, as counts below zoom 12 and as single records from it.
 * Taken with `pnpm shots e2e/shots/findings-first.spec.ts`. They assert
 * nothing beyond the map having drawn.
 *
 * Fixture mode draws every LIDAR view from one public hillshade service. Set
 * `FIELDCLUB_SHOTS_TILES` to a folder of the backend's rendered LIDAR tiles
 * (`var/tiles/lidar` of a checkout that has some) to draw each view from its
 * own tiles instead. Where that folder has no tile for a place, a tile from
 * elsewhere in the same view stands in, so the ground looks right at every
 * zoom though it isn't the real place. "satellite" draws the Sentinel-2
 * picture the backend's catalogue names, and "osm" is the OpenStreetMap view.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });
const TILES = process.env.FIELDCLUB_SHOTS_TILES;

const CENTRE = FINDINGS_CENTRE;
const ZOOMS = [7, 9, 11, 13, 15];
/** Each ground, and the view in the address that draws it. */
const GROUNDS: Array<{ name: string; view: string; lidar?: string }> = [
  { name: "multi_shade", view: "multi_shade", lidar: "multi_shade" },
  { name: "composite", view: "composite", lidar: "composite" },
  { name: "local_relief", view: "local_relief", lidar: "local_relief" },
  { name: "satellite", view: "composite" },
  { name: "osm", view: "osm_standard" },
];
const TIERS = ["spotted", "seen", "corroborated", "probable", "ground_checked", "confirmed"];
const CATEGORIES = ["designation", "monument", "find", "event", "document", "community", "map_label"];
const HALF_WORLD = 20037508.342789244;

/** Metres on the ground per CSS pixel at `zoom`, at the centre's latitude. */
function metresPerPixel(zoom: number): number {
  return (2 * HALF_WORLD * Math.cos((CENTRE.lat * Math.PI) / 180)) / (512 * 2 ** zoom);
}

/** The place `dx` pixels right of the centre and `dy` pixels above it, at `zoom`. */
function px(zoom: number, dx: number, dy: number): [number, number] {
  const m = metresPerPixel(zoom);
  const { lon, lat } = offset(dx * m, dy * m, CENTRE);
  return [lon, lat];
}

function feature(
  publicId: string,
  tier: string,
  anchor: [number, number],
  state = "open",
  shape?: FindingShape,
): FindingFeature {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: anchor },
    properties: {
      public_id: publicId,
      tier,
      state,
      sensitivity: "open",
      obscured: false,
      title: `Finding ${publicId}`,
      feature_class: shape ? "linear" : "enclosure",
      ...(shape ? { shape } : {}),
    },
  } as FindingFeature;
}

/** The findings, laid out the same on screen at `zoom`. */
function findingsAt(zoom: number): FindingFeature[] {
  const at = (dx: number, dy: number) => px(zoom, dx, dy);
  const tiers = TIERS.map((tier, i) => feature(`tier-${tier}`, tier, at(-150 + i * 60, 60)));
  const known = [
    feature("known-seen", "seen", at(-150, 0), "known"),
    feature("known-probable", "probable", at(-90, 0), "known"),
  ];
  const line: FindingShape = { type: "LineString", coordinates: [at(-40, 10), at(20, -10), at(80, 0), at(140, -30)] };
  const ring = [at(40, -60), at(150, -60), at(150, -130), at(40, -130), at(40, -60)];
  const area: FindingShape = { type: "Polygon", coordinates: [ring] };
  return [
    ...tiers,
    ...known,
    feature("line", "seen", at(-40, 10), "open", line),
    feature("area", "spotted", at(95, -95), "open", area),
  ];
}

/** Records beside the findings: one by each tier's marker, and a row of every category below them. */
function recordsAt(zoom: number, counts: boolean) {
  const points = [
    ...TIERS.map((_, i) => ({ at: px(zoom, -150 + i * 60 + 16, 60 - 14), category: CATEGORIES[i % 7] as string })),
    ...CATEGORIES.map((category, i) => ({ at: px(zoom, -180 + i * 60, -170), category })),
  ];
  return {
    type: "FeatureCollection" as const,
    features: points.map((point, i) => ({
      type: "Feature" as const,
      id: i + 1,
      geometry: { type: "Point" as const, coordinates: point.at },
      properties: counts
        ? { category: point.category, count: [3, 48, 1250, 7][i % 4] as number, sources: "nhle-scheduled" }
        : { id: i + 1, category: point.category, source: "nhle-scheduled", name: `Record ${i + 1}` },
    })),
  };
}

async function serveFindingsAt(page: Page, zoom: number): Promise<void> {
  const features = findingsAt(zoom);
  await page.route(apiRoute("/findings"), (route) => {
    const url = new URL(route.request().url());
    const body =
      url.searchParams.get("format") === "geojson"
        ? { type: "FeatureCollection", features, next_cursor: null }
        : { items: features.map((each) => findingSummary(each)), next_cursor: null };
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

/** Records tiles: counts below zoom 12, records from it, as the backend sends them. */
async function serveRecordsAt(page: Page, zoom: number): Promise<void> {
  const options = { maxZoom: 14, indexMaxZoom: 14, extent: 4096, buffer: 64, tolerance: 0 };
  const counts = new GeoJSONVT(recordsAt(zoom, true), options);
  const records = new GeoJSONVT(recordsAt(zoom, false), options);
  const pattern = /\/tiles\/records\/(\d+)\/(\d+)\/(\d+)\.mvt/;
  await page.route(tilesRoute("/records/"), (route) => {
    const match = pattern.exec(route.request().url());
    if (!match) return route.fulfill({ status: 404 });
    const [z, x, y] = [Number(match[1]), Number(match[2]), Number(match[3])];
    const layer = z < 12 ? "record_counts" : "records";
    const tile = (z < 12 ? counts : records).getTile(z, x, y);
    if (!tile) return route.fulfill({ status: 204 });
    const body = Buffer.from(fromGeojsonVt({ [layer]: tile }, { version: 2, extent: 4096 }));
    return route.fulfill({ status: 200, contentType: "application/vnd.mapbox-vector-tile", body });
  });
}

/** Every rendered tile of a LIDAR view under `TILES`, by "z/x/y". */
function lidarIndex(view: string): Map<string, string> {
  const index = new Map<string, string>();
  const root = TILES ? join(TILES, view) : "";
  if (!TILES || !existsSync(root)) return index;
  for (const entry of readdirSync(root, { recursive: true }) as string[]) {
    const match = /(\d+)\/(\d+)\/(\d+)\.png$/.exec(entry);
    if (match) index.set(`${match[1]}/${match[2]}/${match[3]}`, join(root, entry));
  }
  return index;
}

/** The grid tile a WMS request's Web Mercator box covers. */
function tileOfBox(url: string): { z: number; x: number; y: number } | null {
  const box = new URL(url).searchParams.get("bbox")?.split(",").map(Number);
  if (box?.length !== 4) return null;
  const [minX, , maxX, maxY] = box as [number, number, number, number];
  const width = maxX - minX;
  const z = Math.round(Math.log2((2 * HALF_WORLD) / width));
  return { z, x: Math.round((minX + HALF_WORLD) / width), y: Math.round((HALF_WORLD - maxY) / width) };
}

/**
 * Let the fixture's LIDAR views draw below zoom 10, as the backend's do from
 * its national overview, once their tiles are served from here and not from
 * the public service, which can't draw that far out.
 */
async function drawFarOut(page: Page): Promise<void> {
  await page.route(/\/src\/test\/fixtures\/meta\.ts/, async (route) => {
    const response = await route.fetch();
    const body = (await response.text()).replace("minzoom: 10,", "minzoom: 0,");
    return route.fulfill({ response, body });
  });
}

/** Draw the LIDAR views' hillshade service from local tiles of `lidar`, or from the Sentinel-2 picture. */
async function serveGround(page: Page, ground: (typeof GROUNDS)[number]): Promise<void> {
  const wms = /^https:\/\/environment\.data\.gov\.uk\/spatialdata\//;
  if (ground.name === "satellite") {
    await drawFarOut(page);
    await page.route(wms, async (route: Route) => {
      const tile = tileOfBox(route.request().url());
      if (!tile) return route.fulfill({ status: 404 });
      const z = Math.min(tile.z, 14);
      const scale = 2 ** (tile.z - z);
      const [x, y] = [Math.floor(tile.x / scale), Math.floor(tile.y / scale)];
      const url = `https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/${z}/${y}/${x}.jpg`;
      return route.fulfill({ response: await route.fetch({ url }) });
    });
    return;
  }
  if (!ground.lidar) return;
  const index = lidarIndex(ground.lidar);
  if (index.size === 0) return;
  await drawFarOut(page);
  const standIns = [...index.entries()].filter(([key]) => Number(key.split("/")[0]) >= 13).map(([, file]) => file);
  await page.route(wms, (route) => {
    const tile = tileOfBox(route.request().url());
    if (!tile) return route.fulfill({ status: 404 });
    const file = index.get(`${tile.z}/${tile.x}/${tile.y}`) ?? standIns[(tile.x * 31 + tile.y * 17) % standIns.length];
    if (!file) return route.fulfill({ status: 204 });
    return route.fulfill({ status: 200, contentType: "image/png", body: readFileSync(file) });
  });
}

async function settle(page: Page): Promise<void> {
  await expect(page.locator(".fc-map")).toHaveAttribute("data-ready", "true");
  await page
    .locator('.fc-map__pane--main[data-map-idle="true"]')
    .waitFor({ timeout: 30_000 })
    .catch(() => undefined);
  await page.waitForTimeout(800);
}

async function shoot(page: Page, name: string): Promise<void> {
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `first-${name}-${size?.width}x${size?.height}.png`) });
}

function address(view: string, zoom: number, extra = ""): string {
  return `/?panel=none#m=${zoom}/${CENTRE.lat}/${CENTRE.lon}/0/0&v=${view}&o=osm:80,records:100,findings:100${extra}`;
}

test.beforeEach(async ({ page }) => {
  await stubBackend(page);
});

for (const ground of GROUNDS) {
  test(`findings and records over ${ground.name}, zoom 7 to 15`, async ({ page }) => {
    test.skip((page.viewportSize()?.width ?? 0) < 720 && ground.name !== "multi_shade", "one ground on a phone");
    test.setTimeout(300_000);
    for (const zoom of ZOOMS) {
      await page.unrouteAll({ behavior: "ignoreErrors" });
      await stubBackend(page);
      await serveGround(page, ground);
      await serveFindingsAt(page, zoom);
      await serveRecordsAt(page, zoom);
      await page.goto(address(ground.view, zoom));
      await page.reload();
      await settle(page);
      await shoot(page, `${ground.name}-z${zoom}`);
    }
  });
}

test("record counts switched on, zoomed out", async ({ page }) => {
  test.setTimeout(120_000);
  const ground = GROUNDS[0] as (typeof GROUNDS)[number];
  for (const zoom of [9, 11]) {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await stubBackend(page);
    await serveGround(page, ground);
    await serveFindingsAt(page, zoom);
    await serveRecordsAt(page, zoom);
    await page.goto(address(ground.view, zoom, "&rc=1"));
    await page.reload();
    await settle(page);
    await shoot(page, `counts-on-${ground.name}-z${zoom}`);
  }
});
