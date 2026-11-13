import type { Locator, Page } from "@playwright/test";
import { DRAFTS_STORAGE_KEY } from "../src/features/drafts/store.js";
import { fakeSession, meWith } from "./support/account.js";
import { boxOf, openMap, overlaps, sendDraftsFromBeforeSignIn } from "./support/app.js";
import { fakeFindings } from "./support/findings.js";
import { expect, test } from "./support/fixtures.js";
import { apiRoute } from "./support/network.js";

/**
 * Marking a finding and the Explore panel, in fixture mode, at desktop and
 * phone width. The findings endpoints are answered by `fakeFindings`, which
 * serves the map and the list from one set and adds what is saved to it.
 */

const VIEW = "#m=15/51.4286/-1.8542/0/0&v=composite";

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

function markPanel(page: Page): Locator {
  return page.getByRole("complementary", { name: "Mark a finding" });
}

/** The handle of the marking's first point. */
function handle(page: Page): Locator {
  return page.getByRole("button", { name: /^Point 1 of / });
}

/**
 * Stop adding points, so the form comes up: on a phone the sheet rests at
 * peek while the map takes taps, and rises half-way once drawing stops.
 */
async function finish(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Finish" }).click();
}

/** Where on the screen the middle of the mark is. */
async function markCentre(page: Page): Promise<{ x: number; y: number }> {
  const box = await boxOf(handle(page));
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** A tap on a phone, a click on a desktop. */
async function tapMap(page: Page, x: number, y: number): Promise<void> {
  if (isPhone(page)) await page.touchscreen.tap(x, y);
  else await page.mouse.click(x, y);
}

/** Drag with a finger on a phone and the mouse on a desktop, in small steps as a hand would. */
async function drag(page: Page, from: { x: number; y: number }, to: { x: number; y: number }): Promise<void> {
  const steps = 8;
  if (!isPhone(page)) {
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    await page.mouse.move(to.x, to.y, { steps });
    await page.mouse.up();
    return;
  }
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [from] });
  for (let i = 1; i <= steps; i++) {
    const point = { x: from.x + ((to.x - from.x) * i) / steps, y: from.y + ((to.y - from.y) * i) / steps };
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [point] });
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await cdp.detach();
}

/** The part of the map nobody's panel or sheet covers. */
async function openMapArea(page: Page): Promise<{ x: number; y: number }> {
  const stage = await boxOf(page.locator(".fc-stage"));
  return { x: stage.x + stage.width / 2, y: stage.y + stage.height / 2 };
}

async function gridRef(page: Page): Promise<string> {
  return (await markPanel(page).locator(".fc-mark__gridref").textContent()) ?? "";
}

test("marks a finding by pointer and keyboard, saves it at once, and opens its page", async ({ page }) => {
  await fakeSession(page, meWith());
  const findings = await fakeFindings(page);
  await openMap(page, `/${VIEW}`);
  await page.getByRole("button", { name: "Mark a finding" }).click();
  await expect(markPanel(page)).toBeVisible();
  await expect(page.locator(".maplibregl-canvas.fc-canvas--placing")).toHaveCount(1);

  // A tap or click places the first point where it lands, and that alone is a finding at a spot.
  const spot = await openMapArea(page);
  await tapMap(page, spot.x - 60, spot.y - 30);
  await expect(handle(page)).toBeVisible();
  const placed = await markCentre(page);
  expect(Math.abs(placed.x - (spot.x - 60))).toBeLessThan(3);
  expect(Math.abs(placed.y - (spot.y - 30))).toBeLessThan(3);

  // Dragged, by finger or mouse, without moving the map.
  const before = await gridRef(page);
  const canvasBefore = new URL(page.url()).hash;
  await drag(page, placed, { x: placed.x + 40, y: placed.y + 25 });
  const dragged = await markCentre(page);
  expect(Math.abs(dragged.x - (placed.x + 40))).toBeLessThan(3);
  expect(Math.abs(dragged.y - (placed.y + 25))).toBeLessThan(3);
  await expect.poll(() => gridRef(page)).not.toBe(before);
  expect(new URL(page.url()).hash.split("&")[0]).toBe(canvasBefore.split("&")[0]);

  // Nudged with the keyboard.
  await handle(page).focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  const nudged = await markCentre(page);
  expect(nudged.x).toBeLessThan(dragged.x - 4);
  expect(Math.abs(nudged.y - dragged.y)).toBeLessThan(1);
  // The point is selected now. On a phone its bar has taken the drawing bar's place above the sheet.
  if (isPhone(page)) await page.getByRole("button", { name: "Done" }).click();

  // Only the class is needed. The save shows the mark at once, before the server answers.
  await finish(page);
  const release = findings.holdCreates();
  await markPanel(page).getByRole("radio", { name: "Linear bank or ditch" }).click();
  await markPanel(page).getByRole("button", { name: "Save finding" }).click();
  await expect(page.getByRole("img", { name: /^Linear bank or ditch in SU \d{2} \d{2}, saving$/ })).toBeVisible();
  await expect(page.getByRole("list", { name: "Your marks" })).toHaveCount(0);
  release();

  await expect(page).toHaveURL(/\/f\/new-1#/);
  expect(findings.created).toHaveLength(1);
  const [body] = findings.created;
  // One point is sent as a location, with no path.
  expect(body?.location?.type).toBe("Point");
  expect(body?.path ?? null).toBeNull();
  expect(body).toMatchObject({
    feature_class: "linear",
    period: "unknown",
    title: expect.stringMatching(/^Linear bank or ditch in SU \d{2} \d{2}/),
    view_state: { layer: "composite", zoom: 15, bearing: 0, pitch: 0, sun_azimuth: 315, sun_altitude: 20 },
  });
  await expect(page.getByRole("img", { name: /saving$/ })).toHaveCount(0);

  // Back in Explore, the list has it, as the map does.
  await page.getByRole("navigation", { name: "Modes" }).getByRole("link", { name: "Explore" }).click();
  if (isPhone(page)) await page.getByRole("button", { name: /Press to resize/ }).click();
  const list = page.getByRole("list", { name: "Findings in view" });
  await expect(list.getByRole("link", { name: /^Linear bank or ditch in SU \d{2} \d{2}/ })).toBeVisible();
  const lastBox = findings.boxes.at(-1);
  expect(lastBox, "the map asked again after the save").toBeDefined();
});

test("keeps the mark in sight above the form on a phone", async ({ page }) => {
  test.skip(!isPhone(page), "phone layout only");
  await fakeFindings(page);
  await openMap(page, `/mark${VIEW}`);
  const sheet = markPanel(page);
  await expect(sheet).toHaveAttribute("data-stop", "peek");
  // A mark placed low on the screen, just above the drawing bar, where the sheet will come up.
  const bar = await boxOf(page.locator(".fc-mark-float"));
  await page.touchscreen.tap(195, bar.y - 30);
  // The sheet stays at peek while the map takes taps, and rises once drawing stops.
  await expect(handle(page)).toBeVisible();
  await expect(sheet).toHaveAttribute("data-stop", "peek");
  await finish(page);
  await expect(sheet).toHaveAttribute("data-stop", "half");
  await page.waitForTimeout(400);
  const mark = await boxOf(handle(page));
  const sheetBox = await boxOf(sheet);
  expect(overlaps(mark, sheetBox), "the mark is under the sheet").toBe(false);
  await expect(handle(page)).toBeInViewport({ ratio: 1 });
  await expect(sheet.getByRole("radio", { name: "Enclosure" })).toBeVisible();
});

test.describe("a refused save", () => {
  // The browser logs the refused request as an error, which here is the point.
  test.use({ pageProblems: "page-errors" });

  test("takes the mark back when the save fails, says why, and keeps what was typed", async ({ page }) => {
    await fakeSession(page, meWith());
    const findings = await fakeFindings(page);
    findings.failNextCreate(503, "unavailable", "The server is restarting.");
    await openMap(page, `/mark${VIEW}`);
    await page.getByRole("button", { name: "Add a point at the cross" }).click();
    await finish(page);
    await markPanel(page).getByRole("radio", { name: "Moat" }).click();
    await markPanel(page).getByLabel("Title").fill("Moated site by the church");
    await markPanel(page).getByRole("button", { name: "Save finding" }).click();

    const toast = page.locator(".fc-toast").filter({ hasText: "Your finding couldn't be saved." });
    await expect(toast).toContainText("The server is restarting.");
    await expect(page.getByRole("img", { name: /saving$/ })).toHaveCount(0);
    await expect(page).toHaveURL(/\/mark#/);
    await expect(markPanel(page).getByLabel("Title")).toHaveValue("Moated site by the church");
    await expect(markPanel(page).getByRole("radio", { name: "Moat" })).toHaveAttribute("aria-checked", "true");

    await toast.getByRole("button", { name: "Try again" }).click();
    await expect(page).toHaveURL(/\/f\/new-1#/);
    expect(findings.created.map((body) => body.title)).toEqual([
      "Moated site by the church",
      "Moated site by the church",
    ]);
  });
});

test("keeps a signed-out mark as a draft through a reload and a sign-in, then saves it once", async ({ page }) => {
  const session = await fakeSession(page);
  const findings = await fakeFindings(page);
  await openMap(page, `/mark${VIEW}`);
  const spot = await openMapArea(page);
  await tapMap(page, spot.x + 30, spot.y - 20);
  await finish(page);
  await markPanel(page).getByRole("radio", { name: "Hillfort" }).click();
  await markPanel(page).getByRole("button", { name: "Save finding" }).click();

  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await expect(sheet).toBeVisible();
  await expect(page).toHaveURL(/\/mark\/[^/#]+#/);
  await sheet.getByRole("button", { name: "Close" }).click();
  await expect(markPanel(page).locator(".fc-draft-badge")).toHaveText("Not saved yet");
  const where = await gridRef(page);
  const draftUrl = new URL(page.url());

  // It survives a reload, drawn as a draft and not as a real mark.
  await page.reload();
  await expect(markPanel(page).locator(".fc-draft-badge")).toBeVisible();
  await expect.poll(() => gridRef(page)).toBe(where);
  await page.getByRole("navigation", { name: "Modes" }).getByRole("link", { name: "Explore" }).click();
  await expect(page.getByRole("button", { name: /: a draft, not saved yet$/ })).toBeVisible();
  if (isPhone(page)) await page.getByRole("button", { name: /Press to resize/ }).click();
  await expect(page.getByRole("list", { name: "Your marks" }).locator(".fc-draft-badge")).toBeVisible();
  await page.getByRole("button", { name: /: a draft, not saved yet$/ }).click();
  await expect(page).toHaveURL(new RegExp(`${draftUrl.pathname}#`));
  expect(findings.created).toEqual([]);

  // A provider's round trip: away to the provider and back to `next`, signed in.
  let next = "";
  await page.route(apiRoute("/auth/oauth/google/start"), (route) => {
    next = new URL(route.request().url()).searchParams.get("next") ?? "/";
    session.set(meWith());
    return route.fulfill({ status: 302, headers: { Location: next } });
  });
  await markPanel(page).getByRole("button", { name: "Save finding" }).click();
  await page.getByRole("dialog", { name: "Sign in" }).getByRole("link", { name: "Continue with Google" }).click();

  // Back at the draft, it is saved, once the person says to send it, without anything typed again, and its
  // page opens.
  await sendDraftsFromBeforeSignIn(page);
  await expect(page).toHaveURL(/\/f\/new-1#/);
  expect(next.startsWith(draftUrl.pathname)).toBe(true);
  await expect(page.getByText("Your draft is saved.")).toBeVisible();
  await page.waitForTimeout(500);
  expect(findings.created).toHaveLength(1);
  expect(findings.created[0]).toMatchObject({
    feature_class: "hillfort",
    title: expect.stringMatching(/^Hillfort in SU \d{2} \d{2}$/),
  });
  const left = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? "{}"), DRAFTS_STORAGE_KEY);
  expect(left.drafts).toEqual([]);
});

test("keeps the list and the map in step as the map moves and the filters change", async ({ page }) => {
  const findings = await fakeFindings(page);
  await openMap(page, `/${VIEW}`);
  const panel = page.getByRole("complementary", { name: "Explore" });
  if (isPhone(page)) await panel.getByRole("button", { name: /Press to resize/ }).click();
  const list = panel.getByRole("list", { name: "Findings in view" });

  /** The list and the last map request ask for the same box, and list what the map draws. */
  async function agree(): Promise<void> {
    await expect
      .poll(() => {
        const box = findings.boxes.at(-1)?.searchParams.get("bbox");
        const listed = findings.lists.at(-1)?.searchParams.get("bbox");
        return box !== undefined && box === listed;
      })
      .toBe(true);
    const box = findings.boxes.at(-1);
    if (!box) throw new Error("The map asked for nothing");
    const response = await page.evaluate(async (url) => (await fetch(url)).json(), box.href);
    const drawn = (response as { features: Array<{ properties: { state: string } }> }).features.filter(
      (feature) => feature.properties.state !== "ruled_out",
    );
    if (drawn.length === 0) await expect(list).toHaveCount(0);
    else await expect(list.getByRole("listitem")).toHaveCount(drawn.length);
  }

  await expect(list.getByRole("listitem").first()).toBeVisible();
  await agree();

  // Pan well to the east: the findings in view change.
  const lists = findings.lists.length;
  const area = await openMapArea(page);
  await drag(page, { x: area.x + 60, y: area.y - 60 }, { x: area.x - 120, y: area.y - 60 });
  await expect.poll(() => findings.lists.length).toBeGreaterThan(lists);
  await agree();

  // Filter by step.
  await panel.getByRole("button", { name: "Filters", exact: true }).click();
  await panel.getByRole("group", { name: "Step" }).getByRole("button", { name: "Seen by others" }).click();
  await expect.poll(() => findings.lists.at(-1)?.searchParams.getAll("tier")).toEqual(["seen"]);
  await expect.poll(() => findings.boxes.at(-1)?.searchParams.getAll("tier")).toEqual(["seen"]);
  await agree();

  // Choosing one opens its page and marks it on the map.
  await panel.getByRole("button", { name: "Filters (1)" }).click();
  const first = list.getByRole("link").first();
  const href = await first.getAttribute("href");
  await first.click();
  await expect(page).toHaveURL(new RegExp(`${href}#`));
  await expect(page.locator(".fc-highlight-ring, .fc-highlight-square")).toHaveCount(1);
});
