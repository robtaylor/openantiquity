import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../../api/client.js";
import { useMapStore } from "../../map/store.js";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import {
  commentFixture,
  EXPERT,
  evidenceFixture,
  FINDER,
  FINDER_ACTIONS,
  finderView,
  heldFixture,
  MODERATOR_ACTIONS,
  OTHER,
  observationFixture,
  pageFixture,
  revealFixture,
  SQUARE_ACTIONS,
  seenFixture,
  squareFixture,
  suggestionFixture,
  suggestionsFixture,
} from "../../test/fixtures/findingPage.js";
import { meFixture } from "../../test/fixtures/me.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import {
  json,
  mapReady,
  metaResponse,
  renderShell,
  setUpShellTests,
  signedOutResponse,
} from "../../test/shellHarness.js";
import type { Me } from "../account/api.js";
import { useAccountUi } from "../account/requireAccount.js";
import { DRAFTS_STORAGE_KEY, resetDraftsForTests } from "../drafts/store.js";
import { useSelectedFinding } from "../findings/selection.js";
import { useSavedDrafts } from "../mark/findingDrafts.js";
import { useSavedAnswers } from "./secondLook/answerDrafts.js";
import type { FindingDetail, Observation } from "./types.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

const MEMBER = meFixture({ handle: "KeenLynchet7", display_name: "Mary Anning" });
const THE_FINDER = meFixture({ handle: FINDER.handle, display_name: FINDER.display_name });

beforeEach(() => {
  useSelectedFinding.getState().clear();
  useSavedAnswers.getState().clear();
  useAccountUi.setState({ sheet: null, waiting: [] });
  localStorage.clear();
  resetDraftsForTests();
});

/** The finding's page served for `finding`, with an empty discussion and no suggestions, as `me`. */
function serve(finding: FindingDetail, me: Me | null = MEMBER): ApiRoutes {
  const path = `/findings/${finding.public_id}`;
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : signedOutResponse()),
    [`GET ${path}`]: () => json(finding),
    [`GET ${path}/comments`]: () => json({ items: [], next_cursor: null }),
    [`GET ${path}/suggested-records`]: () => json(suggestionsFixture([])),
    [`GET ${path}/observations`]: () => json({ items: [observationFixture()], next_cursor: null }),
  });
}

async function open(finding: FindingDetail, me: Me | null = MEMBER, routes = serve(finding, me)) {
  renderShell(`/f/${finding.public_id}`);
  await mapReady();
  const panel = await screen.findByRole("complementary", { name: finding.title });
  return { panel: within(panel), routes };
}

describe("a finding's head", () => {
  it("shows the step, the meter, who found it and when, what it is and where, and marks it on the map", async () => {
    const { panel } = await open(seenFixture());
    const badges = document.querySelector(".fc-finding__badges") as HTMLElement;
    expect(within(badges).getByText("Seen by others")).toBeInTheDocument();
    expect(panel.getByRole("meter", { name: "Confidence" })).toHaveAttribute("aria-valuenow", "36");
    // Each step of the ladder is named, not numbered, with this one's marked.
    const ladder = panel.getByRole("list", { name: "The ladder" });
    expect(
      within(ladder)
        .getAllByRole("listitem")
        .map((step) => step.textContent),
    ).toEqual(["Spotted", "Seen by others", "Corroborated", "Probable", "Checked on the ground", "On record"]);
    expect(within(ladder).getByText("Seen by others")).toHaveAttribute("aria-current", "step");
    expect(panel.queryByText("30")).toBeNull();
    expect(panel.getByText(/Spotted by/)).toHaveTextContent("Spotted by Ada Lovelace on 1 November 2026");
    expect(panel.getByText("Round barrow or mound")).toBeInTheDocument();
    expect(panel.getByText("SU 1025 6996")).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "See it as the finder did" })).toBeInTheDocument();
    expect(useSelectedFinding.getState().selected).toMatchObject({ publicId: "f-ring", square: null });
  });

  it("names the nearest place, from the position this viewer is shown", async () => {
    const finding = seenFixture();
    const routes = serve(finding);
    routes.on("GET /geo/point", () =>
      json({
        grid_ref: "SU 1025 6996",
        nation: "england",
        elevation: 160,
        place: { name: "Avebury", kind: "village", distance_m: 640, source: null },
      }),
    );
    const { panel } = await open(finding, MEMBER, routes);
    expect(await panel.findByText("Avebury, 640 m away")).toBeInTheDocument();
    const [call] = routes.callsTo("GET /geo/point");
    expect(call?.url.searchParams.get("lon")).toBe(String(finding.location.lon));
  });

  it("names the place near a square without a distance, which would look more exact than the square", async () => {
    const finding = squareFixture();
    const routes = serve(finding, null);
    routes.on("GET /geo/point", () =>
      json({
        grid_ref: "SU 10 69",
        nation: "england",
        elevation: 160,
        place: { name: "Avebury", kind: "village", distance_m: 640, source: null },
      }),
    );
    const { panel } = await open(finding, null, routes);
    expect(await panel.findByText("Avebury")).toBeInTheDocument();
    expect(panel.queryByText(/m away/)).toBeNull();
  });

  it("restores the finder's view: layer, light and zoom", async () => {
    const user = userEvent.setup();
    const { panel } = await open(
      pageFixture({ view_state: { layer: "slope", zoom: 17.5, sun_azimuth: 90, sun_altitude: 30 } }),
    );
    await user.click(panel.getByRole("button", { name: "See it as the finder did" }));
    const state = useMapStore.getState();
    expect(state.mainView).toBe("slope");
    expect(state.sun).toEqual({ azimuth: 90, altitude: 30 });
    expect(state.camera.zoom).toBe(17.5);
  });

  it("shows a signed-out visitor a protected finding's square, says why, and offers sign-in", async () => {
    const { panel } = await open(squareFixture(), null);
    expect(panel.getByText("SU 10 69")).toBeInTheDocument();
    expect(panel.getByText(/not the place itself/)).toHaveTextContent(/Sign in to see it\./);
    expect(panel.queryByRole("button", { name: "See it as the finder did" })).toBeNull();
    expect(panel.queryByRole("group", { name: "Can you see it?" })).toBeNull();
    expect(useSelectedFinding.getState().selected?.square).not.toBeNull();
    await userEvent.setup().click(panel.getByRole("button", { name: "Sign in" }));
    expect(useAccountUi.getState().sheet).toBe("signin");
  });

  it("tells a member shown a restricted finding's square who can see it, without offering sign-in", async () => {
    const { panel } = await open(squareFixture({ sensitivity: "restricted", actions: SQUARE_ACTIONS }));
    expect(panel.getByText(/not the place itself/)).toHaveTextContent(/trusted members, archaeologists and moderators/);
    expect(panel.queryByRole("button", { name: "Sign in" })).toBeNull();
    expect(panel.getByText("Only people who can see the exact place can help with these.")).toBeInTheDocument();
  });

  it.each([
    ["known", null, /Matches a known record/, /existing heritage record/],
    ["disputed", null, /Disputed/, /disagree/],
    ["ruled_out", "natural", /Explained/, /most likely a natural feature/],
    ["withdrawn", null, /Withdrawn/, /took it back/],
  ])("says why a %s finding isn't open", async (state, reason, label, why) => {
    const base = pageFixture();
    const finding = pageFixture({ assessment: { ...base.assessment, state: state as "open", state_reason: reason } });
    const { panel } = await open(finding);
    const block = panel.getByText(why).closest(".fc-finding__state") as HTMLElement;
    expect(within(block).getByText(label)).toBeInTheDocument();
  });
});

describe("what would move it up", () => {
  it("renders the server's steps with a button that opens the right form", async () => {
    const user = userEvent.setup();
    const { panel } = await open(seenFixture());
    expect(panel.getByText("To reach Corroborated:")).toBeInTheDocument();
    expect(panel.getByText(/It needs two more kinds of evidence/)).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "Add old map" }));
    expect(await panel.findByRole("form", { name: "Add old map" })).toBeInTheDocument();
    expect(panel.getByLabelText("Which map")).toBeInTheDocument();
  });

  it("offers the finder a link to share where others' eyes are needed", async () => {
    const { panel } = await open(finderView(), THE_FINDER);
    expect(panel.getByText("Two more people need to say they can see it.")).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Copy a link to ask others" })).toBeInTheDocument();
    expect(panel.queryByRole("group", { name: "Can you see it?" })).toBeNull();
    expect(panel.getByRole("heading", { name: "Your finding" })).toBeInTheDocument();
  });

  it("says when a finding is on record and nothing more is needed", async () => {
    const base = pageFixture();
    const { panel } = await open(
      pageFixture({
        assessment: { ...base.assessment, tier: "confirmed", next_tier: null, next_steps: [], score: 100 },
      }),
    );
    expect(panel.getByText("It's on record. Nothing more is needed.")).toBeInTheDocument();
  });
});

describe("a second look on the page", () => {
  /** The server holds an answer given alone for its detail, and reveals with the detail, as it does. */
  function twoSteps(routes: ApiRoutes, finding: FindingDetail, after: FindingDetail = finding) {
    routes.on("PUT /findings/f-ring/observation", (call) => {
      const body = call.body as { visible: Observation["visible"] };
      return json({
        revealed: false,
        observation: observationFixture({ user: OTHER, visible: body.visible, feature_class: null, revealed: false }),
      });
    });
    routes.on("POST /findings/f-ring/observation/reveal", (call) => {
      const detail = call.body as Partial<Observation>;
      const answered = observationFixture({ user: OTHER, feature_class: null, ...detail });
      return json(
        revealFixture(answered, finding, {
          finding: { ...after, answers_visible: true, my_observation: answered },
          tier_after: after.tier,
          moved_up: after.tier !== finding.tier,
        }),
      );
    });
  }

  it("shows nothing of other people's answers before this person answers, and asks for none", async () => {
    const { panel, routes } = await open(pageFixture({ answers_visible: false }));
    expect(panel.getByRole("group", { name: "Can you see it?" })).toBeInTheDocument();
    expect(panel.queryByRole("heading", { name: "Second looks" })).toBeNull();
    expect(panel.queryByText(/other people can see it/)).toBeNull();
    expect(routes.callsTo("GET /findings/f-ring/observations")).toHaveLength(0);
    // Detail is offered after the answer, never before.
    expect(panel.queryByText("What do you think it is?")).toBeNull();
    expect(panel.getByText(/counts as soon as you give it/)).toBeInTheDocument();
  });

  it("sends the answer alone with one press, then offers the detail, which goes with the reveal", async () => {
    const user = userEvent.setup();
    const finding = pageFixture();
    const { panel, routes } = await open(finding);
    twoSteps(routes, finding, seenFixture());

    await user.click(panel.getByRole("button", { name: "I can see it" }));
    await waitFor(() => expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(1));
    expect(routes.callsTo("PUT /findings/f-ring/observation")[0]?.body).toEqual({
      visible: "yes",
      detail_follows: true,
    });
    // The answer is in. Nothing is revealed, and the detail is offered now, not before.
    expect(await panel.findByText(/Your answer is in, and it counts\./)).toHaveTextContent("You can see it.");
    expect(panel.queryByRole("group", { name: "Can you see it?" })).toBeNull();
    expect(panel.queryByText(/other people can see it/)).toBeNull();
    expect(panel.queryByText(/The finder marked it as/)).toBeNull();
    expect(routes.callsTo("GET /findings/f-ring/observations")).toHaveLength(0);
    expect(document.activeElement).toHaveTextContent(/Your answer is in/);

    // The class question starts with nothing chosen, so nothing in it reads like the answer "Not sure".
    const kind = panel.getByRole("radiogroup", { name: "What do you think it is?" });
    expect(within(kind).queryByRole("radio", { checked: true })).toBeNull();
    expect(within(kind).getByRole("radio", { name: "Don't know" })).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "See how it compares" })).toBeEnabled();
    await user.click(panel.getByRole("radio", { name: "Round barrow or mound" }));
    const modern = panel.getByRole("radiogroup", { name: "Could it be modern?" });
    await user.click(within(modern).getByRole("radio", { name: "No" }));
    await user.click(panel.getByRole("button", { name: "Add this and see how it compares" }));

    await waitFor(() => expect(routes.callsTo("POST /findings/f-ring/observation/reveal")).toHaveLength(1));
    expect(routes.callsTo("POST /findings/f-ring/observation/reveal")[0]?.body).toEqual({
      feature_class: "round_barrow",
      not_modern: true,
    });
    expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(1);
    expect(await panel.findByText(/2 other people can see it and 1 isn't sure\./)).toBeInTheDocument();
    expect(panel.getByText(/The finder marked it as: Round barrow or mound\. So did you\./)).toBeInTheDocument();
    expect(panel.getByText(/Your answer helped\. It has moved up to Seen by others\./)).toBeInTheDocument();
    // The answer is final: only its note can change now.
    expect(panel.queryByRole("group", { name: "Can you see it?" })).toBeNull();
    expect(panel.getByLabelText("Your note")).toBeInTheDocument();
    expect(await panel.findByRole("heading", { name: "Second looks" })).toBeInTheDocument();
  });

  it("reveals with no detail when none is given", async () => {
    const user = userEvent.setup();
    const finding = pageFixture();
    const { panel, routes } = await open(finding);
    twoSteps(routes, finding);
    await user.click(panel.getByRole("button", { name: "I can't see it" }));
    await user.click(await panel.findByRole("button", { name: "See how it compares" }));
    await waitFor(() => expect(routes.callsTo("POST /findings/f-ring/observation/reveal")).toHaveLength(1));
    expect(routes.callsTo("POST /findings/f-ring/observation/reveal")[0]?.body).toEqual({});
    expect(await panel.findByText(/2 other people can see it/)).toBeInTheDocument();
  });

  it("offers the detail again to someone who left between the steps, and nothing revealed meanwhile", async () => {
    const user = userEvent.setup();
    const finding = heldFixture("unsure", { answers_visible: false });
    const { panel, routes } = await open(finding);
    twoSteps(routes, finding);
    expect(panel.getByText(/Your answer is in/)).toHaveTextContent("You weren't sure.");
    expect(panel.queryByRole("group", { name: "Can you see it?" })).toBeNull();
    expect(panel.getByRole("radiogroup", { name: "What do you think it is?" })).toBeInTheDocument();
    expect(routes.callsTo("GET /findings/f-ring/observations")).toHaveLength(0);
    await user.click(panel.getByRole("button", { name: "See how it compares" }));
    expect(await panel.findByText(/2 other people can see it/)).toBeInTheDocument();
    expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(0);
  });

  it("takes the answer back, with a toast, when it can't be sent", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(pageFixture());
    routes.on("PUT /findings/f-ring/observation", () => apiError(503, "busy", "The server is busy."));
    await user.click(panel.getByRole("button", { name: "Not sure" }));
    expect(await screen.findByText(/Your answer couldn't be sent\. The server is busy\./)).toBeInTheDocument();
    expect(await panel.findByRole("group", { name: "Can you see it?" })).toBeInTheDocument();
    expect(panel.queryByText(/Your answer is in/)).toBeNull();
  });

  it("keeps a signed-out person's answer, and then its detail, as a draft, and asks them to sign in", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(pageFixture(), null);
    await user.click(panel.getByRole("button", { name: "Not sure" }));
    const draftOf = () => JSON.parse(localStorage.getItem(DRAFTS_STORAGE_KEY) ?? "{}").drafts?.[0];
    expect(draftOf()).toMatchObject({
      kind: "observation",
      data: { public_id: "f-ring", answer: { visible: "unsure" }, reveal: false },
    });
    // The detail is offered at once, signed out too, and nothing asks for sign-in until they want the comparison.
    expect(useAccountUi.getState().sheet).toBeNull();
    expect(await panel.findByText("Not saved yet")).toBeInTheDocument();
    const natural = panel.getByRole("radiogroup", { name: "Could it be natural?" });
    await user.click(within(natural).getByRole("radio", { name: "No" }));
    await user.click(panel.getByRole("button", { name: "Sign in to see how it compares" }));
    await waitFor(() => expect(useAccountUi.getState().sheet).toBe("signin"));
    expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(0);
    expect(draftOf()).toMatchObject({
      data: { public_id: "f-ring", answer: { visible: "unsure", not_natural: true }, reveal: true },
    });
    act(() => useAccountUi.getState().close());
    expect(await panel.findByText("Not saved yet")).toBeInTheDocument();
  });

  it("never shows an answer saved before the page opened, which may be someone else's, over what the server sends", async () => {
    const theirs = observationFixture({ user: { ...MEMBER, avatar_url: null } });
    act(() => useSavedAnswers.getState().record("f-ring", { kind: "revealed", reveal: revealFixture(theirs) }));
    const { panel, routes } = await open(squareFixture(), null);
    expect(panel.queryByRole("region", { name: "Your second look" })).toBeNull();
    expect(panel.getByText("SU 10 69")).toBeInTheDocument();
    expect(panel.queryByText("SU 1025 6996")).toBeNull();
    expect(useSavedAnswers.getState().saved).toEqual({});
    expect(routes.callsTo("GET /findings/f-ring").length).toBeGreaterThan(0);
  });

  it("forgets the exact place and anything saved for the person when they are signed out", async () => {
    const { routes } = await open(pageFixture());
    // The page as the next viewer sees it hasn't arrived: nothing of the last one's may stay meanwhile.
    routes.on("GET /findings/f-ring", () => new Promise<Response>(() => undefined));
    expect(useSelectedFinding.getState().selected).toMatchObject({ publicId: "f-ring", square: null });
    act(() => {
      useSavedAnswers.getState().record("f-ring", { kind: "revealed", reveal: revealFixture(observationFixture()) });
      useSavedDrafts.getState().record("draft-1", pageFixture());
    });
    harness.fetchMock().mockImplementationOnce(async () => signedOutResponse());
    await act(async () => {
      await apiFetch("/findings", { method: "POST", body: {} }).catch(() => undefined);
    });
    expect(useSelectedFinding.getState().selected).toBeNull();
    expect(useSavedAnswers.getState().saved).toEqual({});
    expect(useSavedDrafts.getState().saved).toEqual({});
    expect(await screen.findByText("Loading the finding")).toBeInTheDocument();
  });

  it("reveals an answer saved from a draft while the page is open, and asks for the finding again", async () => {
    const finding = pageFixture();
    const { panel, routes } = await open(finding);
    const answered = observationFixture({ user: { ...MEMBER, avatar_url: null } });
    const before = routes.callsTo("GET /findings/f-ring").length;
    routes.on("GET /findings/f-ring", () => json(pageFixture({ answers_visible: true, my_observation: answered })));
    act(() =>
      useSavedAnswers.getState().record("f-ring", { kind: "revealed", reveal: revealFixture(answered, finding) }),
    );
    expect(await panel.findByText(/2 other people can see it and 1 isn't sure\./)).toBeInTheDocument();
    await waitFor(() => expect(routes.callsTo("GET /findings/f-ring").length).toBeGreaterThan(before));
    expect(await panel.findByLabelText("Your note")).toBeInTheDocument();
    expect(useSavedAnswers.getState().saved).toEqual({});
  });

  it("offers the detail for an answer saved from a draft before its reveal was asked for", async () => {
    const finding = pageFixture();
    const { panel, routes } = await open(finding);
    routes.on("GET /findings/f-ring", () => json(heldFixture("no")));
    const held = observationFixture({ user: OTHER, visible: "no", revealed: false });
    act(() => useSavedAnswers.getState().record("f-ring", { kind: "held", observation: held }));
    expect(await panel.findByText(/Your answer is in/)).toHaveTextContent("You can't see it.");
    expect(panel.queryByText(/other people/)).toBeNull();
  });

  it("lets an answer's note change, and offers taking it back", async () => {
    const user = userEvent.setup();
    const given = observationFixture({ user: { ...MEMBER, avatar_url: null }, note: "faint" });
    const finding = pageFixture({ answers_visible: true, my_observation: given });
    const { panel, routes } = await open(finding);
    routes.on("PUT /findings/f-ring/observation", () =>
      json(revealFixture({ ...given, note: "clearer in slope" }, finding, {})),
    );
    const note = panel.getByLabelText("Your note");
    await user.clear(note);
    await user.type(note, "clearer in slope");
    await user.click(panel.getByRole("button", { name: "Save note" }));
    await waitFor(() => expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(1));
    expect(routes.callsTo("PUT /findings/f-ring/observation")[0]?.body).toEqual({
      visible: "yes",
      feature_class: "round_barrow",
      note: "clearer in slope",
    });
    await user.click(panel.getByRole("button", { name: "Take my answer back" }));
    expect(screen.getByRole("dialog", { name: "Take your answer back?" })).toBeInTheDocument();
  });
});

describe("evidence", () => {
  it("groups evidence by kind with its stance, who added it, its votes and verification", async () => {
    const finding = seenFixture({
      evidence: [
        evidenceFixture({ id: 1 }),
        evidenceFixture({
          id: 2,
          kind: "designation",
          title: "Bowl barrow",
          reference: "1008391",
          url: null,
          contributor: EXPERT,
        }),
      ],
    });
    const { panel } = await open(finding);
    const map = panel.getByRole("heading", { name: /Old map/ }).parentElement as HTMLElement;
    expect(within(map).getByText("OS 6-inch, Wiltshire sheet XXVIII, 1888")).toBeInTheDocument();
    expect(within(map).getByText("Supports it")).toBeInTheDocument();
    expect(within(map).getByText(/Added by Mary Anning/)).toBeInTheDocument();
    expect(within(map).getByText("Endorsed by 1 person.")).toBeInTheDocument();
    expect(panel.getByText(/A piece stops counting while more people dispute it than endorse it/)).toBeInTheDocument();
    const official = panel.getByRole("heading", { name: /Designation/ }).parentElement as HTMLElement;
    expect(within(official).getByText(/Not verified yet/)).toBeInTheDocument();
  });

  it("says why there are no votes on your own evidence, and on evidence about your own finding", async () => {
    // Mary Anning added this one.
    const own = evidenceFixture({
      id: 1,
      contributor: OTHER,
      endorsements: 2,
      disputes: 1,
      actions: {
        vote: { allowed: false, reason: "vote_not_allowed" },
        verify: { allowed: false, reason: "verify_not_allowed" },
      },
    });
    const { panel } = await open(seenFixture({ evidence: [own] }));
    expect(panel.queryByRole("button", { name: "Endorse" })).toBeNull();
    expect(panel.getByText("Others endorse or dispute what you add.")).toBeInTheDocument();
    expect(panel.getByText("Endorsed by 2 people and disputed by 1.")).toBeInTheDocument();
  });

  it("puts an endorsement back, with a toast, when the server refuses it", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(seenFixture({ evidence: [evidenceFixture({ id: 1, contributor: EXPERT })] }));
    let answer: (response: Response) => void = () => {};
    routes.on(
      "PUT /evidence/1/vote",
      () =>
        new Promise<Response>((resolve) => {
          answer = resolve;
        }),
    );
    const endorse = panel.getByRole("button", { name: "Endorse" });
    await user.click(endorse);
    // The vote shows at once. The total is weighted by who voted, so it stays as the server said until it says again.
    await waitFor(() => expect(panel.getByRole("button", { name: "Endorse" })).toHaveAttribute("aria-pressed", "true"));
    expect(panel.getByText("Endorsed by 1 person.")).toBeInTheDocument();
    act(() => answer(apiError(409, "finding_withdrawn", "This finding was withdrawn.")));
    await waitFor(() =>
      expect(panel.getByRole("button", { name: "Endorse" })).toHaveAttribute("aria-pressed", "false"),
    );
    expect(panel.getByText("Endorsed by 1 person.")).toBeInTheDocument();
    expect(await screen.findByText(/Your vote couldn't be saved\. This finding was withdrawn\./)).toBeInTheDocument();
  });

  it("reminds people of the rules before a site visit is logged, and sends only what that kind needs", async () => {
    const user = userEvent.setup();
    const finding = seenFixture();
    const { panel, routes } = await open(finding);
    routes.on("POST /findings/f-ring/evidence", () =>
      json(
        seenFixture({
          evidence: [evidenceFixture({ id: 9, kind: "field_visit", occurred_on: "2026-11-08", outcome: "supports" })],
        }),
        201,
      ),
    );
    await user.click(panel.getByRole("button", { name: "Add evidence" }));
    // Each kind is explained in words on the page, not in a tooltip that touch and keyboards never see.
    const visit = panel.getByRole("button", { name: "Site visit" });
    expect(visit).toHaveAccessibleDescription(/Notes from someone who has been to look/);
    expect(panel.getByText(/Notes from someone who has been to look/)).toBeVisible();
    await user.click(visit);
    const form = within(await panel.findByRole("form", { name: "Add site visit" }));
    expect(form.getByRole("note")).toHaveTextContent(/landowner's permission/);
    await user.type(form.getByLabelText("When"), "2026-11-08");
    await user.click(form.getByRole("radio", { name: "Found it" }));
    await user.type(form.getByLabelText("Who did it (optional)"), "Avebury Field Club");
    await user.click(form.getByRole("button", { name: "Add it" }));
    await waitFor(() => expect(routes.callsTo("POST /findings/f-ring/evidence")).toHaveLength(1));
    expect(routes.callsTo("POST /findings/f-ring/evidence")[0]?.body).toEqual({
      kind: "field_visit",
      stance: "supports",
      occurred_on: "2026-11-08",
      outcome: "supports",
      organisation: "Avebury Field Club",
    });
    expect(await panel.findByRole("heading", { name: /Site visit/ })).toBeInTheDocument();
  });

  it("uploads a ground photo, then adds it as evidence, and says it waits for approval", async () => {
    const user = userEvent.setup();
    const finding = seenFixture();
    const { panel, routes } = await open(finding);
    routes.on("POST /media", () =>
      json(
        {
          id: 77,
          url: "/api/v1/media/77",
          content_type: "image/jpeg",
          bytes: 2048,
          width: 800,
          height: 600,
          approved: false,
          rejected: false,
          hidden: false,
          created_at: "2026-11-11T10:00:00Z",
        },
        201,
      ),
    );
    routes.on("POST /findings/f-ring/evidence", () =>
      json(
        seenFixture({ evidence: [evidenceFixture({ id: 9, kind: "photo", title: null, url: null, media_id: 77 })] }),
        201,
      ),
    );
    await user.click(panel.getByRole("button", { name: "Add evidence" }));
    await user.click(panel.getByRole("button", { name: "Ground photo" }));
    const form = within(await panel.findByRole("form", { name: "Add ground photo" }));
    await user.click(form.getByRole("button", { name: "Add it" }));
    expect(form.getByText("Choose the photo first.")).toBeInTheDocument();
    expect(routes.callsTo("POST /media")).toHaveLength(0);

    const tooBig = new File([new Uint8Array(16 * 1024 * 1024)], "huge.jpg", { type: "image/jpeg" });
    await user.upload(form.getByLabelText("The photo"), tooBig);
    expect(form.getByText(/over 15 MB/)).toBeInTheDocument();
    expect(form.queryByText("Chosen: huge.jpg")).toBeNull();

    const photo = new File([new Uint8Array(2048)], "barrow.jpg", { type: "image/jpeg" });
    await user.upload(form.getByLabelText("The photo"), photo);
    await user.type(form.getByLabelText("Note (optional)"), "From the east bank.");
    await user.click(form.getByRole("button", { name: "Add it" }));
    await waitFor(() => expect(routes.callsTo("POST /findings/f-ring/evidence")).toHaveLength(1));
    const [upload] = harness.fetchMock().mock.calls.filter(([input]) => String(input).endsWith("/api/v1/media"));
    expect(upload?.[1]).toMatchObject({ method: "POST", body: photo });
    expect(new Headers(upload?.[1]?.headers).get("Content-Type")).toBe("image/jpeg");
    expect(routes.callsTo("POST /findings/f-ring/evidence")[0]?.body).toEqual({
      kind: "photo",
      stance: "supports",
      note: "From the east bank.",
      media_id: 77,
    });
    const item = await panel.findByRole("img", { name: /Ground photo added by/ });
    expect(item).toHaveAttribute("src", "/api/v1/media/77");
  });

  it("opens the form again as it was, with the server's reason, when evidence is refused", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(seenFixture());
    routes.on("POST /findings/f-ring/evidence", () =>
      apiError(422, "invalid_evidence", "Say which map, book or paper it is."),
    );
    await user.click(panel.getByRole("button", { name: "Add old map" }));
    await user.type(await panel.findByLabelText("Which map"), "OS 1888");
    await user.click(panel.getByRole("button", { name: "Add it" }));
    expect(await screen.findByText(/Your evidence couldn't be added\./)).toBeInTheDocument();
    expect(await panel.findByLabelText("Which map")).toHaveValue("OS 1888");
    expect(panel.getByRole("alert")).toHaveTextContent("Say which map, book or paper it is.");
  });

  it("links a suggested heritage record, with how it relates", async () => {
    const user = userEvent.setup();
    const finding = seenFixture();
    const routes = serve(finding);
    routes.on("GET /findings/f-ring/suggested-records", () => json(suggestionsFixture([suggestionFixture()])));
    routes.on("POST /findings/f-ring/evidence", () => json(finding, 201));
    const { panel } = await open(finding, MEMBER, routes);
    const card = within(await panel.findByRole("region", { name: "Is it one of these?" }));
    expect(card.getByText(/Scheduled monuments · .* · 48 m away/)).toBeInTheDocument();
    await user.click(card.getByRole("button", { name: /Link Bowl barrow/ }));
    const form = within(await panel.findByRole("form", { name: "Link a heritage record" }));
    expect(form.getByRole("button", { name: /Bowl barrow 600m north/ })).toHaveAttribute("aria-pressed", "true");
    await user.click(form.getByRole("radio", { name: "The same thing" }));
    await user.click(form.getByRole("button", { name: "Link it" }));
    await waitFor(() => expect(routes.callsTo("POST /findings/f-ring/evidence")).toHaveLength(1));
    expect(routes.callsTo("POST /findings/f-ring/evidence")[0]?.body).toEqual({
      kind: "record_link",
      stance: "supports",
      relation: "same_as",
      record_id: 501,
    });
  });

  it("links a record from a source that is only linked by its identifier and address alone", async () => {
    const user = userEvent.setup();
    const finding = seenFixture();
    const routes = serve(finding);
    const linkOnly = { ...metaFixture.sources[0], key: "her-wilts", name: "Wiltshire HER", access: "link" };
    routes.on("GET /meta", () => metaResponse({ ...metaFixture, sources: [...metaFixture.sources, linkOnly] }));
    routes.on("POST /findings/f-ring/evidence", () => json(finding, 201));
    const { panel } = await open(finding, MEMBER, routes);
    await user.click(panel.getByRole("button", { name: "Add heritage record" }));
    const form = within(await panel.findByRole("form", { name: "Link a heritage record" }));
    await user.click(form.getByRole("button", { name: "It's a record from somewhere else" }));
    // Only the sources whose records may only be linked are offered, from /meta.
    const where = form.getByLabelText("Where it's from (optional)");
    expect(
      within(where)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Not listed", "Wiltshire HER"]);
    await user.selectOptions(where, "her-wilts");
    await user.type(form.getByLabelText("Record identifier"), "MWI4567");
    await user.type(form.getByLabelText("Link to the record"), "https://her.example.org/MWI4567");
    await user.click(form.getByRole("radio", { name: "Related" }));
    await user.click(form.getByRole("button", { name: "Link it" }));
    await waitFor(() => expect(routes.callsTo("POST /findings/f-ring/evidence")).toHaveLength(1));
    expect(routes.callsTo("POST /findings/f-ring/evidence")[0]?.body).toEqual({
      kind: "record_link",
      stance: "supports",
      relation: "related",
      reference: "MWI4567",
      url: "https://her.example.org/MWI4567",
      source_key: "her-wilts",
    });
  });
});

describe("discussion", () => {
  it("shows a comment at once and takes it back, with a toast, when posting fails", async () => {
    const user = userEvent.setup();
    const finding = pageFixture();
    const routes = serve(finding);
    routes.on("GET /findings/f-ring/comments", () => json({ items: [commentFixture()], next_cursor: null }));
    let answer: (response: Response) => void = () => {};
    routes.on(
      "POST /findings/f-ring/comments",
      () =>
        new Promise<Response>((resolve) => {
          answer = resolve;
        }),
    );
    const { panel } = await open(finding, MEMBER, routes);
    expect(await panel.findByText(/parch mark/)).toBeInTheDocument();
    await user.type(panel.getByLabelText("Add a comment"), "I can see it in slope too.");
    await user.click(panel.getByRole("button", { name: "Post" }));
    expect(panel.getByText("I can see it in slope too.")).toBeInTheDocument();
    expect(panel.getByText("Posting…")).toBeInTheDocument();
    act(() => answer(apiError(429, "rate_limited", "Slow down a little.")));
    await waitFor(() => expect(panel.queryByText("I can see it in slope too.", { selector: "p" })).toBeNull());
    expect(await screen.findByText(/Your comment couldn't be posted\. Slow down a little\./)).toBeInTheDocument();
    expect(panel.getByLabelText("Add a comment")).toHaveValue("I can see it in slope too.");
  });

  it("tells the author of a comment a moderator hid that only they and moderators still see it", async () => {
    const finding = pageFixture();
    const routes = serve(finding);
    const mine = { handle: MEMBER.handle, display_name: MEMBER.display_name, role: "member" };
    routes.on("GET /findings/f-ring/comments", () =>
      json({
        items: [
          commentFixture({ id: 1, author: mine, body: "Mine, hidden.", hidden: true }),
          commentFixture({ id: 2, author: null, body: null, deleted: true }),
        ],
        next_cursor: null,
      }),
    );
    const { panel } = await open(finding, MEMBER, routes);
    expect(await panel.findByText("Mine, hidden.")).toBeInTheDocument();
    expect(panel.getByText(/A moderator hid this comment/)).toBeInTheDocument();
    expect(panel.getByText("This comment was removed.")).toBeInTheDocument();
  });

  it("follows at once and puts it back, with a toast, when the server refuses", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(pageFixture({ following: false }));
    routes.on("PUT /findings/f-ring/follow", () => apiError(500, "x", "The database isn't answering."));
    await user.click(panel.getByRole("button", { name: "Follow" }));
    expect(await screen.findByText(/That didn't work\. The database isn't answering\./)).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Follow" })).toHaveAttribute("aria-pressed", "false");
  });

  it("asks a signed-out reader to sign in when they act", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(pageFixture(), null);
    await user.click(panel.getByRole("button", { name: "Follow" }));
    expect(useAccountUi.getState().sheet).toBe("signin");
    expect(routes.callsTo("PUT /findings/f-ring/follow")).toHaveLength(0);
  });
});

describe("states of the page", () => {
  it("says a missing finding isn't there, and offers Explore", async () => {
    routeApi(harness.fetchMock(), {
      "GET /findings/gone": () => apiError(404, "finding_not_found", "No such finding."),
    });
    renderShell("/f/gone");
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Finding not found" }));
    expect(panel.getByRole("link", { name: "Back to Explore" })).toBeInTheDocument();
  });

  it("says a failed load failed, and tries again", async () => {
    const user = userEvent.setup();
    let fail = true;
    const finding = pageFixture();
    const routes = serve(finding);
    routes.on("GET /findings/f-ring", () => (fail ? apiError(400, "x", "Something broke.") : json(finding)));
    renderShell("/f/f-ring");
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Finding" }));
    expect(await panel.findByText("This finding couldn't be loaded")).toBeInTheDocument();
    fail = false;
    await user.click(panel.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("complementary", { name: finding.title })).toBeInTheDocument();
  });

  it("gives the finder their own controls", async () => {
    const user = userEvent.setup();
    const { panel } = await open(finderView(), THE_FINDER);
    expect(panel.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Withdraw" })).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "Protect it more" }));
    const dialog = within(screen.getByRole("dialog", { name: "Protect this finding" }));
    expect(dialog.getByText(/Only people who have signed in see its exact place/)).toBeInTheDocument();
    expect(dialog.getByText("Only a moderator can lower it again.")).toBeInTheDocument();
  });

  it("offers each control the server allows, and none it doesn't, whoever is looking", async () => {
    // A finder of a withdrawn finding may still edit it, and nothing else: the server says so, not their role.
    const withdrawnActions = {
      ...FINDER_ACTIONS,
      withdraw: { allowed: false, reason: "finding_withdrawn" },
      raise_level: { allowed: false, reason: "finding_withdrawn" },
    };
    const { panel } = await open(finderView({ actions: withdrawnActions }), THE_FINDER);
    expect(panel.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(panel.queryByRole("button", { name: "Withdraw" })).toBeNull();
    expect(panel.queryByRole("button", { name: "Protect it more" })).toBeNull();
  });

  it("lets a moderator lower the level through the moderation route, with a reason for the log", async () => {
    const user = userEvent.setup();
    const finding = pageFixture({ sensitivity: "restricted", actions: MODERATOR_ACTIONS });
    const moderator = meFixture({ handle: "Keeper", role: "moderator" });
    const routes = serve(finding, moderator);
    routes.on("PUT /mod/findings/f-ring/sensitivity", () => json({ ...finding, sensitivity: "protected" }));
    const { panel } = await open(finding, moderator, routes);
    expect(panel.getByRole("heading", { name: "Protecting it" })).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "Lower its protection" }));
    const dialog = within(screen.getByRole("dialog", { name: "Lower its protection" }));
    await user.click(dialog.getByRole("button", { name: "Lower it" }));
    expect(dialog.getByText("Say why, for the moderation log.")).toBeInTheDocument();
    await user.type(dialog.getByLabelText("Why"), "Ordinary field bank, no risk");
    await user.click(dialog.getByRole("button", { name: "Lower it" }));
    await waitFor(() => expect(routes.callsTo("PUT /mod/findings/f-ring/sensitivity")).toHaveLength(1));
    expect(routes.callsTo("PUT /mod/findings/f-ring/sensitivity")[0]?.body).toEqual({
      level: "protected",
      reason: "Ordinary field bank, no risk",
    });
  });

  it("says beside the field when the server refuses a title or note that says where the finding is", async () => {
    const user = userEvent.setup();
    const finding = finderView({ sensitivity: "protected" });
    const routes = serve(finding, THE_FINDER);
    routes.on("PATCH /findings/f-ring", () =>
      json(
        {
          error: {
            code: "position_in_text",
            message: "A protected or restricted finding's title and description can't say where it is.",
            details: [
              { field: "body.description", message: "The description gives a position finer than the 1 km square." },
            ],
          },
        },
        422,
      ),
    );
    const { panel } = await open(finding, THE_FINDER, routes);
    await user.click(panel.getByRole("button", { name: "Edit" }));
    const dialog = within(screen.getByRole("dialog", { name: "Edit your finding" }));
    const note = dialog.getByLabelText("Note (optional)");
    await user.clear(note);
    await user.type(note, "Clearest at SU 1025 6996");
    await user.click(dialog.getByRole("button", { name: "Save changes" }));
    expect(
      await dialog.findByText(/Take the grid reference, coordinates or three-word address out of the note\./),
    ).toBeInTheDocument();
    expect(note).toHaveAttribute("aria-invalid", "true");
    expect(dialog.getByLabelText("Title")).not.toHaveAttribute("aria-invalid");
    await user.type(note, "!");
    expect(note).not.toHaveAttribute("aria-invalid");
  });

  it("shows a position the server hid in free text just as it sends it", async () => {
    const hidden = "[position hidden]";
    const finding = squareFixture({ description: `Bank and ditch at ${hidden}, clearest in slope.` });
    const { panel } = await open(finding, null);
    expect(panel.getByText(`Bank and ditch at ${hidden}, clearest in slope.`)).toBeInTheDocument();
  });

  it("offers everyone a link and the downloads", async () => {
    const { panel } = await open(pageFixture(), null);
    expect(panel.getByRole("link", { name: "GeoJSON" })).toHaveAttribute(
      "href",
      "/api/v1/findings/f-ring/export?format=geojson",
    );
    expect(panel.getByRole("link", { name: "Spreadsheet (CSV)" })).toHaveAttribute(
      "href",
      "/api/v1/findings/f-ring/export?format=csv",
    );
    expect(panel.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  });
});
