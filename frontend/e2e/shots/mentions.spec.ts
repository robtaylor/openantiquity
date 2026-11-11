import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Locator, type Page, test } from "@playwright/test";
import type { FindingDetail } from "../../src/features/finding/types.js";
import { EXPERT, evidenceFixture, seenFixture, squareFixture } from "../../src/test/fixtures/findingPage.js";
import { mentionFixture, paperMentionFixture } from "../../src/test/fixtures/mentions.js";
import { fakeSession, meWith } from "../support/account.js";
import { openMap } from "../support/app.js";
import { fakeFindingPage } from "../support/findingPage.js";
import { fakeMentions } from "../support/mentions.js";
import { apiRoute, stubNetwork } from "../support/network.js";

/**
 * Screenshots of mentions and the follow-up timeline, taken with `pnpm shots`,
 * at desktop and phone width: a finding's mentions, adding one, the recent
 * feed in each state, and the timeline. They assert nothing.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const VIEW = "#m=15/51.4286/-1.8542/0/0&v=composite";
const MEMBER = meWith({ handle: "BrightBank3", display_name: "Gertrude Bell" });
const AS_MEMBER = { me: { handle: MEMBER.handle, display_name: MEMBER.display_name } };
const MINE = { handle: MEMBER.handle, display_name: MEMBER.display_name, role: "member" };

async function shoot(page: Page, name: string): Promise<void> {
  await page.waitForTimeout(450);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `mentions-${name}-${size?.width}x${size?.height}.png`) });
}

async function sheetTo(page: Page, stop: "peek" | "half" | "full"): Promise<void> {
  if ((page.viewportSize()?.width ?? 0) >= 720) return;
  const handle = page.getByRole("button", { name: /Press to resize/ });
  for (let i = 0; i < 3; i++) {
    if ((await page.locator(".fc-shell").getAttribute("data-sheet")) === stop) return;
    await handle.click();
  }
}

async function scrollTo(locator: Locator): Promise<void> {
  await locator.evaluate((element) => element.scrollIntoView({ block: "start" }));
}

async function open(page: Page, finding: FindingDetail): Promise<Locator> {
  await openMap(page, `/f/${finding.public_id}${VIEW}`);
  const panel = page.getByRole("complementary", { name: finding.title });
  await panel.waitFor();
  await sheetTo(page, "full");
  return panel;
}

const FOLLOWED_UP = seenFixture({
  evidence: [
    evidenceFixture({ id: 1, kind: "historic_map" }),
    evidenceFixture({
      id: 2,
      kind: "excavation",
      title: "Trial trench across the ditch",
      note: "The ditch is 1.2 m deep, with Beaker sherds in its lower fill.",
      occurred_on: "2026-09-01",
      organisation: "Wessex Archaeology",
      outcome: "supports",
      url: "https://reports.example.org/trench",
      contributor: EXPERT,
      created_at: "2026-11-01T00:00:00Z",
    }),
    evidenceFixture({
      id: 3,
      kind: "field_visit",
      title: null,
      url: null,
      note: "A low bank, just visible in the grass.",
      occurred_on: "2026-06-12",
      outcome: "inconclusive",
      created_at: "2026-11-03T00:00:00Z",
    }),
  ],
});

const MOVES = {
  items: [
    {
      id: 41,
      kind: "tier_changed",
      created_at: "2026-11-01T00:00:01Z",
      actor: EXPERT,
      finding: null,
      investigation: null,
      details: { tier_from: "probable", tier_to: "ground_checked" },
    },
    {
      id: 40,
      kind: "followup_logged",
      created_at: "2026-11-01T00:00:00Z",
      actor: EXPERT,
      finding: null,
      investigation: null,
      details: { evidence_id: 2 },
    },
  ],
  next_cursor: null,
};

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
});

test("a finding's mentions", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture();
  await fakeFindingPage(page, finding, AS_MEMBER);
  await fakeMentions(page, finding, {
    ...AS_MEMBER,
    mentions: [
      mentionFixture({ id: 4, added_by: MINE }),
      mentionFixture({
        id: 3,
        auto_detected: true,
        added_by: null,
        title: "Ridgeway walk, part 3: the barrow cemetery above Avebury and the ring ditch nobody had noticed",
        start_seconds: null,
        note: null,
      }),
      paperMentionFixture(),
    ],
  });
  const panel = await open(page, finding);
  await scrollTo(panel.getByRole("heading", { name: "Mentions" }));
  await shoot(page, "01-list");
});

test("no mentions, and loading and failing", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture();
  await fakeFindingPage(page, finding, AS_MEMBER);
  await fakeMentions(page, finding, AS_MEMBER);
  let answer: "empty" | "hold" | "fail" = "empty";
  await page.route(apiRoute(`/findings/${finding.public_id}/mentions`), async (route) => {
    if (answer === "empty") return route.fallback();
    if (answer === "hold") return;
    return route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "unavailable", message: "The server is busy." } }),
    });
  });
  let panel = await open(page, finding);
  await scrollTo(panel.getByRole("heading", { name: "Mentions" }));
  await shoot(page, "02-empty");
  answer = "hold";
  await page.reload();
  panel = await open(page, finding);
  await scrollTo(panel.getByRole("heading", { name: "Mentions" }));
  await shoot(page, "03-loading");
  answer = "fail";
  await page.reload();
  panel = await open(page, finding);
  await panel.getByText("The mentions couldn't be loaded.", { exact: false }).waitFor();
  await scrollTo(panel.getByRole("heading", { name: "Mentions" }));
  await shoot(page, "04-failed");
});

test("adding a mention", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture();
  await fakeFindingPage(page, finding, AS_MEMBER);
  const mentions = await fakeMentions(page, finding, { ...AS_MEMBER, mentions: [paperMentionFixture()] });
  const panel = await open(page, finding);
  const section = panel.getByRole("region", { name: "Mentions" });
  await section.getByRole("button", { name: "Add a mention" }).click();
  await scrollTo(panel.getByRole("heading", { name: "Add a mention" }));
  await shoot(page, "10-add-empty");
  await section.getByRole("textbox", { name: "Address" }).fill("https://youtu.be/dQw4w9WgXcQ?t=754");
  await section.getByRole("button", { name: "Look it up" }).click();
  await section.getByRole("button", { name: "Save the mention" }).waitFor();
  await scrollTo(panel.getByRole("heading", { name: "Add a mention" }));
  await shoot(page, "11-add-found");
  await section.getByRole("radio", { name: "Video" }).scrollIntoViewIfNeeded();
  await shoot(page, "11b-add-found-details");

  mentions.failNext("POST mention", 409, "mention_exists", "That's already mentioned on this finding.");
  await section.getByRole("button", { name: "Save the mention" }).click();
  await page.getByText("Your mention couldn't be added.", { exact: false }).waitFor();
  await scrollTo(panel.getByRole("heading", { name: "Add a mention" }));
  await shoot(page, "12-add-refused");

  mentions.previewWith({
    canonical_url: "https://news.example.org/barrows",
    kind: "article",
    provider: "news.example.org",
    fetch_status: "failed",
    title: null,
    author_name: null,
    thumbnail_url: null,
    start_seconds: null,
    published_at: null,
  });
  await section.getByRole("textbox", { name: "Address" }).fill("https://news.example.org/barrows");
  await section.getByRole("button", { name: "Look it up" }).click();
  await section.getByText("Its page didn't answer", { exact: false }).waitFor();
  await scrollTo(panel.getByRole("heading", { name: "Add a mention" }));
  await shoot(page, "13-add-fetch-failed");
  await section.getByRole("button", { name: "Save the mention" }).click();
  await section.getByRole("link", { name: /news\.example\.org\/barrows/ }).waitFor();
  // Where the page itself puts the saved mention, in sight with focus on it.
  await shoot(page, "14-added-address-alone");
  await section
    .getByRole("button", { name: /^Remove/ })
    .first()
    .click();
  await shoot(page, "15-removed");
});

test("the recent mentions", async ({ page }) => {
  const open = squareFixture();
  await fakeFindingPage(page, open);
  await fakeMentions(page, open, {
    mentions: [
      mentionFixture({ id: 9, auto_detected: true, added_by: null }),
      paperMentionFixture({ id: 8, note: "Lists it as site 14 in the gazetteer." }),
    ],
  });
  await openMap(page, `/activity${VIEW}`);
  await page.getByRole("complementary", { name: "Activity" }).waitFor();
  await shoot(page, "20-activity-link");
  await page.getByRole("link", { name: "Recent mentions" }).click();
  await page.getByRole("complementary", { name: "Recent mentions" }).getByRole("article").first().waitFor();
  await sheetTo(page, "half");
  await shoot(page, "21-feed-half");
  await sheetTo(page, "full");
  await shoot(page, "22-feed-full");
  await sheetTo(page, "peek");
  await shoot(page, "23-feed-peek");
});

test("the recent mentions, empty, loading and failing", async ({ page }) => {
  let answer: "empty" | "hold" | "fail" = "empty";
  await page.route(apiRoute("/mentions/recent"), async (route) => {
    if (answer === "empty") return route.fallback();
    if (answer === "hold") return;
    return route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "unavailable", message: "The server is busy." } }),
    });
  });
  await openMap(page, `/mentions${VIEW}`);
  await page.getByRole("heading", { name: "No mentions yet" }).waitFor();
  await sheetTo(page, "full");
  await shoot(page, "24-feed-empty");
  answer = "hold";
  await page.reload();
  await page.getByRole("complementary", { name: "Recent mentions" }).waitFor();
  await sheetTo(page, "full");
  await shoot(page, "25-feed-loading");
  answer = "fail";
  await page.reload();
  await page.getByText("The mentions couldn't be loaded").waitFor();
  await sheetTo(page, "full");
  await shoot(page, "26-feed-failed");
});

test("the timeline", async ({ page }) => {
  await fakeSession(page, MEMBER);
  await fakeFindingPage(page, FOLLOWED_UP, AS_MEMBER);
  await fakeMentions(page, FOLLOWED_UP, AS_MEMBER);
  await page.route(apiRoute("/activity"), (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(MOVES) }),
  );
  const panel = await open(page, FOLLOWED_UP);
  await panel.getByText("It moved the finding up to", { exact: false }).waitFor();
  await scrollTo(panel.getByRole("heading", { name: "Timeline" }));
  await shoot(page, "30-timeline");
  await panel.getByRole("button", { name: "Add to the timeline" }).click();
  // The chooser brings itself into view.
  await shoot(page, "31-timeline-choose");
  await panel.getByRole("button", { name: "Site visit" }).last().click();
  await panel.getByRole("form", { name: "Add site visit" }).waitFor();
  await page.waitForTimeout(400);
  await shoot(page, "32-visit-reminder");
});

test("the timeline, empty", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture();
  await fakeFindingPage(page, finding, AS_MEMBER);
  await fakeMentions(page, finding, AS_MEMBER);
  const panel = await open(page, finding);
  await scrollTo(panel.getByRole("heading", { name: "Timeline" }));
  await shoot(page, "33-timeline-empty");
});
