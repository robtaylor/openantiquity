import { openMap } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";
import { apiRoute, tilesRoute } from "./support/network.js";

/**
 * What the map does when things go wrong: a control pressed twice in a
 * hurry, tiles that fail, a TileJSON that fails. The map prints a console
 * warning for each kind of failure, which is expected here, so only page
 * errors count against a test.
 */

test.use({ pageProblems: "page-errors" });

test.describe("when things go wrong", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) < 720, "one layout is enough for these");

  /** Longer than the map's own waits put together: judge, pause, second attempt, judge again. */
  const REPORTED_WITHIN_MS = 15_000;

  test("survives the comparison switch being pressed twice in a hurry", async ({ page }) => {
    await openMap(page, "/?panel=layers");
    const panel = page.getByRole("complementary", { name: "Layers" });
    const toggle = panel.getByRole("switch", { name: "Compare two layers" });

    // The second press used to land as the second map finished loading, and blank the whole app.
    for (const delay of [0, 20, 40, 60, 90, 120, 180]) {
      await toggle.dblclick({ delay });
      await page.waitForTimeout(250);
      await expect(page.locator(".fc-shell"), `after a double click ${delay} ms apart`).toBeVisible();
      await expect(page.getByRole("alert")).toHaveCount(0);
      await expect(toggle).not.toBeChecked();
      await expect(page.locator(".fc-map__pane--compare")).toHaveCount(0);
    }

    await toggle.focus();
    await page.keyboard.press("Space");
    await page.keyboard.press("Space");
    await page.waitForTimeout(250);
    await expect(page.locator(".fc-shell")).toBeVisible();
    await expect(toggle).not.toBeChecked();

    // And the comparison still works afterwards.
    await toggle.check();
    await expect(page.locator(".fc-map__pane--compare canvas")).toBeVisible();
    await expect(page.locator(".fc-map")).toHaveAttribute("data-ready", "true");
  });

  test("says so, and offers another attempt, when the view's tiles fail", async ({ page, network }) => {
    let failing = true;
    await page.route(/^https:\/\/environment\.data\.gov\.uk\//, (route) =>
      failing ? route.fulfill({ status: 500 }) : route.fallback(),
    );
    await openMap(page);

    const notice = page.getByRole("alert").filter({ hasText: "The Composite layer isn't loading." });
    await expect(notice).toBeVisible({ timeout: REPORTED_WITHIN_MS });

    // The tiles now answer, but one after another. While some are drawn and
    // others are still on their way, a map that had marked the failed ones
    // drawable throws from its painter on every frame.
    failing = false;
    let answered = 0;
    await page.route(/^https:\/\/environment\.data\.gov\.uk\//, async (route) => {
      answered += 1;
      await new Promise((resolve) => setTimeout(resolve, answered * 120));
      await route.fallback();
    });
    const before = network.served.lidar ?? 0;
    await notice.getByRole("button", { name: "Try again" }).click();
    await expect(notice).toHaveCount(0);
    await expect.poll(() => network.served.lidar ?? 0, { message: "tiles fetched again" }).toBeGreaterThan(before + 3);
    await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-map-idle", "true");
    // It stays gone: the second attempt worked.
    await page.waitForTimeout(2500);
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("draws raking light again, without errors, when its height data recovers", async ({ page, network }) => {
    // The hillshade painter is the other one that threw on a failed tile marked drawable.
    let failing = true;
    await page.route(/^https:\/\/s3\.amazonaws\.com\//, (route) =>
      failing ? route.fulfill({ status: 500 }) : route.fallback(),
    );
    await openMap(page, "/#m=15/51.4286/-1.8542/0/0&v=raking&s=300/18&x=3&t=0/1.5&o=osm:60");

    const notice = page.getByRole("alert").filter({ hasText: "The height data isn't loading" });
    await expect(notice).toBeVisible({ timeout: REPORTED_WITHIN_MS });

    failing = false;
    let answered = 0;
    await page.route(/^https:\/\/s3\.amazonaws\.com\//, async (route) => {
      answered += 1;
      await new Promise((resolve) => setTimeout(resolve, answered * 120));
      await route.fallback();
    });
    const before = network.served.dem ?? 0;
    await notice.getByRole("button", { name: "Try again" }).click();
    await expect(notice).toHaveCount(0);
    await expect
      .poll(() => network.served.dem ?? 0, { message: "height tiles fetched again" })
      .toBeGreaterThan(before + 3);
    await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-map-idle", "true");
    await page.waitForTimeout(2500);
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("leaves an overlay on when one of its tiles fails", async ({ page }) => {
    let failed = 0;
    let served = 0;
    await page.route(tilesRoute("/records/"), (route) => {
      if (failed === 0) {
        failed += 1;
        return route.fulfill({ status: 500 });
      }
      served += 1;
      return route.fulfill({ status: 204 });
    });
    await openMap(page, "/?panel=layers");
    await expect.poll(() => served, { message: "other records tiles answered" }).toBeGreaterThan(3);
    expect(failed).toBe(1);

    // Long enough for the map to have judged, retried and judged again, had it been going to.
    await page.waitForTimeout(7000);
    await expect(page.getByRole("alert")).toHaveCount(0);
    const row = page.locator('[data-overlay="records"]');
    await expect(row.getByRole("switch", { name: "Heritage records", exact: true })).toBeChecked();
    await expect(row.getByText(/isn't loading/)).toHaveCount(0);
    await expect(row.getByRole("slider", { name: "Heritage records opacity" })).toBeVisible();
  });

  test("carries on without a word when the findings and point endpoints are not built yet", async ({ page }) => {
    let findingsAsked = 0;
    let pointAsked = 0;
    await page.route(apiRoute("/findings"), (route) => {
      findingsAsked += 1;
      return route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"Not Found"}' });
    });
    await page.route(apiRoute("/geo/point"), (route) => {
      pointAsked += 1;
      return route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"Not Found"}' });
    });
    await openMap(page, "/?panel=layers");
    await expect.poll(() => findingsAsked).toBe(1);
    await expect.poll(() => pointAsked).toBe(1);

    // Moving the map and resting the pointer ask neither again.
    const canvas = page.locator(".fc-map__pane--main canvas");
    const box = await canvas.boundingBox();
    if (!box) throw new Error("No map canvas");
    await page.mouse.move(box.x + box.width / 3, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 3 + 120, box.y + box.height / 2 + 40, { steps: 6 });
    await page.mouse.up();
    await page.waitForTimeout(1500);
    expect(findingsAsked).toBe(1);
    expect(pointAsked).toBe(1);

    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(page.locator('[data-overlay="findings"]').getByText(/isn't loading/)).toHaveCount(0);
    await expect(page.getByTestId("status-height")).toHaveCount(0);
    await expect(page.getByTestId("status-gridref")).toHaveText(/^SU \d{3} \d{3}$/);
    await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-map-idle", "true");
  });

  test("switches an overlay off with a notice when all its tiles fail, and brings it back on request", async ({
    page,
  }) => {
    let failing = true;
    let served = 0;
    await page.route(tilesRoute("/records/"), (route) => {
      if (failing) return route.fulfill({ status: 500 });
      served += 1;
      return route.fulfill({ status: 204 });
    });
    await openMap(page);

    // The layer panel is closed. The notice is on the map all the same.
    const notice = page.getByRole("alert").filter({ hasText: "The Heritage records layer isn't loading" });
    await expect(notice).toBeVisible({ timeout: REPORTED_WITHIN_MS });

    failing = false;
    await notice.getByRole("button", { name: "Try again" }).click();
    await expect(notice).toHaveCount(0);
    await expect.poll(() => served, { message: "records tiles fetched again" }).toBeGreaterThan(0);
    await page.getByRole("button", { name: "Layers" }).click();
    const row = page.locator('[data-overlay="records"]');
    await expect(row.getByRole("slider", { name: "Heritage records opacity" })).toBeVisible();
    await expect(row.getByText(/isn't loading/)).toHaveCount(0);
  });

  test("says the layer catalogue is at fault when the map refuses the style built from it", async ({ page }) => {
    // A colour name that looks like one but is not. It gets past the check on /meta, and MapLibre refuses the style.
    await page.route(/\/src\/test\/fixtures\/meta\.ts/, async (route) => {
      const response = await route.fetch();
      const body = await response.text();
      expect(body).toContain('"#d9544d"');
      await route.fulfill({ response, body: body.replace('"#d9544d"', '"notacolour"') });
    });
    await page.goto("/");
    const alert = page.getByRole("alert");
    await expect(alert).toContainText("The map's layers couldn't be set up");
    await expect(alert).toContainText("Could not parse color from value 'notacolour'");
    await expect(alert).not.toContainText("WebGL");
    await expect(alert.getByRole("button", { name: "Reload the page" })).toBeVisible();
    // The shell is still there round it.
    await expect(page.getByRole("navigation", { name: "Modes" })).toBeVisible();
  });

  test("fetches failed street-map tiles again when its TileJSON was fine", async ({ page }) => {
    // MapLibre 6.17 leaves a failed vector tile waiting for good when the
    // source is reloaded by its public calls. See reloadSource.ts.
    let failing = true;
    let served = 0;
    await page.route(/^https:\/\/tiles\.openfreemap\.org\/planet\/stub\//, (route) => {
      if (failing) return route.fulfill({ status: 500 });
      served += 1;
      return route.fulfill({ status: 204 });
    });
    await openMap(page);

    const notice = page.getByRole("alert").filter({ hasText: "The OpenStreetMap layer isn't loading" });
    await expect(notice).toBeVisible({ timeout: REPORTED_WITHIN_MS });

    failing = false;
    await notice.getByRole("button", { name: "Try again" }).click();
    await expect(notice).toHaveCount(0);
    await expect.poll(() => served, { message: "street-map tiles fetched again" }).toBeGreaterThan(0);
    await page.waitForTimeout(2500);
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("fetches a failed TileJSON again when asked to try again", async ({ page, network }) => {
    let tileJsonRequests = 0;
    let failing = true;
    await page.route("https://tiles.openfreemap.org/planet", (route) => {
      tileJsonRequests += 1;
      return failing ? route.fulfill({ status: 503 }) : route.fallback();
    });
    await openMap(page, "/?panel=layers");

    const notice = page.getByRole("alert").filter({ hasText: "The OpenStreetMap layer isn't loading" });
    await expect(notice).toBeVisible({ timeout: REPORTED_WITHIN_MS });
    // Once when the map started, and once more unprompted.
    expect(tileJsonRequests).toBe(2);
    const row = page.locator('[data-overlay="osm"]');
    await expect(row.getByText(/isn't loading/)).toBeVisible();

    failing = false;
    await row.getByRole("button", { name: "Try again" }).click();
    await expect(notice).toHaveCount(0);
    // Reloading tiles would never have asked for the TileJSON again. This does, and then the tiles follow.
    await expect.poll(() => tileJsonRequests, { message: "TileJSON fetched again" }).toBe(3);
    await expect
      .poll(() => network.served["osm-vector"] ?? 0, { message: "vector tiles requested" })
      .toBeGreaterThan(0);
    await expect(row.getByRole("slider", { name: "OpenStreetMap opacity" })).toBeVisible();
    await expect(row.getByText(/isn't loading/)).toHaveCount(0);
  });
});
