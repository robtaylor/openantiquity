import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Locator, type Page, test } from "@playwright/test";
import { liveSourceFixture } from "../../src/test/fixtures/about.js";
import { seenFixture } from "../../src/test/fixtures/findingPage.js";
import { answerJson, fakeSession, meWith, newcomerFixture } from "../support/account.js";
import { openMap } from "../support/app.js";
import { fakeFindingPage } from "../support/findingPage.js";
import { apiRoute, stubNetwork } from "../support/network.js";

/**
 * Screenshots of the guide, the about page and the notices, taken with `pnpm
 * shots`, for looking at the design at desktop and phone width: each section,
 * the phone sheet's stops, the credits while searching, loading and failed,
 * each notice, the welcome sheet's link, and the two notices `/meta` words
 * that show elsewhere: the reminder before a site visit and the finds notice.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const VIEW = "#m=15/51.4286/-1.8542/0/0&v=composite";

async function shoot(page: Page, name: string): Promise<void> {
  await page.waitForTimeout(400);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `reference-${name}-${size?.width}x${size?.height}.png`) });
}

const isPhone = (page: Page) => (page.viewportSize()?.width ?? 1440) < 720;

async function sheetTo(page: Page, stop: "peek" | "half" | "full"): Promise<void> {
  if (!isPhone(page)) return;
  const handle = page.getByRole("button", { name: /Press to resize/ });
  for (let i = 0; i < 3; i++) {
    if ((await page.locator(".fc-shell").getAttribute("data-sheet")) === stop) return;
    await handle.click();
  }
}

async function scrollTo(locator: Locator): Promise<void> {
  await locator.evaluate((element) => element.scrollIntoView({ block: "start" }));
}

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
});

test("guide", async ({ page }) => {
  await openMap(page, `/guide${VIEW}`);
  const panel = page.getByRole("complementary", { name: "Guide" });
  await panel.waitFor();
  await shoot(page, "guide");
  if (isPhone(page)) {
    await sheetTo(page, "peek");
    await shoot(page, "guide-peek");
  }
  await sheetTo(page, "full");
  await shoot(page, "guide-full");
  for (const [name, heading] of [
    ["guide-views", "The views"],
    ["guide-lookalikes", "Real or not?"],
    ["guide-ladder", "How a finding climbs"],
    ["guide-ground", "On the ground"],
  ] as const) {
    await scrollTo(panel.getByRole("heading", { name: heading, level: 3 }));
    await shoot(page, name);
  }
  await scrollTo(panel.getByRole("heading", { name: /^A field system or/ }));
  await shoot(page, "guide-pair-fields");
  await scrollTo(panel.getByRole("heading", { name: /^A hollow way or/ }));
  await shoot(page, "guide-pair-no-picture");
  await panel.getByText("England", { exact: true }).click();
  await scrollTo(panel.getByText("England", { exact: true }));
  await shoot(page, "guide-ground-england");
  await scrollTo(panel.getByText("Northern Ireland", { exact: true }));
  await panel.getByText("Northern Ireland", { exact: true }).click();
  await shoot(page, "guide-ground-ni");
  await scrollTo(panel.getByRole("heading", { name: "Real or not?", level: 3 }));
  await panel.getByRole("button", { name: "Show plough marks on the map" }).click();
  await page.waitForTimeout(1500);
  await shoot(page, "guide-shown-on-map");
});

test("about", async ({ page }) => {
  await answerJson(page, "/context/live-sources", { items: [liveSourceFixture()] });
  await openMap(page, `/about${VIEW}`);
  const panel = page.getByRole("complementary", { name: "About Field Club" });
  await panel.waitFor();
  await shoot(page, "about");
  await sheetTo(page, "full");
  await shoot(page, "about-full");
  await scrollTo(panel.getByRole("heading", { name: "The rules" }));
  await shoot(page, "about-rules");
  await scrollTo(panel.getByRole("heading", { name: "Where the data comes from" }));
  await shoot(page, "about-sources");
  await panel.getByText(/^Map layers/).click();
  await scrollTo(panel.getByText(/^Map layers/));
  await shoot(page, "about-sources-open");
  const search = panel.getByRole("searchbox", { name: "Search the sources" });
  await search.fill("historic england");
  await scrollTo(search);
  await shoot(page, "about-search");
  await search.fill("nothing like this");
  await shoot(page, "about-search-empty");
});

test("about while the live sources load and when they fail", async ({ page }) => {
  await page.route(apiRoute("/context/live-sources"), () => undefined);
  await openMap(page, `/about${VIEW}`);
  const panel = page.getByRole("complementary", { name: "About Field Club" });
  await sheetTo(page, "full");
  await scrollTo(panel.getByRole("heading", { name: "Where the data comes from" }));
  await shoot(page, "about-loading");

  await page.unroute(apiRoute("/context/live-sources"));
  await page.route(apiRoute("/context/live-sources"), (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: '{"code":"unavailable","message":"x"}' }),
  );
  await page.reload();
  await sheetTo(page, "full");
  await panel.getByText(/didn't load/).waitFor({ timeout: 15_000 });
  await scrollTo(panel.getByRole("heading", { name: "Where the data comes from" }));
  await shoot(page, "about-failed");
});

test("notices", async ({ page }) => {
  for (const [id, title] of [
    ["terms", "Contributor terms"],
    ["privacy", "Privacy notice"],
    ["reporting", "Reporting something"],
    ["takedown", "Asking for something to be taken down"],
  ] as const) {
    await openMap(page, `/about/${id}${VIEW}`);
    const panel = page.getByRole("complementary", { name: title });
    await panel.waitFor();
    await sheetTo(page, "full");
    await shoot(page, `notice-${id}`);
    await scrollTo(panel.getByRole("navigation", { name: "The other notices" }));
    await shoot(page, `notice-${id}-end`);
  }
});

test("welcome sheet link", async ({ page }) => {
  await fakeSession(page, newcomerFixture());
  await openMap(page, `/${VIEW}`);
  const sheet = page.getByRole("dialog", { name: "Welcome to Field Club" });
  await sheet.waitFor();
  await sheet.getByRole("link", { name: /Read the contributor terms/ }).scrollIntoViewIfNeeded();
  await shoot(page, "welcome-terms-link");
});

test("the rail's foot and More", async ({ page }) => {
  await openMap(page, `/guide${VIEW}`);
  if (isPhone(page))
    await page.getByRole("navigation", { name: "Modes" }).getByRole("button", { name: /^More/ }).click();
  await shoot(page, "rail");
});

test("site visit reminder and finds notice", async ({ page }) => {
  await fakeSession(page, meWith({ handle: "KeenLynchet7", display_name: "Mary Anning" }));
  const finding = seenFixture();
  await fakeFindingPage(page, finding);
  await openMap(page, `/f/${finding.public_id}${VIEW}`);
  const panel = page.getByRole("complementary", { name: finding.title });
  await panel.waitFor();
  await sheetTo(page, "full");
  await panel.getByRole("button", { name: "Add evidence" }).click();
  await panel.locator(".fc-kind-list").getByRole("button", { name: "Site visit", exact: true }).click();
  await scrollTo(panel.locator(".fc-evidence-add"));
  await shoot(page, "visit-reminder");

  await fakeSession(page, meWith({ handle: "KeenLynchet7", age_band: "16_17" }));
  await page.reload();
  await panel.waitFor();
  await sheetTo(page, "full");
  await panel.getByRole("button", { name: "Add evidence" }).click();
  await panel.locator(".fc-kind-list").getByRole("button", { name: "Site visit", exact: true }).click();
  await scrollTo(panel.locator(".fc-evidence-add"));
  await shoot(page, "visit-reminder-16-17");

  await openMap(page, `/?panel=none${VIEW}`);
  await page.getByRole("button", { name: "Mark a finding" }).click();
  await page.getByRole("button", { name: "Place it here" }).click();
  const mark = page.getByRole("complementary", { name: "Mark a finding" });
  await sheetTo(page, "full");
  await mark.getByText(/This map is for earthworks, not objects/).scrollIntoViewIfNeeded();
  await shoot(page, "finds-notice");
});
