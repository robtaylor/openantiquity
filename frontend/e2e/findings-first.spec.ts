import type { Page } from "@playwright/test";
import { findingCollection } from "../src/test/fixtures/findings.js";
import { TIER_COLOURS } from "../src/ui/tokens.js";
import { openMap } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";
import { CENTRE, offset, serveRecordTiles } from "./support/markerTiles.js";
import { apiRoute } from "./support/network.js";
import { colourDistance, countColour, decodePng, hexToRgb, pixelAt, type Rgb } from "./support/png.js";

/**
 * The map puts findings first: they are drawn and listed at every zoom, and
 * the map says when it was sent fewer than there are in view. Zoomed-out
 * counts of heritage records are a choice in the Layers panel, off until
 * asked for. Fixture mode, at desktop and phone width.
 */

const PROBABLE = hexToRgb(TIER_COLOURS.probable as string);

function hash(zoom: number, extra = ""): string {
  return `#m=${zoom}/${CENTRE.lat}/${CENTRE.lon}/0/0&v=composite&s=315/25&x=2&t=0/1.5&o=osm:80:h,records:100:h,findings:100${extra}`;
}

/** A probable finding at the centre and a spotted one 40 km away, answered with `nextCursor`, logging each box. */
async function serveFindings(page: Page, nextCursor: () => string | null): Promise<URL[]> {
  const asked: URL[] = [];
  const collection = findingCollection([
    { at: CENTRE, public_id: "centre", tier: "probable" },
    { at: offset(40_000, 0), public_id: "far", tier: "spotted" },
  ]);
  await page.route(apiRoute("/findings"), (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("format") !== "geojson") return route.fallback();
    asked.push(url);
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...collection, next_cursor: nextCursor() }),
    });
  });
  return asked;
}

/** The middle of the main map, where the address centres it. */
async function mapCentre(page: Page): Promise<{ x: number; y: number }> {
  const box = await page.locator(".fc-map__pane--main canvas").boundingBox();
  if (!box) throw new Error("The map is not on screen");
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

test("draws findings when zoomed out to a county or more", async ({ page }) => {
  const asked = await serveFindings(page, () => null);
  await openMap(page, `/?panel=none${hash(7)}`);
  const centre = await mapCentre(page);
  await expect(async () => {
    const image = decodePng(await page.screenshot());
    expect(colourDistance(pixelAt(image, centre.x, centre.y), PROBABLE), "the finding's marker").toBeLessThanOrEqual(
      12,
    );
  }).toPass({ timeout: 15_000 });
  // The box is asked for at the furthest-out zoom the server simplifies shapes for.
  expect(asked.at(-1)?.searchParams.get("zoom")).toBe("9");
  await expect(page.getByTestId("findings-cut-short-notice")).toHaveCount(0);
});

test("says so when not every finding in view is drawn, until the answer is whole", async ({ page }) => {
  let cut = true;
  const asked = await serveFindings(page, () => (cut ? "next" : null));
  await openMap(page, `/?panel=none${hash(7)}`);
  const notice = page.getByRole("status").filter({ hasText: "Not every finding in view is drawn" });
  await expect(notice).toHaveText("Not every finding in view is drawn. Zoom in to see the rest.");
  // What was sent is drawn, and the rest isn't paged through.
  const centre = await mapCentre(page);
  await expect(async () => {
    const image = decodePng(await page.screenshot());
    expect(colourDistance(pixelAt(image, centre.x, centre.y), PROBABLE)).toBeLessThanOrEqual(12);
  }).toPass({ timeout: 15_000 });
  expect(asked.every((url) => !url.searchParams.has("cursor"))).toBe(true);

  cut = false;
  await page.goto(`/?panel=none${hash(13)}`);
  await expect(notice).toHaveCount(0);
});

/** The stubbed terrain tiles are this grey, so anything else in a patch was drawn over them. */
const BACKDROP: Rgb = [128, 128, 128];
const COUNTS_ZOOM = 10.5;
/** A count 6 km north of the centre, about 180 px above it: clear of the notices and the phone's sheet. */
const COUNT_NORTH_M = 6_000;
const COUNT_AT = offset(0, COUNT_NORTH_M);

/** How many pixels in a patch round the count differ from the backdrop. */
async function drawnAtCount(page: Page): Promise<number> {
  const centre = await mapCentre(page);
  const metresPerPixel = (40_075_016.686 * Math.cos((CENTRE.lat * Math.PI) / 180)) / (512 * 2 ** COUNTS_ZOOM);
  const y = centre.y - COUNT_NORTH_M / metresPerPixel;
  const image = decodePng(await page.screenshot());
  const patch = { x: Math.round(centre.x) - 12, y: Math.round(y) - 12, width: 25, height: 25 };
  return patch.width * patch.height - countColour(image, patch, BACKDROP, 24);
}

test("keeps zoomed-out record counts off until they're switched on, and through a reload", async ({ page }) => {
  await serveRecordTiles(
    page,
    [{ ...COUNT_AT, properties: { category: "designation", count: 240, sources: "nhle-scheduled" } }],
    "record_counts",
  );
  const view = `#m=${COUNTS_ZOOM}/${CENTRE.lat}/${CENTRE.lon}/0/0&v=composite&s=315/25&x=2&t=0/1.5&o=osm:80:h,records:100,findings:100:h`;
  await openMap(page, `/?panel=layers${view}`);
  const counts = page.getByRole("switch", { name: "Counts when zoomed out" });
  await expect(counts).not.toBeChecked();
  await expect(
    page.getByText("Records are shown from closer in. Zoom in to see them, or turn on counts."),
  ).toBeVisible();
  // Give the tiles time to arrive, then check nothing was drawn where the count is.
  await page.locator('.fc-map__pane--main[data-map-idle="true"]').waitFor();
  expect(await drawnAtCount(page), "pixels drawn where the count would be").toBe(0);

  await counts.click();
  await expect(counts).toBeChecked();
  await expect(page).toHaveURL(/&rc=1/);
  await expect(async () => expect(await drawnAtCount(page)).toBeGreaterThan(40)).toPass({ timeout: 15_000 });

  await page.reload();
  await expect(page.locator(".fc-map")).toHaveAttribute("data-ready", "true");
  await expect(page.getByRole("switch", { name: "Counts when zoomed out" })).toBeChecked();
  await expect(async () => expect(await drawnAtCount(page)).toBeGreaterThan(40)).toPass({ timeout: 15_000 });
});

test("fetches no records tile while zoomed out with counts off, and only far tiles' counts once they're on", async ({
  page,
}) => {
  const asked: number[] = [];
  page.on("request", (request) => {
    const match = /\/tiles\/records\/(\d+)\//.exec(request.url());
    if (match) asked.push(Number(match[1]));
  });
  await openMap(page, `/?panel=layers#m=9/${CENTRE.lat}/${CENTRE.lon}/0/0&v=composite&o=osm:80:h,records:100`);
  await page.locator('.fc-map__pane--main[data-map-idle="true"]').waitFor();
  expect(asked, "records tiles fetched with counts off").toEqual([]);
  await page.getByRole("switch", { name: "Counts when zoomed out" }).click();
  await expect.poll(() => asked.length).toBeGreaterThan(0);
  expect(Math.max(...asked)).toBeLessThan(12);
});
