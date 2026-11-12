import type { Page } from "@playwright/test";
import { answerJson } from "./support/account.js";
import { boxOf, describeFocus, openMap, overlaps, SLOW_MAP, tabTo } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";

/**
 * Keyboard, focus and small-screen behaviour, checked in a real browser
 * because none of it shows up in jsdom: what is drawn, what is covered, and
 * what scrolls.
 */

/** The focus ring colour, `--accent-strong`. */
const RING = "rgb(242, 185, 79)";

interface Ring {
  style: string;
  width: string;
  colour: string;
  focusVisible: boolean;
}

function ringOf(page: Page, selector?: string): Promise<Ring> {
  return page.evaluate((ringSelector) => {
    const focused = document.activeElement as HTMLElement;
    const drawn = ringSelector ? (document.querySelector(ringSelector) as HTMLElement) : focused;
    const computed = getComputedStyle(drawn);
    return {
      style: computed.outlineStyle,
      width: computed.outlineWidth,
      colour: computed.outlineColor,
      focusVisible: focused.matches(":focus-visible"),
    };
  }, selector);
}

const HAS_RING: Ring = { style: "solid", width: "2px", colour: RING, focusVisible: true };

test.describe("desktop", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) < 720, "desktop layout only");

  test("draws a focus ring on the controls that float on the map", async ({ page }) => {
    await openMap(page);
    // These all carry a drop shadow, which used to replace the ring, itself a shadow.
    for (const control of [
      page.getByRole("combobox", { name: /Search for a place/ }),
      page.getByRole("button", { name: "Layers" }),
      page.getByRole("button", { name: "Tilt into 3D" }),
      page.getByRole("button", { name: "Zoom in" }),
      page.getByRole("button", { name: "Zoom out" }),
      page.getByRole("button", { name: "Mark a finding" }),
    ]) {
      await tabTo(page, control);
      expect(await ringOf(page), `focus ring on ${await describeFocus(page)}`).toEqual(HAS_RING);
    }
  });

  test("draws the map's own focus ring round the part of the map that shows", async ({ page }) => {
    await openMap(page, "/review");
    await tabTo(page, page.locator(".fc-map__pane--main canvas"));
    // The canvas runs under the rail, the panel and the status bar. The ring is drawn on the stage, which does not.
    expect(await ringOf(page, ".fc-stage")).toEqual(HAS_RING);
    const stage = await boxOf(page.locator(".fc-stage"));
    expect(stage.x).toBe(56);
    expect(stage.x + stage.width).toBe(1440 - 400);
    expect(stage.y + stage.height).toBe(900 - 28);
    // And it goes when focus moves on.
    await page.keyboard.press("Tab");
    expect((await ringOf(page, ".fc-stage")).style).toBe("none");
  });

  test("moves focus into a panel when it opens and back out when it closes", async ({ page }) => {
    await openMap(page);
    const layers = page.getByRole("button", { name: "Layers" });
    await tabTo(page, layers);
    await page.keyboard.press("Enter");
    const panel = page.getByRole("complementary", { name: "Layers" });
    await expect(panel.getByRole("heading", { name: "Layers" })).toBeFocused();

    // One press of Tab is inside the panel. It used to take fourteen.
    await page.keyboard.press("Tab");
    await expect(panel.getByRole("button", { name: "Close panel" })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(panel.getByRole("switch", { name: "Compare two layers" })).toBeFocused();

    // Escape closes from anywhere inside, and focus goes back to the button that opened it.
    await page.keyboard.press("Escape");
    await expect(panel).toHaveCount(0);
    await expect(page).not.toHaveURL(/panel=layers/);
    await expect(layers).toBeFocused();

    // The same with the close button.
    await page.keyboard.press("Enter");
    await expect(panel.getByRole("heading", { name: "Layers" })).toBeFocused();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");
    await expect(panel).toHaveCount(0);
    await expect(layers).toBeFocused();
  });

  test("does the same for a mode opened from the rail", async ({ page }) => {
    await openMap(page);
    const link = page.getByRole("navigation", { name: "Modes" }).getByRole("link", { name: "Second look" });
    await tabTo(page, link);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/review#/);
    await expect(page.getByRole("heading", { name: "Second look" })).toBeFocused();
    await page.keyboard.press("Escape");
    // Closing a panel leaves the bare map.
    await expect(page).toHaveURL(/\/\?panel=none#/);
    await expect(link).toBeFocused();
  });

  test("has a main landmark and a top-level heading", async ({ page }) => {
    await openMap(page);
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("OpenAntiquity");
    await expect(page.getByRole("main").locator(".fc-map")).toHaveCount(1);
  });

  test("answers a search that finds nothing with a notice", async ({ page }) => {
    await answerJson(page, "/geo/search", { items: [] });
    await openMap(page);
    const search = page.getByRole("combobox", { name: /Search for a place/ });
    await search.fill("Avebury");
    await search.press("Enter");
    await expect(page.getByRole("status").filter({ hasText: "Nothing matches “Avebury”" })).toBeVisible();
  });

  test("zooms with the buttons and resets a turned map with the compass", async ({ page }) => {
    await openMap(page, "/?panel=none#m=14/51.4286/-1.8542/-46.2/0&v=composite");
    await page.getByRole("button", { name: "Zoom in" }).click();
    await expect(page.getByTestId("status-zoom")).toHaveText("z15.0");
    await page.getByRole("button", { name: "Zoom out" }).click();
    await page.getByRole("button", { name: "Zoom out" }).click();
    await expect(page.getByTestId("status-zoom")).toHaveText("z13.0");

    const compass = page.getByRole("button", { name: "Reset to north-up" });
    await expect(compass).toBeVisible();
    await compass.click();
    await expect(page).toHaveURL(/#m=13\/[\d.-]+\/[\d.-]+\/0\/0&/);
    await expect(compass).toHaveCount(0);
  });

  test("keeps the 3D view when the compass turns a tilted map north-up", async ({ page }) => {
    test.slow();
    await openMap(page, "/?panel=none#m=14/51.4286/-1.8542/-46.2/60&v=raking&s=300/25&x=2&t=1/1.5", SLOW_MAP);
    const threeD = page.getByRole("button", { name: "Tilt into 3D" });
    await expect(threeD).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "Reset to north-up" }).click();
    await expect(page).toHaveURL(/#m=14\/[\d.-]+\/[\d.-]+\/0\/60&.*\bt=1\/1\.5\b/);
    await expect(threeD).toHaveAttribute("aria-pressed", "true");
  });

  test("keeps the comparison divide, its grip and its labels inside the map", async ({ page }) => {
    await openMap(page, "/?panel=none#m=14/51.4286/-1.8542/0/0&v=composite&c=osm_standard");
    const divide = page.getByRole("slider", { name: "Comparison divide" });
    const grip = page.locator(".fc-swipe__grip");
    const buttons = page.locator(".fc-stage__controls");
    await expect(page.locator(".fc-map__pane--compare canvas")).toBeVisible();

    // At the half-way mark the divide runs behind the primary button, so its line stops above it.
    const line = await boxOf(page.locator(".fc-swipe__line"));
    const primary = await boxOf(page.getByRole("button", { name: "Mark a finding" }));
    expect(line.x).toBeGreaterThan(primary.x);
    expect(line.x).toBeLessThan(primary.x + primary.width);
    expect(line.y + line.height).toBeLessThanOrEqual(primary.y);
    await expect(page.locator(".fc-swipe__label")).toHaveText(["Composite", "OpenStreetMap"]);

    await divide.focus();

    await page.keyboard.press("Home");
    let gripBox = await boxOf(grip);
    // Clear of the 56 px rail.
    expect(gripBox.x).toBeGreaterThanOrEqual(56);
    // No room for the left-hand name here, so only the right-hand one is shown.
    await expect(page.locator(".fc-swipe__label")).toHaveText(["OpenStreetMap"]);

    await page.keyboard.press("End");
    gripBox = await boxOf(grip);
    expect(gripBox.x + gripBox.width).toBeLessThanOrEqual(1440);
    const labels = page.locator(".fc-swipe__label");
    await expect(labels).toHaveText(["Composite"]);
    expect(overlaps(await boxOf(labels.first()), await boxOf(buttons)), "label under the buttons").toBe(false);
  });

  test("fits the whole rail in a window as short as a phone held sideways", async ({ page }) => {
    await page.setViewportSize({ width: 844, height: 390 });
    await openMap(page);
    const rail = page.getByRole("navigation", { name: "Modes" });
    for (const name of ["Explore", "Activity", "Guide", "About", "Account"]) {
      const link = rail.getByRole("link", { name });
      await link.scrollIntoViewIfNeeded();
      await expect(link, `${name} link`).toBeInViewport({ ratio: 1 });
    }
    // The pop-out labels are clipped by a rail that scrolls, so each link carries a tooltip of its own.
    await expect(rail.getByRole("link", { name: "Account" })).toHaveAttribute("title", "Account");
    // And if the window is shorter still, the rail scrolls.
    await page.setViewportSize({ width: 844, height: 300 });
    const account = rail.getByRole("link", { name: "Account" });
    await account.scrollIntoViewIfNeeded();
    await expect(account).toBeInViewport({ ratio: 1 });
  });
});

test.describe("forced colours", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) < 720, "one layout is enough for this");
  test.use({ forcedColors: "active" });

  test("still shows which switches are on, and still draws the focus ring", async ({ page }) => {
    await openMap(page, "/?panel=layers");
    const panel = page.getByRole("complementary", { name: "Layers" });
    const look = (name: string) =>
      panel.getByRole("switch", { name, exact: true }).evaluate((element) => {
        const knob = getComputedStyle(element, "::before");
        return { track: getComputedStyle(element).backgroundColor, knob: knob.backgroundColor };
      });
    // Findings is on and scan coverage is off. With author colours gone, they used to look the same.
    const on = await look("Findings");
    const off = await look("Scan coverage");
    expect(on.track).not.toBe(off.track);
    expect(on.knob).not.toBe(off.knob);

    // The ring is an outline, which this mode keeps. As a box-shadow it vanished.
    await tabTo(page, page.getByRole("button", { name: "Layers" }));
    const ring = await ringOf(page);
    expect(ring.style).toBe("solid");
    expect(ring.width).toBe("2px");
    expect(ring.focusVisible).toBe(true);
  });
});

test.describe("phone", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) >= 720, "phone layout only");

  test("keeps the shell still while Tab goes through a half-open sheet, and never lands on anything hidden", async ({
    page,
  }) => {
    await openMap(page, "/?panel=layers#m=14/51.4286/-1.8542/0/0&v=raking");
    const sheet = page.getByRole("complementary", { name: "Layers" });
    await expect(sheet).toHaveAttribute("data-stop", "half");
    const tabBar = page.getByRole("navigation", { name: "Modes" });
    const before = await boxOf(tabBar);
    const search = await boxOf(page.getByRole("combobox", { name: /Search for a place/ }));

    const seen = new Set<string>();
    for (let presses = 0; presses < 70; presses++) {
      await page.keyboard.press("Tab");
      const state = await page.evaluate(() => {
        const element = document.activeElement as HTMLElement | null;
        const shell = document.querySelector(".fc-shell") as HTMLElement;
        if (!element || element === document.body) return { scrollTop: shell.scrollTop, label: "body", onTop: true };
        const box = element.getBoundingClientRect();
        const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
        const labelledBy = element.getAttribute("aria-labelledby");
        const name =
          element.getAttribute("aria-label") ??
          (labelledBy ? document.getElementById(labelledBy)?.textContent : null) ??
          element.textContent ??
          "";
        const label = `${element.tagName.toLowerCase()}.${String(element.className).split(" ")[0]} ${name.trim().slice(0, 30)}`;
        // The map canvas is the one thing that is meant to lie under everything else.
        const isCanvas = element.tagName === "CANVAS";
        const onTop = isCanvas || (hit !== null && (element.contains(hit) || hit.contains(element)));
        return { scrollTop: shell.scrollTop, label, onTop };
      });
      expect(state.scrollTop, `shell scrolled after focusing ${state.label}`).toBe(0);
      expect(state.onTop, `${state.label} took focus while something else was drawn over it`).toBe(true);
      seen.add(state.label);
    }
    // The walk went through the sheet and the controls on the map.
    expect([...seen].join(" | ")).toContain("Scan coverage");
    expect([...seen].join(" | ")).toContain("Mark a finding");
    expect([...seen].join(" | ")).toContain("Sun direction");

    expect(await boxOf(tabBar), "tab bar moved").toEqual(before);
    expect(await boxOf(page.getByRole("combobox", { name: /Search for a place/ })), "search field moved").toEqual(
      search,
    );
  });

  test("scrolls a half-open sheet all the way to its end", async ({ page }) => {
    await openMap(page, "/?panel=layers");
    const sheet = page.getByRole("complementary", { name: "Layers" });
    await expect(sheet).toHaveAttribute("data-stop", "half");
    const tabBar = await boxOf(page.getByRole("navigation", { name: "Modes" }));
    // The sheet ends where the tab bar begins. It used to run 360 px below the window.
    const sheetBox = await boxOf(sheet);
    expect(sheetBox.y + sheetBox.height).toBeLessThanOrEqual(tabBar.y);

    const body = sheet.locator(".fc-panel__body");
    await body.evaluate((element) => element.scrollTo(0, element.scrollHeight));
    const lastCredit = sheet.locator(".fc-layers__credits li").last();
    await expect(lastCredit).toBeInViewport({ ratio: 1 });
    const creditBox = await boxOf(lastCredit);
    expect(creditBox.y + creditBox.height).toBeLessThanOrEqual(tabBar.y);
    await expect(sheet.getByRole("switch", { name: "Scan coverage" })).toBeInViewport({ ratio: 1 });
  });

  test("keeps the primary action, the status bar and the sun dial clear of a half-open sheet", async ({ page }) => {
    await openMap(page, "/?panel=layers#m=14/51.4286/-1.8542/0/0&v=raking");
    const sheet = page.getByRole("complementary", { name: "Layers" });
    await expect(sheet).toHaveAttribute("data-stop", "half");
    // Let the controls finish gliding up with the sheet.
    await page.waitForTimeout(400);
    const sheetBox = await boxOf(sheet);
    const primary = page.getByRole("button", { name: "Mark a finding" });
    const status = page.locator(".fc-shell__status");
    const raking = page.getByRole("region", { name: "Raking light", exact: true });
    const buttons = page.locator(".fc-stage__controls");
    const search = page.getByRole("combobox", { name: /Search for a place/ });

    for (const [name, locator] of [
      ["primary action", primary],
      ["status bar", status],
      ["sun dial", raking],
      ["buttons", buttons],
    ] as const) {
      await expect(locator, name).toBeInViewport({ ratio: 1 });
      expect(overlaps(await boxOf(locator), sheetBox), `${name} under the sheet`).toBe(false);
    }
    // Nor do they collide with each other.
    expect(overlaps(await boxOf(raking), await boxOf(buttons)), "sun dial under the buttons").toBe(false);
    expect(overlaps(await boxOf(raking), await boxOf(primary)), "sun dial under the primary action").toBe(false);
    expect(overlaps(await boxOf(raking), await boxOf(search)), "sun dial under the search field").toBe(false);
    expect(overlaps(await boxOf(status), await boxOf(primary)), "status bar under the primary action").toBe(false);

    // Fully open, the sheet covers them, and they are put out of reach.
    const handle = sheet.getByRole("button", { name: /Press to resize/ });
    await handle.focus();
    await page.keyboard.press("ArrowUp");
    await expect(sheet).toHaveAttribute("data-stop", "full");
    await expect(primary).toBeHidden();
    await expect(page.locator(".fc-stage__primary")).toHaveAttribute("inert", "");
    await expect(page.locator(".fc-shell__status")).toHaveAttribute("inert", "");
    await expect(search).toBeVisible();

    // Back at half, the primary action really can be pressed with the sheet open.
    await page.keyboard.press("ArrowDown");
    await expect(sheet).toHaveAttribute("data-stop", "half");
    await primary.click();
    await expect(page.getByRole("complementary", { name: "Mark a finding" })).toBeVisible();
  });

  test("gives the credits button a target at least 24 px high", async ({ page }) => {
    await openMap(page);
    const credits = await boxOf(page.locator(".fc-status__credits-button"));
    expect(credits.height).toBeGreaterThanOrEqual(24);
  });

  test("gives the grid reference's copy button a 44 px target, clear of the credits", async ({ page }) => {
    await openMap(page);
    const copy = page.getByRole("button", { name: "Copy the grid reference of the middle of the map" });
    const box = await boxOf(copy);
    expect(box.width).toBeGreaterThanOrEqual(24);
    expect(box.height).toBeGreaterThanOrEqual(24);
    const middle = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    // A finger landing 20 px above the button, or 20 px to either side of its middle, still lands on it.
    const hits = await page.evaluate(
      ({ x, y }) =>
        [
          [x, y - 20],
          [x - 20, y],
          [x + 20, y],
        ].map(([px = 0, py = 0]) => document.elementFromPoint(px, py)?.closest("button")?.className ?? ""),
      middle,
    );
    expect(hits).toEqual(["fc-status__copy", "fc-status__copy", "fc-status__copy"]);
    const credits = await boxOf(page.locator(".fc-status__credits-button"));
    expect(credits.x).toBeGreaterThan(middle.x + 22);
  });

  test("zooms out with one finger, and shows a compass once the map is turned", async ({ page }) => {
    await openMap(page, "/?panel=none#m=14/51.4286/-1.8542/-46.2/0&v=composite");
    await page.getByRole("button", { name: "Zoom out" }).tap();
    await expect(page).toHaveURL(/#m=13\//);
    const compass = page.getByRole("button", { name: "Reset to north-up" });
    await expect(compass).toBeVisible();
    await compass.tap();
    await expect(page).toHaveURL(/#m=13\/[\d.-]+\/[\d.-]+\/0\/0&/);
    await expect(compass).toHaveCount(0);
  });

  test("gives focus back to More when Escape closes its menu", async ({ page }) => {
    await openMap(page);
    const tabs = page.getByRole("navigation", { name: "Modes" });
    const more = tabs.getByRole("button", { name: "More" });
    await more.focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Tab");
    await expect(tabs.getByRole("link", { name: "Investigations" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(tabs.getByRole("link", { name: "Investigations" })).toHaveCount(0);
    await expect(more).toBeFocused();
  });
});
