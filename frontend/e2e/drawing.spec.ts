import type { Locator, Page } from "@playwright/test";
import { DRAFTS_STORAGE_KEY, DRAFTS_VERSION } from "../src/features/drafts/store.js";
import { boxOf, drag, openMap, overlaps } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";

/**
 * The drawing tool's midpoint dots and its guidance on the map, in fixture
 * mode, at desktop and phone width: a mouse on a desktop and a finger on a
 * phone.
 */

const VIEW = "#m=15/51.4286/-1.8542/0/0&v=composite";

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

/** A tap on a phone, a click on a desktop. */
async function tapAt(page: Page, at: { x: number; y: number }): Promise<void> {
  if (isPhone(page)) await page.touchscreen.tap(at.x, at.y);
  else await page.mouse.click(at.x, at.y);
}

async function middleOf(locator: Locator): Promise<{ x: number; y: number }> {
  const box = await boxOf(locator);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

function point(page: Page, index: number, of: number): Locator {
  return page.getByRole("button", { name: new RegExp(`^Point ${index} of ${of},`) });
}

/** Opens the tool and draws a line of two points 160 px apart across the middle of the uncovered map. */
async function drawLine(page: Page): Promise<{ x: number; y: number }> {
  await openMap(page, `/mark${VIEW}`);
  await page.getByRole("complementary", { name: "Mark a finding" }).waitFor();
  const stage = await middleOf(page.locator(".fc-stage"));
  const middle = { x: stage.x, y: stage.y + 40 };
  await tapAt(page, { x: middle.x - 80, y: middle.y });
  await expect(point(page, 1, 1)).toBeVisible();
  await tapAt(page, { x: middle.x + 80, y: middle.y });
  await expect(point(page, 2, 2)).toBeVisible();
  return middle;
}

test.describe("midpoint dots", () => {
  test("a dot dragged inserts a point where it is dropped, as one step to undo", async ({ page }) => {
    const middle = await drawLine(page);
    const dot = page.getByTestId("midpoint-dot");
    await expect(dot).toHaveCount(1);
    const from = await middleOf(dot);
    expect(Math.abs(from.x - middle.x)).toBeLessThan(3);
    expect(Math.abs(from.y - middle.y)).toBeLessThan(3);

    const to = { x: middle.x + 10, y: middle.y + 60 };
    await drag(page, from, to);
    await expect(point(page, 2, 3)).toBeVisible();
    const dropped = await middleOf(point(page, 2, 3));
    expect(Math.abs(dropped.x - to.x)).toBeLessThan(3);
    expect(Math.abs(dropped.y - to.y)).toBeLessThan(3);
    await expect(point(page, 2, 3)).toHaveAttribute("aria-pressed", "false");
    // The ends stayed where they were.
    const first = await middleOf(point(page, 1, 3));
    expect(Math.abs(first.x - (middle.x - 80))).toBeLessThan(3);

    await page.getByRole("button", { name: "Undo" }).first().click();
    await expect(point(page, 2, 2)).toBeVisible();
    await expect(page.getByRole("button", { name: /^Point \d of 3,/ })).toHaveCount(0);
  });

  test("a tap or click on a dot inserts a point there and selects it", async ({ page }) => {
    const middle = await drawLine(page);
    await tapAt(page, await middleOf(page.getByTestId("midpoint-dot")));
    await expect(point(page, 2, 3)).toHaveAttribute("aria-pressed", "true");
    const placed = await middleOf(point(page, 2, 3));
    expect(Math.abs(placed.x - middle.x)).toBeLessThan(3);
    expect(Math.abs(placed.y - middle.y)).toBeLessThan(3);
    await expect(page.getByRole("region", { name: "Selected point" }).first()).toBeVisible();
  });
});

function guide(page: Page): Locator {
  return page.getByRole("region", { name: "How to draw" });
}

function searchBox(page: Page): Locator {
  return page.getByRole("combobox", { name: /Search for a place/ });
}

test.describe("the drawing guide", () => {
  test("takes the search box's place while the tool is open, and the search box is back when it closes", async ({
    page,
  }) => {
    await openMap(page, `/${VIEW}`);
    await expect(searchBox(page)).toBeVisible();
    await expect(guide(page)).toHaveCount(0);
    await page.locator(".fc-stage__primary").getByRole("button", { name: "Mark a finding" }).click();
    await expect(guide(page)).toBeVisible();
    await expect(page.locator(".fc-stage__search").getByRole("region", { name: "How to draw" })).toBeVisible();
    await expect(searchBox(page)).toHaveCount(0);
    await expect(guide(page).getByRole("listitem").first()).toContainText(/^(Click|Tap) the map/);

    await page
      .getByRole("complementary", { name: "Mark a finding" })
      .getByRole("button", { name: "Close panel" })
      .click();
    await expect(searchBox(page)).toBeVisible();
    await expect(guide(page)).toHaveCount(0);
  });

  test("swaps to the search box with focus in it, and back on Escape, still drawing", async ({ page }) => {
    await openMap(page, `/mark${VIEW}`);
    await guide(page).getByRole("button", { name: "Search for a place" }).click();
    await expect(searchBox(page)).toBeFocused();
    await expect(guide(page)).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(guide(page)).toBeVisible();
    await expect(guide(page).getByRole("button", { name: "Search for a place" })).toBeFocused();
    await expect(page).toHaveURL(/\/mark#/);
    await expect(page.getByRole("complementary", { name: "Mark a finding" })).toBeVisible();
  });

  test("never moves the map as it grows, folds or unfolds, even over a point", async ({ page }) => {
    await openMap(page, `/mark${VIEW}`);
    const card = await boxOf(guide(page));
    // Just below the card as it is with nothing placed. Once a point is there the card grows over it.
    await tapAt(page, { x: card.x + 60, y: card.y + card.height + 12 });
    await expect(point(page, 1, 1)).toBeVisible();
    await page.waitForTimeout(300);
    const hash = new URL(page.url()).hash;
    await tapAt(page, { x: card.x + 220, y: card.y + card.height + 200 });
    await expect(point(page, 2, 2)).toBeVisible();
    await guide(page).getByRole("button", { name: "Gestures", exact: true }).click();
    await guide(page).getByRole("button", { name: "Gestures", exact: true }).click();
    await page.waitForTimeout(500);
    expect(new URL(page.url()).hash).toBe(hash);
  });

  test("folds to its header, and stays folded next time", async ({ page }) => {
    await openMap(page, `/mark${VIEW}`);
    const open = await boxOf(guide(page));
    await guide(page).getByRole("button", { name: "Gestures", exact: true }).click();
    await expect(guide(page).getByRole("list")).toBeHidden();
    const folded = await boxOf(guide(page));
    expect(folded.height).toBeLessThan(60);
    expect(folded.height).toBeLessThan(open.height);

    await page.reload();
    await expect(guide(page)).toBeVisible();
    await expect(guide(page).getByRole("list")).toBeHidden();
    await guide(page).getByRole("button", { name: "Gestures", exact: true }).click();
    await expect(guide(page).getByRole("list")).toBeVisible();
  });

  test("keeps every row to two lines at most, clear of the map's buttons", async ({ page }) => {
    await drawLine(page);
    await tapAt(page, await middleOf(page.locator(".fc-stage")).then(({ x, y }) => ({ x, y: y + 120 })));
    await expect(guide(page).getByRole("listitem")).toHaveCount(6);
    expect(await tallestRow(page)).toBeLessThanOrEqual(2.05);
    const card = await boxOf(guide(page));
    const buttons = await boxOf(page.locator(".fc-stage__controls"));
    const apart = card.x + card.width <= buttons.x || card.y + card.height <= buttons.y;
    expect(apart, "the guide is clear of the map's buttons").toBe(true);

    await page.getByRole("button", { name: "Finish" }).first().click();
    await expect(guide(page)).toContainText("Lets you draw on from there");
    expect(await tallestRow(page)).toBeLessThanOrEqual(2.05);
  });
});

/** The most lines any part of any row of the guide runs to. */
async function tallestRow(page: Page): Promise<number> {
  return guide(page)
    .getByRole("listitem")
    .evaluateAll((items) =>
      Math.max(
        ...items.flatMap((item) =>
          Array.from(item.children).map((part) => {
            const lines = part.getBoundingClientRect().height / Number.parseFloat(getComputedStyle(part).lineHeight);
            return Number.isFinite(lines) ? lines : 0;
          }),
        ),
      ),
    );
}

/** One signed-out draft waiting in this tab, of the stand-in kind fixture mode registers. */
async function seedDraft(page: Page): Promise<void> {
  const now = new Date().toISOString();
  const draft = {
    id: "seed-waiting",
    kind: "fixture_probe",
    data: { note: "waiting" },
    owner: { signedOut: "seeded-visit" },
    createdAt: now,
    updatedAt: now,
    state: "waiting",
  };
  await page.addInitScript(
    ([key, value]) => {
      localStorage.setItem(key, value);
      sessionStorage.setItem("fieldclub.drafts.visit", "seeded-visit");
    },
    [DRAFTS_STORAGE_KEY, JSON.stringify({ version: DRAFTS_VERSION, drafts: [draft] })] as const,
  );
}

test.describe("the drafts bar beside the guide", () => {
  test("sits below the guide, unfolded and folded, where there is no room beside it", async ({ page }) => {
    // A computer's stage under 820 px puts the bar under the search slot, as a phone does.
    if (!isPhone(page)) await page.setViewportSize({ width: 1000, height: 800 });
    await seedDraft(page);
    await openMap(page, `/mark${VIEW}`);
    const drafts = page.getByRole("region", { name: "Drafts" });
    await expect(drafts).toBeVisible();
    for (const state of ["unfolded", "folded"] as const) {
      if (state === "folded") {
        await guide(page).getByRole("button", { name: "Gestures", exact: true }).click();
        await expect(guide(page).getByRole("list")).toBeHidden();
      }
      await page.waitForTimeout(300);
      const card = await boxOf(guide(page));
      const bar = await boxOf(drafts);
      expect(overlaps(card, bar), `the drafts bar overlaps the ${state} guide`).toBe(false);
      expect(bar.y, `the drafts bar is below the ${state} guide`).toBeGreaterThanOrEqual(card.y + card.height);
      expect(bar.y - (card.y + card.height)).toBeLessThan(20);
    }
  });
});
