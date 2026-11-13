import type { Page } from "@playwright/test";
import { kmSquareAt } from "../src/map/gridref.js";
import { RECORD_SQUARE_OPACITY } from "../src/map/overlayLayers.js";
import { findingCollection } from "../src/test/fixtures/findings.js";
import { metaFixture } from "../src/test/fixtures/meta.js";
import { COLOURS, STATE_COLOURS, TIER_COLOURS } from "../src/ui/tokens.js";
import { openMap, SLOW_MAP } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";
import { CENTRE, type MarkerPoint, offset, serveFindings, serveRecordTiles } from "./support/markerTiles.js";
import {
  blend,
  colourDistance,
  countColour,
  type DecodedImage,
  decodePng,
  hexToRgb,
  pixelAt,
  type Rgb,
} from "./support/png.js";

/**
 * The records and findings overlays, drawn from stand-in records tiles and a
 * stand-in findings endpoint, and checked by the colour of the pixels the map
 * paints. This is the marker styling in docs/UI.md, driven by the properties
 * in the contract.
 */

test.skip(({ viewport }) => (viewport?.width ?? 0) < 720, "one layout is enough for marker styling");

const ZOOM = 15;
const VIEW = { width: 1440, height: 900 };
/** The stubbed base tiles are this grey, so anything else was drawn by an overlay. */
const BACKDROP: Rgb = [128, 128, 128];
const OUTLINE = hexToRgb(COLOURS.bg);

function token(colours: Readonly<Record<string, string>>, id: string): Rgb {
  const hex = colours[id];
  if (hex === undefined) throw new Error(`No colour token for "${id}"`);
  return hexToRgb(hex);
}

function categoryColour(id: string): Rgb {
  const category = metaFixture.vocab.record_categories.find((candidate) => candidate.id === id);
  if (!category) throw new Error(`The meta fixture has no record category "${id}"`);
  return hexToRgb(category.colour);
}

const TIER = {
  seen: token(TIER_COLOURS, "seen"),
  corroborated: token(TIER_COLOURS, "corroborated"),
  probable: token(TIER_COLOURS, "probable"),
};
const RULED_OUT = token(STATE_COLOURS, "ruled_out");
/** Record squares are drawn a little faint, so over the backdrop they are their colour mixed with it. */
const DESIGNATION = blend(categoryColour("designation"), BACKDROP, RECORD_SQUARE_OPACITY);
const FIND = blend(categoryColour("find"), BACKDROP, RECORD_SQUARE_OPACITY);
/** The stubbed street-map tiles' colour (`MAP_TILE` in support/network.ts), and a designation's square over them. */
const MAP_BACKDROP: Rgb = [222, 214, 196];
const DESIGNATION_ON_MAP = blend(categoryColour("designation"), MAP_BACKDROP, RECORD_SQUARE_OPACITY);

/** Where a longitude and latitude fall on screen, with the map centred on `CENTRE`, north up. */
function project(lon: number, lat: number): { x: number; y: number } {
  const world = 512 * 2 ** ZOOM;
  const mercator = (lo: number, la: number) => ({
    x: ((lo + 180) / 360) * world,
    y: ((1 - Math.asinh(Math.tan((la * Math.PI) / 180)) / Math.PI) / 2) * world,
  });
  const centre = mercator(CENTRE.lon, CENTRE.lat);
  const point = mercator(lon, lat);
  return { x: VIEW.width / 2 + point.x - centre.x, y: VIEW.height / 2 + point.y - centre.y };
}

const PROBABLE = { ...CENTRE };
const KNOWN = offset(120, 0);
const RULED = offset(-120, 0);
/** Where an obscured finding really is. The server sends the centre of its square instead. */
const OBSCURED = offset(380, 260);
const RECORD_DESIGNATION = offset(0, -120);
const RECORD_FIND = offset(120, -120);

function findings() {
  return findingCollection([
    { at: PROBABLE, public_id: "a", tier: "probable" },
    { at: KNOWN, public_id: "b", tier: "seen", state: "known" },
    { at: RULED, public_id: "c", tier: "probable", state: "ruled_out" },
    { at: OBSCURED, public_id: "d", tier: "corroborated", sensitivity: "protected", obscured: true },
  ]);
}
const RECORDS: MarkerPoint[] = [
  { ...RECORD_DESIGNATION, properties: { id: 1, category: "designation" } },
  { ...RECORD_FIND, properties: { id: 2, category: "find" } },
];

async function openWithMarkers(page: Page, extraHash = ""): Promise<void> {
  await serveFindings(page, findings());
  await serveRecordTiles(page, RECORDS);
  // The street-map overlay is hidden so the backdrop is one flat colour.
  await openMap(
    page,
    `/?panel=none#m=${ZOOM}/${CENTRE.lat}/${CENTRE.lon}/0/0&v=composite&s=315/25&x=2&t=0/1.5&o=osm:80:h,records:100,findings:100${extraHash}`,
  );
}

/** Take screenshots until `check` passes, as markers appear a frame or two after their tiles. */
async function expectDrawn(page: Page, check: (image: DecodedImage) => void): Promise<void> {
  await expect(async () => {
    check(decodePng(await page.screenshot()));
  }).toPass({ timeout: 15_000 });
}

function near(image: DecodedImage, at: { x: number; y: number }, dx = 0, dy = 0): Rgb {
  return pixelAt(image, at.x + dx, at.y + dy);
}

/**
 * How a marker of `colour` centred near `at` fills the box round it: the
 * width and height of the run of that colour through its middle, and the
 * share of the width-by-height box that is that colour. About 1 for a
 * square, and about 0.79 for a circle.
 */
function filledShare(image: DecodedImage, at: { x: number; y: number }, colour: Rgb, tolerance = 24) {
  const x0 = Math.round(at.x);
  const y0 = Math.round(at.y);
  const matches = (x: number, y: number) => colourDistance(pixelAt(image, x, y), colour) <= tolerance;
  const run = (dx: number, dy: number) => {
    let n = 0;
    while (n < 20 && matches(x0 + dx * (n + 1), y0 + dy * (n + 1))) n += 1;
    return n;
  };
  const [left, right, up, down] = [run(-1, 0), run(1, 0), run(0, -1), run(0, 1)];
  const width = left + right + 1;
  const height = up + down + 1;
  let filled = 0;
  for (let y = y0 - up; y <= y0 + down; y++) for (let x = x0 - left; x <= x0 + right; x++) if (matches(x, y)) filled++;
  return { width, height, share: filled / (width * height) };
}

/** A 7 by 7 box around a point. */
function around(at: { x: number; y: number }, reach = 3) {
  return { x: Math.round(at.x) - reach, y: Math.round(at.y) - reach, width: reach * 2 + 1, height: reach * 2 + 1 };
}

test("draws findings by tier and state, and records as squares by category", async ({ page }) => {
  await openWithMarkers(page);
  const probable = project(PROBABLE.lon, PROBABLE.lat);
  const known = project(KNOWN.lon, KNOWN.lat);
  const ruled = project(RULED.lon, RULED.lat);
  const designation = project(RECORD_DESIGNATION.lon, RECORD_DESIGNATION.lat);
  const find = project(RECORD_FIND.lon, RECORD_FIND.lat);

  await expectDrawn(page, (image) => {
    // An open finding is a filled circle in its tier's colour, with a dark outline.
    expect(colourDistance(near(image, probable), TIER.probable), "probable finding fill").toBeLessThanOrEqual(10);
    expect(countColour(image, around(probable, 10), OUTLINE, 40), "dark outline pixels").toBeGreaterThan(20);
    // With its light ring and dark outline it reaches 10.5 px, so it is gone 12 px out.
    expect(colourDistance(near(image, probable, 12, 0), BACKDROP), "beyond the circle").toBeLessThanOrEqual(6);

    // A known finding is a hollow ring: backdrop in the middle, tier colour on the ring.
    expect(colourDistance(near(image, known), BACKDROP), "middle of the known ring").toBeLessThanOrEqual(6);
    expect(countColour(image, around(known, 9), TIER.seen, 14), "ring pixels in the tier colour").toBeGreaterThan(30);

    // Records are squares in their category's colour. A square fills the whole box its width and height
    // span, where a round marker of the same size would fill about 79% of it.
    expect(colourDistance(near(image, designation), DESIGNATION), "designation record").toBeLessThanOrEqual(10);
    expect(colourDistance(near(image, find), FIND), "find record").toBeLessThanOrEqual(10);
    const shape = filledShare(image, designation, DESIGNATION);
    expect(shape.width, "width of the square").toBeGreaterThanOrEqual(5);
    expect(shape.share, "share of its box the square fills").toBeGreaterThan(0.9);
    // The same measure tells a round marker apart: the probable finding's fill is a circle.
    expect(filledShare(image, probable, TIER.probable, 10).share, "share a circle fills").toBeLessThan(0.86);

    // Ruled-out findings are hidden until asked for.
    expect(countColour(image, around(ruled, 8), BACKDROP, 6), "nothing where the ruled-out finding is").toBe(17 * 17);
  });
});

test("draws a protected finding sent obscured as a dashed one-kilometre square, never a point", async ({ page }) => {
  await openWithMarkers(page);
  const point = project(OBSCURED.lon, OBSCURED.lat);
  const square = kmSquareAt(OBSCURED.lon, OBSCURED.lat);
  if (!square) throw new Error("The obscured test point is off the grid");
  const corners = square.ring.slice(0, 4).map(([lon, lat]) => project(lon, lat));
  // The ring runs south-west, south-east, north-east, north-west.
  const [southWest, southEast, , northWest] = corners as [
    { x: number; y: number },
    { x: number; y: number },
    { x: number; y: number },
    { x: number; y: number },
  ];
  // A kilometre is about 670 px at this zoom and latitude, so the square overflows the window a little.
  expect(southEast.x - southWest.x).toBeGreaterThan(600);
  expect(southEast.x - southWest.x).toBeLessThan(740);

  // The server sends the centre of the square. No marker is drawn there either.
  const sent = findings().features.find((f) => f.properties.public_id === "d");
  if (!sent?.properties.obscured) throw new Error("The fixture did not obscure the finding");
  const centre = project(...sent.geometry.coordinates);

  await expectDrawn(page, (image) => {
    // No marker at the finding's own position, nor at the centre of its square.
    expect(countColour(image, around(point, 8), BACKDROP, 6), "no point at the finding").toBe(17 * 17);
    if (centre.x > 20 && centre.x < VIEW.width - 20 && centre.y > 20 && centre.y < VIEW.height - 20) {
      expect(countColour(image, around(centre, 8), BACKDROP, 6), "no point at the square's centre").toBe(17 * 17);
    }

    // The west edge crosses the screen as a line in the tier colour, broken by gaps.
    const visibleTop = Math.max(northWest.y, 80);
    const visibleBottom = Math.min(southWest.y, VIEW.height - 80);
    expect(visibleBottom - visibleTop, "length of west edge on screen").toBeGreaterThan(200);
    const edgeX = (y: number): number =>
      northWest.x + ((southWest.x - northWest.x) * (y - northWest.y)) / (southWest.y - northWest.y);
    let coloured = 0;
    let gaps = 0;
    let rows = 0;
    for (let y = Math.ceil(visibleTop) + 10; y < visibleBottom - 10; y++) {
      const hit = countColour(image, { x: Math.round(edgeX(y)) - 3, y, width: 7, height: 1 }, TIER.corroborated, 30);
      rows += 1;
      if (hit > 0) coloured += 1;
      else gaps += 1;
    }
    expect(coloured / rows, "share of the edge that is dash").toBeGreaterThan(0.35);
    expect(gaps / rows, "share of the edge that is gap").toBeGreaterThan(0.2);

    // And it is a square: the south edge is there too, running east from the same corner.
    const southY = (x: number): number =>
      southWest.y + ((southEast.y - southWest.y) * (x - southWest.x)) / (southEast.x - southWest.x);
    let southHits = 0;
    const from = Math.max(Math.ceil(southWest.x) + 20, 80);
    const to = Math.min(Math.floor(southEast.x) - 20, VIEW.width - 80);
    expect(to - from, "length of south edge on screen").toBeGreaterThan(200);
    for (let x = from; x < to; x++) {
      if (countColour(image, { x, y: Math.round(southY(x)) - 3, width: 1, height: 7 }, TIER.corroborated, 30) > 0) {
        southHits += 1;
      }
    }
    expect(southHits / (to - from), "share of the south edge that is dash").toBeGreaterThan(0.35);
  });
});

test("draws an obscured square whose centre is off screen when its body covers the view", async ({ page }) => {
  const collection = findings();
  const sent = collection.features.find((f) => f.properties.public_id === "d");
  if (!sent?.properties.obscured) throw new Error("The fixture did not obscure the finding");
  const [centreLon, centreLat] = sent.geometry.coordinates;
  const log = await serveFindings(page, collection);
  await serveRecordTiles(page, []);
  // Zoom 18 shows about 540 m by 340 m. Centre the view 400 m east and 300 m north of the square's centre:
  // inside the square, with the centre well outside the view.
  const view = offset(400, 300, { lon: centreLon, lat: centreLat });
  await openMap(
    page,
    `/?panel=none#m=18/${view.lat}/${view.lon}/0/0&v=composite&s=315/25&x=2&t=0/1.5&o=osm:80:h,findings:100`,
  );

  await expect(async () => {
    const image = decodePng(await page.screenshot());
    const drawn = countColour(image, { x: 0, y: 0, width: VIEW.width, height: VIEW.height }, TIER.corroborated, 30);
    expect(drawn, "pixels of the square's edge on screen").toBeGreaterThan(200);
  }).toPass({ timeout: 15_000 });

  const asked = log.boxes.at(-1);
  if (!asked) throw new Error("No findings request was made");
  expect(asked[0] <= centreLon && centreLon <= asked[2], "the request covers the square's centre east to west").toBe(
    true,
  );
  expect(asked[1] <= centreLat && centreLat <= asked[3], "the request covers the square's centre south to north").toBe(
    true,
  );
});

test("shows ruled-out findings as small grey rings when asked", async ({ page }) => {
  await openWithMarkers(page, "&r=1");
  const ruled = project(RULED.lon, RULED.lat);
  await expectDrawn(page, (image) => {
    expect(colourDistance(near(image, ruled), BACKDROP), "middle of the ruled-out ring").toBeLessThanOrEqual(6);
    expect(countColour(image, around(ruled, 7), RULED_OUT, 14), "grey ring pixels").toBeGreaterThan(12);
    // Grey, not the colour of its tier.
    expect(countColour(image, around(ruled, 7), TIER.probable, 14), "tier-coloured pixels").toBe(0);
  });
});

test("hides an overlay when it is switched off", async ({ page }) => {
  await openWithMarkers(page);
  const probable = project(PROBABLE.lon, PROBABLE.lat);
  const designation = project(RECORD_DESIGNATION.lon, RECORD_DESIGNATION.lat);
  await expectDrawn(page, (image) => {
    expect(colourDistance(near(image, probable), TIER.probable)).toBeLessThanOrEqual(10);
  });

  await page.getByRole("button", { name: "Layers" }).click();
  const panel = page.getByRole("complementary", { name: "Layers" });
  await panel.getByRole("switch", { name: "Findings", exact: true }).uncheck();
  await expectDrawn(page, (image) => {
    expect(colourDistance(near(image, probable), BACKDROP), "finding gone").toBeLessThanOrEqual(6);
    expect(colourDistance(near(image, designation), DESIGNATION), "record still there").toBeLessThanOrEqual(10);
  });

  // Half opacity blends the record with the backdrop.
  await panel.locator('[data-overlay="records"]').getByRole("slider", { name: "Opacity" }).fill("50");
  await expectDrawn(page, (image) => {
    const drawn = near(image, designation);
    const half = blend(categoryColour("designation"), BACKDROP, RECORD_SQUARE_OPACITY / 2);
    expect(colourDistance(drawn, half), "record at half opacity").toBeLessThanOrEqual(14);
  });
});

/** The middle of the pixels near `colour` in a region, or null if there are fewer than `least`. */
function centreOf(
  image: DecodedImage,
  region: { x: number; y: number; width: number; height: number },
  colour: Rgb,
  least = 12,
): { x: number; y: number } | null {
  let sumX = 0;
  let sumY = 0;
  let count = 0;
  for (let y = region.y; y < region.y + region.height; y++) {
    for (let x = region.x; x < region.x + region.width; x++) {
      if (colourDistance(pixelAt(image, x, y), colour) <= 12) {
        sumX += x;
        sumY += y;
        count += 1;
      }
    }
  }
  return count >= least ? { x: sumX / count, y: sumY / count } : null;
}

for (const terrain of ["flat", "3D"] as const) {
  test(`keeps the comparison pane in step while the main one is dragged, ${terrain}`, async ({ page }) => {
    // One record each side of the divide: the left one is drawn by the main pane, the right one by the comparison.
    const left = offset(-260, 0);
    const right = offset(260, 0);
    await serveFindings(page, findingCollection([]));
    await serveRecordTiles(page, [
      { ...left, properties: { id: 1, category: "designation" } },
      { ...right, properties: { id: 2, category: "designation" } },
    ]);
    const camera = terrain === "3D" ? "0/50" : "0/0";
    // Two panes of terrain in 3D are the slowest thing the suite draws. In software a frame takes
    // 3 to 5 seconds on a CI runner, and the drag alone is a dozen moves of two frames each. The
    // test took 2.1 minutes on a quick runner and ran out of three on a slow one, still drawing,
    // so it gets eight: about twice what that slow run would have needed.
    const wait = terrain === "3D" ? SLOW_MAP : undefined;
    if (terrain === "3D") test.setTimeout(480_000);
    await openMap(
      page,
      `/?panel=none#m=${ZOOM}/${CENTRE.lat}/${CENTRE.lon}/${camera}&v=composite&c=osm_standard&s=315/25&x=2&t=${terrain === "3D" ? 1 : 0}/1.5&o=osm:80:h,records:100`,
      wait,
    );
    await expect(page.locator(".fc-map__pane--compare canvas")).toBeVisible();
    for (const pane of await page.locator(".fc-map__pane").all()) {
      await expect(pane).toHaveAttribute("data-map-idle", "true", wait);
    }

    const halves = {
      left: { x: 80, y: 80, width: VIEW.width / 2 - 100, height: VIEW.height - 160 },
      right: { x: VIEW.width / 2 + 20, y: 80, width: VIEW.width / 2 - 100, height: VIEW.height - 160 },
    };
    const find = async () => {
      let found: { left: { x: number; y: number }; right: { x: number; y: number } } | null = null;
      await expect(async () => {
        const image = decodePng(await page.screenshot());
        const l = centreOf(image, halves.left, DESIGNATION);
        const r = centreOf(image, halves.right, DESIGNATION_ON_MAP);
        expect(l, "record left of the divide").not.toBeNull();
        expect(r, "record right of the divide").not.toBeNull();
        found = { left: l as { x: number; y: number }, right: r as { x: number; y: number } };
      }).toPass({ timeout: 15_000 });
      if (!found) throw new Error("Records not found");
      return found as { left: { x: number; y: number }; right: { x: number; y: number } };
    };
    const before = await find();

    // Drag the main pane, on the left of the divide, and hold still before letting go so nothing flings on.
    // The drag is level: in a tilted view a drag towards or away from the horizon moves points either side
    // of the centre by different amounts, so only a level one moves both records alike.
    const start = { x: VIEW.width / 4, y: VIEW.height / 2 + 120 };
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(start.x + 110, start.y, { steps: 12 });
    await page.waitForTimeout(300);
    await page.mouse.up();
    for (const pane of await page.locator(".fc-map__pane").all()) {
      await expect(pane).toHaveAttribute("data-map-idle", "true", wait);
    }
    await page.waitForTimeout(300);
    const after = await find();

    const moved = (a: { x: number; y: number }, b: { x: number; y: number }) => ({ x: b.x - a.x, y: b.y - a.y });
    const main = moved(before.left, after.left);
    const follower = moved(before.right, after.right);
    expect(Math.hypot(main.x, main.y), "the main pane moved").toBeGreaterThan(40);
    // Both records are at the same depth, so the same camera moves them the same way, to within a pixel or two.
    expect(Math.abs(follower.x - main.x), `comparison pane x: ${follower.x} against ${main.x}`).toBeLessThanOrEqual(3);
    expect(Math.abs(follower.y - main.y), `comparison pane y: ${follower.y} against ${main.y}`).toBeLessThanOrEqual(3);
  });
}
