import { openMap } from "../e2e/support/app.js";
import { tilesRoute } from "../e2e/support/network.js";
import { expect, test } from "./support/fixtures.js";

/**
 * Terrain tiles the server is too busy to draw, in a real browser with the
 * real catalogue, which names this server's own tile addresses. Fixture mode
 * can't show this: its terrain comes from other people's servers.
 *
 * The server draws a few tiles at once and answers the rest 503 with a
 * `Retry-After` (`terrain/workers.py`). A map jumping to ground nobody had
 * looked at got a screenful of those, never asked again, and reported the
 * layer as not loading.
 */

// A one-pixel transparent PNG, which the map stretches over the tile.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

// The map's own second attempt at a troubled layer comes after 3 s, and its report after that.
const LONG_ENOUGH_TO_REPORT_MS = 12_000;

test("asks again for terrain tiles the server puts off, and doesn't call the layer broken", async ({ page }) => {
  const asked = new Map<string, number>();
  let putOff = 0;
  await page.route(tilesRoute("/lidar/"), (route) => {
    const url = route.request().url();
    const times = (asked.get(url) ?? 0) + 1;
    asked.set(url, times);
    // Each tile is put off twice before it is drawn, as on a server busy with a screenful.
    if (times <= 2) {
      putOff += 1;
      return route.fulfill({
        status: 503,
        headers: { "Retry-After": "1" },
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "tiles_busy", message: "Busy." } }),
      });
    }
    return route.fulfill({ status: 200, contentType: "image/png", body: PNG });
  });

  await openMap(page);

  await expect.poll(() => asked.size, { message: "terrain tiles asked for" }).toBeGreaterThan(0);
  await expect
    .poll(() => [...asked.values()].every((times) => times >= 3), {
      message: "every tile put off was asked for until it was drawn",
      timeout: LONG_ENOUGH_TO_REPORT_MS,
    })
    .toBe(true);
  expect(putOff).toBeGreaterThan(0);

  // Long enough for the map to have tried the layer again and reported it, had the tiles failed.
  await page.waitForTimeout(LONG_ENOUGH_TO_REPORT_MS);
  await expect(page.getByRole("alert")).toHaveCount(0);
  // Each tile was asked for three times and no more: nothing reloaded the whole layer.
  expect(Math.max(...asked.values())).toBe(3);
});
