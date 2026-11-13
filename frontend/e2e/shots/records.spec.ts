import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { AVENUE_RECORD, FIND_RECORD, HOSTILE_RECORD } from "../../src/test/fixtures/records.js";
import { CENTRE, type MarkerPoint, offset, SAMPLE_RECORDS, serveRecordTiles } from "../support/markerTiles.js";
import { stubBackend } from "../support/network.js";
import { serveLiveHosts, serveRecordsApi } from "../support/records.js";

/**
 * Design-review screenshots of the heritage records feature: the map layer,
 * a record's page, the search box, the record search, "open elsewhere" and
 * the live sources, in their empty, loading and failed states too. Taken
 * with `pnpm shots e2e/shots/records.spec.ts`, using the live tile services.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const VIEW = `#m=15/${CENTRE.lat}/${CENTRE.lon}/0/0&v=composite&s=315/25&x=2&t=0/1.5&o=osm:80,records:100,findings:100`;

async function settle(page: Page): Promise<void> {
  await expect(page.locator(".fc-map")).toHaveAttribute("data-ready", "true");
  await page
    .locator('.fc-map__pane--main[data-map-idle="true"]')
    .waitFor({ timeout: 20_000 })
    .catch(() => undefined);
  await page.waitForTimeout(700);
}

async function shoot(page: Page, name: string): Promise<void> {
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `records-${name}-${size?.width}x${size?.height}.png`) });
}

const RECORD_POINTS: MarkerPoint[] = SAMPLE_RECORDS.map((point) => ({
  ...point,
  properties: { ...point.properties, source: "nhle-scheduled" },
}));

const COUNTS: MarkerPoint[] = [
  { ...offset(-800, 300), properties: { category: "designation", count: 3, sources: "nhle-scheduled" } },
  { ...offset(-200, 300), properties: { category: "monument", count: 48, sources: "nhle-scheduled" } },
  { ...offset(400, 300), properties: { category: "find", count: 1250, sources: "nhle-scheduled" } },
];

test.beforeEach(async ({ page }) => {
  await stubBackend(page);
});

test("records and counts on the map, with the layer panel's record controls", async ({ page }) => {
  await serveRecordsApi(page);
  await serveRecordTiles(page, RECORD_POINTS);
  await page.goto(`/?panel=layers${VIEW}`);
  await settle(page);
  await page.getByRole("switch", { name: "Heritage records" }).scrollIntoViewIfNeeded();
  await shoot(page, "01-layer-panel");
});

test("record counts at a busy tile", async ({ page }) => {
  await serveRecordsApi(page);
  await serveRecordTiles(page, COUNTS, "record_counts");
  await page.goto(`/${VIEW}`);
  await settle(page);
  await shoot(page, "02-counts");
});

test("a record's page, exact and imprecise", async ({ page }) => {
  await serveRecordsApi(page);
  await page.goto(`/r/${AVENUE_RECORD.id}${VIEW}`);
  await settle(page);
  await shoot(page, "03-record");
  await page.goto(`/r/${FIND_RECORD.id}`);
  await settle(page);
  await shoot(page, "04-record-square");
  await page.goto(`/r/${HOSTILE_RECORD.id}`);
  await settle(page);
  await shoot(page, "05-record-hostile");
});

test("a record's page: loading, missing and failed", async ({ page }) => {
  await serveRecordsApi(page);
  await page.route(/\/api\/v1\/records\/101(\?|$)/, () => new Promise(() => {}));
  await page.route(/\/api\/v1\/records\/202(\?|$)/, (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: '{"error":{"code":"internal_error","message":"The server had a problem."}}',
    }),
  );
  await page.goto(`/r/101${VIEW}`);
  await settle(page);
  await shoot(page, "06-record-loading");
  await page.goto("/r/31337");
  await settle(page);
  await shoot(page, "07-record-missing");
  await page.goto("/r/202");
  await page.getByText("This record couldn't be loaded").waitFor();
  await shoot(page, "08-record-failed");
});

test("the search box: results, nothing found, too slow", async ({ page }) => {
  await serveRecordsApi(page);
  await page.goto(`/${VIEW}`);
  await settle(page);
  const box = page.getByRole("combobox", { name: /Search for a place/ });
  await box.fill("ave");
  await page.getByRole("option", { name: /West Kennet Avenue/ }).waitFor();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await shoot(page, "09-search-results");
  await box.fill("zzz");
  await page.getByText(/Nothing matches/).waitFor();
  await shoot(page, "10-search-nothing");
  await box.fill("slow");
  await page.getByText(/took too long/).waitFor();
  await shoot(page, "11-search-slow");
});

test("the record search panel", async ({ page }) => {
  await serveRecordsApi(page);
  await page.goto(`/records${VIEW}`);
  await settle(page);
  await page.getByRole("link", { name: AVENUE_RECORD.name }).waitFor();
  await shoot(page, "12-record-search");
  await page.route(/\/api\/v1\/records\/search/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: '{"items":[],"next_cursor":null}' }),
  );
  await page.getByRole("searchbox", { name: "Words to look for" }).fill("nothing here");
  await page.getByText("No records match").waitFor();
  await shoot(page, "13-record-search-empty");
});

test("open elsewhere", async ({ page }) => {
  await serveRecordsApi(page);
  await page.goto(`/elsewhere?lon=${CENTRE.lon}&lat=${CENTRE.lat}${VIEW}`);
  await settle(page);
  await page.getByRole("heading", { name: "Old maps" }).waitFor();
  await shoot(page, "14-elsewhere");
});

test("live sources, on and failed", async ({ page }) => {
  const log = await serveRecordsApi(page);
  await serveLiveHosts(page, log);
  await page.goto(`/?panel=layers${VIEW}`);
  await settle(page);
  await page.getByText("Live sources", { exact: true }).click();
  await page.getByRole("switch", { name: /Wiltshire/ }).check();
  await page.getByRole("switch", { name: /Wolverhampton and Walsall HER/ }).check();
  await page.getByText(/records in view/).waitFor();
  await page.getByText(/didn't answer this browser/).waitFor();
  await page.locator("details.fc-live[open]").scrollIntoViewIfNeeded();
  await page.waitForTimeout(700);
  await shoot(page, "15-live");
});

test("a record's page in each of the phone sheet's stops", async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? 0) >= 720, "phone only");
  await serveRecordsApi(page);
  await page.goto(`/r/${AVENUE_RECORD.id}${VIEW}`);
  await settle(page);
  const handle = page.getByRole("button", { name: /Press to resize/ });
  for (const stop of ["peek", "full"] as const) {
    await handle.focus();
    await page.keyboard.press(stop === "peek" ? "ArrowDown" : "ArrowUp");
    if (stop === "full") await page.keyboard.press("ArrowUp");
    await page.waitForTimeout(400);
    await shoot(page, `16-sheet-${stop}`);
  }
});
