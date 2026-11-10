import type { Page, Route } from "@playwright/test";
import { DRAFTS_STORAGE_KEY, DRAFTS_VERSION } from "../src/features/drafts/store.js";
import { fakeSession, meWith } from "./support/account.js";
import { openMap } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";
import { apiRoute, stubNetwork } from "./support/network.js";

/**
 * Drafts, in fixture mode. No feature has registered a real saver yet, so
 * these use the stand-in `fixture_probe` kind that `main.tsx` registers in
 * fixture mode only (`src/features/drafts/fixtureSaver.ts`). It saves by
 * posting to `/_fixture/drafts`, which these tests answer and count.
 */

const KIND = "fixture_probe";

const EPOCH = "seeded-epoch";

/**
 * Put drafts in this browser's storage, as signed-out work would have, or
 * as someone else's work left behind when `owner` is given.
 */
async function seedDrafts(page: Page, notes: string[], owner: object = { signedOut: EPOCH }): Promise<void> {
  const now = new Date().toISOString();
  const drafts = notes.map((note, index) => ({
    id: `seed-${index}-${note}`,
    kind: KIND,
    data: { note },
    owner,
    createdAt: now,
    updatedAt: now,
    state: "waiting",
  }));
  await page.evaluate(([key, value]) => localStorage.setItem(key, value), [
    DRAFTS_STORAGE_KEY,
    JSON.stringify({ version: DRAFTS_VERSION, epoch: EPOCH, drafts }),
  ] as const);
}

interface SaveLog {
  notes: string[];
}

/** Answer the stand-in saver's endpoint, keeping what was saved. */
async function answerSaves(
  page: Page,
  respond: (route: Route) => Promise<void> | void = (route) => route.fulfill({ status: 201, body: "{}" }),
  log: SaveLog = { notes: [] },
): Promise<SaveLog> {
  await page.route(apiRoute("/_fixture/drafts"), async (route) => {
    log.notes.push((route.request().postDataJSON() as { note: string }).note);
    await respond(route);
  });
  return log;
}

function bar(page: Page) {
  return page.getByRole("region", { name: "Drafts" });
}

test("keeps drafts through a reload and a provider's round trip, then saves each once", async ({ page }) => {
  const session = await fakeSession(page);
  const saves = await answerSaves(page);
  await openMap(page, "/review#m=13.5/51.4/-1.85/0/0&v=slope");
  await seedDrafts(page, ["ring ditch"]);
  await page.reload();
  await expect(bar(page).getByRole("status")).toHaveText("1 draft not saved yet");

  // A reload keeps it.
  await page.reload();
  await expect(bar(page).getByRole("status")).toHaveText("1 draft not saved yet");
  const before = new URL(page.url());

  // The provider round trip: the start route sends the browser away and back to `next`, signed in.
  await page.route(apiRoute("/auth/oauth/google/start"), (route) => {
    const next = new URL(route.request().url()).searchParams.get("next") ?? "/";
    session.set(meWith());
    return route.fulfill({ status: 302, headers: { Location: next } });
  });
  await bar(page).getByRole("button", { name: "Save" }).click();
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await sheet.getByRole("link", { name: "Continue with Google" }).click();

  await expect(page.getByText("Your draft is saved.")).toBeVisible();
  await expect(bar(page)).toHaveCount(0);
  const after = new URL(page.url());
  expect(after.pathname).toBe(before.pathname);
  expect(after.hash).toContain("m=13.5/51.4/-1.85/0/0");
  expect(after.hash).toContain("v=slope");
  await page.waitForTimeout(500);
  expect(saves.notes).toEqual(["ring ditch"]);
  const left = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? "{}"), DRAFTS_STORAGE_KEY);
  expect(left).toMatchObject({ version: DRAFTS_VERSION, drafts: [] });
});

test("asks before saving drafts someone else left in this browser", async ({ page }) => {
  await fakeSession(page, meWith());
  const saves = await answerSaves(page);
  await openMap(page, "/");
  await seedDrafts(page, ["their barrow"], { account: "someone-else" });
  await page.reload();
  await expect(bar(page).getByRole("status")).toHaveText("1 draft left here");
  await page.waitForTimeout(300);
  expect(saves.notes).toEqual([]);

  await bar(page).getByRole("button", { name: "Check" }).click();
  await expect(bar(page).getByText(/left in this browser before you signed in, perhaps by someone else/)).toBeVisible();
  await bar(page).getByRole("button", { name: "Save as mine" }).click();
  await expect(page.getByText("Your draft is saved.")).toBeVisible();
  expect(saves.notes).toEqual(["their barrow"]);
});

test("saves each draft once with two tabs open", async ({ page, context }) => {
  test.skip((page.viewportSize()?.width ?? 0) < 720, "one layout is enough for this");
  const other = await context.newPage();
  await stubNetwork(other);
  const sessions = [await fakeSession(page), await fakeSession(other)];
  const log: SaveLog = { notes: [] };
  // Slow saves, so the two tabs are both trying at the same time.
  const slow = async (route: Route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({ status: 201, body: "{}" });
  };
  await answerSaves(page, slow, log);
  await answerSaves(other, slow, log);

  await openMap(page, "/");
  await seedDrafts(page, ["first", "second"]);
  await page.reload();
  await openMap(other, "/");
  for (const tab of [page, other]) await expect(bar(tab).getByRole("status")).toHaveText("2 drafts not saved yet");

  // Both tabs learn of the sign-in at once.
  for (const session of sessions) session.set(meWith());
  await Promise.all(
    [page, other].map((tab) =>
      tab.evaluate(() => window.dispatchEvent(new StorageEvent("storage", { key: "fieldclub.session-changed" }))),
    ),
  );
  for (const tab of [page, other]) await expect(bar(tab)).toHaveCount(0);
  await page.waitForTimeout(800);
  expect(log.notes.sort()).toEqual(["first", "second"]);
  await other.close();
});

test.describe("a save that fails", () => {
  // The browser logs the 422 these tests are built on.
  test.use({ pageProblems: "page-errors" });

  test("keeps the draft with its reason through a reload, and saves it when asked again", async ({ page }) => {
    await fakeSession(page, meWith());
    let refuse = true;
    const saves = await answerSaves(page, (route) =>
      refuse
        ? route.fulfill({
            status: 422,
            contentType: "application/json",
            body: JSON.stringify({ error: { code: "validation_error", message: "That square isn't in Britain." } }),
          })
        : route.fulfill({ status: 201, body: "{}" }),
    );
    await openMap(page, "/");
    await seedDrafts(page, ["offshore"]);
    await page.reload();
    await expect(page.getByText("One draft couldn't be saved. It's still here, with the reason.")).toBeVisible();
    await expect(bar(page).getByRole("status")).toHaveText("1 draft couldn't be saved");

    // Still there after a reload, and not sent again unasked.
    await page.reload();
    await expect(bar(page).getByRole("status")).toHaveText("1 draft couldn't be saved");
    await bar(page).getByRole("button", { name: "Show drafts" }).click();
    await expect(bar(page).getByText("Couldn't be saved: That square isn't in Britain.")).toBeVisible();
    expect(saves.notes).toEqual(["offshore"]);

    refuse = false;
    await bar(page).getByRole("button", { name: "Try again" }).first().click();
    await expect(page.getByText("Your draft is saved.")).toBeVisible();
    await expect(bar(page)).toHaveCount(0);
    expect(saves.notes).toEqual(["offshore", "offshore"]);
  });
});

test("the drafts bar and its list stay on screen, clear of the other controls", async ({ page }) => {
  await fakeSession(page);
  await openMap(page, "/");
  await seedDrafts(page, ["a", "b", "c"]);
  await page.reload();
  const region = bar(page);
  await expect(region.getByRole("status")).toHaveText("3 drafts not saved yet");
  const strip = region.locator(".fc-drafts__bar");
  const closed = await strip.boundingBox();
  await region.getByRole("button", { name: "Show drafts" }).click();
  const viewport = page.viewportSize() ?? { width: 0, height: 0 };
  const box = await region.boundingBox();
  const list = await region.locator(".fc-drafts__list").boundingBox();
  if (!box || !closed || !list) throw new Error("No drafts bar on screen");
  // Opening the list doesn't change the bar.
  expect(await strip.boundingBox()).toEqual(closed);
  for (const shown of [box, list]) {
    expect(shown.x).toBeGreaterThanOrEqual(0);
    expect(shown.x + shown.width).toBeLessThanOrEqual(viewport.width);
  }
  for (const name of ["Layers", "Zoom in"]) {
    const control = await page.getByRole("button", { name, exact: true }).boundingBox();
    if (!control) continue;
    const overlap =
      box.x < control.x + control.width &&
      control.x < box.x + box.width &&
      box.y < control.y + control.height &&
      control.y < box.y + box.height;
    expect(overlap, `drafts bar over ${name}`).toBe(false);
  }
  await page.keyboard.press("Escape");
  await expect(region.getByRole("button", { name: "Show drafts" })).toHaveAttribute("aria-expanded", "false");
});
