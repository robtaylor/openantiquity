import { readFileSync } from "node:fs";
import type { Page, Response } from "@playwright/test";
import { openMap } from "../e2e/support/app.js";
import { formatGridRef, kmSquareAt, wgs84ToGrid } from "../src/map/gridref.js";
import { expect, test } from "./support/fixtures.js";
import { helper } from "./support/people.js";

/**
 * The leak run (WS-C step 3), against the real backend. A member draws a
 * protected line about 3 km long, another member gives it a second look,
 * and the finder carries it on. Then someone signed out reads everything
 * that can name it: its page and both downloads, the map and the Explore
 * list at the line's far end and at its anchor, the activity feed, help
 * wanted, the second-look queue, the finder's profile, recent mentions,
 * search and the suggested records. Every response the page gets, every
 * download and every direct API read is searched, as text, for anything
 * placing a point within 200 m of the line: a pair of decimal degrees in
 * any field or column, a pair of grid metres, or a grid reference of 100 m
 * or finer. The 1 km square is the only place allowed. Because the search
 * reads the text and not named fields, a new field carrying a coordinate
 * fails it. Then a member reads the same finding and gets the line.
 *
 * The event stream is left out: it sends ids, never positions, and its
 * response never ends, so its body can't be read here.
 */

const HEADERS = { "X-OpenAntiquity-Client": "web" };
/** In Shropshire, away from every other spec's places. */
const PLACES = { desktop: { lon: -2.62, lat: 52.66 }, phone: { lon: -2.62, lat: 52.74 } } as const;
const NEAR_M = 200;

type LonLat = [number, number];

/** A line from `start` running 3 km roughly east-north-east, with a bend. */
function lineFrom(start: { lon: number; lat: number }): LonLat[] {
  return [
    [start.lon, start.lat],
    [start.lon + 0.012, start.lat + 0.004],
    [start.lon + 0.024, start.lat + 0.005],
    [start.lon + 0.036, start.lat + 0.011],
  ];
}

function metresBetween([lon1, lat1]: LonLat, [lon2, lat2]: LonLat): number {
  const k = Math.cos((((lat1 + lat2) / 2) * Math.PI) / 180);
  return Math.hypot((lon2 - lon1) * 111_320 * k, (lat2 - lat1) * 111_320);
}

/** How far `point` is from the polyline, in metres, near enough at these distances. */
function distanceToLine(point: LonLat, line: readonly LonLat[]): number {
  let best = Number.POSITIVE_INFINITY;
  const k = Math.cos((point[1] * Math.PI) / 180) * 111_320;
  const xy = ([lon, lat]: LonLat): [number, number] => [lon * k, lat * 111_320];
  const [px, py] = xy(point);
  for (let i = 0; i + 1 < line.length; i++) {
    const [ax, ay] = xy(line[i] as LonLat);
    const [bx, by] = xy(line[i + 1] as LonLat);
    const length2 = (bx - ax) ** 2 + (by - ay) ** 2;
    const t = length2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / length2));
    best = Math.min(best, Math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay))));
  }
  return best;
}

/** Every 100 m grid square within 200 m of the line, as six-figure references. */
function nearSquares(line: readonly LonLat[]): Set<string> {
  const refs = new Set<string>();
  for (let i = 0; i + 1 < line.length; i++) {
    const [a, b] = [line[i] as LonLat, line[i + 1] as LonLat];
    const steps = Math.ceil(metresBetween(a, b) / 20);
    for (let step = 0; step <= steps; step++) {
      const lon = a[0] + ((b[0] - a[0]) * step) / steps;
      const lat = a[1] + ((b[1] - a[1]) * step) / steps;
      const centre = wgs84ToGrid(lon, lat);
      if (!centre) continue;
      for (const de of [-200, -100, 0, 100, 200]) {
        for (const dn of [-200, -100, 0, 100, 200]) {
          refs.add(formatGridRef({ ...centre, easting: centre.easting + de, northing: centre.northing + dn }, 6));
        }
      }
    }
  }
  return refs;
}

interface Exposure {
  where: string;
  what: string;
}

/**
 * What in `text` places a point within 200 m of `line`, other than the
 * square's corners and centre in `allowed`: consecutive decimal numbers
 * read as longitude and latitude either way round, consecutive whole
 * numbers read as grid metres, and grid references of 100 m or finer.
 */
function exposures(where: string, text: string, line: readonly LonLat[], allowed: readonly LonLat[]): Exposure[] {
  const found: Exposure[] = [];
  const isAllowed = (point: LonLat): boolean => allowed.some((spot) => metresBetween(spot, point) < 3);
  const decimals = (text.match(/-?\d+\.\d+/g) ?? []).map(Number);
  for (let i = 0; i + 1 < decimals.length; i++) {
    for (const point of [[decimals[i], decimals[i + 1]] as LonLat, [decimals[i + 1], decimals[i]] as LonLat]) {
      const [lon, lat] = point;
      if (lon < -9 || lon > 3 || lat < 49 || lat > 61) continue;
      if (distanceToLine(point, line) <= NEAR_M && !isAllowed(point)) found.push({ where, what: `${lon}, ${lat}` });
    }
  }
  const grid = line.map(([lon, lat]) => wgs84ToGrid(lon, lat)).filter((position) => position !== null);
  const wholes = (text.match(/(?<![\d.])\d{5,7}(?![\d.])/g) ?? []).map(Number);
  for (let i = 0; i + 1 < wholes.length; i++) {
    const [easting, northing] = [wholes[i] as number, wholes[i + 1] as number];
    const close = grid.some(
      (position) => Math.hypot(position.easting - easting, position.northing - northing) < NEAR_M,
    );
    const onTheKilometre = easting % 500 === 0 && northing % 500 === 0;
    if (close && !onTheKilometre) found.push({ where, what: `grid metres ${easting} ${northing}` });
  }
  const squares = nearSquares(line);
  const allowedRefs = new Set(
    allowed
      .map(([lon, lat]) => wgs84ToGrid(lon, lat))
      .flatMap((position) => (position ? [formatGridRef(position, 6)] : [])),
  );
  for (const match of text.matchAll(/\b([A-Z]{2}) ?(\d{3,5}) ?(\d{3,5})\b/g)) {
    const [, letters, east, north] = match;
    if (!letters || !east || !north || east.length !== north.length) continue;
    const six = `${letters} ${east.slice(0, 3)} ${north.slice(0, 3)}`;
    if (squares.has(six) && !allowedRefs.has(six)) found.push({ where, what: `grid reference ${match[0]}` });
  }
  return found;
}

/**
 * The place a request itself asked about. The status bar asks the backend
 * for the grid reference and height of the map's middle (`/geo/point`), and
 * the answer names that place, which the reader chose.
 */
function askedAbout(where: string): LonLat[] {
  const match = /\/api\/v1\/geo\/point\?lon=(-?[\d.]+)&lat=(-?[\d.]+)/.exec(where);
  return match ? [[Number(match[1]), Number(match[2])]] : [];
}

/** Every body the backend sends this page, as text, by address. The event stream never ends and is left out. */
function collectBodies(page: Page): { bodies: Promise<[string, string]>[] } {
  const seen = { bodies: [] as Promise<[string, string]>[] };
  page.on("response", (response: Response) => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith("/api/")) return;
    if ((response.headers()["content-type"] ?? "").includes("event-stream")) return;
    seen.bodies.push(
      response
        .text()
        .then((body): [string, string] => [`${response.request().method()} ${url.pathname}${url.search}`, body])
        .catch((): [string, string] => [`${url.pathname} (no body)`, ""]),
    );
  });
  return seen;
}

function view(at: LonLat, zoom: number): string {
  return `#m=${zoom}/${at[1]}/${at[0]}/0/0&v=composite`;
}

test("a protected line read signed out names nothing of it but its square, and a member sees it", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(180_000);
  const project = testInfo.project.name === "phone" ? "phone" : "desktop";
  const tag = `${project.slice(0, 1)}${Date.now() % 1_000_000}`;
  const finderHandle = `Keeper${tag}`;
  // In letters: a run of digits in a protected finding's title reads as a grid reference, and is refused.
  const title = `Bank across the moor ${tag.replace(/\d/g, (digit) => "abcdefghij"[Number(digit)] ?? "")}`;
  const drawn = lineFrom(PLACES[project]);

  // A member draws it, protected; another gives it a second look; the finder carries it on.
  const finder = await helper(browser, page.viewportSize(), finderHandle);
  const member = await helper(browser, page.viewportSize(), `Reader${tag}`);
  let publicId = "";
  let line: LonLat[] = [];
  let anchor: LonLat = [0, 0];
  let memberSees = 0;
  try {
    const created = await finder.page.request.post("/api/v1/findings", {
      headers: HEADERS,
      data: {
        path: { closed: false, points: drawn.slice(0, 3).map(([lon, lat]) => ({ lon, lat, kind: "smooth" })) },
        feature_class: "linear",
        sensitivity: "protected",
        title,
        view_state: { layer: "composite", zoom: 14 },
      },
    });
    expect(created.status(), await created.text()).toBe(201);
    publicId = ((await created.json()) as { public_id: string }).public_id;

    const answered = await member.page.request.put(`/api/v1/findings/${publicId}/observation`, {
      headers: HEADERS,
      data: { visible: "yes", shape_revision: 0 },
    });
    expect(answered.status(), await answered.text()).toBeLessThan(300);

    const extended = await finder.page.request.patch(`/api/v1/findings/${publicId}`, {
      headers: HEADERS,
      data: {
        path: { closed: false, points: drawn.map(([lon, lat]) => ({ lon, lat, kind: "smooth" })) },
        path_revision: 0,
      },
    });
    expect(extended.status(), await extended.text()).toBe(200);

    // The whole line as the finder downloads it, every derived vertex, and its anchor.
    const own = await finder.page.request.get(`/api/v1/findings/${publicId}/export?format=geojson`);
    const feature = (
      (await own.json()) as {
        features: Array<{ geometry: { coordinates: LonLat }; properties: { outline: { coordinates: LonLat[] } } }>;
      }
    ).features[0];
    if (!feature) throw new Error("The finder's download has no feature");
    line = feature.properties.outline.coordinates;
    anchor = feature.geometry.coordinates;
    expect(line.length).toBeGreaterThan(drawn.length);

    // A member sees the line exactly: its path, its outline and its shape on the map.
    const seen = await member.page.request.get(`/api/v1/findings/${publicId}`);
    const memberText = await seen.text();
    const detail = JSON.parse(memberText) as {
      location: { obscured: boolean; path: { points: unknown[] } | null; outline: unknown; shape: { kind: string } };
    };
    expect(detail.location.obscured).toBe(false);
    expect(detail.location.path?.points).toHaveLength(drawn.length);
    expect(detail.location.outline).not.toBeNull();
    expect(detail.location.shape.kind).toBe("line");
    // The search below finds the line in what a member is sent, so it would find it in a leak.
    memberSees = exposures("a member's read", memberText, line, []).length;
    const end = drawn.at(-1) as LonLat;
    const box = [end[0] - 0.005, end[1] - 0.005, end[0] + 0.005, end[1] + 0.005].join(",");
    const map = await member.page.request.get(`/api/v1/findings?format=geojson&zoom=16&bbox=${box}`);
    const mapped = ((await map.json()) as { features: Array<{ properties: { public_id: string; shape?: unknown } }> })
      .features;
    expect(mapped.find((entry) => entry.properties.public_id === publicId)?.properties.shape).toBeTruthy();
    await openMap(member.page, `/f/${publicId}${view(end, 15)}`);
    await expect(member.page.getByRole("complementary", { name: title })).toBeVisible();
  } finally {
    await finder.context.close();
    await member.context.close();
  }

  expect(memberSees, "the search finds the line in a member's read").toBeGreaterThan(10);

  // Signed out: the square is the only place allowed.
  const square = kmSquareAt(anchor[0], anchor[1]);
  if (!square) throw new Error("The anchor is off the grid");
  const corners = square.ring.slice(0, 4);
  const centre: LonLat = [
    corners.reduce((sum, [lon]) => sum + lon, 0) / 4,
    corners.reduce((sum, [, lat]) => sum + lat, 0) / 4,
  ];
  const allowed: LonLat[] = [...square.ring, centre];
  const collected = collectBodies(page);
  const read: Array<[string, string]> = [];

  // The finding's page, and both downloads from it.
  await openMap(page, `/f/${publicId}${view(anchor, 14)}`);
  const findingPanel = page.getByRole("complementary", { name: title });
  await expect(findingPanel).toBeVisible();
  for (const name of ["GeoJSON", "Spreadsheet (CSV)"]) {
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      findingPanel.getByRole("link", { name }).click(),
    ]);
    const path = await download.path();
    read.push([`download ${name}`, readFileSync(path, "utf8")]);
  }

  // The map and Explore at the line's far end, where only its shape lies, and at its anchor.
  const end = drawn.at(-1) as LonLat;
  for (const [at, zoom] of [
    [end, 16],
    [end, 13],
    [anchor, 14],
  ] as const) {
    await openMap(page, `/${view(at, zoom)}`);
    await page.waitForTimeout(800);
  }

  // Everything else that lists or names findings.
  for (const address of ["/activity", "/help", `/review${view(end, 14)}`, `/u/${finderHandle}`, "/mentions"]) {
    await openMap(page, address);
    await page.waitForTimeout(800);
  }

  // And the API, read directly, for what no page asks in this way.
  const box = (at: LonLat, half: number) => [at[0] - half, at[1] - half, at[0] + half, at[1] + half].join(",");
  for (const address of [
    `/api/v1/findings/${publicId}`,
    `/api/v1/findings?bbox=${box(end, 0.01)}`,
    `/api/v1/findings?format=geojson&zoom=16&bbox=${box(end, 0.005)}`,
    `/api/v1/findings?format=geojson&zoom=9&bbox=${box(anchor, 0.2)}`,
    `/api/v1/findings/export?format=csv&bbox=${box(anchor, 0.1)}`,
    `/api/v1/findings/export?format=geojson&bbox=${box(end, 0.1)}`,
    `/api/v1/findings/${publicId}/export?format=geojson`,
    `/api/v1/findings/${publicId}/suggested-records`,
    `/api/v1/findings/${publicId}/observations`,
    `/api/v1/activity`,
    `/api/v1/activity?finding=${publicId}`,
    `/api/v1/activity?bbox=${box(end, 0.01)}`,
    `/api/v1/review/tasks`,
    `/api/v1/review/next?lon=${end[0]}&lat=${end[1]}`,
    `/api/v1/users/${finderHandle}/findings`,
    `/api/v1/users/${finderHandle}/contributions`,
    `/api/v1/mentions/recent`,
    `/api/v1/geo/search?q=${encodeURIComponent(title)}`,
  ]) {
    const response = await page.request.get(address);
    // Refusals are read too: a signed-out reader is refused other people's answers until they give their own.
    expect(response.status(), `${address}: ${await response.text()}`).toBeLessThan(500);
    read.push([`GET ${address}`, await response.text()]);
  }

  const bodies = [...(await Promise.all(collected.bodies)), ...read];
  const addresses = bodies.map(([where]) => where);
  // The run read what it meant to: the finding, its map and list at the far end, the feed, and its downloads.
  for (const expected of [
    `/api/v1/findings/${publicId}`,
    "format=geojson",
    "/api/v1/activity",
    "/api/v1/review/tasks",
    `/api/v1/users/${finderHandle}/findings`,
    "download GeoJSON",
    "download Spreadsheet (CSV)",
  ]) {
    expect(
      addresses.some((where) => where.includes(expected)),
      `nothing was read from ${expected}`,
    ).toBe(true);
  }
  // Something did name it, by its square.
  expect(bodies.some(([, body]) => body.includes(publicId))).toBe(true);
  const leaks = bodies.flatMap(([where, body]) => exposures(where, body, line, [...allowed, ...askedAbout(where)]));
  expect(leaks).toEqual([]);
});
