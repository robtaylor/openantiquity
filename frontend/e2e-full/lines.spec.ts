import type { CDPSession, Locator, Page } from "@playwright/test";
import { openMap, sendDraftsFromBeforeSignIn } from "../e2e/support/app.js";
import { expect, test } from "./support/fixtures.js";
import { helper, join } from "./support/people.js";

/**
 * Lines and shapes against the real backend (WS-C step 1). On a computer a
 * finder draws a line of straight and curved points with the mouse and
 * Shift-click, saves it, and after a second account's second look carries
 * it on from its far end, and the page says how much was added since. On a
 * phone a signed-out visitor draws a closed shape with taps, a long press
 * on a handle and the bar's buttons, keeps it as a draft, signs in and
 * sends it. A finder who deletes a line down to one point is left with a
 * spot. Each project works at a place of its own, as both share one
 * database.
 */

const HEADERS = { "X-OpenAntiquity-Client": "web" };
const PLACES = { desktop: { lon: -1.62, lat: 51.2 }, phone: { lon: -1.42, lat: 51.2 } } as const;

function place(page: Page): { lon: number; lat: number } {
  return (page.viewportSize()?.width ?? 0) < 720 ? PLACES.phone : PLACES.desktop;
}

function view(at: { lon: number; lat: number }, zoom = 15): string {
  return `#m=${zoom}/${at.lat}/${at.lon}/0/0&v=composite`;
}

interface PathOut {
  closed: boolean;
  curve: string;
  points: Array<{ lon: number; lat: number; kind: string }>;
}

interface FindingOut {
  public_id: string;
  location: {
    lon: number;
    lat: number;
    outline: { type: string } | null;
    path: PathOut | null;
    shape: {
      kind: string | null;
      revision: number | null;
      changes: Array<{ kind: string }>;
      added_since_looked_m: number | null;
    };
  };
}

async function readFinding(page: Page, publicId: string): Promise<FindingOut> {
  const response = await page.request.get(`/api/v1/findings/${publicId}`);
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()) as FindingOut;
}

function publicIdOf(page: Page): string {
  const match = /\/f\/([^/#?]+)/.exec(new URL(page.url()).pathname);
  if (!match?.[1]) throw new Error(`Not on a finding's page: ${page.url()}`);
  return decodeURIComponent(match[1]);
}

/** Hold a finger on `target` for `ms`, as a long press, through the browser's own touch input. */
async function longPress(cdp: CDPSession, target: Locator, ms = 700): Promise<void> {
  const box = await target.boundingBox();
  if (!box) throw new Error(`Nothing on screen for ${target}`);
  const at = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [at] });
  await new Promise((resolve) => setTimeout(resolve, ms));
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

test("a line drawn with the mouse and Shift-click is saved, looked at, carried on, and the page says what was added", async ({
  page,
  browser,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Shift-click and a mouse are the computer's");
  test.setTimeout(120_000);
  const at = place(page);
  const tag = `d${Date.now() % 1_000_000}`;
  await join(page, `Liner${tag}`);

  // Three clicks, the middle one with Shift held: straight, curved, straight.
  await openMap(page, `/mark${view(at)}`);
  const panel = page.getByRole("complementary", { name: "Mark a finding" });
  await page.mouse.click(420, 520);
  await page.keyboard.down("Shift");
  await page.mouse.click(560, 420);
  await page.keyboard.up("Shift");
  await page.mouse.click(700, 470);
  await expect(page.locator(".fc-path-handle")).toHaveCount(3);
  await panel.getByRole("button", { name: "Finish" }).click();
  await panel.getByRole("radio", { name: "Road" }).click();
  await panel.getByRole("button", { name: "Save finding" }).click();
  await expect(page).toHaveURL(/\/f\/[^/#]+/);
  const publicId = publicIdOf(page);

  const saved = await readFinding(page, publicId);
  expect(saved.location.path?.closed).toBe(false);
  expect(saved.location.path?.points.map((point) => point.kind)).toEqual(["corner", "smooth", "corner"]);
  // Made with its shape, it is at revision 0 with no change recorded yet.
  expect(saved.location.shape).toMatchObject({ kind: "line", revision: 0, changes: [] });
  expect(saved.location.outline?.type).toBe("LineString");

  // A second account answers on the shape as it is.
  const ann = await helper(browser, page.viewportSize(), `Ann${tag}`);
  try {
    await openMap(ann.page, `/f/${publicId}${view(at)}`);
    const look = ann.page
      .getByRole("complementary", { name: /^Road in / })
      .getByRole("region", { name: "Your second look" });
    await look.getByRole("button", { name: "I can see it" }).click();
    await expect(look.getByText(/Your answer is in/)).toBeVisible();
  } finally {
    await ann.context.close();
  }

  // The finder reopens it and carries it on from the far end, well past what was looked at.
  await page.reload();
  await page
    .getByRole("complementary", { name: /^Road in / })
    .getByRole("button", { name: "Change the shape" })
    .click();
  const change = page.getByRole("complementary", { name: "Change the shape" });
  await expect(page.locator(".fc-path-handle")).toHaveCount(3);
  await page.getByRole("button", { name: /^Point 3 of 3/ }).click();
  await change.getByRole("button", { name: "Continue from this end" }).click();
  await change.getByRole("button", { name: "Done" }).click();
  // Out by four zoom levels, so a click 260 px away is about a kilometre on.
  for (let step = 0; step < 4; step++) await page.getByRole("button", { name: "Zoom out" }).click();
  await page.waitForTimeout(800);
  const end = await page.getByRole("button", { name: /^Point 3 of 3/ }).boundingBox();
  if (!end) throw new Error("The far end isn't on screen");
  await page.mouse.click(end.x + end.width / 2 - 260, end.y + end.height / 2 + 40);
  await expect(page.locator(".fc-path-handle")).toHaveCount(4);
  await change.getByRole("button", { name: "Finish" }).click();
  await change.getByRole("button", { name: "Save the shape" }).click();
  await expect(page.getByText("The new shape is saved.")).toBeVisible();

  const page2 = page.getByRole("complementary", { name: /^Road in / });
  const added = page2.getByRole("region", { name: "Added since the last second look" });
  await expect(added).toContainText(/^Added since the last second look[\d.,]+ k?m added since the last second look\./);
  await expect(added.getByRole("button", { name: "Show the new part on the map" })).toBeVisible();

  const extended = await readFinding(page, publicId);
  expect(extended.location.path?.points).toHaveLength(4);
  expect(extended.location.path?.points.slice(0, 3)).toEqual(saved.location.path?.points);
  expect(extended.location.shape.revision).toBe(1);
  expect(extended.location.shape.changes.map((entry) => entry.kind)).toEqual(["extended"]);
  expect(extended.location.shape.added_since_looked_m).toBeGreaterThan(200);
  // The anchor stays where the server first put it.
  expect([extended.location.lon, extended.location.lat]).toEqual([saved.location.lon, saved.location.lat]);
});

test("a closed shape drawn on a phone with taps, a long press and the bar is kept as a draft, then sent after sign-in", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "phone", "taps and a long press are the phone's");
  test.setTimeout(120_000);
  const at = place(page);
  const handle = `Shaper${Date.now() % 1_000_000}`;
  await openMap(page, `/mark${view(at)}`);

  // Four taps, then a tap on the first point closes it.
  for (const [x, y] of [
    [90, 180],
    [280, 180],
    [280, 360],
    [90, 360],
  ] as const) {
    await page.touchscreen.tap(x, y);
  }
  await expect(page.locator(".fc-path-handle")).toHaveCount(4);
  await page.getByRole("button", { name: /^Point 1 of 4/ }).tap();
  const panel = page.getByRole("complementary", { name: "Mark a finding" });
  await expect(panel.getByRole("status").filter({ hasText: "A closed shape of 4 points" })).toBeVisible();

  // A long press on the second point makes it curved; the bar's Undo and Redo take it back and put it again.
  const cdp = await page.context().newCDPSession(page);
  const second = page.getByRole("button", { name: /^Point 2 of 4/ });
  await longPress(cdp, second);
  await expect(second).toHaveAttribute("data-kind", "smooth");
  await panel.getByRole("button", { name: "Undo" }).click();
  await expect(second).toHaveAttribute("data-kind", "corner");
  await panel.getByRole("button", { name: "Redo" }).click();
  await expect(second).toHaveAttribute("data-kind", "smooth");

  await panel.getByRole("radio", { name: "Enclosure" }).click();
  await panel.getByRole("button", { name: "Save finding" }).click();

  // Signed out, it is kept as a draft while the sign-in sheet is open.
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await expect(sheet).toBeVisible();
  await sheet.getByLabel("Development sign-in").fill(handle);
  await sheet.getByRole("button", { name: "Sign in", exact: true }).click();
  const welcome = page.getByRole("dialog", { name: "Welcome to OpenAntiquity" });
  await welcome.getByRole("radio", { name: "18 or over" }).click();
  await welcome.getByRole("checkbox", { name: "I accept the contributor terms" }).check();
  await welcome.getByRole("button", { name: "Join OpenAntiquity" }).click();
  await sendDraftsFromBeforeSignIn(page);

  await expect(page).toHaveURL(/\/f\/[^/#]+#/);
  const saved = await readFinding(page, publicIdOf(page));
  expect(saved.location.path?.closed).toBe(true);
  expect(saved.location.path?.points.map((point) => point.kind)).toEqual(["corner", "smooth", "corner", "corner"]);
  expect(saved.location.shape.kind).toBe("area");
  expect(saved.location.outline?.type).toBe("Polygon");
  const mine = await (await page.request.get(`/api/v1/findings?author=${handle}`)).json();
  expect(mine.items).toHaveLength(1);
});

test("a line deleted down to one point is saved as a spot there", async ({ page }, testInfo) => {
  const at = place(page);
  const tag = `${testInfo.project.name.slice(0, 1)}${Date.now() % 1_000_000}`;
  await join(page, `Spotter${tag}`);
  const first = { lon: at.lon + 0.004, lat: at.lat + 0.004 };
  const created = await page.request.post("/api/v1/findings", {
    headers: HEADERS,
    data: {
      path: {
        closed: false,
        points: [
          { ...first, kind: "corner" },
          { lon: first.lon + 0.002, lat: first.lat + 0.001, kind: "corner" },
        ],
      },
      feature_class: "trackway",
      title: `Short way ${tag}`,
      view_state: { layer: "composite", zoom: 15 },
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const { public_id: publicId } = (await created.json()) as { public_id: string };

  await openMap(page, `/mark/finding/${publicId}${view(first, 16)}`);
  const change = page.getByRole("complementary", { name: "Change the shape" });
  await expect(page.locator(".fc-path-handle")).toHaveCount(2);
  await page.getByRole("button", { name: /^Point 2 of 2/ }).click();
  await page.getByRole("button", { name: "Delete point" }).first().click();
  await expect(page.locator(".fc-path-handle")).toHaveCount(1);
  await change.getByRole("button", { name: "Save the shape" }).click();
  await expect(page.getByText("The new shape is saved.")).toBeVisible();

  const spot = await readFinding(page, publicId);
  expect(spot.location.path).toBeNull();
  expect(spot.location.outline).toBeNull();
  expect(spot.location.shape.kind).toBeNull();
  expect(spot.location.shape.changes.map((entry) => entry.kind)).toEqual(["removed"]);
  expect(spot.location.lon).toBeCloseTo(first.lon, 6);
  expect(spot.location.lat).toBeCloseTo(first.lat, 6);
});
