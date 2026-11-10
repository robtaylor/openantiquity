import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { SAMPLE_RECORDS, serveFindings, serveRecordTiles } from "../support/markerTiles.js";
import { stubBackend } from "../support/network.js";

/**
 * Screenshots for looking at the design, taken with `pnpm shots`. Unlike the
 * tests, these use the live tile services named in the fixture, so the
 * pictures show real terrain. They assert almost nothing and are not part of
 * `pnpm e2e`.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

/** How long to wait for every tile before trying the page again. */
const IDLE_TIMEOUT_MS = 20_000;
/** The upstream LIDAR service sometimes leaves a tile hanging. A reload fetches only what is missing. */
const ATTEMPTS = 3;

async function allPanesIdle(page: Page): Promise<boolean> {
  for (const pane of await page.locator(".fc-map__pane").all()) {
    const idle = await pane
      .and(page.locator('[data-map-idle="true"]'))
      .waitFor({ timeout: IDLE_TIMEOUT_MS })
      .then(
        () => true,
        () => false,
      );
    if (!idle) return false;
  }
  return true;
}

async function settle(page: Page): Promise<void> {
  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    await expect(page.locator(".fc-map")).toHaveAttribute("data-ready", "true");
    if (await allPanesIdle(page)) break;
    if (attempt < ATTEMPTS) await page.reload();
  }
  // Let fades and transitions finish.
  await page.waitForTimeout(700);
}

async function shoot(page: Page, name: string): Promise<void> {
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `${name}-${size?.width}x${size?.height}.png`) });
}

test.beforeEach(async ({ page }) => {
  // No backend is assumed. Records tiles answer "nothing here", and the API
  // has no findings and a fixed point lookup, unless a shot supplies them.
  // The outside tile services are left live.
  await stubBackend(page);
});

test("bare map", async ({ page }) => {
  await page.goto("/");
  await settle(page);
  await shoot(page, "01-map");
});

test("layer panel", async ({ page }) => {
  await page.goto("/?panel=layers");
  await settle(page);
  await shoot(page, "02-layers");
});

test("raking light with the sun dial", async ({ page }) => {
  await page.goto("/#m=15/51.4286/-1.8542/0/0&v=raking&s=300/18&x=3&t=0/1.5&o=osm:60");
  await settle(page);
  await shoot(page, "03-raking");
});

test("compare mode", async ({ page }) => {
  await page.goto("/#m=14/51.4286/-1.8542/0/0&v=composite&c=osm_standard&s=315/30&x=0.5&t=0/1.5&o=osm:80:h");
  await settle(page);
  await shoot(page, "04-compare");
});

test("placeholder route", async ({ page }) => {
  await page.goto("/review");
  await settle(page);
  await shoot(page, "05-placeholder");
});

test("markers", async ({ page }) => {
  await serveFindings(page);
  await serveRecordTiles(page, SAMPLE_RECORDS);
  await page.goto(
    "/#m=14.6/51.4286/-1.8500/0/0&v=composite&s=315/30&x=0.5&t=0/1.5&o=osm:80,records:100,findings:100&r=1",
  );
  await settle(page);
  await shoot(page, "06-markers");
});

test("3D terrain", async ({ page }) => {
  await page.goto("/#m=14.5/51.4286/-1.8542/-20/60&v=raking&s=300/25&x=2&t=1/2.5&o=osm:60");
  await settle(page);
  await shoot(page, "07-3d");
});

test("layer panel while comparing", async ({ page }) => {
  await page.goto("/?panel=layers#m=14/51.4286/-1.8542/0/0&v=raking&c=composite&s=120/25&x=3&t=0/1.5&o=osm:80");
  await settle(page);
  await shoot(page, "08-layers-compare");
});

test("raking light with the layer panel open", async ({ page }) => {
  // On a phone this is the half-open sheet with the sun dial and the primary action riding above it.
  await page.goto("/?panel=layers#m=15/51.4286/-1.8542/0/0&v=raking&s=300/18&x=3&t=0/1.5&o=osm:60");
  await settle(page);
  await shoot(page, "10-raking-layers");
});

test("turned map with its compass and a keyboard focus ring", async ({ page }) => {
  await page.goto("/#m=14.5/51.4286/-1.8542/-46/0&v=raking&s=300/25&x=2&t=0/1.5&o=osm:60");
  await settle(page);
  // Tab to the Layers button, so the shot shows the focus ring on a floating control.
  const layers = page.getByRole("button", { name: "Layers" });
  for (let presses = 0; presses < 30; presses++) {
    await page.keyboard.press("Tab");
    if (await layers.evaluate((element) => element === document.activeElement)) break;
  }
  await shoot(page, "11-turned-compass-focus");
});

test("interface kit", async ({ page }) => {
  await page.goto("/_ui");
  await settle(page);
  const size = page.viewportSize();
  const body = page.locator(".fc-panel__body");
  await body.screenshot({ path: join(OUT, `09-kit-top-${size?.width}x${size?.height}.png`) });
  await page.screenshot({ path: join(OUT, `09-kit-${size?.width}x${size?.height}.png`) });
  // The kit is taller than the panel, so scroll through it a screen at a time.
  for (let part = 2; part <= 4; part++) {
    await body.evaluate((element) => element.scrollBy(0, element.clientHeight - 40));
    await page.waitForTimeout(150);
    await page.screenshot({ path: join(OUT, `09-kit-part${part}-${size?.width}x${size?.height}.png`) });
  }
});
