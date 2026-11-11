import type { TaskGroup, TaskItem } from "../src/features/help/api.js";
import { seenFixture } from "../src/test/fixtures/findingPage.js";
import { fakeSession, meWith } from "./support/account.js";
import { openMap } from "./support/app.js";
import { fakeFindingPage } from "./support/findingPage.js";
import { expect, test } from "./support/fixtures.js";
import { fakeTasks } from "./support/review.js";

/**
 * Help wanted, in fixture mode at desktop and phone width: the kinds of
 * work by name, a kind's findings, a finding opened with the right form
 * ready, and second looks sent to the blind queue, never listed.
 */

const MEMBER = meWith({ handle: "KeenLynchet7", display_name: "Mary Anning" });
const VIEW = "#m=12/51.40/-1.80/0/0&v=composite";
const FINDING = seenFixture();

function evidenceTask(finding = FINDING): TaskItem {
  const [step] = finding.assessment.next_steps;
  if (!step) throw new Error("the fixture has a next step");
  return {
    public_id: finding.public_id,
    code: "need_strand",
    place: finding.location,
    view_state: finding.view_state,
    step,
    finding: { title: finding.title, feature_class: finding.feature_class, tier: finding.tier, state: finding.state },
  };
}

const GROUPS: TaskGroup[] = [
  {
    code: "need_observers",
    total: 5,
    items: [
      {
        public_id: "blind-1",
        code: "need_observers",
        place: { lon: -1.85, lat: 51.42, obscured: false, grid_ref: "SU 1 2", square: null, outline: null },
        view_state: {},
        step: null,
        finding: null,
      },
    ],
    next_cursor: null,
  },
  { code: "need_strand", total: 1, items: [evidenceTask()], next_cursor: null },
];

test("lists the kinds of help, and a finding opens with the form for that work ready", async ({ page }) => {
  await fakeSession(page, MEMBER);
  await fakeTasks(page, GROUPS);
  await fakeFindingPage(page, FINDING);
  await openMap(page, `/help${VIEW}`);

  const panel = page.getByRole("complementary", { name: "Help wanted" });
  const kinds = panel.getByRole("list", { name: "Kinds of help" });
  await expect(kinds.getByRole("link", { name: /^Second looks/ })).toContainText("5 findings");
  await expect(kinds.getByRole("link", { name: /^Map detectives/ })).toContainText(
    "Map detectives check old maps for a feature drawn or named there.",
  );
  // A second look is never listed by its finding.
  await expect(page.locator('a[href*="blind-1"]')).toHaveCount(0);

  await kinds.getByRole("link", { name: /^Map detectives/ }).click();
  await expect(page).toHaveURL(/\/help\/historic_map#/);
  const list = page.getByRole("complementary", { name: "Map detectives" }).getByRole("list", {
    name: "Findings that need this",
  });
  await list.getByRole("link", { name: new RegExp(FINDING.title) }).click();

  const findingPanel = page.getByRole("complementary", { name: FINDING.title });
  await expect(findingPanel.getByRole("heading", { name: "Add old map" })).toBeVisible();
  await expect(findingPanel.getByRole("heading", { name: "Add old map" })).toBeInViewport();
  // The address says what is open, without the request.
  await expect(page).toHaveURL(new RegExp(`/f/${FINDING.public_id}#`));
});

test("second looks go to the blind queue", async ({ page }) => {
  await fakeTasks(page, GROUPS);
  await openMap(page, `/help${VIEW}`);
  await page.getByRole("link", { name: /^Second looks/ }).click();
  await expect(page).toHaveURL(/\/review#/);
  await expect(page.getByRole("complementary", { name: "Second look" })).toBeVisible();

  await page.goto(`/help/second-look${VIEW}`);
  await expect(page).toHaveURL(/\/review#/);
});

test("says when nothing needs a hand, and offers other work", async ({ page }) => {
  await openMap(page, `/help${VIEW}`);
  const panel = page.getByRole("complementary", { name: "Help wanted" });
  await expect(panel.getByRole("heading", { name: "Nothing needs a hand just now" })).toBeVisible();
  await expect(panel.getByRole("link", { name: "Give a second look" })).toBeVisible();
});
