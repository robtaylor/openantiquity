import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page, test } from "@playwright/test";
import type { TaskGroup } from "../../src/features/help/api.js";
import { seenFixture } from "../../src/test/fixtures/findingPage.js";
import { fakeSession, meWith } from "../support/account.js";
import { openMap } from "../support/app.js";
import { fakeFindingPage } from "../support/findingPage.js";
import { apiRoute, stubNetwork } from "../support/network.js";
import { fakeQueue, fakeTasks, queuedFinding } from "../support/review.js";

/**
 * Screenshots of second look and help wanted, taken with `pnpm shots`, for
 * looking at the design at desktop and phone width: each state of a card,
 * the empty, loading and failed queue, and help wanted's kinds and lists.
 * They stub every tile, so the map behind is plain, and they assert nothing.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const VIEW = "#m=15/51.4286/-1.8542/0/0&v=composite";
const MEMBER = meWith({ handle: "KeenLynchet7", display_name: "Mary Anning" });
const CLAIMED = queuedFinding("f-ring", "Ring ditch by the long barrow");

async function shoot(page: Page, name: string): Promise<void> {
  await page.waitForTimeout(500);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `${name}-${size?.width}x${size?.height}.png`) });
}

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

async function sheetTo(page: Page, stop: "peek" | "half" | "full"): Promise<void> {
  if (!isPhone(page)) return;
  const handle = page.getByRole("button", { name: /Press to resize/ });
  for (let i = 0; i < 3; i++) {
    if ((await page.locator(".fc-shell").getAttribute("data-sheet")) === stop) return;
    await handle.click();
  }
}

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
});

test("second look: a card, its detail, the reveal", async ({ page }) => {
  await fakeSession(page, MEMBER);
  await fakeQueue(page, [CLAIMED]);
  await openMap(page, `/review${VIEW}`);
  const look = page.getByRole("complementary", { name: "Second look" });
  await look.getByRole("group", { name: "Can you see it?" }).waitFor();
  await shoot(page, "review-01-card");
  await look.getByRole("button", { name: "I can see it", exact: true }).click();
  await look.getByRole("radio", { name: "Round barrow or mound" }).click();
  await shoot(page, "review-02-detail");
  await sheetTo(page, "full");
  await shoot(page, "review-02b-detail-full");
  await look.getByRole("button", { name: "Send “I can see it”" }).click();
  await look.getByRole("heading", { name: CLAIMED.title }).waitFor();
  await sheetTo(page, "half");
  await shoot(page, "review-03-reveal");
  await sheetTo(page, "full");
  await shoot(page, "review-03b-reveal-full");
});

test("second look: a signed-out answer kept as a draft", async ({ page }) => {
  await fakeSession(page);
  await fakeQueue(page, [CLAIMED]);
  await openMap(page, `/review${VIEW}`);
  const look = page.getByRole("complementary", { name: "Second look" });
  await look.getByRole("button", { name: "Not sure", exact: true }).click();
  await shoot(page, "review-04a-signed-out-detail");
  await look.getByRole("button", { name: "Send “Not sure”" }).click();
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await sheet.waitFor();
  await shoot(page, "review-04b-sign-in");
  await sheet.getByRole("button", { name: "Close" }).click();
  await look.locator(".fc-draft-badge").waitFor();
  await shoot(page, "review-04c-draft");
});

test("second look: empty, loading and failed", async ({ page }) => {
  await openMap(page, `/review${VIEW}`);
  await page.getByRole("heading", { name: "Nothing waiting just now" }).waitFor();
  await shoot(page, "review-05-empty");

  let release = (): void => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(apiRoute("/review/next"), async (route) => {
    await held;
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: '{"error":{"code":"x","message":"The queue is resting."}}',
    });
  });
  await page.reload();
  await page.locator(".fc-review__loading").waitFor();
  await shoot(page, "review-06-loading");
  release();
  await page.getByRole("heading", { name: "The next finding couldn't be fetched" }).waitFor();
  await shoot(page, "review-07-failed");
});

const FINDING = seenFixture();
const GROUPS: TaskGroup[] = [
  { code: "need_observers", total: 12, items: [], next_cursor: null, strands: [] },
  {
    code: "need_strand",
    total: 3,
    items: [
      {
        public_id: FINDING.public_id,
        code: "need_strand",
        place: FINDING.location,
        view_state: FINDING.view_state,
        step: FINDING.assessment.next_steps[0] ?? null,
        finding: {
          title: FINDING.title,
          feature_class: FINDING.feature_class,
          tier: FINDING.tier,
          state: FINDING.state,
        },
      },
      {
        public_id: "f-bank",
        code: "need_strand",
        place: { ...FINDING.location, obscured: true, grid_ref: "SU 10 69", square: "SU1069" },
        view_state: {},
        step: { code: "need_strand", prompt: "It needs one more kind of evidence.", missing_strands: ["historic_map"] },
        finding: {
          title: "Bank and ditch along the parish edge",
          feature_class: "linear",
          tier: "seen",
          state: "open",
        },
      },
    ],
    next_cursor: null,
    strands: [],
  },
  { code: "need_ground", total: 1, items: [], next_cursor: null, strands: [] },
];

test("help wanted: kinds, a list, and a finding opened with its form ready", async ({ page }) => {
  await fakeSession(page, MEMBER);
  await fakeTasks(page, GROUPS);
  await fakeFindingPage(page, FINDING);
  await openMap(page, `/help${VIEW}`);
  await page.getByRole("list", { name: "Kinds of help" }).waitFor();
  await shoot(page, "help-01-kinds");
  await sheetTo(page, "full");
  await shoot(page, "help-01b-kinds-full");
  await page.getByRole("link", { name: /^Map detectives/ }).click();
  await page.getByRole("list", { name: "Findings that need this" }).waitFor();
  await shoot(page, "help-02-list");
  await page.getByRole("link", { name: new RegExp(FINDING.title) }).click();
  await page.getByRole("heading", { name: "Add old map" }).waitFor();
  await shoot(page, "help-03-form-ready");
});

test("help wanted: empty, loading and failed", async ({ page }) => {
  await openMap(page, `/help${VIEW}`);
  await page.getByRole("heading", { name: "Nothing needs a hand just now" }).waitFor();
  await shoot(page, "help-04-empty");
  let release = (): void => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(apiRoute("/review/tasks"), async (route) => {
    await held;
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: '{"error":{"code":"x","message":"Not now."}}',
    });
  });
  await page.reload();
  await page.locator(".fc-help__loading").waitFor();
  await shoot(page, "help-05-loading");
  release();
  await page.getByRole("heading", { name: "Help wanted couldn't be loaded" }).waitFor();
  await shoot(page, "help-06-failed");
});
