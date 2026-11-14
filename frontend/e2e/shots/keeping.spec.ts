import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page, test } from "@playwright/test";
import {
  EXPERT,
  FINDER,
  FINDER_ACTIONS,
  lineFixture,
  MODERATOR_ACTIONS,
  OTHER,
  shapeSuggestionFixture,
} from "../../src/test/fixtures/findingPage.js";
import { findingSummary, offset } from "../../src/test/fixtures/findings.js";
import { fakeSession, meWith } from "../support/account.js";
import { openMap } from "../support/app.js";
import { fakeFindingPage } from "../support/findingPage.js";
import { fakeFindings } from "../support/findings.js";
import { fakeKeeping } from "../support/keeping.js";
import { fakeModeration } from "../support/moderation.js";
import { stubNetwork } from "../support/network.js";
import { finding, line } from "../support/shapes.js";

/**
 * Screenshots of keepers, suggestions and an admin's removal, at desktop and
 * phone width, with the browser asking for a light and a dark scheme. The
 * interface has one dark theme, so the two should match. They stub every
 * tile and assert nothing.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const VIEW = "#m=16/51.4286/-1.8542/0/0&v=composite";
const MEMBER = meWith({ handle: OTHER.handle, display_name: OTHER.display_name });
const THE_FINDER = meWith({ handle: FINDER.handle, display_name: FINDER.display_name });
const ADMIN = meWith({ handle: "AdminAnwen", display_name: "Anwen Price", role: "admin" });
const GONE = { handle: "former-member-1", display_name: "Former member", role: "member" };
const SCHEMES = ["dark", "light"] as const;

async function shoot(page: Page, name: string, scheme: string): Promise<void> {
  await page.waitForTimeout(600);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `keeping-${name}-${scheme}-${size?.width}x${size?.height}.png`) });
}

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
  // The line on the map, as the findings layer draws it, so what is suggested or put back is seen against it.
  await fakeFindings(page, [
    finding(
      "f-ring",
      "Ring ditch by the long barrow",
      [0, 20],
      line([
        [-100, 0],
        [0, 20],
        [100, 0],
      ]),
      "round_barrow",
    ),
  ]);
});

for (const scheme of SCHEMES) {
  test(`suggesting a change, ${scheme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await fakeSession(page, MEMBER);
    const fake = await fakeFindingPage(page, lineFixture(), { me: MEMBER });
    await fakeKeeping(page, fake, { me: OTHER });
    await openMap(page, `/f/f-ring${VIEW}`);
    const panel = page.getByRole("complementary", { name: "Ring ditch by the long barrow" });
    await panel.getByRole("button", { name: "Suggest a change" }).scrollIntoViewIfNeeded();
    await shoot(page, "10-its-shape", scheme);
    await panel.getByRole("button", { name: "Suggest a change" }).click();
    const handle = page.getByRole("button", { name: /^Point 3 of 3,/ });
    await handle.waitFor();
    await handle.focus();
    for (let step = 0; step < 3; step++) await page.keyboard.press("Shift+ArrowUp");
    await shoot(page, "11-suggest-panel", scheme);
    await page
      .getByRole("complementary", { name: "Suggest a change" })
      .getByRole("button", { name: "Close panel" })
      .click();
    await page.getByRole("button", { name: "Carry on with your suggested change" }).waitFor();
    await shoot(page, "12-unfinished-suggestion", scheme);
    await page.getByRole("button", { name: "Mark a finding" }).click();
    await page.getByRole("complementary", { name: "Mark a finding" }).getByRole("alert").waitFor();
    await shoot(page, "13-mark-asks", scheme);
  });

  test(`the keeper's suggested changes and handing on, ${scheme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await fakeSession(page, THE_FINDER);
    const mine = shapeSuggestionFixture();
    const behind = shapeSuggestionFixture({ id: 72, by: EXPERT, kind: "reshaped", length_m: 230, behind: true });
    const fake = await fakeFindingPage(
      page,
      lineFixture({ actions: FINDER_ACTIONS }, { suggestions: [behind, mine] }),
      {
        me: THE_FINDER,
      },
    );
    const keeping = await fakeKeeping(page, fake, { me: FINDER, people: { [OTHER.handle]: OTHER } });
    await openMap(page, `/f/f-ring${VIEW}`);
    const panel = page.getByRole("complementary", { name: "Ring ditch by the long barrow" });
    const list = panel.getByRole("list", { name: "Suggested changes" });
    await list.scrollIntoViewIfNeeded();
    await shoot(page, "20-suggested-changes", scheme);
    await list
      .getByRole("listitem")
      .filter({ hasText: "Mary Anning" })
      .getByRole("button", { name: "Show on the map" })
      .click();
    await shoot(page, "21-suggestion-on-map", scheme);
    keeping.refuseNextAccept(
      "Only 60% of what others looked at would be left within 250 m of it, and three-quarters has to stay.",
    );
    await list.getByRole("listitem").filter({ hasText: "Mary Anning" }).getByRole("button", { name: "Accept" }).click();
    await list.getByRole("alert").waitFor();
    await shoot(page, "22-accept-refused", scheme);
    await list.getByRole("listitem").filter({ hasText: "Dr Ditch" }).getByRole("button", { name: "Accept" }).click();
    await page.getByRole("dialog", { name: "Accept a suggestion made on an earlier shape?" }).waitFor();
    await shoot(page, "23-accept-behind", scheme);
    await page.keyboard.press("Escape");

    await panel.getByRole("button", { name: "Hand it on" }).click();
    const dialog = page.getByRole("dialog", { name: "Hand it on" });
    await dialog.getByLabel("Their handle").fill("NobodyByThisName");
    await dialog.getByRole("button", { name: "Offer it" }).click();
    await dialog.getByRole("alert").waitFor();
    await shoot(page, "24-hand-on-refused", scheme);
    await dialog.getByLabel("Their handle").fill(OTHER.handle);
    await dialog.getByRole("button", { name: "Offer it" }).click();
    await panel.getByText(/Offered to/).scrollIntoViewIfNeeded();
    await shoot(page, "25-offer-standing", scheme);
  });

  test(`the person offered, ${scheme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await fakeSession(page, MEMBER);
    await fakeFindingPage(
      page,
      lineFixture({
        keeper: FINDER,
        keeping: { offered_to: OTHER, offered_at: "2026-11-12T08:00:00Z" },
        actions: { ...lineFixture().actions, take_keeping: { allowed: true, reason: null } },
      }),
      { me: MEMBER },
    );
    await openMap(page, `/f/f-ring${VIEW}`);
    await page.getByRole("button", { name: "Take it on" }).scrollIntoViewIfNeeded();
    await shoot(page, "30-offer-to-you", scheme);
  });

  test(`an admin and a marking without a keeper, ${scheme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await fakeSession(page, ADMIN);
    await fakeModeration(page);
    const fake = await fakeFindingPage(
      page,
      lineFixture({
        keeper: GONE,
        actions: {
          ...MODERATOR_ACTIONS,
          hand_on: { allowed: true, reason: null },
          remove_marking: { allowed: true, reason: null },
        },
      }),
      { me: ADMIN },
    );
    const before = [offset(-140, -30), offset(-40, -60), offset(60, -40)];
    await fakeKeeping(page, fake, {
      me: ADMIN,
      orphaned: [
        {
          finding: findingSummary(
            {
              type: "Feature",
              geometry: { type: "Point", coordinates: [offset(0, 0).lon, offset(0, 0).lat] },
              properties: { public_id: "f-ring", tier: "seen", state: "open", obscured: false },
            },
            { title: "Ring ditch by the long barrow" },
          ),
          keeper: GONE,
          keeper_gone: "deleted",
        },
      ],
      earlier: [
        {
          revision: 3,
          kind: "extended",
          by: GONE,
          created_at: "2026-11-09T10:00:00Z",
          path_before: {
            closed: false,
            curve: "catmull-rom-centripetal-1",
            points: before.map(({ lon, lat }) => ({ lon, lat, kind: "smooth" as const })),
          },
          restorable: true,
        },
        {
          revision: 2,
          kind: "reshaped",
          by: GONE,
          created_at: "2026-11-05T10:00:00Z",
          path_before: {
            closed: false,
            curve: "catmull-rom-centripetal-1",
            points: before.slice(0, 2).map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
          },
          restorable: false,
        },
      ],
    });
    await openMap(page, `/mod/markings${VIEW}`);
    await page.getByRole("list", { name: "Markings without a keeper" }).waitFor();
    await shoot(page, "40-no-keeper-list", scheme);
    await page.goto(`/f/f-ring${VIEW}`);
    const panel = page.getByRole("complementary", { name: "Ring ditch by the long barrow" });
    await panel.getByRole("heading", { name: "No keeper" }).scrollIntoViewIfNeeded();
    await shoot(page, "41-no-keeper-on-page", scheme);
    await panel.getByRole("button", { name: "Remove the marking" }).click();
    const removal = page.getByRole("complementary", { name: "Remove the marking" });
    await removal.getByRole("radio", { name: /As it was until 9 November 2026/ }).check();
    await shoot(page, "42-removal-chosen", scheme);
    await removal.getByRole("button", { name: "Put this shape back" }).scrollIntoViewIfNeeded();
    await shoot(page, "43-removal-foot", scheme);
  });
}

/** A line of `lineFixture`'s shape, as metres east and north of the centre. */
const LINE_M: Array<[number, number]> = [
  [-100, 0],
  [0, 20],
  [100, 0],
];

function suggestedPath(points: Array<[number, number]>) {
  const placed = points.map(([east, north]) => offset(east, north));
  return {
    path: {
      closed: false,
      curve: "catmull-rom-centripetal-1",
      points: placed.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
    },
    outline: { type: "LineString" as const, coordinates: placed.map(({ lon, lat }) => [lon, lat]) },
  };
}

const KINDS = {
  extends: shapeSuggestionFixture({
    id: 81,
    ...suggestedPath([...LINE_M, [250, 10]]),
    kind: "extended",
    length_m: 355,
  }),
  reshapes: shapeSuggestionFixture({
    id: 82,
    by: EXPERT,
    ...suggestedPath([
      [-100, 0],
      [0, 70],
      [100, 0],
    ]),
    kind: "reshaped",
    length_m: 245,
  }),
  shortens: shapeSuggestionFixture({
    id: 83,
    by: { handle: "FieldWalker9", display_name: "Sam Field", role: "member" },
    ...suggestedPath(LINE_M.slice(0, 2)),
    kind: "reshaped",
    length_m: 102,
  }),
} as const;

for (const ground of ["composite", "osm_standard"] as const) {
  test(`a suggestion that extends, reshapes and shortens a line, on ${ground}`, async ({ page }) => {
    await fakeSession(page, THE_FINDER);
    const suggestions = Object.values(KINDS);
    await fakeFindingPage(page, lineFixture({ actions: FINDER_ACTIONS }, { suggestions }), { me: THE_FINDER });
    await openMap(page, `/f/f-ring#m=17/51.4287/-1.8542/0/0&v=${ground}`);
    const list = page
      .getByRole("complementary", { name: "Ring ditch by the long barrow" })
      .getByRole("list", { name: "Suggested changes" });
    for (const [name, suggestion] of Object.entries(KINDS)) {
      const show = list
        .locator(`[data-suggestion="${suggestion.id}"]`)
        .getByRole("button", { name: "Show on the map" });
      await show.click();
      await shoot(page, `50-${name}-${ground}`, "dark");
      await show.click();
    }
  });
}
