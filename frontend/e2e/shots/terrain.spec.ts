import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, type Page, test } from "@playwright/test";

/**
 * Terrain against the real backend: every terrain view at Avebury from zoom
 * 13 to 16, and Fyfield Down, the plan's exit test for terrain. Nothing is
 * stubbed, so run it against a dev server that proxies to a backend with the
 * Avebury tiles mirrored:
 *
 *   FIELDCLUB_API_URL=http://localhost:6231 pnpm dev --port 7231
 *   FIELDCLUB_E2E_PORT=7231 pnpm shots e2e/shots/terrain.spec.ts
 *
 * Set FIELDCLUB_TERRAIN_SHOTS=1 to take them. Without it they are skipped, so
 * `pnpm shots` with no backend still runs the fixture shots.
 */

test.skip(process.env.FIELDCLUB_TERRAIN_SHOTS !== "1", "needs a real backend: set FIELDCLUB_TERRAIN_SHOTS=1");

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const AVEBURY = { lat: 51.4286, lng: -1.8542 };
const FYFIELD = { lat: 51.435, lng: -1.795 };
const VIEWS = ["composite", "local_relief", "sky_view", "multi_shade", "slope", "raking"];
/** Everything over the terrain is off, so the pictures show the ground alone. */
const BARE = "o=osm:80:h,records:100:h,findings:100:h";

function hash(where: { lat: number; lng: number }, zoom: number, view: string, extra = ""): string {
  return `#m=${zoom}/${where.lat}/${where.lng}/0/0&v=${view}&${BARE}${extra}`;
}

async function settle(page: Page): Promise<void> {
  await expect(page.locator(".fc-map")).toHaveAttribute("data-ready", "true");
  // The first view of an area renders every tile, which takes a while on a busy machine.
  await page.locator('.fc-map__pane--main[data-map-idle="true"]').waitFor({ timeout: 60_000 });
  await page.waitForTimeout(500);
}

async function shoot(page: Page, name: string): Promise<void> {
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `terrain-${name}-${size?.width}x${size?.height}.png`) });
}

for (const view of VIEWS) {
  test(`Avebury in ${view}, zoom 13 to 16`, async ({ page }) => {
    test.setTimeout(300_000);
    for (const zoom of [13, 14, 15, 16]) {
      await page.goto(`/${hash(AVEBURY, zoom, view)}`);
      await settle(page);
      await shoot(page, `avebury-${view}-z${zoom}`);
    }
  });
}

test("raking light at several sun heights and reliefs, for tuning the defaults", async ({ page }) => {
  test.setTimeout(300_000);
  for (const [altitude, relief] of [
    [15, 2],
    [20, 2],
    [20, 3],
    [25, 2],
    [35, 2],
  ] as const) {
    await page.goto(`/${hash(FYFIELD, 16, "raking", `&s=315/${altitude}&x=${relief}`)}`);
    await settle(page);
    await shoot(page, `fyfield-raking-z16-sun${altitude}-x${relief}`);
  }
});

/** Across the henge's eastern bank and ditch, from inside the circle to the field beyond. */
const HENGE_SECTION = "line=-1.853,51.4286,-1.849,51.4286";

test("a height profile across the henge's bank and ditch", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(`/profile?${HENGE_SECTION}${hash(AVEBURY, 16, "composite")}`);
  await settle(page);
  await expect(page.getByRole("slider", { name: "Height along the line" })).toBeVisible();
  await shoot(page, "profile-henge");
  const chart = page.getByRole("slider", { name: "Height along the line" });
  await chart.focus();
  for (let i = 0; i < 90; i++) await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  await shoot(page, "profile-henge-marker");
});

test("the height profile's empty, one-point, loading, refused and failed states", async ({ page }) => {
  test.setTimeout(180_000);
  const view = hash(AVEBURY, 16, "composite");
  await page.goto(`/profile${view}`);
  await settle(page);
  await shoot(page, "profile-empty");

  await page.goto(`/profile?line=-1.853,51.4286${view}`);
  await settle(page);
  await shoot(page, "profile-one-point");

  // An answer that never comes.
  await page.route("**/api/v1/terrain/profile", () => undefined);
  await page.goto(`/profile?${HENGE_SECTION}${view}`);
  await settle(page);
  await shoot(page, "profile-loading");
  await page.unrouteAll({ behavior: "ignoreErrors" });

  // The server's own refusal of a line that is too long.
  await page.goto(`/profile?line=-1.9,51.4,-1.8,51.45${view}`);
  await settle(page);
  await expect(page.getByRole("heading", { name: "That line can't be profiled" })).toBeVisible();
  await shoot(page, "profile-refused");

  await page.route("**/api/v1/terrain/profile", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "http_503", message: "The server isn't answering right now." } }),
    }),
  );
  await page.goto(`/profile?${HENGE_SECTION}${view}`);
  await settle(page);
  await shoot(page, "profile-failed");
});

test("the height profile in each of the phone sheet's stops", async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? 0) >= 720, "phone only");
  await page.goto(`/profile?${HENGE_SECTION}${hash(AVEBURY, 16, "composite")}`);
  await settle(page);
  const handle = page.getByRole("button", { name: /Press to resize/ });
  for (const stop of ["peek", "full"] as const) {
    await handle.focus();
    await page.keyboard.press(stop === "peek" ? "ArrowDown" : "ArrowUp");
    if (stop === "full") await page.keyboard.press("ArrowUp");
    await page.waitForTimeout(400);
    await shoot(page, `profile-sheet-${stop}`);
  }
});

test("a terrain view where there is no data at all", async ({ page }) => {
  test.setTimeout(120_000);
  // Mid Wales: England's elevation doesn't reach it.
  await page.goto(`/${hash({ lat: 52.3, lng: -3.6 }, 12, "composite")}`);
  await settle(page);
  await expect(page.getByTestId("coverage-notice")).toBeVisible();
  await shoot(page, "coverage-none");
});

test("the layer panel's terrain tools, and the raking light's control", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(`/?panel=layers${hash(AVEBURY, 15, "raking")}`);
  await settle(page);
  await page.getByRole("heading", { name: "Terrain tools" }).scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await shoot(page, "layer-panel-tools");
});

test("copying the grid reference", async ({ page }) => {
  test.setTimeout(60_000);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto(`/${hash(AVEBURY, 15, "composite")}`);
  await settle(page);
  await page.waitForTimeout(600);
  await page.getByRole("button", { name: "Copy the grid reference of the middle of the map" }).click();
  await expect(page.getByText(/^Copied /)).toBeVisible();
  await shoot(page, "copy-gridref");
});

test("3D over the henge", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(`/${hash(AVEBURY, 15.5, "composite", "&t=1/2")}`.replace("/0/0&", "/30/60&"));
  await settle(page);
  await shoot(page, "3d-henge");
});

test("coverage at the Welsh border, where England's data stops", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(`/?panel=layers${hash({ lat: 51.65, lng: -2.68 }, 11, "composite")}`);
  await settle(page);
  await page.getByRole("switch", { name: "Where there's one-metre LIDAR" }).check();
  await settle(page);
  await shoot(page, "coverage-border");
});

test("the layer panel with real previews", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(`/?panel=layers${hash(AVEBURY, 15, "composite")}`);
  await settle(page);
  await page.waitForTimeout(1500);
  await shoot(page, "layer-panel");
});

test("Fyfield Down in the composite and raking light", async ({ page }) => {
  test.setTimeout(180_000);
  for (const view of ["composite", "raking"]) {
    await page.goto(`/${hash(FYFIELD, 15, view)}`);
    await settle(page);
    await shoot(page, `fyfield-${view}-z15`);
  }
});
