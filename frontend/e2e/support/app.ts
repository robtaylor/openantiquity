import { expect, type Locator, type Page } from "@playwright/test";

/** The bare map, with no panel open. `/` itself opens the Explore panel. */
export const BARE_MAP = "/?panel=none";

/**
 * How long a map tilted into 3D may take to settle. The test browser draws terrain in software,
 * which takes most of a minute alone and longer while other suites are running. On a slow CI
 * runner one of two panes took 56 seconds, so the limit is twice that.
 */
export const SLOW_MAP = { timeout: 120_000 } as const;

/**
 * Open the app, at the bare map unless told otherwise, and wait for the map to be on screen.
 * Pass `SLOW_MAP` for an address that opens in 3D.
 */
export async function openMap(page: Page, path = BARE_MAP, wait?: { timeout: number }): Promise<void> {
  await page.goto(path);
  await expect(page.locator(".fc-map")).toHaveAttribute("data-ready", "true", wait);
  await expect(page.locator(".fc-map__pane--main canvas")).toBeVisible(wait);
}

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

export async function boxOf(locator: Locator): Promise<Box> {
  const box = await locator.boundingBox();
  if (!box) throw new Error(`Nothing on screen for ${locator}`);
  return box;
}

export function overlaps(a: Box, b: Box): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

/** What the focused element is, in words, for failure messages. */
export function describeFocus(page: Page): Promise<string> {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (!element || element === document.body) return "nothing";
    const name = element.getAttribute("aria-label") ?? element.textContent?.trim().slice(0, 40) ?? "";
    return `${element.tagName.toLowerCase()}.${element.className} "${name}"`;
  });
}

/** Press Tab until `target` has focus. Fails if it never arrives. */
export async function tabTo(page: Page, target: Locator, limit = 60): Promise<number> {
  for (let presses = 1; presses <= limit; presses++) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((element) => element === document.activeElement)) return presses;
  }
  throw new Error(`Tab never reached ${target}. Focus ended on ${await describeFocus(page)}.`);
}

/**
 * After a sign-in from this tab, the drafts made before it wait to be sent (Decision 0024): open the
 * drafts bar and send them, as the person would. `count` is how many are waiting.
 */
export async function sendDraftsFromBeforeSignIn(page: Page, count = 1): Promise<void> {
  const bar = page.getByRole("region", { name: "Drafts" });
  const noun = count === 1 ? "draft" : "drafts";
  await expect(bar.getByRole("status")).toHaveText(`${count} ${noun} to send`);
  await bar.getByRole("button", { name: "Check" }).click();
  await bar.getByRole("button", { name: count === 1 ? "Send it" : "Send all", exact: true }).click();
}
