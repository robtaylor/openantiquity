import type { Locator, Page } from "@playwright/test";
import type { FindingDetail } from "../src/features/finding/types.js";
import {
  commentFixture,
  EXPERT,
  evidenceFixture,
  FINDER,
  finderView,
  pageFixture,
  seenFixture,
  squareFixture,
} from "../src/test/fixtures/findingPage.js";
import { metaFixture } from "../src/test/fixtures/meta.js";
import { fakeSession, meWith } from "./support/account.js";
import { openMap } from "./support/app.js";
import { fakeFindingPage } from "./support/findingPage.js";
import { expect, test } from "./support/fixtures.js";

/**
 * A finding's page in fixture mode, at desktop and phone width: for each
 * tier and state, as a signed-out visitor, a member, the finder and someone
 * who may only see the square; the second look and its reveal; every
 * evidence form; and optimistic writes that fail and roll back.
 */

const MEMBER = meWith({ handle: "KeenLynchet7", display_name: "Mary Anning" });
const VIEW = "#m=12/51.40/-1.80/0/0&v=composite";

function panelOf(page: Page, finding: FindingDetail): Locator {
  return page.getByRole("complementary", { name: finding.title });
}

async function openFinding(page: Page, finding: FindingDetail): Promise<Locator> {
  await openMap(page, `/f/${finding.public_id}${VIEW}`);
  const panel = panelOf(page, finding);
  await expect(panel).toBeVisible();
  return panel;
}

/** The camera as the address bar records it: zoom, latitude, longitude. */
function camera(page: Page): { zoom: number; lat: number; lon: number } {
  const match = /#m=([\d.]+)\/(-?[\d.]+)\/(-?[\d.]+)/.exec(page.url());
  return { zoom: Number(match?.[1]), lat: Number(match?.[2]), lon: Number(match?.[3]) };
}

test("a member sees the step, what would move it up, and the map goes to the finding", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture();
  await fakeFindingPage(page, finding);
  const panel = await openFinding(page, finding);
  await expect(panel.locator(".fc-tier-badge")).toHaveText("Seen by others");
  await expect(panel.getByRole("meter", { name: "Confidence" })).toHaveAttribute("aria-valuenow", "36");
  await expect(panel.getByText("Spotted by Ada Lovelace on 1 November 2026")).toBeVisible();
  await expect(
    panel.getByText("It needs two more kinds of evidence, such as an old map or an aerial photo."),
  ).toBeVisible();

  // The map came in close, to the finding.
  await expect.poll(() => camera(page).zoom).toBeGreaterThanOrEqual(16);
  await expect(page.locator(".fc-highlight-ring")).toBeVisible();

  // A step's button opens the form for that kind.
  await panel.getByRole("button", { name: "Add aerial photo" }).click();
  const form = panel.getByRole("form", { name: "Add aerial photo" });
  await expect(form).toBeVisible();
  await expect(form.getByLabel("Source")).toBeVisible();
});

test("shows each tier and each state with its label and meter", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const fake = await fakeFindingPage(page, pageFixture());
  await openFinding(page, pageFixture());
  for (const tier of metaFixture.vocab.tiers) {
    const finding = pageFixture({
      assessment: { ...pageFixture().assessment, tier: tier.id as "seen", score: tier.base_score + 2 },
    });
    fake.set(finding);
    await page.reload();
    const panel = panelOf(page, finding);
    await expect(panel.locator(".fc-tier-badge")).toHaveText(tier.label);
    await expect(panel.getByRole("meter", { name: "Confidence" })).toHaveAttribute(
      "aria-valuetext",
      new RegExp(`^${tier.label}\\.`),
    );
  }
  for (const state of metaFixture.vocab.states.filter((entry) => entry.id !== "open")) {
    const finding = pageFixture({
      assessment: {
        ...pageFixture().assessment,
        state: state.id as "known",
        state_reason: state.id === "ruled_out" ? "not_visible" : null,
      },
    });
    fake.set(finding);
    await page.reload();
    const block = panelOf(page, finding).locator(".fc-finding__state");
    await expect(block.getByText(state.label, { exact: true })).toBeVisible();
  }
});

test("a signed-out visitor sees a protected finding's square, why, and how to see more", async ({ page }) => {
  const finding = squareFixture();
  await fakeFindingPage(page, finding);
  const panel = await openFinding(page, finding);
  await expect(panel.getByText("SU1069", { exact: true })).toBeVisible();
  await expect(panel.getByText(/not the place itself/)).toContainText("Sign in to see it.");
  await expect(panel.getByRole("group", { name: "Can you see it?" })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "See it as the finder did" })).toHaveCount(0);
  await expect(page.locator(".fc-highlight-square")).toBeVisible();
  await expect.poll(() => camera(page).zoom).toBeCloseTo(13.5, 1);
  await panel.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("dialog", { name: "Sign in" })).toBeVisible();
});

test("a member who may only see a restricted finding's square is told who can", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = squareFixture({ sensitivity: "restricted" });
  await fakeFindingPage(page, finding);
  const panel = await openFinding(page, finding);
  await expect(panel.getByText(/not the place itself/)).toContainText("trusted members, archaeologists and moderators");
  await expect(panel.getByRole("button", { name: "Sign in" })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Add evidence" })).toHaveCount(0);
});

test("the finder gets their own controls and a link to ask others", async ({ page }) => {
  await fakeSession(page, meWith({ handle: FINDER.handle, display_name: FINDER.display_name }));
  const finding = finderView();
  await fakeFindingPage(page, finding);
  const panel = await openFinding(page, finding);
  await expect(panel.getByRole("group", { name: "Can you see it?" })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Copy a link to ask others" })).toBeVisible();
  await panel.getByRole("button", { name: "Withdraw" }).click();
  const dialog = page.getByRole("dialog", { name: "Withdraw this finding?" });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await panel.getByRole("button", { name: "Protect it more" }).click();
  await expect(page.getByRole("dialog", { name: "Protect this finding" })).toContainText(
    "Only people who have signed in see its exact place.",
  );
});

test("a second look reveals nothing before the answer, offers detail after it, and then reveals", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = pageFixture();
  const fake = await fakeFindingPage(page, finding);
  const panel = await openFinding(page, finding);
  const look = panel.getByRole("region", { name: "Your second look" });

  // Before answering: no answers, no counts, and none asked for.
  await expect(look.getByText(/final once sent/)).toBeVisible();
  await expect(look.getByText("What do you think it is?")).toHaveCount(0);
  await expect(panel.getByRole("heading", { name: "Second looks" })).toHaveCount(0);
  expect(fake.asked).not.toContain("observations");
  const text = await panel.textContent();
  expect(text).not.toMatch(/other people can see it|can't see it\b.*\d/);

  await look.getByRole("button", { name: "I can see it" }).click();
  await expect(look.getByText("What do you think it is?")).toBeVisible();
  await look.getByRole("radio", { name: "Round barrow or mound" }).click();
  await look.getByRole("button", { name: "Send: i can see it" }).click();

  await expect(look.getByText(/2 other people can see it, 1 isn't sure and 0 can't\./)).toBeVisible();
  await expect(look.getByText(/So do you\./)).toBeVisible();
  expect(fake.sent["PUT observation"]).toEqual([{ visible: "yes", feature_class: "round_barrow" }]);
  await expect(panel.getByRole("heading", { name: "Second looks" })).toBeVisible();
  await expect(look.getByRole("group", { name: "Can you see it?" })).toHaveCount(0);
  await expect(look.getByLabel("Your note")).toBeVisible();
});

test("every evidence form fits the screen and asks only for what its kind needs", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture();
  await fakeFindingPage(page, finding);
  const panel = await openFinding(page, finding);
  const width = page.viewportSize()?.width ?? 0;
  for (const kind of metaFixture.vocab.evidence_kinds) {
    await panel.getByRole("button", { name: "Add evidence" }).click();
    await panel.locator(".fc-kind-list").getByRole("button", { name: kind.label, exact: true }).click();
    const add = panel.locator(".fc-evidence-add");
    await expect(add).toBeVisible();
    const fieldVisit = kind.id === "field_visit" || kind.id === "geophysics" || kind.id === "excavation";
    await expect(add.getByRole("note")).toHaveCount(fieldVisit ? 1 : 0);
    if (fieldVisit) await expect(add.getByLabel("When")).toBeVisible();
    // Nothing in the form runs off the side of the screen.
    const overflow = await add.evaluate((element) =>
      Array.from(element.querySelectorAll<HTMLElement>("*")).some(
        (child) => child.getBoundingClientRect().right > window.innerWidth + 0.5,
      ),
    );
    expect(overflow, `${kind.id} at ${width}px`).toBe(false);
    await add.getByRole("button", { name: "Cancel" }).click();
    await expect(add).toHaveCount(0);
  }
});

test("adds an old map at once and keeps it once the server has it", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture();
  const fake = await fakeFindingPage(page, finding);
  const panel = await openFinding(page, finding);
  const release = fake.hold("POST evidence");
  await panel.getByRole("button", { name: "Add old map" }).click();
  await panel.getByLabel("Which map").fill("OS 6-inch, 1888");
  await panel.getByRole("button", { name: "Add it" }).click();
  const item = panel.locator(".fc-evidence").filter({ hasText: "OS 6-inch, 1888" });
  await expect(item).toContainText("Saving…");
  release();
  await expect(item).not.toContainText("Saving…");
  expect(fake.sent["POST evidence"]).toEqual([{ kind: "historic_map", stance: "supports", title: "OS 6-inch, 1888" }]);
});

// Each of these makes a request fail on purpose, which the browser logs as an error.
test.describe("failures", () => {
  test.use({ pageProblems: "page-errors" });

  test("a comment, a vote and a follow that fail are taken back with a toast", async ({ page }) => {
    await fakeSession(page, MEMBER);
    const finding = seenFixture({ following: false, evidence: [evidenceFixture({ id: 1, contributor: EXPERT })] });
    const fake = await fakeFindingPage(page, finding, { comments: [commentFixture()] });
    const panel = await openFinding(page, finding);
    const toasts = page.locator(".fc-toast");

    // A comment shows at once, then goes, and the text comes back to the box.
    const releaseComment = fake.hold("POST comments");
    fake.failNext("POST comments", 500, "The database isn't answering.");
    await panel.getByLabel("Add a comment").fill("Clear in slope too.");
    await panel.getByRole("button", { name: "Post" }).click();
    await expect(panel.locator(".fc-comment").filter({ hasText: "Clear in slope too." })).toBeVisible();
    releaseComment();
    await expect(toasts.filter({ hasText: "Your comment couldn't be posted." })).toBeVisible();
    await expect(panel.locator(".fc-comment").filter({ hasText: "Clear in slope too." })).toHaveCount(0);
    await expect(panel.getByLabel("Add a comment")).toHaveValue("Clear in slope too.");

    // A vote.
    const releaseVote = fake.hold("PUT vote");
    fake.failNext("PUT vote", 409, "This finding was withdrawn.");
    const endorse = panel.getByRole("button", { name: "Endorse" });
    await endorse.click();
    await expect(endorse).toHaveAttribute("aria-pressed", "true");
    releaseVote();
    await expect(toasts.filter({ hasText: "Your vote couldn't be saved." })).toBeVisible();
    await expect(endorse).toHaveAttribute("aria-pressed", "false");

    // A follow.
    const releaseFollow = fake.hold("PUT follow");
    fake.failNext("PUT follow", 500, "Try later.");
    await panel.getByRole("button", { name: "Follow" }).click();
    await expect(panel.getByRole("button", { name: "Unfollow" })).toBeVisible();
    releaseFollow();
    await expect(toasts.filter({ hasText: "That didn't work." })).toBeVisible();
    await expect(panel.getByRole("button", { name: "Follow" })).toHaveAttribute("aria-pressed", "false");
  });

  test("a finding that isn't there says so and offers Explore", async ({ page }) => {
    await page.route(/\/api\/v1\/findings\/gone(\?|$)/, (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "finding_not_found", message: "No such finding." } }),
      }),
    );
    await openMap(page, `/f/gone${VIEW}`);
    const panel = page.getByRole("complementary", { name: "Finding not found" });
    await expect(panel.getByRole("heading", { name: "There's no finding at this address" })).toBeVisible();
    await panel.getByRole("link", { name: "Back to Explore" }).click();
    await expect(page.getByRole("complementary", { name: "Explore" })).toBeVisible();
  });

  test("a load that fails says so and tries again", async ({ page }) => {
    let fail = true;
    const finding = pageFixture();
    await fakeFindingPage(page, finding);
    await page.route(/\/api\/v1\/findings\/f-ring(\?|$)/, (route) =>
      fail
        ? route.fulfill({
            status: 400,
            contentType: "application/json",
            body: JSON.stringify({ error: { code: "x", message: "Something broke." } }),
          })
        : route.fallback(),
    );
    await openMap(page, `/f/f-ring${VIEW}`);
    const panel = page.getByRole("complementary", { name: "Finding" });
    await expect(panel.getByRole("heading", { name: "This finding couldn't be loaded" })).toBeVisible();
    fail = false;
    await panel.getByRole("button", { name: "Try again" }).click();
    await expect(panelOf(page, finding)).toBeVisible();
  });
});
