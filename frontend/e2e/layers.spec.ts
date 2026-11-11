import type { Locator, Page } from "@playwright/test";
import { openMap, tabTo } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";
import { serveBorderCoverage, serveProfile } from "./support/terrain.js";

/**
 * The layer panel and the terrain tools: previews and credits, the height
 * profile by mouse and by keyboard, 3D on and off, and where one-metre
 * elevation exists. Fixture mode, with the terrain API answered by stand-ins.
 */

const AVEBURY = "#m=16/51.4286/-1.851/0/0&v=composite&o=osm:80:h,records:100:h,findings:100:h";

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

/** Click, or on a phone tap, the main map at a screen position. */
async function pressMap(page: Page, position: { x: number; y: number }): Promise<void> {
  const canvas = page.locator(".fc-map__pane--main canvas");
  if (isPhone(page)) await canvas.tap({ position });
  else await canvas.click({ position });
}

/** The panel, or on a phone the sheet, with this title. */
function panel(page: Page, title: string): Locator {
  return page.locator(".fc-panel").filter({ has: page.getByRole("heading", { name: title, level: 2 }) });
}

/** Two points across the middle of the map, above the phone's sheet. */
function linePoints(page: Page): Array<{ x: number; y: number }> {
  const size = page.viewportSize() ?? { width: 1440, height: 900 };
  const y = isPhone(page) ? 200 : size.height / 2;
  const middle = isPhone(page) ? size.width / 2 : (size.width - 400) / 2;
  return [
    { x: middle - 120, y },
    { x: middle + 120, y },
  ];
}

test.describe("the layer panel", () => {
  test("lists each terrain view with a preview, the composite first, and credits what is on", async ({ page }) => {
    await openMap(page, `/?panel=layers${AVEBURY}`);
    const layers = panel(page, "Layers");
    const terrain = layers.getByRole("group", { name: "Terrain from LIDAR" });
    await expect(terrain.getByRole("radio").first()).toHaveAccessibleName("Composite");
    // Every tiled preview loads, from the view's own address.
    const previews = terrain.locator(".fc-view-preview img");
    await expect(previews).toHaveCount(6);
    for (const preview of await previews.all()) {
      await expect.poll(() => preview.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
    }
    await expect(terrain.locator(".fc-view-preview--raking")).toBeVisible();
    // The credit of the view that's on sits under it.
    await expect(layers.locator(".fc-layer-credit").first()).toContainText("Environment Agency");

    await layers.getByRole("radio", { name: "OpenStreetMap" }).check();
    await expect(page).toHaveURL(/&v=osm_standard&/);
    const credit = layers.locator(".fc-layer-credit", { hasText: "contributors" });
    await expect(credit.getByRole("link", { name: "OpenStreetMap" })).toHaveAttribute(
      "href",
      "https://www.openstreetmap.org/copyright",
    );
  });

  test("works every view in compare and swipe", async ({ page }) => {
    await openMap(page, `/?panel=layers${AVEBURY}`);
    const layers = panel(page, "Layers");
    await layers.getByRole("switch", { name: "Compare two layers" }).check();
    await expect(page.locator(".fc-map__pane--compare canvas")).toBeVisible();
    await layers.getByRole("tab", { name: /^Right/ }).click();
    const views = await layers.getByRole("radio").all();
    expect(views.length).toBeGreaterThan(5);
    for (const view of views) {
      const name = (await view.getAttribute("value")) ?? "";
      await view.check();
      await expect(page.locator(".fc-map__pane--compare")).toHaveAttribute("data-view", name);
    }
  });
});

test.describe("the height profile", () => {
  test("is drawn with the mouse or a finger, and the marker follows along chart and line", async ({ page }) => {
    const log = await serveProfile(page);
    await openMap(page, `/profile${AVEBURY}`);
    const profile = panel(page, "Height profile");
    await expect(profile.getByRole("heading", { name: "Draw a line on the map" })).toBeVisible();

    const [start, end] = linePoints(page) as [{ x: number; y: number }, { x: number; y: number }];
    await pressMap(page, start);
    await expect(profile.getByRole("heading", { name: "Add one more point" })).toBeVisible();
    await pressMap(page, end);
    const chart = profile.getByRole("slider", { name: "Height along the line" });
    await expect(chart).toBeVisible();
    expect(log.requests).toHaveLength(1);
    expect(log.requests[0]?.line.coordinates).toHaveLength(2);
    // The line is in the address, to share.
    await expect(page).toHaveURL(/\/profile\?line=-?[\d.]+,[\d.]+,-?[\d.]+,[\d.]+#/);
    await expect(profile.getByText("every metre")).toBeVisible();

    // Along the chart.
    const box = await chart.boundingBox();
    if (!box) throw new Error("no chart");
    if (!isPhone(page)) {
      await page.mouse.move(box.x + box.width * 0.5, box.y + box.height / 2);
      await expect(profile.getByTestId("profile-chart-marker")).toBeVisible();

      // Along the line on the map, a quarter of the way.
      await page.mouse.move(start.x + (end.x - start.x) / 4, start.y);
      await expect(profile.getByTestId("profile-chart-marker")).toContainText(/^\d+ m along: [\d.]+ m$/);
      await page.mouse.move(start.x, start.y + 150);
      await expect(profile.getByTestId("profile-chart-marker")).toHaveCount(0);
    } else {
      await chart.tap({ position: { x: box.width * 0.5, y: box.height / 2 } });
      await expect(profile.getByTestId("profile-chart-marker")).toBeVisible();
    }

    // Reloading the address brings the same profile back.
    await page.reload();
    await expect(panel(page, "Height profile").getByRole("slider", { name: "Height along the line" })).toBeVisible();
  });

  test("is drawn with the keyboard alone", async ({ page }) => {
    const log = await serveProfile(page);
    await openMap(page, `/profile${AVEBURY}`);
    const profile = panel(page, "Height profile");
    await expect(page.getByTestId("profile-crosshair")).toBeVisible();

    const add = profile.getByRole("button", { name: "Add a point at the cross" });
    await tabTo(page, add);
    await page.keyboard.press("Enter");
    await expect(profile.getByRole("heading", { name: "Add one more point" })).toBeVisible();

    // Move the map with its own arrow keys, then add a second point at the cross.
    await page.locator(".fc-map__pane--main canvas").focus();
    for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowRight");
    await expect(page).not.toHaveURL(/-1\.851\/0\/0/);
    await tabTo(page, add);
    await page.keyboard.press("Enter");
    const chart = profile.getByRole("slider", { name: "Height along the line" });
    await expect(chart).toBeVisible();
    const [first, second] = log.requests[0]?.line.coordinates ?? [];
    expect(second?.[0]).toBeGreaterThan(first?.[0] ?? 0);

    await tabTo(page, chart);
    await page.keyboard.press("ArrowRight");
    await expect(chart).toHaveAttribute("aria-valuetext", /^0 m along, [\d.]+ m high$/);
    await page.keyboard.press("End");
    await expect(chart).toHaveAttribute("aria-valuetext", /^280 m along/);
    await expect(profile.getByTestId("profile-chart-marker")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(profile.getByTestId("profile-chart-marker")).toHaveCount(0);
    await expect(profile).toBeVisible();
  });
});

test.describe("the profile's cross", () => {
  test("sits in the part of the map that shows, clear of the panel, the sheet and the status bar", async ({ page }) => {
    await serveProfile(page);
    await openMap(page, `/profile${AVEBURY}`);
    const cross = await page.getByTestId("profile-crosshair").boundingBox();
    if (!cross) throw new Error("No cross on screen");
    const middle = { x: cross.x + cross.width / 2, y: cross.y + cross.height / 2 };
    // Nothing lies over the cross but the map.
    const onMap = await page.evaluate(
      ({ x, y }) =>
        Boolean(
          document
            .elementsFromPoint(x, y)
            .find((element) => !element.closest(".fc-map-crosshair"))
            ?.closest(".fc-map__pane--main"),
        ),
      middle,
    );
    expect(onMap).toBe(true);
    const sheetOrPanel = await page.locator(".fc-panel").first().boundingBox();
    if (!sheetOrPanel) throw new Error("No panel on screen");
    if (isPhone(page)) expect(middle.y).toBeLessThan(sheetOrPanel.y - 28);
    else expect(middle.x).toBeLessThan(sheetOrPanel.x);
  });
});

test.describe("3D", () => {
  test("tilts in, and goes back to a flat plan view", async ({ page }) => {
    await openMap(page, `/${AVEBURY}`);
    const threeD = page.getByRole("button", { name: "Tilt into 3D" });
    await threeD.click();
    await expect(threeD).toHaveAttribute("aria-pressed", "true");
    await expect(page).toHaveURL(/#m=16\/[\d.-]+\/[\d.-]+\/0\/60&.*\bt=1\//);
    const plan = page.getByRole("button", { name: "Back to plan view" });
    await expect(plan).toBeVisible();
    await plan.click();
    await expect(page).toHaveURL(/#m=16\/[\d.-]+\/[\d.-]+\/0\/0&/);
    await expect(plan).toHaveCount(0);
    // 3D stays on in plan view, and the 3D button turns it off.
    await expect(threeD).toHaveAttribute("aria-pressed", "true");
    await threeD.click();
    await expect(threeD).toHaveAttribute("aria-pressed", "false");
    await expect(page).toHaveURL(/\bt=0\//);
  });
});

test.describe("coverage", () => {
  test("shades the squares with no data, says so, and outlines where the data is", async ({ page }) => {
    await serveBorderCoverage(page);
    await openMap(page, "/?panel=layers#m=12/51.68/-2.73/0/0&v=composite&o=osm:80:h,records:100:h,findings:100:h");
    await expect(page.getByTestId("coverage-notice")).toContainText("Shaded squares have no one-metre LIDAR");
    const layers = panel(page, "Layers");
    await layers.getByRole("switch", { name: "Where there's one-metre LIDAR" }).check();
    await expect(layers.getByTestId("coverage-summary")).toContainText(
      /In view: 2022 composite, flown between 2005 and 2022, with \d+ of \d+/,
    );

    // On a map that isn't drawn from the elevation, there is nothing to shade.
    await layers.getByRole("radio", { name: "OpenStreetMap" }).check();
    await expect(page.getByTestId("coverage-notice")).toHaveCount(0);
  });
});
