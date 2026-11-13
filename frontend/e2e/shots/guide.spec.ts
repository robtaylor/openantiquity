import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page, test } from "@playwright/test";
import { fakeSession, meWith } from "../support/account.js";
import { openMap } from "../support/app.js";
import { fakeFindings } from "../support/findings.js";
import { stubNetwork } from "../support/network.js";

/**
 * Screenshots of the drawing guide in the search box's place and of the
 * midpoint dots, at desktop and phone width: each state's rows, the guide
 * folded, the swap to search, and a line with its dots. They stub every
 * tile and assert nothing.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const VIEW = "#m=15/51.4286/-1.8542/0/0&v=composite";

async function shoot(page: Page, name: string): Promise<void> {
  await page.waitForTimeout(500);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `guide-${name}-${size?.width}x${size?.height}.png`) });
}

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

async function tapAt(page: Page, x: number, y: number): Promise<void> {
  if (isPhone(page)) await page.touchscreen.tap(x, y);
  else await page.mouse.click(x, y);
}

/** The middle of the part of the map nothing covers, a little low, clear of the guide. */
async function middle(page: Page): Promise<{ x: number; y: number }> {
  const stage = await page.locator(".fc-stage").boundingBox();
  if (!stage) throw new Error("No stage");
  return { x: stage.x + stage.width / 2, y: stage.y + stage.height / 2 + 30 };
}

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
  await fakeFindings(page);
  await fakeSession(page, meWith());
});

test("the guide, state by state", async ({ page }) => {
  await openMap(page, `/mark${VIEW}`);
  const guide = page.getByRole("region", { name: "How to draw" });
  await guide.waitFor();
  await shoot(page, "01-empty");

  const at = await middle(page);
  await tapAt(page, at.x - 90, at.y + 40);
  await page.getByRole("button", { name: /^Point 1 of 1/ }).waitFor();
  await shoot(page, "02-spot");

  await tapAt(page, at.x + 10, at.y - 30);
  await tapAt(page, at.x + 100, at.y + 50);
  await page.getByRole("button", { name: /^Point 3 of 3/ }).waitFor();
  await shoot(page, "03-line-with-dots");

  // The keys, once a point has keyboard focus.
  await page.getByRole("button", { name: /^Point 3 of 3/ }).focus();
  await page.keyboard.press("[");
  await guide.getByText("Step between points").waitFor();
  await shoot(page, "04-keys");
  // "[" selected the point before. Done, by pointer, brings the drawing bar and the pointer's rows back.
  await page.getByRole("button", { name: "Done" }).first().click();
  await page.getByRole("button", { name: "Finish" }).first().click();
  await guide.getByText("Lets you draw on from there").waitFor();
  await shoot(page, "05-finished");

  await page.getByRole("button", { name: "Close the shape" }).first().click();
  await shoot(page, "06-closed-shape");
});

test("the guide folded, and the swap to search", async ({ page }) => {
  await openMap(page, `/mark${VIEW}`);
  const guide = page.getByRole("region", { name: "How to draw" });
  const at = await middle(page);
  await tapAt(page, at.x - 80, at.y);
  await tapAt(page, at.x + 80, at.y);
  await page.getByRole("button", { name: /^Point 2 of 2/ }).waitFor();
  await guide.getByRole("button", { name: "Gestures", exact: true }).click();
  await shoot(page, "10-folded");
  await guide.getByRole("button", { name: "Gestures", exact: true }).click();

  await guide.getByRole("button", { name: "Search for a place" }).click();
  await page.getByRole("combobox", { name: /Search for a place/ }).waitFor();
  await shoot(page, "11-search");
  await page.keyboard.press("Escape");
  await guide.waitFor();
  await shoot(page, "12-back-from-search");
});

test("a curved line with its dots, close in", async ({ page }) => {
  await openMap(page, `/mark${VIEW}`);
  await page
    .getByRole("radio", { name: "Curved" })
    .or(page.getByRole("button", { name: /^Next point/ }))
    .first()
    .click();
  const at = await middle(page);
  for (const [dx, dy] of [
    [-130, 40],
    [-40, -40],
    [50, 30],
    [130, -30],
  ] as const) {
    await tapAt(page, at.x + dx, at.y + dy);
  }
  await page.getByRole("button", { name: /^Point 4 of 4/ }).waitFor();
  await shoot(page, "20-curve-dots");
});
