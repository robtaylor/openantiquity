import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page, test } from "@playwright/test";
import { SQUARE_SPOT, squareAt, squareEastOf } from "../../src/test/fixtures/squares.js";
import { fakeSession, meWith } from "../support/account.js";
import { openMap } from "../support/app.js";
import { apiRoute, stubNetwork } from "../support/network.js";
import { fakeSquares } from "../support/squares.js";

/**
 * Screenshots of "Scan a square", taken with `pnpm shots`, for looking at the
 * design at desktop and phone width: a square up, with and without coverage,
 * a finding counted, each result, the phone sheet's three stops, the layer
 * panel's coverage row, and the loading, empty, busy, failed and
 * no-elevation states. They stub every tile, so the map behind is plain, and
 * they assert nothing.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const VIEW = "#m=13/51.4286/-1.8542/0/0&v=composite";
const MEMBER = meWith({ handle: "KeenLynchet7", display_name: "Mary Anning" });
const FIRST = squareAt(...SQUARE_SPOT, 2);
const SECOND = squareEastOf(1, 1);

async function shoot(page: Page, name: string): Promise<void> {
  await page.waitForTimeout(700);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `${name}-${size?.width}x${size?.height}.png`) });
}

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

async function sheetTo(page: Page, stop: "peek" | "half" | "full"): Promise<void> {
  if (!isPhone(page)) return;
  const handle = page.getByRole("button", { name: /Press to resize/ });
  for (let i = 0; i < 3; i++) {
    if ((await page.locator(".fc-shell").getAttribute("data-sheet")) === stop) return;
    await handle.click();
  }
}

function panel(page: Page) {
  return page.getByRole("complementary", { name: "Scan a square" });
}

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
});

test("scan: a square, coverage, results", async ({ page }) => {
  await fakeSquares(page, [FIRST, SECOND]);
  await openMap(page, `/scan${VIEW}`);
  await panel(page).locator(".fc-scan__place").waitFor();
  await shoot(page, "scan-01-square-signed-out");
  await sheetTo(page, "peek");
  await shoot(page, "scan-01b-square-peek");
  await sheetTo(page, "full");
  await shoot(page, "scan-01c-square-full");
  await sheetTo(page, "half");
  await panel(page).getByRole("switch", { name: "Scan coverage" }).click();
  await shoot(page, "scan-02-coverage-on");
  await panel(page).getByRole("button", { name: "Nothing obvious" }).click();
  await panel(page).getByRole("button", { name: "Next square" }).waitFor();
  await shoot(page, "scan-03-recorded-draft");
  await panel(page).getByRole("button", { name: "Next square" }).click();
  await panel(page).locator(".fc-scan__place").filter({ hasText: SECOND.grid_ref }).waitFor();
  await shoot(page, "scan-04-second-square-with-count");
});

test("scan: signed in, a finding counted, marked", async ({ page }) => {
  await fakeSession(page, MEMBER);
  await fakeSquares(page, [FIRST, SECOND]);
  await page.route(apiRoute("/findings"), (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("author") !== MEMBER.handle) return route.fallback();
    const summary = {
      public_id: "f-new",
      title: "Enclosure in SU 10 69",
      feature_class: "enclosure",
      period: "unknown",
      tier: "spotted",
      state: "open",
      state_reason: null,
      confidence: 10,
      sensitivity: "open",
      location: {
        lon: FIRST.centre[0],
        lat: FIRST.centre[1],
        obscured: false,
        grid_ref: "SU 1050 6950",
        square: null,
        outline: null,
      },
      author: { handle: MEMBER.handle, display_name: MEMBER.display_name, avatar_url: null, role: "member" },
      created_at: new Date(Date.now() + 60_000).toISOString(),
      updated_at: new Date().toISOString(),
      evidence_count: 0,
      comment_count: 0,
      mention_count: 0,
    };
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [summary], next_cursor: null }),
    });
  });
  await openMap(page, `/scan${VIEW}`);
  await panel(page).getByText("You've marked 1 finding in this square.").waitFor();
  await shoot(page, "scan-05-finding-counted");
  await panel(page).getByRole("button", { name: "I marked something" }).click();
  await panel(page).getByRole("button", { name: "Next square" }).waitFor();
  await shoot(page, "scan-06-recorded-marked");
});

test("scan: marking a finding in the square", async ({ page }) => {
  await fakeSquares(page, [FIRST, SECOND]);
  await openMap(page, `/scan${VIEW}`);
  await panel(page).locator(".fc-scan__place").waitFor();
  await page.waitForTimeout(700);
  await page.getByRole("button", { name: "Mark a finding" }).click();
  await shoot(page, "scan-13-marking-in-square");
});

test("scan: the layer panel's coverage row", async ({ page }) => {
  await fakeSquares(page, [FIRST, SECOND]);
  await openMap(page, "/?panel=layers#m=9/51.4286/-1.8542/0/0&v=composite&o=coverage:100");
  const layers = page.getByRole("complementary", { name: "Layers" });
  await layers.getByText(/Zoom in to see scan coverage/).scrollIntoViewIfNeeded();
  await sheetTo(page, "full");
  await layers.getByText(/Zoom in to see scan coverage/).scrollIntoViewIfNeeded();
  await shoot(page, "scan-07-layers-too-wide");
});

test("scan: loading, none, busy, failed", async ({ page }) => {
  let release = (): void => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let mode: "hold" | "none" | "busy" | "failed" = "hold";
  await page.route(apiRoute("/squares/next"), async (route) => {
    const reply = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    // The first request waits, so the loading state can be seen, and then finds no square.
    if (mode === "hold") await held;
    if (mode === "hold" || mode === "none")
      return reply(404, { error: { code: "no_square_available", message: "There's no square left." } });
    if (mode === "busy") return reply(429, { error: { code: "rate_limited", message: "Slow down." } });
    return reply(400, { error: { code: "invalid_point", message: "Give both lon and lat, or neither." } });
  });
  await openMap(page, `/scan${VIEW}`);
  await panel(page).getByRole("status").first().waitFor();
  await shoot(page, "scan-08-loading");
  mode = "none";
  release();
  await panel(page).getByRole("heading", { name: "No square left near here" }).waitFor();
  await shoot(page, "scan-09-none");
  mode = "busy";
  await panel(page).getByRole("button", { name: "Look again from here" }).click();
  await panel(page).getByRole("heading", { name: "The server is busy" }).waitFor();
  await shoot(page, "scan-10-busy");
  mode = "failed";
  await panel(page).getByRole("button", { name: "Try again" }).click();
  await panel(page).getByRole("heading", { name: "The next square couldn't be fetched" }).waitFor();
  await shoot(page, "scan-11-failed");
});

test("scan: a square with no elevation", async ({ page }) => {
  await fakeSquares(page, [FIRST, SECOND]);
  await page.route(apiRoute("/terrain/coverage"), (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ type: "FeatureCollection", features: [] }),
    }),
  );
  await openMap(page, `/scan${VIEW}`);
  await panel(page)
    .getByText(/There's no one-metre elevation for/)
    .waitFor();
  await shoot(page, "scan-12-no-elevation");
});
