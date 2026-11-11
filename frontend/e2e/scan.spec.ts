import type { Locator, Page } from "@playwright/test";
import { DRAFTS_STORAGE_KEY } from "../src/features/drafts/store.js";
import { SQUARE_SPOT, squareAt, squareEastOf } from "../src/test/fixtures/squares.js";
import { fakeSession, meWith } from "./support/account.js";
import { openMap } from "./support/app.js";
import { fakeFindings } from "./support/findings.js";
import { expect, test } from "./support/fixtures.js";
import { apiRoute } from "./support/network.js";
import { fakeSquares } from "./support/squares.js";

/**
 * Scan a square, in fixture mode, at desktop and phone width: the square
 * framed on the map; ending it with each of the three presses and going on
 * with one more; a signed-out scan kept as drafts through a provider's round
 * trip and saved once, with a finding marked in the square counting towards
 * it; the coverage layer while scanning and from the layer panel, refusing a
 * view too wide to ask about; and the states with no square to give.
 */

const VIEW = "#m=13/51.4286/-1.8542/0/0&v=composite";
const MEMBER = meWith({ handle: "KeenLynchet7", display_name: "Mary Anning" });
const FIRST = squareAt(...SQUARE_SPOT, 2);
const SECOND = squareEastOf(1);
const THIRD = squareEastOf(2);

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

function panel(page: Page): Locator {
  return page.getByRole("complementary", { name: "Scan a square" });
}

/** The square's reference as the panel shows it. */
function place(page: Page, square: { grid_ref: string }): Locator {
  return panel(page).locator(".fc-scan__place .fc-mono").filter({ hasText: square.grid_ref });
}

/** The camera in the address: zoom, latitude and longitude. */
function camera(page: Page): { zoom: number; lat: number; lon: number } {
  const match = /#m=([\d.]+)\/(-?[\d.]+)\/(-?[\d.]+)/.exec(page.url());
  if (!match) throw new Error(`No camera in ${page.url()}`);
  return { zoom: Number(match[1]), lat: Number(match[2]), lon: Number(match[3]) };
}

/** Go back to the scan from another mode, by the rail or the phone's tab bar. */
async function backToScan(page: Page): Promise<void> {
  const name = isPhone(page) ? "Scan" : "Scan a square";
  await page.getByRole("navigation", { name: "Modes" }).getByRole("link", { name, exact: true }).click();
}

function storedDrafts(page: Page): Promise<Array<{ kind: string; data: unknown }>> {
  return page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? "{}").drafts ?? [], DRAFTS_STORAGE_KEY);
}

test("frames a square near the map, and ends it with one press and goes on with another", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const squares = await fakeSquares(page, [FIRST, SECOND, THIRD]);
  await openMap(page, `/scan${VIEW}`);
  await expect(place(page, FIRST)).toBeVisible();
  await expect(panel(page).getByText("2 people have looked it over so far.")).toBeVisible();
  await expect(page).toHaveTitle("Scan a square · Field Club");
  // Asked near the middle of the map the panel leaves in sight, rounded to about 100 m.
  const near = Number(squares.asked[0]?.searchParams.get("lon"));
  expect(Math.abs(near - SQUARE_SPOT[0])).toBeLessThan(0.03);
  expect(String(near)).toMatch(/^-1\.\d{1,3}$/);

  // The map goes in to the square, from zoom 13, and centres on it.
  await expect.poll(() => camera(page).zoom).toBeGreaterThan(13.2);
  expect(Math.abs(camera(page).lat - FIRST.centre[1])).toBeLessThan(0.01);
  expect(Math.abs(camera(page).lon - FIRST.centre[0])).toBeLessThan(0.01);

  // Nothing obvious counts, and one press brings the next square.
  await expect(panel(page).getByRole("button", { name: "I marked something" })).toBeDisabled();
  await panel(page).getByRole("button", { name: "Nothing obvious" }).click();
  await expect(panel(page).getByText(`${FIRST.grid_ref} is recorded: nothing obvious.`)).toBeVisible();
  await expect(panel(page).getByText(/1 square\s*looked over this visit/)).toBeVisible();
  await expect(panel(page).getByRole("button", { name: "Next square" })).toBeFocused();
  await expect.poll(() => squares.results[FIRST.square]?.length ?? 0).toBe(1);
  expect(squares.results[FIRST.square]?.[0]).toMatchObject({ result: "nothing", findings_count: 0 });

  await page.keyboard.press("Enter");
  await expect(place(page, SECOND)).toBeVisible();

  // A skip records it for ranking and goes straight on, uncounted.
  await panel(page).getByRole("button", { name: "Skip this square" }).click();
  await expect(place(page, THIRD)).toBeVisible();
  await expect.poll(() => squares.results[SECOND.square]?.[0]?.result).toBe("skipped");
  await expect(panel(page).getByText(/1 square\s*looked over this visit/)).toBeVisible();

  // The square stays through the layer panel.
  await page.getByRole("button", { name: "Layers" }).click();
  await page.getByRole("button", { name: "Layers" }).click();
  await expect(place(page, THIRD)).toBeVisible();
});

test("a signed-out scan, with a finding marked in the square, is kept as drafts and saved once after sign-in", async ({
  page,
}) => {
  const session = await fakeSession(page);
  const squares = await fakeSquares(page, [FIRST, SECOND]);
  const findings = await fakeFindings(page);
  await openMap(page, `/scan${VIEW}`);
  await expect(place(page, FIRST)).toBeVisible();
  await expect(panel(page).getByText(/kept in this browser until you are/)).toBeVisible();
  // Once the map has framed the square, the middle of the map is in it.
  await expect.poll(() => camera(page).zoom).toBeGreaterThan(13.2);
  await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-map-idle", "true");

  // Mark something in the square with the marking flow every mode uses.
  await page.getByRole("button", { name: "Mark a finding" }).click();
  await page.getByRole("button", { name: "Place it here" }).click();
  const mark = page.getByRole("complementary", { name: "Mark a finding" });
  await mark.getByRole("radio", { name: "Hillfort" }).click();
  await mark.getByRole("button", { name: "Save finding" }).click();
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await sheet.getByRole("button", { name: "Close" }).click();

  // Back to the square: the finding counts towards it.
  await backToScan(page);
  await expect(place(page, FIRST)).toBeVisible();
  await expect(panel(page).getByText("You've marked 1 finding in this square.")).toBeVisible();
  await panel(page).getByRole("button", { name: "I marked something" }).click();
  await expect(panel(page).getByText(`${FIRST.grid_ref} is recorded: you marked something.`)).toBeVisible();
  await expect(panel(page).locator(".fc-scan__thanks .fc-draft-badge")).toHaveText("Not saved yet");
  await expect(page.getByRole("region", { name: "Drafts" }).getByRole("status")).toHaveText("2 drafts not saved yet");
  expect(squares.results).toEqual({});

  // The next square leaves out the one kept as a draft, which the server hasn't heard of.
  await panel(page).getByRole("button", { name: "Next square" }).click();
  await expect(place(page, SECOND)).toBeVisible();
  expect(squares.asked.at(-1)?.searchParams.getAll("exclude")).toEqual([FIRST.square]);

  // Away to the provider and back, signed in: both drafts are saved once, and the visit's count is still there.
  await page.route(apiRoute("/auth/oauth/google/start"), (route) => {
    const next = new URL(route.request().url()).searchParams.get("next") ?? "/";
    session.set(MEMBER);
    return route.fulfill({ status: 302, headers: { Location: next } });
  });
  await page.getByRole("region", { name: "Drafts" }).getByRole("button", { name: "Save" }).click();
  await sheet.getByRole("link", { name: "Continue with Google" }).click();
  await expect(place(page, SECOND)).toBeVisible();
  await expect.poll(() => squares.results[FIRST.square]?.length ?? 0).toBe(1);
  expect(squares.results[FIRST.square]?.[0]).toMatchObject({ result: "marked", findings_count: 1 });
  expect(findings.created.map((body) => body.feature_class)).toEqual(["hillfort"]);
  await expect.poll(async () => (await storedDrafts(page)).length).toBe(0);
  await expect(panel(page).getByText(/1 square\s*looked over this visit/)).toBeVisible();
});

test("the coverage layer is offered while scanning and in the layer panel, and refuses a view too wide", async ({
  page,
}) => {
  const squares = await fakeSquares(page, [FIRST, SECOND]);
  await openMap(page, `/scan${VIEW}`);
  await expect(place(page, FIRST)).toBeVisible();
  await panel(page).getByRole("switch", { name: "Scan coverage" }).click();
  await expect(panel(page).getByText(/1 square around here has been looked over/)).toBeVisible();
  expect(squares.coverage.length).toBeGreaterThan(0);

  // From the layer panel at any time, and politely refused when zoomed out too far.
  await openMap(page, "/?panel=layers#m=9/51.4286/-1.8542/0/0&v=composite&o=coverage:100");
  const layers = page.getByRole("complementary", { name: "Layers" });
  await expect(layers.getByRole("switch", { name: "Scan coverage" })).toBeChecked();
  await expect(layers.getByText(/Zoom in to see scan coverage/)).toBeVisible();
});

test.describe("with no square to give", () => {
  // The browser logs each refused request as an error, which here is the point.
  test.use({ pageProblems: "page-errors" });

  test("says there's none left near here, and offers to look again or give a second look", async ({ page }) => {
    await fakeSquares(page, []);
    await openMap(page, `/scan${VIEW}`);
    await expect(panel(page).getByRole("heading", { name: "No square left near here" })).toBeVisible();
    await expect(panel(page).getByRole("link", { name: "Give a second look" })).toHaveAttribute("href", "/review");
  });

  test("says the server is busy and tries again when asked", async ({ page }) => {
    let busy = true;
    await page.route(apiRoute("/squares/next"), (route) =>
      busy
        ? route.fulfill({
            status: 429,
            contentType: "application/json",
            body: JSON.stringify({ error: { code: "rate_limited", message: "Slow down." } }),
          })
        : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FIRST) }),
    );
    await openMap(page, `/scan${VIEW}`);
    await expect(panel(page).getByRole("heading", { name: "The server is busy" })).toBeVisible();
    busy = false;
    await panel(page).getByRole("button", { name: "Try again" }).click();
    await expect(place(page, FIRST)).toBeVisible();
  });

  test("says when a square has no elevation, and finds another without recording it", async ({ page }) => {
    const squares = await fakeSquares(page, [FIRST, SECOND]);
    await page.route(apiRoute("/terrain/coverage"), (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ type: "FeatureCollection", features: [] }),
      }),
    );
    await openMap(page, `/scan${VIEW}`);
    await expect(panel(page).getByText(/There's no one-metre elevation for/)).toBeVisible();
    await panel(page).getByRole("button", { name: "Find another square" }).click();
    await expect.poll(() => squares.asked.length).toBe(2);
    expect(squares.results).toEqual({});
  });
});
