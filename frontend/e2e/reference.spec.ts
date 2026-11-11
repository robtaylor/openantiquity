import type { Page } from "@playwright/test";
import { liveSourceFixture } from "../src/test/fixtures/about.js";
import { answerJson, fakeSession, newcomerFixture } from "./support/account.js";
import { openMap, tabTo } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";

/**
 * The guide, the about page and the notices, in fixture mode at desktop and
 * phone width: reached from the foot of the mode rail (or "More" on a phone)
 * and from the welcome sheet, and used by keyboard.
 */

const isPhone = (page: Page) => (page.viewportSize()?.width ?? 1440) < 720;

/** Go to a reference page from the foot of the rail on a desktop, or through "More" on a phone. */
async function goTo(page: Page, name: "Guide" | "About"): Promise<void> {
  const modes = page.getByRole("navigation", { name: "Modes" });
  if (isPhone(page)) await modes.getByRole("button", { name: /^More/ }).click();
  await modes.getByRole("link", { name, exact: true }).click();
}

/** Every picture in the panel has loaded. */
async function picturesLoaded(panel: ReturnType<Page["getByRole"]>): Promise<void> {
  const pictures = panel.locator("img");
  const count = await pictures.count();
  expect(count).toBeGreaterThan(0);
  for (let index = 0; index < count; index++) {
    const picture = pictures.nth(index);
    await picture.scrollIntoViewIfNeeded();
    await expect.poll(() => picture.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  }
}

test("the guide opens from the rail, shows its pictures and sends each example to the map", async ({ page }) => {
  await openMap(page);
  await goTo(page, "Guide");
  await expect(page).toHaveURL(/\/guide#/);
  await expect(page).toHaveTitle("Guide · Open Antiquity");
  const panel = page.getByRole("complementary", { name: "Guide" });
  await expect(panel.getByRole("heading", { name: "The views", level: 3 })).toBeVisible();
  await picturesLoaded(panel);

  const show = panel.getByRole("button", { name: "Show tramlines on the map" });
  await show.scrollIntoViewIfNeeded();
  await show.click();
  // The map goes to the place in the view the example uses, and the address says so.
  await expect(page).toHaveURL(/v=local_relief/);
  await expect(page).toHaveURL(/m=16\/51\.36\d*\/-1\.85\d*/);
  // Record squares and finding markers would sit on the feature, so they are hidden, and the address says so.
  await expect(page).toHaveURL(/records:\d+:h/);
  await expect(page).toHaveURL(/findings:\d+:h/);
  if (isPhone(page)) await expect(page.locator(".fc-shell")).toHaveAttribute("data-sheet", "peek");
});

test("the guide works by keyboard: jump to a section, open a place, close with Escape", async ({ page }) => {
  await openMap(page, "/guide");
  const panel = page.getByRole("complementary", { name: "Guide" });
  await expect(panel).toBeVisible();
  if (isPhone(page)) await panel.getByRole("button", { name: /Panel is .* Press to resize\./ }).click();

  await tabTo(page, panel.getByRole("button", { name: "On the ground" }));
  await page.keyboard.press("Enter");
  const heading = panel.getByRole("heading", { name: "On the ground", level: 3 });
  await expect(heading).toBeFocused();
  await expect(heading).toBeInViewport();

  // The next stop after the heading is the first nation's rules, which open with Enter.
  await tabTo(page, panel.getByText("England", { exact: true }));
  await page.keyboard.press("Enter");
  await expect(
    panel.getByText(/A marker on this map is not permission to visit|landowner's permission/).first(),
  ).toBeVisible();

  await panel.getByRole("button", { name: "Real or not?" }).focus();
  await page.keyboard.press("Enter");
  await tabTo(page, panel.getByRole("button", { name: "Show a round barrow on the map" }));
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/v=composite/);
  await expect(page).toHaveURL(/m=16\/51\.42\d*\/-1\.83\d*/);

  if (!isPhone(page)) {
    // The focus stayed on the button, inside the panel, so Escape closes it.
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(page).toHaveURL(/\/\?panel=none#/);
  }
});

test("the about page credits every source, grouped and searchable", async ({ page }) => {
  await answerJson(page, "/context/live-sources", { items: [liveSourceFixture()] });
  await openMap(page);
  await goTo(page, "About");
  await expect(page).toHaveURL(/\/about#/);
  const panel = page.getByRole("complementary", { name: "About Open Antiquity" });
  await expect(panel.getByText(/a shared map for finding and checking/)).toBeVisible();
  await expect(panel.getByText(/free and non-commercial/)).toBeVisible();

  const groups = panel.locator("details.fc-about__group > summary");
  await expect(groups).toHaveText([/^Map layers/, /^Designations \(1\)/, /^Looked up from your browser \(1\)/]);

  const search = panel.getByRole("searchbox", { name: "Search the sources" });
  await search.scrollIntoViewIfNeeded();
  await search.focus();
  await page.keyboard.type("wiltshire");
  await expect(panel.getByText("1 of", { exact: false })).toBeVisible();
  await expect(panel.getByText("Wiltshire and Swindon HER")).toBeVisible();
  await expect(panel.getByText("Scheduled monuments in England")).toBeHidden();

  await search.fill("nothing like this");
  await expect(panel.getByText("Nothing matches “nothing like this”.")).toBeVisible();
  await panel.getByRole("button", { name: "Clear the search" }).click();
  await expect(search).toHaveValue("");

  // A group opens and closes from the keyboard.
  const designations = panel.getByText("Designations (1)");
  await designations.focus();
  await page.keyboard.press("Enter");
  await expect(panel.getByText("Scheduled monuments in England")).toBeVisible();
});

test("each notice is marked as a draft and reached by keyboard from the about page", async ({ page }) => {
  for (const title of [
    "Contributor terms",
    "Privacy notice",
    "Reporting something",
    "Asking for something to be taken down",
  ]) {
    await openMap(page, "/about");
    const panel = page.getByRole("complementary", { name: "About Open Antiquity" });
    await expect(panel).toBeVisible();
    await tabTo(page, panel.getByRole("link", { name: new RegExp(`^${title}`) }), 80);
    await page.keyboard.press("Enter");
    const notice = page.getByRole("complementary", { name: title });
    await expect(notice).toBeVisible();
    await expect(notice.getByRole("note")).toContainText("Draft");
    await expect(notice.getByRole("article", { name: title })).toBeVisible();
    await expect(page).toHaveTitle(`${title} · Open Antiquity`);
  }
});

test("the welcome sheet links to the contributor terms, which open at their own page", async ({ page }) => {
  await fakeSession(page, newcomerFixture());
  await openMap(page, "/");
  const sheet = page.getByRole("dialog", { name: "Welcome to Open Antiquity" });
  await expect(sheet).toBeVisible();
  const link = sheet.getByRole("link", { name: /Read the contributor terms/ });
  await tabTo(page, link);
  await expect(link).toHaveAttribute("target", "_blank");
  const href = await link.getAttribute("href");
  expect(href).toBe("/about#terms");

  // What the new tab would load: the terms' own page, with the section the link names.
  await page.goto(href ?? "");
  const terms = page.getByRole("complementary", { name: "Contributor terms" });
  await expect(terms).toBeVisible();
  await expect(page).toHaveURL(/\/about\/terms#/);
  await expect(page.locator("#terms")).toBeVisible();
  await expect(terms.getByText(/published under/).first()).toBeVisible();
});
