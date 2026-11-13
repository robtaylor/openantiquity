import type { Locator, Page } from "@playwright/test";
import { boxOf, drag, openMap } from "./support/app.js";
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
