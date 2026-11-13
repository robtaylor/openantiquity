import type { Locator, Page } from "@playwright/test";
import { RECORD_SQUARE_OPACITY } from "../src/map/overlayLayers.js";
import {
  ADS_LIVE,
  AVENUE_RECORD,
  DARTMOOR_LIVE,
  FIND_RECORD,
  HOSTILE_LIVE_ANSWER,
  HOSTILE_RECORD,
  WILTSHIRE_LIVE,
  WOLVERHAMPTON_LIVE,
} from "../src/test/fixtures/records.js";
import { openMap } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";
import { CENTRE, type MarkerPoint, offset, serveRecordTiles } from "./support/markerTiles.js";
import { blend, colourDistance, decodePng, hexToRgb, pixelAt, type Rgb } from "./support/png.js";
import { type RecordsLog, serveLiveHosts, serveRecordsApi } from "./support/records.js";

/**
 * Heritage records: on the map, on their own page, through the search box
 * and the record search, "open elsewhere", and the live sources a browser
 * asks itself (Decision 0007). Every answer comes from the shared fixtures.
 */

const ZOOM = 15;
const BACKDROP: Rgb = [128, 128, 128];
/** A designation's square, drawn a little faint over the backdrop. */
const DESIGNATION = blend(hexToRgb("#d9544d"), BACKDROP, RECORD_SQUARE_OPACITY);
const VIEW_HASH = `#m=${ZOOM}/${CENTRE.lat}/${CENTRE.lon}/0/0&v=composite&s=315/25&x=2&t=0/1.5&o=osm:80:h,records:100,findings:100`;

const RECORD_AT = offset(0, -120);
const RECORDS: MarkerPoint[] = [
  { ...RECORD_AT, properties: { id: AVENUE_RECORD.id, category: "designation", source: "nhle-scheduled", name: "x" } },
];

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

/** Where a longitude and latitude fall on screen, with the map centred on `CENTRE`, north up, at `ZOOM`. */
function project(page: Page, at: { lon: number; lat: number }): { x: number; y: number } {
  const size = page.viewportSize() ?? { width: 1440, height: 900 };
  const world = 512 * 2 ** ZOOM;
  const mercator = (lon: number, lat: number) => ({
    x: ((lon + 180) / 360) * world,
    y: ((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * world,
  });
  const centre = mercator(CENTRE.lon, CENTRE.lat);
  const point = mercator(at.lon, at.lat);
  return { x: size.width / 2 + point.x - centre.x, y: size.height / 2 + point.y - centre.y };
}

/** Click, or on a phone tap, the map at a screen position. */
async function pressMap(page: Page, position: { x: number; y: number }): Promise<void> {
  const canvas = page.locator(".fc-map__pane--main canvas");
  if (isPhone(page)) await canvas.tap({ position });
  else await canvas.click({ position });
}

async function colourAt(page: Page, at: { x: number; y: number }) {
  return pixelAt(decodePng(await page.screenshot()), at.x, at.y);
}

/** The panel, or on a phone the sheet, with this title. */
function panel(page: Page, title: string | RegExp): Locator {
  return page.locator(".fc-panel").filter({ has: page.getByRole("heading", { name: title, level: 2 }) });
}

/** Every link inside goes to this site or to an http or https address. */
async function expectOnlyWebLinks(scope: Locator): Promise<void> {
  for (const href of await scope.locator("a").evaluateAll((links) => links.map((a) => a.getAttribute("href") ?? ""))) {
    expect(href.startsWith("/") || /^https?:\/\//.test(href), `link to ${href}`).toBe(true);
  }
}

let log: RecordsLog;

test.beforeEach(async ({ page }) => {
  log = await serveRecordsApi(page);
  // An alert from a hostile record would mean its words ran as code.
  page.on("dialog", (dialog) => {
    throw new Error(`A dialog opened: ${dialog.message()}`);
  });
});

test.describe("on the map", () => {
  test("draws a record as a square, opens its page from the map, and hides its category on request", async ({
    page,
  }) => {
    await serveRecordTiles(page, RECORDS);
    await openMap(page, `/${VIEW_HASH}`);
    const at = project(page, RECORD_AT);
    await expect(async () => {
      expect(colourDistance(await colourAt(page, at), DESIGNATION)).toBeLessThanOrEqual(12);
    }).toPass();

    await pressMap(page, at);
    await expect(page).toHaveURL(new RegExp(`/r/${AVENUE_RECORD.id}`));
    await expect(panel(page, AVENUE_RECORD.name)).toBeVisible();

    await page.goto(`/?panel=layers${VIEW_HASH}`);
    await expect(page.locator(".fc-map")).toHaveAttribute("data-ready", "true");
    const designations = page.getByRole("group", { name: "Kinds of record to show" }).getByRole("button", {
      name: "Designations",
    });
    await designations.click();
    await expect(designations).toHaveAttribute("aria-pressed", "false");
    if (!isPhone(page)) {
      await expect(async () => {
        expect(colourDistance(await colourAt(page, at), BACKDROP)).toBeLessThanOrEqual(8);
      }).toPass();
    }
  });

  test("draws a busy tile's counts as larger squares and zooms in when one is pressed", async ({ page }) => {
    await serveRecordTiles(
      page,
      [{ ...RECORD_AT, properties: { category: "designation", count: 240, sources: "nhle-scheduled" } }],
      "record_counts",
    );
    await openMap(page, `/${VIEW_HASH}`);
    const at = project(page, RECORD_AT);
    await expect(async () => {
      const image = decodePng(await page.screenshot());
      // Bigger than a single record's eight or nine pixels: still in colour five and a half pixels out.
      expect(colourDistance(pixelAt(image, at.x + 5.5, at.y + 5.5), DESIGNATION)).toBeLessThanOrEqual(40);
    }).toPass();
    await pressMap(page, at);
    await expect(page).toHaveURL(/#m=17(\.\d+)?\//);
  });
});

test.describe("a record's page", () => {
  test("shows a record's source, licence and original, and how exact its position is", async ({ page }) => {
    await openMap(page, `/r/${AVENUE_RECORD.id}`);
    const record = panel(page, AVENUE_RECORD.name);
    await expect(record.getByText("Scheduled monument", { exact: true })).toBeVisible();
    await expect(record.getByText(/Exact to within about 5 m/)).toBeAttached();
    const licence = record.getByRole("link", { name: "OGL v3.0" });
    await expect(licence).toHaveAttribute("href", AVENUE_RECORD.source.licence_url ?? "");
    const original = record.getByRole("link", { name: /See the original record/ });
    await expect(original).toHaveAttribute("target", "_blank");
    await expect(original).toHaveAttribute("rel", /noopener/);
    await expect(original).toHaveAttribute("rel", /noreferrer/);
    // The findings linked to it open their own pages.
    const linked = record.getByRole("region", { name: "Findings linked to it" });
    await expect(linked.getByRole("link", { name: /Bank beside the avenue/ })).toHaveAttribute("href", "/f/f-7k2m9q");
    await expect(linked.getByText("Seen by others")).toBeAttached();

    await page.goto(`/r/${FIND_RECORD.id}`);
    await expect(
      panel(page, FIND_RECORD.name).getByText(/No finding has been linked to this record yet/),
    ).toBeAttached();
    await expect(
      panel(page, FIND_RECORD.name).getByText(/Published only to the one-kilometre square SU\d{4}/),
    ).toBeAttached();
  });

  test("shows a hostile record's words as text and links only to web addresses", async ({ page }) => {
    await openMap(page, `/r/${HOSTILE_RECORD.id}`);
    const record = panel(page, HOSTILE_RECORD.name);
    await expect(record).toBeVisible();
    await expect(record.getByText(HOSTILE_RECORD.summary ?? "")).toBeAttached();
    await expect(record.locator("script, img, iframe, b")).toHaveCount(0);
    await expectOnlyWebLinks(record);
    await expect(record.getByText("The source doesn't give a page for this record.")).toBeAttached();
  });

  test.describe("when the server says no", () => {
    test.use({ pageProblems: "page-errors" });

    test("says when there is no such record", async ({ page }) => {
      await openMap(page, "/r/31337");
      await expect(page.getByText("There's no record at this address")).toBeVisible();
    });
  });
});

test.describe("the search box", () => {
  test("is worked by keyboard alone: arrows, Enter and Escape", async ({ page }) => {
    await openMap(page);
    const box = page.getByRole("combobox", { name: /Search for a place/ });
    await box.focus();
    await page.keyboard.type("ave");
    await expect(page.getByRole("option", { name: /West Kennet Avenue/ })).toBeVisible();
    await expect(page.getByRole("group", { name: "Places" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Heritage records" })).toBeVisible();
    // Typing three letters asked once.
    expect(log.geoSearches).toEqual(["ave"]);

    await page.keyboard.press("Escape");
    await expect(box).toHaveAttribute("aria-expanded", "false");
    await page.keyboard.press("ArrowDown");
    await expect(box).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await expect(page.getByRole("option", { name: /West Kennet Avenue/ })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(new RegExp(`/r/${AVENUE_RECORD.id}#m=16/`));
    await expect(panel(page, AVENUE_RECORD.name)).toBeVisible();
    await expect(box).toHaveValue(AVENUE_RECORD.name);

    await box.focus();
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expect(box).toHaveValue("");
  });

  test.describe("when the server says no", () => {
    test.use({ pageProblems: "page-errors" });

    test("says when nothing matches and when the server ran out of time", async ({ page }) => {
      await openMap(page);
      const box = page.getByRole("combobox", { name: /Search for a place/ });
      await box.fill("zzz");
      await expect(page.getByRole("status").filter({ hasText: "Nothing matches “zzz”" })).toBeVisible();
      await box.fill("slow");
      await expect(page.getByRole("status").filter({ hasText: "That search took too long" })).toBeVisible();
    });
  });
});

test.describe("the record search", () => {
  test("lists records in view with their sources, pages on, and downloads them with their licences", async ({
    page,
  }) => {
    await openMap(page, "/records");
    const search = panel(page, "Search the records");
    await expect(search.getByRole("link", { name: AVENUE_RECORD.name })).toBeVisible();
    await expect(search.getByText(`From ${FIND_RECORD.source.name}`)).toBeAttached();
    expect(log.recordSearches[0]?.get("bbox")).toMatch(/^-?\d/);

    await search.getByRole("button", { name: "Show more" }).click();
    await expect(search.getByRole("link", { name: "Avebury henge" })).toBeAttached();

    // The download is a plain link to the same search as GeoJSON. Its file is fetched as the browser would.
    const download = search.getByRole("link", { name: /Download as GeoJSON/ });
    await expect(download).toHaveAttribute("download", "heritage-records.geojson");
    const href = (await download.getAttribute("href")) ?? "";
    expect(new URL(href, page.url()).searchParams.get("format")).toBe("geojson");
    const body = (await page.evaluate(async (url) => (await fetch(url)).json(), href)) as {
      features: Array<{ properties: Record<string, unknown> }>;
    };
    expect(body.features.length).toBeGreaterThan(0);
    for (const feature of body.features) expect(feature.properties.licence).toEqual(expect.any(String));

    await search.getByRole("link", { name: AVENUE_RECORD.name }).click();
    await expect(panel(page, AVENUE_RECORD.name)).toBeVisible();
  });
});

test.describe("open elsewhere", () => {
  test("offers the links for a spot, each to open in a new tab, and says which are unchecked", async ({ page }) => {
    await openMap(page, `/${VIEW_HASH}`);
    if (isPhone(page)) {
      await page.getByRole("button", { name: "Open the middle of the map in other viewers" }).click();
    } else {
      await page.locator(".fc-map__pane--main canvas").click({ button: "right", position: { x: 700, y: 400 } });
    }
    const elsewhere = panel(page, "Open elsewhere");
    await expect(elsewhere.getByRole("heading", { name: "Aerial photographs" })).toBeVisible();
    await expect(elsewhere.getByRole("heading", { name: "Old maps" })).toBeVisible();
    await expect(elsewhere.getByText(isPhone(page) ? "The middle of the map" : "The spot you chose")).toBeVisible();
    const links = elsewhere.getByRole("link");
    await expect(links).toHaveCount(3);
    for (const link of await links.all()) {
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(link).toHaveAttribute("rel", /noopener noreferrer/);
    }
    await expectOnlyWebLinks(elsewhere);
    await expect(elsewhere.getByText("unchecked", { exact: true })).toHaveCount(2);
    await expect(elsewhere.getByText(/haven't been able to check/)).toHaveCount(1);
  });
});

test.describe("live sources", () => {
  async function openLiveSources(page: Page): Promise<Locator> {
    await openMap(page, `/?panel=layers${VIEW_HASH}`);
    await page.getByText("Live sources", { exact: true }).click();
    return page.locator(".fc-live");
  }

  test("asks a publisher directly once it is turned on, lists and credits what it sends, and tells our server nothing", async ({
    page,
  }) => {
    await serveLiveHosts(page, log);
    const ours: string[] = [];
    page.on("request", (request) => {
      if (new URL(request.url()).host === new URL(page.url()).host)
        ours.push(`${request.url()} ${request.postData() ?? ""}`);
    });
    const live = await openLiveSources(page);
    const toggle = live.getByRole("switch", { name: WILTSHIRE_LIVE.name });
    await expect(toggle).not.toBeChecked();
    expect(log.live["maps.wiltshire.gov.uk"]).toBeUndefined();

    await toggle.check();
    const list = live.getByRole("list", { name: `Records from ${WILTSHIRE_LIVE.name}` });
    await expect(list.getByText("Stone hole 41, Avebury henge", { exact: true })).toBeVisible();
    await expect(live.getByText(/4 records in view/)).toBeVisible();
    await expect(live.getByText(new RegExp(`^${WILTSHIRE_LIVE.attribution.replace(/[()]/g, "\\$&")}`))).toBeVisible();
    // The catalogue's notes on the licence aren't shown, and a source credited per record isn't offered.
    await expect(live.getByText(/Website' folder/)).toHaveCount(0);
    await expect(live.getByRole("switch", { name: ADS_LIVE.name })).toHaveCount(0);
    expect(log.live["maps.wiltshire.gov.uk"]).toHaveLength(1);
    expect(ours.filter((line) => line.includes("MWI") || line.includes("Avebury Vicarage"))).toEqual([]);
  });

  test.describe("when a source fails", () => {
    test.use({ pageProblems: "page-errors" });

    test("turns off quietly when a source refuses this browser, or answers with an error", async ({ page }) => {
      await serveLiveHosts(page, log);
      const live = await openLiveSources(page);
      // A click, not check(): the failure can turn the switch off again before check() looks at it.
      const refusing = live.getByRole("switch", { name: WOLVERHAMPTON_LIVE.name });
      await refusing.click();
      await expect(live.getByText(/didn't answer this browser/)).toBeVisible();
      await expect(refusing).not.toBeChecked();

      const failing = live.getByRole("switch", { name: DARTMOOR_LIVE.name });
      await failing.click();
      await expect(live.getByText(/answered with an error \(500\)/)).toBeVisible();
      await expect(failing).not.toBeChecked();
      await page.waitForTimeout(1500);
      expect(log.live["services2.arcgis.com"]).toHaveLength(1);
      expect(log.live["services-eu1.arcgis.com"]).toHaveLength(1);
    });
  });

  test("shows a hostile live record's name as text, with no link", async ({ page }) => {
    await serveLiveHosts(page, log, HOSTILE_LIVE_ANSWER);
    const live = await openLiveSources(page);
    await live.getByRole("switch", { name: WILTSHIRE_LIVE.name }).check();
    const list = live.getByRole("list", { name: `Records from ${WILTSHIRE_LIVE.name}` });
    await expect(list.getByText('<img src=x onerror="alert(1)">Evil')).toBeVisible();
    await expect(list.locator("img, a")).toHaveCount(0);
  });
});
