import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useHiddenFindings } from "../../../map/hiddenFindings.js";
import { type ApiRoutes, routeApi } from "../../../test/apiRoutes.js";
import { pageFixture, suggestionsFixture } from "../../../test/fixtures/findingPage.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../../test/shellHarness.js";
import type { Me } from "../../account/api.js";
import { useAccountUi } from "../../account/requireAccount.js";
import { resetDraftsForTests } from "../../drafts/store.js";
import { useSelectedFinding } from "../../findings/selection.js";
import { useReviewStore } from "../../review/reviewStore.js";
import type { ReviewCard } from "../../review/types.js";
import { SHAPE_CHANGED_WORDS } from "../api.js";
import type { FindingDetail } from "../types.js";
import {
  type AnswerDraftData,
  answerDrafts,
  answerDraftsFor,
  keepAnswerDraft,
  useSavedAnswers,
} from "./answerDrafts.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

/**
 * An answer names the shape it was given on, and nothing of an answer to a
 * shape that has since changed is kept. A draft kept in this browser on an
 * older shape than the one now shown is not offered: it is removed, and
 * the person sees the finding as it is now, with the sentence that says the
 * shape changed. A draft kept before answers named a revision was given on
 * revision 0.
 */

const harness = setUpShellTests();

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  resetDraftsForTests();
  useAccountUi.setState({ sheet: null, waiting: [] });
  useSavedAnswers.getState().clear();
  useReviewStore.getState().reset();
  useHiddenFindings.setState({ reasons: [] });
  useSelectedFinding.getState().clear();
});

/** A line at shape revision `revision`. */
function line(revision: number): FindingDetail {
  const base = pageFixture();
  return {
    ...base,
    location: {
      ...base.location,
      shape: { ...base.location.shape, kind: "line", length_m: 300, revision, changes: [] },
    },
  };
}

/** An answer of "I can see it" kept in this browser, given on `revision`, or before answers named one. */
function keptAnswer(revision: number | undefined): void {
  const data: AnswerDraftData = { public_id: "f-ring", answer: { visible: "yes" }, reveal: false };
  if (revision !== undefined) data.shape_revision = revision;
  expect(keepAnswerDraft(data)).toBe(true);
}

function keptRevisions(): Array<number | null | undefined> {
  return answerDraftsFor("f-ring").map((draft) => answerDrafts.read(draft)?.shape_revision);
}

function servePage(finding: FindingDetail, me: Me | null): ApiRoutes {
  const path = `/findings/${finding.public_id}`;
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : signedOutResponse()),
    [`GET ${path}`]: () => json(finding),
    [`GET ${path}/comments`]: () => json({ items: [], next_cursor: null }),
    [`GET ${path}/suggested-records`]: () => json(suggestionsFixture([])),
    [`GET ${path}/observations`]: () => json({ items: [], next_cursor: null }),
  });
}

async function openPage(finding: FindingDetail) {
  renderShell(`/f/${finding.public_id}`);
  await mapReady();
  return within(await screen.findByRole("complementary", { name: finding.title }));
}

describe("a kept answer on the finding's page", () => {
  it("is not offered, and is removed, when it was given on another shape, and the page says the shape changed", async () => {
    const user = userEvent.setup();
    keptAnswer(2);
    servePage(line(3), null);
    const panel = await openPage(line(3));
    expect(await panel.findByText(SHAPE_CHANGED_WORDS)).toBeInTheDocument();
    await waitFor(() => expect(answerDraftsFor("f-ring")).toHaveLength(0));
    expect(panel.queryByText("Not saved yet")).toBeNull();
    expect(panel.getByRole("button", { name: "I can see it" })).not.toHaveAttribute("aria-pressed", "true");

    // Answered again, the answer names the shape shown.
    await user.click(panel.getByRole("button", { name: "Not sure" }));
    await waitFor(() => expect(keptRevisions()).toEqual([3]));
  });

  it("is offered as it was when it was given on the shape shown", async () => {
    keptAnswer(3);
    servePage(line(3), null);
    const panel = await openPage(line(3));
    expect(await panel.findByText("Not saved yet")).toBeInTheDocument();
    expect(panel.queryByText(SHAPE_CHANGED_WORDS)).toBeNull();
    expect(keptRevisions()).toEqual([3]);
  });

  it("counts a draft kept before answers named a revision as given on revision 0", async () => {
    keptAnswer(undefined);
    servePage(line(0), null);
    const panel = await openPage(line(0));
    expect(await panel.findByText("Not saved yet")).toBeInTheDocument();
    expect(answerDraftsFor("f-ring")).toHaveLength(1);
  });

  it("removes a draft kept before answers named a revision once the shape has been changed", async () => {
    keptAnswer(undefined);
    servePage(line(2), null);
    const panel = await openPage(line(2));
    expect(await panel.findByText(SHAPE_CHANGED_WORDS)).toBeInTheDocument();
    await waitFor(() => expect(answerDraftsFor("f-ring")).toHaveLength(0));
    expect(panel.queryByText("Not saved yet")).toBeNull();
  });
});

function card(revision: number): ReviewCard {
  return {
    public_id: "f-ring",
    place: { lon: pageFixture().location.lon, lat: pageFixture().location.lat, grid_ref: "SU 1025 6996" },
    shape_revision: revision,
    view_state: { layer: "slope", zoom: 16.5, bearing: 12, pitch: 0, sun_azimuth: 200, sun_altitude: 30 },
  };
}

function serveQueue(cards: ReviewCard[], me: Me | null): ApiRoutes {
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : signedOutResponse()),
    "GET /review/next": () => json({ items: cards, next_cursor: null }),
  });
}

async function openQueue() {
  renderShell("/review");
  await mapReady();
  return within(screen.getByRole("complementary", { name: "Second look" }));
}

describe("a kept answer in the queue", () => {
  it("is not offered, and is removed, when the card shows another shape, which is shown as it is now", async () => {
    const user = userEvent.setup();
    keptAnswer(2);
    serveQueue([card(5)], null);
    const panel = await openQueue();
    expect(await panel.findByRole("group", { name: "Can you see it?" })).toBeInTheDocument();
    expect(await screen.findByText(SHAPE_CHANGED_WORDS)).toBeInTheDocument();
    await waitFor(() => expect(answerDraftsFor("f-ring")).toHaveLength(0));
    expect(panel.queryByText("Not saved yet")).toBeNull();

    // Answered now, the answer names the shape the card shows.
    await user.click(panel.getByRole("button", { name: "I can see it" }));
    await waitFor(() => expect(keptRevisions()).toEqual([5]));
  });

  it("is passed over as it was when the card shows the shape it was given on", async () => {
    keptAnswer(5);
    serveQueue([card(5)], null);
    const panel = await openQueue();
    expect(await panel.findByText("Nothing waiting just now")).toBeInTheDocument();
    expect(screen.queryByText(SHAPE_CHANGED_WORDS)).toBeNull();
    expect(keptRevisions()).toEqual([5]);
  });

  it("counts a draft kept before answers named a revision as given on revision 0", async () => {
    keptAnswer(undefined);
    serveQueue([card(0)], null);
    const panel = await openQueue();
    expect(await panel.findByText("Nothing waiting just now")).toBeInTheDocument();
    expect(answerDraftsFor("f-ring")).toHaveLength(1);
  });
});
