import type { Locator, Page } from "@playwright/test";
import { DRAFTS_STORAGE_KEY } from "../src/features/drafts/store.js";
import { findingCollection } from "../src/test/fixtures/findings.js";
import { fakeSession, meWith } from "./support/account.js";
import { boxOf, openMap, overlaps } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";
import { serveFindings } from "./support/markerTiles.js";
import { apiRoute, FINDING_PAGE_ROUTE } from "./support/network.js";
import { fakeQueue, queuedFinding } from "./support/review.js";

/**
 * Second look, the blind queue, in fixture mode at desktop and phone width:
 * nothing of the finder's claim before the answer, in the page, its title,
 * the address, the network or the map; the answer keys; the reveal and the
 * next card; a signed-out answer kept as a draft through a provider's round
 * trip and saved once; and the empty and failed queue.
 */

const MEMBER = meWith({ handle: "KeenLynchet7", display_name: "Mary Anning" });
const VIEW = "#m=14/51.4286/-1.8542/0/0&v=composite";

const CLAIMED = queuedFinding("f-ring", "Ring ditch by the long barrow");
const NEXT = queuedFinding("f-bank", "Bank along the parish edge", 0.01, "SU 1094 6996");
/** Everything that would give the finder's claim away: its title, class, period, finder and description. */
const CLAIM = [CLAIMED.title, "Round barrow or mound", "round_barrow", "bronze_age", "Ada Lovelace", "faint ring"];

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

function panel(page: Page): Locator {
  return page.getByRole("complementary", { name: "Second look" });
}

/** Every API answer the page gets, but `/meta`, whose vocabulary names every class there is. */
function recordResponses(page: Page): string[] {
  const bodies: string[] = [];
  page.on("response", async (response) => {
    const url = new URL(response.url());
    if (!url.pathname.startsWith("/api/") || url.pathname === "/api/v1/meta") return;
    bodies.push(`${url.href} ${await response.text().catch(() => "")}`);
  });
  return bodies;
}

test("before an answer the page, its title, the address, the network and the map say nothing of the claim", async ({
  page,
}) => {
  await fakeSession(page, MEMBER);
  // The findings in view would carry the claim: the map must not ask for them while the card is up.
  const near = findingCollection([{ at: CLAIMED.location, public_id: CLAIMED.public_id, tier: "spotted" }]);
  for (const feature of near.features)
    Object.assign(feature.properties, { title: CLAIMED.title, feature_class: "round_barrow" });
  const findingsLog = await serveFindings(page, near);
  const queue = await fakeQueue(page, [CLAIMED]);
  const bodies = recordResponses(page);
  await openMap(page, `/review${VIEW}`);
  const look = panel(page);
  await expect(look.getByRole("group", { name: "Can you see it?" })).toBeVisible();
  await expect(look.getByText("SU 1025 6996")).toBeVisible();
  await expect(page.locator(".fc-look-here")).toBeVisible();
  // Let the map settle where the card put it, long enough for the findings overlay to have asked if it were going to.
  await page.waitForTimeout(1200);

  const html = await page.content();
  for (const words of CLAIM) {
    expect(html, `the page holds "${words}"`).not.toContain(words);
    expect(await page.title()).not.toContain(words);
    expect(decodeURIComponent(page.url())).not.toContain(words);
    for (const body of bodies) expect(body, `a response holds "${words}"`).not.toContain(words);
  }
  await expect(page).toHaveTitle("Second look · Field Club");
  await expect(page).toHaveURL(/\/review#/);
  expect(findingsLog.boxes, "the map asked for the findings in view").toEqual([]);
  expect(bodies.some((body) => body.includes("/api/v1/findings/f-ring "))).toBe(false);
  await expect(page.locator(".fc-highlight-ring")).toHaveCount(0);
  // The map is in the finder's view at the place: the address now carries their layer and light.
  await expect(page).toHaveURL(/v=composite/);
  await expect(page).toHaveURL(/#m=16\.5\//);
  expect(queue.asked).toHaveLength(1);
  expect(queue.asked[0]?.searchParams.get("lon")).toBe("-1.854");

  // Answering reveals it.
  await look.getByRole("button", { name: "I can see it", exact: true }).click();
  await look.getByRole("button", { name: "Send “I can see it”" }).click();
  await expect(look.getByRole("heading", { name: CLAIMED.title })).toBeVisible();
  await expect(look.getByText(/Your answer helped\. It has moved up to Seen by others\./)).toBeVisible();
});

test("the keys 1, 2 and 3 answer, and do nothing while a text field has focus", async ({ page }) => {
  await fakeSession(page, MEMBER);
  await fakeQueue(page, [CLAIMED]);
  await openMap(page, `/review${VIEW}`);
  const look = panel(page);
  await expect(look.getByRole("group", { name: "Can you see it?" })).toBeVisible();
  await page.keyboard.press("2");
  await expect(look.getByRole("button", { name: "Not sure", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("1");
  await expect(look.getByRole("button", { name: "I can see it", exact: true })).toHaveAttribute("aria-pressed", "true");
  const note = look.getByLabel("Note (optional)");
  await note.click();
  await page.keyboard.type("3 banks");
  await expect(note).toHaveValue("3 banks");
  await expect(look.getByRole("button", { name: "I can see it", exact: true })).toHaveAttribute("aria-pressed", "true");
  // The search box is a text field too.
  await page.getByRole("searchbox", { name: /Search for a place/ }).click();
  await page.keyboard.press("3");
  await expect(look.getByRole("button", { name: "I can't see it", exact: true })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});

test("answers, sees how it compares and that it moved up, and goes on with one press", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const queue = await fakeQueue(page, [CLAIMED, NEXT]);
  await openMap(page, `/review${VIEW}`);
  const look = panel(page);

  // The place stays in sight beside the panel, or above the sheet.
  await expect(page.locator(".fc-look-here")).toBeVisible();
  if (isPhone(page)) await expect(page.locator(".fc-shell")).toHaveAttribute("data-sheet", "half");
  await expect(async () => {
    const frame = await boxOf(page.locator(".fc-look-here"));
    const sheet = await boxOf(look);
    if (isPhone(page)) expect(frame.y + frame.height).toBeLessThanOrEqual(sheet.y);
    else expect(frame.x + frame.width).toBeLessThanOrEqual(sheet.x);
    expect(frame.y).toBeGreaterThan(0);
  }).toPass();
  await expect(look.getByRole("button", { name: "I can see it", exact: true })).toBeInViewport();
  // Going from card to card adds nothing to the browser's history.
  const history = await page.evaluate(() => window.history.length);

  await look.getByRole("button", { name: "I can see it", exact: true }).click();
  await look.getByRole("radio", { name: "Round barrow or mound" }).click();
  await expect(look.getByRole("button", { name: "Send “I can see it”" })).toBeInViewport();
  await look.getByRole("button", { name: "Send “I can see it”" }).click();

  await expect(look.getByRole("heading", { name: CLAIMED.title })).toBeVisible();
  await expect(look.getByText(/2 other people can see it and 1 isn't sure\./)).toBeVisible();
  await expect(look.getByText(/So did you\./)).toBeVisible();
  expect(queue.answers["f-ring"]).toEqual([{ visible: "yes", feature_class: "round_barrow" }]);
  await expect(look.getByRole("button", { name: "Next finding" })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect(look.getByRole("heading", { name: CLAIMED.title })).toHaveCount(0);
  await expect(look.getByRole("button", { name: "I can see it", exact: true })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  await expect(look.getByText("SU 1094 6996")).toBeVisible();
  expect(await page.evaluate(() => window.history.length)).toBe(history);
  await expect(page).toHaveURL(/\/review#/);
  await look.getByRole("button", { name: "Skip this one" }).click();
  await expect(look.getByRole("heading", { name: "Nothing waiting just now" })).toBeVisible();
  await expect(look.getByRole("button", { name: "Look at the one you skipped" })).toBeVisible();
  expect(queue.answers["f-bank"]).toBeUndefined();
});

test("opened from Explore, the frame is in the middle of the map left uncovered, clear of the primary button", async ({
  page,
}) => {
  await fakeSession(page, MEMBER);
  await fakeQueue(page, [CLAIMED]);
  // Explore rests the phone sheet at peek, and the queue at half: the card waits for the sheet to get there.
  await openMap(page, `/${VIEW}`);
  await page.getByRole("navigation", { name: "Modes" }).getByRole("link", { name: "Second look" }).click();
  await expect(page.locator(".fc-look-here")).toBeVisible();
  await expect(async () => {
    const frame = await boxOf(page.locator(".fc-look-here"));
    const stage = await boxOf(page.locator(".fc-stage"));
    const button = await boxOf(page.getByRole("button", { name: "Mark a finding" }));
    expect(overlaps(frame, button), "the primary button covers the frame").toBe(false);
    expect(Math.abs(frame.y + frame.height / 2 - (stage.y + stage.height / 2))).toBeLessThan(4);
    expect(Math.abs(frame.x + frame.width / 2 - (stage.x + stage.width / 2))).toBeLessThan(4);
  }).toPass();
});

test("a signed-out answer is a draft through a provider's round trip, saved once, then revealed", async ({ page }) => {
  const session = await fakeSession(page);
  const queue = await fakeQueue(page, [CLAIMED]);
  await openMap(page, `/review${VIEW}`);
  const look = panel(page);
  await look.getByRole("button", { name: "Not sure", exact: true }).click();
  await look.getByRole("button", { name: "Send “Not sure”" }).click();
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await expect(sheet).toBeVisible();
  await sheet.getByRole("button", { name: "Close" }).click();

  // Kept, changeable, and nothing revealed.
  await expect(look.locator(".fc-draft-badge")).toHaveText("Not saved yet");
  await expect(look.getByText(/Until then you can change it\. Once it's saved it's final/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Drafts" }).getByRole("status")).toHaveText("1 draft not saved yet");
  for (const words of CLAIM) expect(await page.content()).not.toContain(words);
  await look.getByRole("button", { name: "Change my answer" }).click();
  await look.getByRole("button", { name: "I can see it", exact: true }).click();
  await look.getByRole("button", { name: "Send “I can see it”" }).click();
  await sheet.getByRole("button", { name: "Close" }).click();
  await expect(look.getByText("You can see it.")).toBeVisible();
  expect(queue.answers).toEqual({});

  // Away to the provider and back, signed in: the draft is saved once and the card shows what it revealed.
  let next = "";
  await page.route(apiRoute("/auth/oauth/google/start"), (route) => {
    next = new URL(route.request().url()).searchParams.get("next") ?? "/";
    session.set(MEMBER);
    return route.fulfill({ status: 302, headers: { Location: next } });
  });
  await look.getByRole("button", { name: "Sign in to save it" }).click();
  await sheet.getByRole("link", { name: "Continue with Google" }).click();
  await expect(look.getByRole("heading", { name: CLAIMED.title })).toBeVisible();
  expect(next.startsWith("/review")).toBe(true);
  await page.waitForTimeout(500);
  expect(queue.answers["f-ring"]).toEqual([{ visible: "yes" }]);
  const left = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? "{}"), DRAFTS_STORAGE_KEY);
  expect(left.drafts).toEqual([]);
});

test.describe("failures", () => {
  // The browser reports the refused request as a console error, which is the point here.
  test.use({ pageProblems: "page-errors" });

  test("a draft answer that failed to save, changed and sent from the card, is not offered again", async ({ page }) => {
    const session = await fakeSession(page);
    const queue = await fakeQueue(page, [CLAIMED]);
    let failNext = true;
    await page.route(FINDING_PAGE_ROUTE, (route) => {
      if (route.request().method() !== "PUT" || !failNext) return route.fallback();
      failNext = false;
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: '{"error":{"code":"internal","message":"Broke."}}',
      });
    });
    await openMap(page, `/review${VIEW}`);
    const look = panel(page);
    await look.getByRole("button", { name: "Not sure", exact: true }).click();
    await look.getByRole("button", { name: "Send “Not sure”" }).click();
    await page.route(apiRoute("/auth/oauth/google/start"), (route) => {
      const next = new URL(route.request().url()).searchParams.get("next") ?? "/";
      session.set(MEMBER);
      return route.fulfill({ status: 302, headers: { Location: next } });
    });
    await page.getByRole("dialog", { name: "Sign in" }).getByRole("link", { name: "Continue with Google" }).click();
    await expect(look.getByText(/It couldn't be saved/)).toBeVisible();

    await look.getByRole("button", { name: "Change my answer" }).click();
    await look.getByRole("button", { name: "I can see it", exact: true }).click();
    await look.getByRole("button", { name: "Send “I can see it”" }).click();
    await expect(look.getByRole("heading", { name: CLAIMED.title })).toBeVisible();
    expect(queue.answers["f-ring"]).toEqual([{ visible: "yes" }]);
    await expect(page.getByRole("region", { name: "Drafts" })).toHaveCount(0);
    const left = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? "{}"), DRAFTS_STORAGE_KEY);
    expect(left.drafts).toEqual([]);
  });

  test("an empty queue says so and offers other work, and a failed one offers a retry", async ({ page }) => {
    let fail = true;
    await page.route(apiRoute("/review/next"), (route) =>
      fail
        ? route.fulfill({
            status: 400,
            contentType: "application/json",
            body: '{"error":{"code":"x","message":"Not now."}}',
          })
        : route.fulfill({ status: 200, contentType: "application/json", body: '{"items":[],"next_cursor":null}' }),
    );
    await openMap(page, `/review${VIEW}`);
    const look = panel(page);
    await expect(look.getByRole("heading", { name: "The next finding couldn't be fetched" })).toBeVisible();
    fail = false;
    await look.getByRole("button", { name: "Try again" }).click();
    await expect(look.getByRole("heading", { name: "Nothing waiting just now" })).toBeVisible();
    await look.getByRole("link", { name: "Help wanted" }).click();
    await expect(page.getByRole("complementary", { name: "Help wanted" })).toBeVisible();
  });
});
