import type { Page } from "@playwright/test";
import { findingCollection } from "../src/test/fixtures/findings.js";
import { TIER_COLOURS } from "../src/ui/tokens.js";
import { openMap } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";
import { CENTRE, offset } from "./support/markerTiles.js";
import { apiRoute } from "./support/network.js";
import { colourDistance, decodePng, hexToRgb, pixelAt } from "./support/png.js";

/**
 * The map puts findings first: they are drawn and listed at every zoom, and
 * the map says when it was sent fewer than there are in view. Fixture mode,
 * at desktop and phone width.
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
