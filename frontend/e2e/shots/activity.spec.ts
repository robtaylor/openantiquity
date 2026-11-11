import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page, test } from "@playwright/test";
import type { ActivityItem } from "../../src/features/activity/api.js";
import type { Notification } from "../../src/features/notifications/api.js";
import { pageFixture } from "../../src/test/fixtures/findingPage.js";
import { answerJson, fakeSession, meWith } from "../support/account.js";
import { openMap } from "../support/app.js";
import { apiRoute, stubNetwork } from "../support/network.js";

/**
 * Screenshots of the activity feed and notifications, taken with `pnpm
 * shots`, for looking at the design at desktop and phone width: the feed,
 * its filters, its empty, loading and failed states, the phone sheet's
 * stops, and the unread count and the list on the account page.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

async function shoot(page: Page, name: string): Promise<void> {
  await page.waitForTimeout(400);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `activity-${name}-${size?.width}x${size?.height}.png`) });
}

const isPhone = (page: Page) => (page.viewportSize()?.width ?? 1440) < 720;
const ago = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();
const RING = pageFixture();
const ring = {
  public_id: RING.public_id,
  title: RING.title,
  feature_class: RING.feature_class,
  tier: "seen" as const,
  state: "open" as const,
  location: RING.location,
};
const barrow = {
  public_id: "f-barrow",
  title: "Round barrow in SU 10 69",
  feature_class: "round_barrow" as const,
  tier: "spotted" as const,
  state: "open" as const,
  location: { lon: -1.855, lat: 51.425, obscured: true, grid_ref: null, square: "SU1069", outline: null },
};
const MARY = { handle: "KeenLynchet7", display_name: "Mary Anning", avatar_url: null, role: "member" };

const FEED: ActivityItem[] = [
  { id: 9, kind: "tier_changed", details: { tier_from: "spotted", tier_to: "seen" }, actor: null, finding: ring },
  { id: 8, kind: "observation_added", details: {}, actor: null, finding: ring },
  { id: 7, kind: "evidence_added", details: { evidence_kind: "historic_map" }, actor: MARY, finding: ring },
  { id: 6, kind: "finding_created", details: {}, actor: MARY, finding: barrow },
  { id: 5, kind: "comment_added", details: {}, actor: MARY, finding: barrow },
  {
    id: 4,
    kind: "state_changed",
    details: { state_from: "open", state_to: "ruled_out", state_reason: "modern" },
    actor: null,
    finding: { ...ring, public_id: "f-drain", title: "Straight bank by the lane" },
  },
  { id: 3, kind: "mention_added", details: {}, actor: null, finding: ring },
].map((item, index) => ({ created_at: ago(3 + index * 40), investigation: null, ...item }) as ActivityItem);

const INBOX: Notification[] = [
  { ...(FEED[0] as ActivityItem), read: false, investigation: null },
  { ...(FEED[2] as ActivityItem), read: false, investigation: null },
  { ...(FEED[4] as ActivityItem), read: true, investigation: null },
  {
    id: 2,
    kind: "investigation_invitation",
    created_at: ago(3000),
    read: true,
    actor: MARY,
    finding: null,
    investigation: "i-ridge",
    details: {},
  },
];

async function openActivity(page: Page): Promise<void> {
  await openMap(page, "/activity");
  await page.getByRole("complementary", { name: "Activity" }).waitFor();
}

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
});

test("feed", async ({ page }) => {
  await answerJson(page, "/activity", { items: FEED, next_cursor: "more" });
  await openActivity(page);
  await page.getByRole("list", { name: "What has happened" }).waitFor();
  await shoot(page, "feed");
  const panel = page.getByRole("complementary", { name: "Activity" });
  await panel.getByRole("button", { name: "Filters" }).click();
  await panel.getByRole("radio", { name: "In the map's view" }).click();
  await shoot(page, "filters");
  if (isPhone(page)) {
    const grip = page.getByRole("button", { name: /Panel is .* Press to resize\./ });
    await grip.click();
    await shoot(page, "sheet-full");
    await grip.click();
    await shoot(page, "sheet-peek");
  }
});

test("empty", async ({ page }) => {
  await openActivity(page);
  await page.getByText("Nothing has happened yet").waitFor();
  await shoot(page, "empty");
});

test("loading", async ({ page }) => {
  await page.route(apiRoute("/activity"), () => new Promise(() => {}));
  await openActivity(page);
  await shoot(page, "loading");
});

test("failed", async ({ page }) => {
  await answerJson(
    page,
    "/activity",
    { error: { code: "internal", message: "The server tripped over." } },
    {
      status: 400,
    },
  );
  await openActivity(page);
  await page.getByRole("alert").waitFor();
  await shoot(page, "failed");
});

test("notifications", async ({ page }) => {
  await fakeSession(page, meWith());
  await answerJson(page, "/notifications", { items: INBOX, next_cursor: null, unread_count: 2 }, { method: "GET" });
  await page.route(apiRoute("/notifications/read"), () => new Promise(() => {}));
  await openMap(page);
  await page.getByTestId("notification-count").first().waitFor();
  await shoot(page, "count");
  if (isPhone(page)) {
    await page.getByRole("button", { name: /^More/ }).click();
    await shoot(page, "count-more");
    await page.getByRole("link", { name: /^Account/ }).click();
  } else {
    await page.getByRole("link", { name: /^Account/ }).click();
  }
  const list = page.getByRole("list", { name: "Your notifications" });
  await list.waitFor();
  await shoot(page, "notifications");
});
