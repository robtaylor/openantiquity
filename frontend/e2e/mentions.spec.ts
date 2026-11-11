import type { Locator, Page } from "@playwright/test";
import type { FindingDetail } from "../src/features/finding/types.js";
import { EXPERT, evidenceFixture, seenFixture, squareFixture } from "../src/test/fixtures/findingPage.js";
import { mentionFixture, paperMentionFixture } from "../src/test/fixtures/mentions.js";
import { fakeSession, meWith } from "./support/account.js";
import { openMap } from "./support/app.js";
import { fakeFindingPage } from "./support/findingPage.js";
import { expect, test } from "./support/fixtures.js";
import { fakeMentions } from "./support/mentions.js";
import { apiRoute } from "./support/network.js";

/**
 * Mentions and the follow-up timeline in fixture mode, at desktop and phone
 * width: adding a mention after seeing what its address holds, saving one
 * whose page gave nothing, a refusal taken back, removing one's own, the
 * recent feed across the map, and what happened on the ground.
 */

const MEMBER = meWith({ handle: "BrightBank3", display_name: "Gertrude Bell" });
const AS_MEMBER = { me: { handle: MEMBER.handle, display_name: MEMBER.display_name } };
const VIEW = "#m=12/51.40/-1.80/0/0&v=composite";
const VIDEO = "https://youtu.be/dQw4w9WgXcQ?t=754";

async function openFinding(page: Page, finding: FindingDetail): Promise<Locator> {
  await openMap(page, `/f/${finding.public_id}${VIEW}`);
  const panel = page.getByRole("complementary", { name: finding.title });
  await expect(panel).toBeVisible();
  return panel;
}

/** Bring the sheet to full on a phone, so a section low on the page has room. */
async function fullSheet(page: Page): Promise<void> {
  if ((page.viewportSize()?.width ?? 0) >= 720) return;
  const handle = page.getByRole("button", { name: /Press to resize/ });
  for (let i = 0; i < 3; i++) {
    if ((await page.locator(".fc-shell").getAttribute("data-sheet")) === "full") return;
    await handle.click();
  }
}

test("a member adds a mention after seeing what it is, and finds it in the recent feed", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture();
  await fakeFindingPage(page, finding, AS_MEMBER);
  const mentions = await fakeMentions(page, finding, { ...AS_MEMBER, mentions: [paperMentionFixture()] });
  const panel = await openFinding(page, finding);
  await fullSheet(page);
  const section = panel.getByRole("region", { name: "Mentions" });
  await expect(section.getByRole("link", { name: /Prehistoric round barrows/ })).toBeVisible();

  await section.getByRole("button", { name: "Add a mention" }).click();
  await section.getByRole("textbox", { name: "Address" }).fill(VIDEO);
  await section.getByRole("button", { name: "Look it up" }).click();
  // What the address holds is shown before anything is saved.
  await expect(section.getByRole("link", { name: /Barrows of the Marlborough Downs/ })).toBeVisible();
  expect(mentions.sent["POST mention"]).toBeUndefined();
  const form = section.getByRole("form", { name: "Add a mention" });
  await expect(form.getByRole("radio", { name: "Video" })).toHaveAttribute("aria-checked", "true");
  await expect(form.getByLabel("Where it comes up (optional)")).toHaveValue("12:34");
  await form.getByLabel("Note (optional)").fill("Walks the ring ditch at the start.");
  await form.getByRole("button", { name: "Save the mention" }).click();

  const list = section.getByRole("list", { name: "Mentions of this finding" });
  const added = list.getByRole("article").first();
  await expect(added.getByText("Added by Gertrude Bell", { exact: false })).toBeVisible();
  await expect(added.getByRole("link", { name: /Barrows of the Marlborough Downs/ })).toHaveAttribute(
    "href",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=754s",
  );
  await expect(added.getByRole("img")).toHaveCount(0);
  await expect(added.locator("img")).toHaveAttribute("referrerpolicy", "no-referrer");
  expect(mentions.sent["POST mention"]).toEqual([
    { url: VIDEO, kind: "video", start_seconds: 754, note: "Walks the ring ditch at the start." },
  ]);

  await section.getByRole("link", { name: "Recent mentions everywhere" }).click();
  const feed = page.getByRole("complementary", { name: "Recent mentions" });
  await expect(feed).toBeVisible();
  const first = feed.getByRole("list", { name: "Recent mentions" }).getByRole("article").first();
  await expect(first.getByRole("link", { name: /Barrows of the Marlborough Downs/ })).toBeVisible();
  await expect(first.getByRole("link", { name: /About the finding/ })).toContainText(finding.title);
});

test("a mention whose page gave nothing is saved by its address alone, and says so", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture();
  await fakeFindingPage(page, finding, AS_MEMBER);
  const mentions = await fakeMentions(page, finding, AS_MEMBER);
  mentions.previewWith({
    canonical_url: "https://news.example.org/barrows",
    kind: "article",
    provider: "news.example.org",
    fetch_status: "refused",
    title: null,
    author_name: null,
    thumbnail_url: null,
    start_seconds: null,
    published_at: null,
  });
  const panel = await openFinding(page, finding);
  await fullSheet(page);
  const section = panel.getByRole("region", { name: "Mentions" });
  await expect(section.getByText(/Nobody has said where it was talked about yet/)).toBeVisible();
  await section.getByRole("button", { name: "Add a mention" }).click();
  await section.getByRole("textbox", { name: "Address" }).fill("https://news.example.org/barrows");
  await section.getByRole("button", { name: "Look it up" }).click();
  await expect(
    section.getByText("We don't fetch pages from that site, so it will be listed by its address alone."),
  ).toBeVisible();
  await section.getByRole("button", { name: "Save the mention" }).click();
  await expect(
    section
      .getByRole("list", { name: "Mentions of this finding" })
      .getByRole("link", { name: /news\.example\.org\/barrows/ }),
  ).toBeVisible();
});

// The refusal is a 409, which the browser logs as an error.
test.describe("a refusal", () => {
  test.use({ pageProblems: "page-errors" });

  test("a mention already listed is taken back, and the reason is put beside the address", async ({ page }) => {
    await fakeSession(page, MEMBER);
    const finding = seenFixture();
    await fakeFindingPage(page, finding, AS_MEMBER);
    const mentions = await fakeMentions(page, finding, AS_MEMBER);
    mentions.failNext("POST mention", 409, "mention_exists", "That's already mentioned on this finding.");
    const panel = await openFinding(page, finding);
    await fullSheet(page);
    const section = panel.getByRole("region", { name: "Mentions" });
    await section.getByRole("button", { name: "Add a mention" }).click();
    await section.getByRole("textbox", { name: "Address" }).fill(VIDEO);
    await section.getByRole("button", { name: "Look it up" }).click();
    await section.getByRole("button", { name: "Save the mention" }).click();
    await expect(
      page.getByText("Your mention couldn't be added. That's already listed on this finding."),
    ).toBeVisible();
    await expect(section.getByRole("textbox", { name: "Address" })).toHaveAttribute("aria-invalid", "true");
    await expect(section.getByRole("textbox", { name: "Address" })).toHaveValue(VIDEO);
    await expect(section.getByRole("list", { name: "Mentions of this finding" })).toHaveCount(0);
  });
});

test("the person who added a mention can remove it, and nobody else is offered to", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture();
  const mine = mentionFixture({
    id: 3,
    added_by: { handle: MEMBER.handle, display_name: MEMBER.display_name, role: "member" },
  });
  await fakeFindingPage(page, finding, AS_MEMBER);
  const mentions = await fakeMentions(page, finding, { ...AS_MEMBER, mentions: [mine, paperMentionFixture()] });
  const panel = await openFinding(page, finding);
  await fullSheet(page);
  const list = panel.getByRole("list", { name: "Mentions of this finding" });
  await expect(list.getByRole("article")).toHaveCount(2);
  await expect(list.getByRole("button", { name: "Remove" })).toHaveCount(1);
  await list.getByRole("button", { name: "Remove" }).click();
  await expect(list.getByRole("article")).toHaveCount(1);
  expect(mentions.sent["DELETE mention"]).toHaveLength(1);
});

test("the recent feed gives a finding whose place is kept back as its square, never a point", async ({ page }) => {
  const finding = squareFixture();
  await fakeFindingPage(page, finding);
  await fakeMentions(page, finding, { mentions: [mentionFixture({ auto_detected: true, added_by: null })] });
  await openMap(page, `/activity${VIEW}`);
  await page.getByRole("complementary", { name: "Activity" }).getByRole("link", { name: "Recent mentions" }).click();
  const feed = page.getByRole("complementary", { name: "Recent mentions" });
  const item = feed.getByRole("article").first();
  await expect(item.getByText("Found automatically: its description links to this finding.")).toBeVisible();
  const about = item.getByRole("link", { name: /About the finding/ });
  await expect(about).toContainText("Somewhere in square SU 10 69");
  await about.click();
  await expect(page.getByRole("complementary", { name: finding.title })).toBeVisible();
  await expect(page.locator(".fc-highlight-square")).toBeVisible();
  await expect(page.locator(".fc-highlight-ring")).toHaveCount(0);
});

test("the timeline lists what happened on the ground, and a visit is logged after the reminder", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture({
    evidence: [
      evidenceFixture({
        id: 2,
        kind: "excavation",
        title: "Trial trench across the ditch",
        occurred_on: "2026-09-01",
        organisation: "Wessex Archaeology",
        outcome: "supports",
        contributor: EXPERT,
        created_at: "2026-11-01T00:00:00Z",
      }),
      evidenceFixture({
        id: 3,
        kind: "field_visit",
        title: null,
        url: null,
        occurred_on: "2026-06-12",
        outcome: "inconclusive",
      }),
    ],
  });
  await fakeFindingPage(page, finding, AS_MEMBER);
  await fakeMentions(page, finding, AS_MEMBER);
  await page.route(apiRoute("/activity"), (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
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
      }),
    }),
  );
  const panel = await openFinding(page, finding);
  await fullSheet(page);
  const timeline = panel.getByRole("region", { name: "Timeline" });
  const entries = timeline.getByRole("list", { name: "What happened, oldest first" }).getByRole("listitem");
  await expect(entries).toHaveCount(2);
  await expect(entries.nth(0)).toContainText("12 June 2026");
  await expect(entries.nth(1)).toContainText("Trial trench across the ditch");
  await expect(entries.nth(1)).toContainText("It moved the finding up toChecked on the ground");

  await timeline.getByRole("button", { name: "Add to the timeline" }).click();
  await timeline.getByRole("button", { name: "Site visit" }).click();
  const form = panel.getByRole("form", { name: "Add site visit" });
  await expect(form).toBeInViewport();
  await expect(form.getByRole("note")).toContainText("landowner's permission");
});
