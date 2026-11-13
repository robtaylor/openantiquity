import type { Page } from "@playwright/test";
import type { ActivityItem } from "../src/features/activity/api.js";
import type { Notification } from "../src/features/notifications/api.js";
import { pageFixture, seenFixture } from "../src/test/fixtures/findingPage.js";
import { answerJson, fakeSession, meWith } from "./support/account.js";
import { openMap } from "./support/app.js";
import { testStream } from "./support/events.js";
import { fakeFindingPage } from "./support/findingPage.js";
import { expect, test } from "./support/fixtures.js";
import { apiRoute } from "./support/network.js";

/**
 * Activity, notifications and what changes live, in fixture mode at desktop
 * and phone width. The tests stand in for the event stream themselves
 * (`support/events.ts`).
 */

const RING = pageFixture();
const MARY = { handle: "KeenLynchet7", display_name: "Mary Anning", role: "member" };
const ME = meWith();
const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

const ringRef = {
  public_id: RING.public_id,
  title: RING.title,
  feature_class: RING.feature_class,
  tier: "seen" as const,
  state: "open" as const,
  location: RING.location,
};

const FEED: ActivityItem[] = [
  {
    id: 3,
    kind: "tier_changed",
    created_at: minutesAgo(4),
    actor: null,
    finding: ringRef,
    investigation: null,
    details: { tier_from: "spotted", tier_to: "seen" },
  },
  {
    id: 2,
    kind: "observation_added",
    created_at: minutesAgo(4),
    actor: null,
    finding: ringRef,
    investigation: null,
    details: {},
  },
  {
    id: 1,
    kind: "finding_created",
    created_at: minutesAgo(90),
    actor: MARY,
    finding: {
      public_id: "f-barrow",
      title: "Round barrow in SU 10 69",
      feature_class: "round_barrow",
      tier: "spotted",
      state: "open",
      location: { lon: -1.855, lat: 51.425, obscured: true, grid_ref: null, square: "SU1069", outline: null },
    },
    investigation: null,
    details: {},
  },
];

/** Go to a mode by its rail link on a desktop, or through the tab bar's "More" on a phone. */
async function goTo(page: Page, name: string): Promise<void> {
  const modes = page.getByRole("navigation", { name: "Modes" });
  if ((page.viewportSize()?.width ?? 1440) < 720) {
    await modes.getByRole("button", { name: /^More/ }).click();
  }
  await modes.getByRole("link", { name: new RegExp(`^${name}`) }).click();
}

test("the feed says what happened in plain sentences and opens each finding", async ({ page }) => {
  await answerJson(page, "/activity", { items: FEED, next_cursor: null });
  await openMap(page);
  await goTo(page, "Activity");
  const panel = page.getByRole("complementary", { name: "Activity" });
  const list = panel.getByRole("list", { name: "What has happened" });
  await expect(list.getByRole("listitem")).toHaveText([
    /^Ring ditch by the long barrow moved up to Seen by others\.4 minutes ago$/,
    /^Ring ditch by the long barrow had a second look\.4 minutes ago$/,
    /^Mary Anning marked Round barrow in SU 10 69\.1 hour ago\s*Somewhere in square SU 10 69$/,
  ]);
  await expect(page).toHaveTitle("Activity · OpenAntiquity");

  // Narrowing to a kind asks the server for that kind.
  const asked = page.waitForRequest((request) => new URL(request.url()).searchParams.get("kind") === "finding_created");
  await panel.getByRole("button", { name: "Filters" }).click();
  await panel.getByRole("button", { name: "Findings marked or drawn further" }).click();
  await asked;
  await panel.getByRole("button", { name: "Clear filters" }).click();

  await list.getByRole("link", { name: /moved up to Seen by others/ }).click();
  await expect(page).toHaveURL(/\/f\/f-ring/);
  await expect(page.getByRole("complementary", { name: /^Finding f-ring/ })).toBeVisible();
});

test("notifications show as a quiet count, list what happened, and are marked read as they are seen", async ({
  page,
}) => {
  await fakeSession(page, ME);
  const inbox: Notification[] = [
    {
      id: 7,
      kind: "tier_changed",
      created_at: minutesAgo(3),
      read: false,
      actor: null,
      finding: ringRef,
      investigation: null,
      details: { tier_from: "spotted", tier_to: "seen" },
    },
    {
      id: 6,
      kind: "comment_added",
      created_at: minutesAgo(30),
      read: true,
      actor: MARY,
      finding: ringRef,
      investigation: null,
      details: {},
    },
  ];
  let unread = 1;
  const marked: unknown[] = [];
  await page.route(apiRoute("/notifications"), (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: inbox.map((item) => ({ ...item, read: item.read || unread === 0 })),
        next_cursor: null,
        unread_count: unread,
      }),
    }),
  );
  await page.route(apiRoute("/notifications/read"), (route) => {
    marked.push(route.request().postDataJSON());
    unread = 0;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ marked: 1, unread_count: 0 }) });
  });

  await openMap(page);
  const modes = page.getByRole("navigation", { name: "Modes" });
  const phone = (page.viewportSize()?.width ?? 1440) < 720;
  const counted = phone
    ? modes.getByRole("button", { name: "More, 1 new notification" })
    : modes.getByRole("link", { name: "Account, 1 new notification" });
  await expect(counted.getByTestId("notification-count")).toHaveText("1");

  await goTo(page, "Account");
  const list = page.getByRole("list", { name: "Your notifications" });
  await list.scrollIntoViewIfNeeded();
  await expect(list.getByRole("listitem").first()).toHaveText(
    /^Ring ditch by the long barrow moved up to Seen by others\.New\s*3 minutes ago$/,
  );
  await expect.poll(() => marked).toEqual([{ ids: [7], all: false }]);
  await expect(page.getByTestId("notification-count")).toHaveCount(0);
  // Still marked new while the page is open.
  await expect(list.getByRole("listitem").first()).toContainText("New");
});

test("a finding's page moves up a step as it happens, without a reload", async ({ page }) => {
  const stream = await testStream(page);
  const finding = await fakeFindingPage(page, pageFixture());
  await openMap(page, `/f/${RING.public_id}`);
  const panel = page.getByRole("complementary", { name: RING.title });
  const badge = panel.locator(".fc-finding__badges");
  await expect(badge).toContainText("Spotted");
  await stream.open();

  finding.set(seenFixture());
  await stream.activity({ id: 40, kind: "observation_added", finding: RING.public_id });
  await stream.activity({ id: 41, kind: "tier_changed", finding: RING.public_id });
  await expect(badge).toContainText("Seen by others");
  await expect(panel.getByRole("meter", { name: "Confidence" })).toHaveAttribute("aria-valuenow", "36");
  await expect(panel.getByRole("status").filter({ hasText: "It has moved up to Seen by others" })).toBeVisible();
  // The meter slides to its new place.
  const slide = await panel.locator(".fc-meter__fill").evaluate((fill) => getComputedStyle(fill).transitionDuration);
  expect(slide).not.toMatch(/^0\.001ms|^0s$/);
  // One stream for the whole app. (React's development checks open and close one first.)
  expect((await stream.counts()).open).toBe(1);
});

test("with reduced motion, a live change of step swaps without moving", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const stream = await testStream(page);
  const finding = await fakeFindingPage(page, pageFixture());
  await openMap(page, `/f/${RING.public_id}`);
  const panel = page.getByRole("complementary", { name: RING.title });
  await stream.open();
  finding.set(seenFixture());
  await stream.activity({ id: 41, kind: "tier_changed", finding: RING.public_id });
  await expect(panel.locator(".fc-finding__badges")).toContainText("Seen by others");
  const fill = panel.locator(".fc-meter__fill");
  expect(await fill.evaluate((element) => getComputedStyle(element).transitionDuration)).toMatch(/^0\.001ms|^1e-06s/);
  expect(
    await panel.locator(".fc-finding__badge").evaluate((element) => getComputedStyle(element).animationDuration),
  ).toMatch(/^0\.001ms|^1e-06s/);
});

test("after the stream is refused, the app asks the feed now and then, and refetches what it missed", async ({
  page,
}) => {
  const stream = await testStream(page);
  const finding = await fakeFindingPage(page, pageFixture());
  let latest = 50;
  await page.route(apiRoute("/activity"), (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [{ ...FEED[0], id: latest }], next_cursor: null }),
    }),
  );
  await openMap(page, `/f/${RING.public_id}`);
  const panel = page.getByRole("complementary", { name: RING.title });
  await expect(panel.locator(".fc-finding__badges")).toContainText("Spotted");
  await expect.poll(async () => (await stream.counts()).open).toBe(1);
  const { opened } = await stream.counts();
  const checked = page.waitForRequest((request) => new URL(request.url()).searchParams.get("limit") === "1");
  await stream.refuse();
  await checked;

  // The next try, some seconds later, opens; what changed meanwhile is fetched again.
  finding.set(seenFixture());
  latest = 51;
  await expect.poll(() => stream.counts(), { timeout: 15_000 }).toEqual({ opened: opened + 1, open: 1 });
  await stream.open();
  await expect(panel.locator(".fc-finding__badges")).toContainText("Seen by others");
});
