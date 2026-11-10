import { expect, type Locator, type Page } from "@playwright/test";

/** Open the app and wait for the map to be on screen. */
export async function openMap(page: Page, path = "/"): Promise<void> {
  await page.goto(path);
  await expect(page.locator(".fc-map")).toHaveAttribute("data-ready", "true");
  await expect(page.locator(".fc-map__pane--main canvas")).toBeVisible();
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
