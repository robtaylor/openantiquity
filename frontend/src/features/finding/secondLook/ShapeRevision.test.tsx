import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useHiddenFindings } from "../../../map/hiddenFindings.js";
import { type ApiRoutes, apiError, routeApi } from "../../../test/apiRoutes.js";
import { observationFixture, pageFixture, suggestionsFixture } from "../../../test/fixtures/findingPage.js";
import { meFixture } from "../../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../../test/shellHarness.js";
import { useAccountUi } from "../../account/requireAccount.js";
import { resetDraftsForTests } from "../../drafts/store.js";
import { useSelectedFinding } from "../../findings/selection.js";
import { useReviewStore } from "../../review/reviewStore.js";
import type { ReviewCard } from "../../review/types.js";
import type { FindingDetail } from "../types.js";
import { answerDraftsFor, parseAnswerDraft, useSavedAnswers } from "./answerDrafts.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();
const MEMBER = meFixture({ handle: "KeenLynchet7", display_name: "Mary Anning" });

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

function servePage(finding: FindingDetail, me = MEMBER): ApiRoutes {
  const path = `/findings/${finding.public_id}`;
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : signedOutResponse()),
    [`GET ${path}`]: () => json(finding),
    [`GET ${path}/comments`]: () => json({ items: [], next_cursor: null }),
    [`GET ${path}/suggested-records`]: () => json(suggestionsFixture([])),
    [`GET ${path}/observations`]: () => json({ items: [], next_cursor: null }),
  });
}

const SHAPE_CHANGED = "The finder changed this finding's shape after you opened it.";

describe("a second look on the finding's page", () => {
  it("names the shape revision it was given on", async () => {
    const user = userEvent.setup();
    const routes = servePage(line(3));
    routes.on("PUT /findings/f-ring/observation", () =>
      json({ revealed: false, observation: observationFixture({ user: MEMBER, revealed: false }) }),
    );
    renderShell("/f/f-ring");
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: line(3).title }));
    await user.click(await panel.findByRole("button", { name: "I can see it" }));
    await waitFor(() => expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(1));
    expect(routes.callsTo("PUT /findings/f-ring/observation")[0]?.body).toEqual({
      visible: "yes",
      detail_follows: true,
      shape_revision: 3,
    });
  });

  it("shows the finding as it now is when its shape changed meanwhile, says so, and keeps nothing of the answer", async () => {
    const user = userEvent.setup();
    const routes = servePage(line(3));
    routes.on("PUT /findings/f-ring/observation", () => apiError(409, "shape_changed", SHAPE_CHANGED));
    renderShell("/f/f-ring");
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: line(3).title }));
    const before = routes.callsTo("GET /findings/f-ring").length;
    routes.on("GET /findings/f-ring", () => json(line(4)));
    await user.click(await panel.findByRole("button", { name: "I can see it" }));
    expect(
      await panel.findByText(
        "The finder changed its shape while you were looking, so your answer wasn't counted. Have a look at it as it is now.",
      ),
    ).toBeInTheDocument();
    await waitFor(() => expect(routes.callsTo("GET /findings/f-ring").length).toBeGreaterThan(before));
    // The answer buttons are back, unpressed, and nothing of the answer was kept or offered for detail.
    expect(panel.getByRole("button", { name: "I can see it" })).not.toHaveAttribute("aria-pressed", "true");
    expect(panel.queryByText(/Your answer is in/)).toBeNull();
    expect(answerDraftsFor("f-ring")).toHaveLength(0);

    routes.on("PUT /findings/f-ring/observation", () =>
      json({ revealed: false, observation: observationFixture({ user: MEMBER, revealed: false }) }),
    );
    await user.click(panel.getByRole("button", { name: "I can see it" }));
    await waitFor(() => expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(2));
    const second = routes.callsTo("PUT /findings/f-ring/observation")[1]?.body as { shape_revision?: number };
    expect(second?.shape_revision).toBe(4);
  });

  it("keeps the revision in a signed-out answer's draft and sends it after sign-in", () => {
    expect(
      parseAnswerDraft({ public_id: "f-ring", answer: { visible: "yes" }, reveal: false, shape_revision: 3 }),
    ).toMatchObject({ shape_revision: 3 });
    expect(parseAnswerDraft({ public_id: "f-ring", answer: { visible: "yes" }, reveal: false })).toMatchObject({
      shape_revision: null,
    });
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

describe("a second look in the queue", () => {
  it("sends the revision the card was shown with, and on a change shows the card again as it now is", async () => {
    const user = userEvent.setup();
    let cards = [card(2)];
    const routes = routeApi(harness.fetchMock(), {
      "GET /auth/me": () => json(MEMBER),
      "GET /review/next": () => json({ items: cards, next_cursor: null }),
      "PUT /findings/f-ring/observation": () => apiError(409, "shape_changed", SHAPE_CHANGED),
    });
    renderShell("/review");
    await mapReady();
    const panel = within(screen.getByRole("complementary", { name: "Second look" }));
    cards = [card(5)];
    await user.click(await panel.findByRole("button", { name: "I can see it" }));
    await waitFor(() => expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(1));
    expect(routes.callsTo("PUT /findings/f-ring/observation")[0]?.body).toMatchObject({ shape_revision: 2 });
    expect(
      await screen.findByText(
        "The finder changed its shape while you were looking, so your answer wasn't counted. Have a look at it as it is now.",
      ),
    ).toBeInTheDocument();
    await waitFor(() => expect(useReviewStore.getState().current?.shape_revision).toBe(5));
    expect(useReviewStore.getState()).toMatchObject({ sending: null, held: null, answer: null });
    expect(panel.queryByText(/Your answer is in/)).toBeNull();

    routes.on("PUT /findings/f-ring/observation", () =>
      json({ revealed: false, observation: observationFixture({ user: MEMBER, revealed: false }) }),
    );
    await user.click(await panel.findByRole("button", { name: "I can see it" }));
    await waitFor(() => expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(2));
    expect(routes.callsTo("PUT /findings/f-ring/observation")[1]?.body).toMatchObject({ shape_revision: 5 });
  });
});
