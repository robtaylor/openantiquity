import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMapStore } from "../../map/store.js";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import {
  commentFixture,
  EXPERT,
  evidenceFixture,
  FINDER,
  finderView,
  observationFixture,
  pageFixture,
  revealFixture,
  seenFixture,
  squareFixture,
  suggestionFixture,
  suggestionsFixture,
} from "../../test/fixtures/findingPage.js";
import { meFixture } from "../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import type { Me } from "../account/api.js";
import { useAccountUi } from "../account/requireAccount.js";
import { DRAFTS_STORAGE_KEY } from "../drafts/store.js";
import { useSelectedFinding } from "../findings/selection.js";
import type { FindingDetail } from "./types.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

const MEMBER = meFixture({ handle: "KeenLynchet7", display_name: "Mary Anning" });
const THE_FINDER = meFixture({ handle: FINDER.handle, display_name: FINDER.display_name });

beforeEach(() => {
  useSelectedFinding.getState().clear();
  useAccountUi.setState({ sheet: null, waiting: [] });
  localStorage.clear();
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
    expect(panel.getByText("Seen by others")).toBeInTheDocument();
    expect(panel.getByRole("meter", { name: "Confidence" })).toHaveAttribute("aria-valuenow", "36");
    expect(panel.getByText(/Spotted by/)).toHaveTextContent("Spotted by Ada Lovelace on 1 November 2026");
    expect(panel.getByText("Round barrow or mound")).toBeInTheDocument();
    expect(panel.getByText("SU 1025 6996")).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "See it as the finder did" })).toBeInTheDocument();
    expect(useSelectedFinding.getState().selected).toMatchObject({ publicId: "f-ring", square: null });
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
    expect(panel.getByText("SU1069")).toBeInTheDocument();
    expect(panel.getByText(/not the place itself/)).toHaveTextContent(/Sign in to see it\./);
    expect(panel.queryByRole("button", { name: "See it as the finder did" })).toBeNull();
    expect(panel.queryByRole("group", { name: "Can you see it?" })).toBeNull();
    expect(useSelectedFinding.getState().selected?.square).not.toBeNull();
    await userEvent.setup().click(panel.getByRole("button", { name: "Sign in" }));
    expect(useAccountUi.getState().sheet).toBe("signin");
  });

  it("tells a member shown a restricted finding's square who can see it, without offering sign-in", async () => {
    const { panel } = await open(squareFixture({ sensitivity: "restricted" }));
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
  it("shows nothing of other people's answers before this person answers, and asks for none", async () => {
    const { panel, routes } = await open(pageFixture({ answers_visible: false }));
    expect(panel.getByRole("group", { name: "Can you see it?" })).toBeInTheDocument();
    expect(panel.queryByRole("heading", { name: "Second looks" })).toBeNull();
    expect(panel.queryByText(/other people can see it/)).toBeNull();
    expect(routes.callsTo("GET /findings/f-ring/observations")).toHaveLength(0);
    // Detail is offered after the answer, never before.
    expect(panel.queryByText("What do you think it is?")).toBeNull();
    expect(panel.getByText(/final once sent/)).toBeInTheDocument();
  });

  it("offers the detail after the answer, sends it all at once, and reveals how it compares and that it moved", async () => {
    const user = userEvent.setup();
    const finding = pageFixture();
    const { panel, routes } = await open(finding);
    const answered = observationFixture({
      user: { ...MEMBER, avatar_url: null },
      feature_class: "round_barrow",
      not_modern: true,
    });
    const moved = seenFixture({ answers_visible: true, my_observation: answered });
    routes.on("PUT /findings/f-ring/observation", () =>
      json(revealFixture(answered, finding, { finding: moved, tier_after: "seen", moved_up: true })),
    );

    await user.click(panel.getByRole("button", { name: "I can see it" }));
    expect(panel.getByRole("button", { name: "I can see it" })).toHaveAttribute("aria-pressed", "true");
    await user.click(panel.getByRole("radio", { name: "Round barrow or mound" }));
    const modern = panel.getByRole("radiogroup", { name: "Could it be modern?" });
    await user.click(within(modern).getByRole("radio", { name: "No" }));
    await user.click(panel.getByRole("button", { name: "Send: i can see it" }));

    await waitFor(() => expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(1));
    expect(routes.callsTo("PUT /findings/f-ring/observation")[0]?.body).toEqual({
      visible: "yes",
      feature_class: "round_barrow",
      not_modern: true,
    });
    expect(await panel.findByText(/2 other people can see it, 1 isn't sure and 0 can't\./)).toBeInTheDocument();
    expect(panel.getByText(/So do you\./)).toBeInTheDocument();
    expect(panel.getByText(/Your answer helped\. It has moved up to Seen by others\./)).toBeInTheDocument();
    expect(panel.getAllByText("Seen by others").length).toBeGreaterThan(0);
    // The answer is final: only its note can change now.
    expect(panel.queryByRole("group", { name: "Can you see it?" })).toBeNull();
    expect(panel.getByLabelText("Your note")).toBeInTheDocument();
    expect(await panel.findByRole("heading", { name: "Second looks" })).toBeInTheDocument();
  });

  it("keeps a signed-out person's answer as a draft and asks them to sign in", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(pageFixture(), null);
    await user.click(panel.getByRole("button", { name: "Not sure" }));
    await user.click(panel.getByRole("button", { name: "Send: not sure" }));
    await waitFor(() => expect(useAccountUi.getState().sheet).toBe("signin"));
    expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(0);
    const stored = JSON.parse(localStorage.getItem(DRAFTS_STORAGE_KEY) ?? "{}");
    expect(stored.drafts[0]).toMatchObject({
      kind: "observation",
      data: { public_id: "f-ring", answer: { visible: "unsure" } },
    });
    act(() => useAccountUi.getState().close());
    expect(await panel.findByText("Not saved yet")).toBeInTheDocument();
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
    expect(within(map).getByText("+1")).toBeInTheDocument();
    const official = panel.getByRole("heading", { name: /Designation/ }).parentElement as HTMLElement;
    expect(within(official).getByText(/Not verified yet/)).toBeInTheDocument();
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
    // Shown at once.
    await waitFor(() => expect(panel.getByRole("button", { name: "Endorse" })).toHaveAttribute("aria-pressed", "true"));
    expect(panel.getByText("+2")).toBeInTheDocument();
    act(() => answer(apiError(409, "finding_withdrawn", "This finding was withdrawn.")));
    await waitFor(() =>
      expect(panel.getByRole("button", { name: "Endorse" })).toHaveAttribute("aria-pressed", "false"),
    );
    expect(panel.getByText("+1")).toBeInTheDocument();
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
    await user.click(panel.getByRole("button", { name: "Site visit" }));
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
    routes.on("GET /sources", () => json([]));
    routes.on("POST /findings/f-ring/evidence", () => json(finding, 201));
    const { panel } = await open(finding, MEMBER, routes);
    await user.click(panel.getByRole("button", { name: "Add heritage record" }));
    const form = within(await panel.findByRole("form", { name: "Link a heritage record" }));
    await user.click(form.getByRole("button", { name: "It's a record from somewhere else" }));
    await user.type(form.getByLabelText("Record identifier"), "MWI4567");
    await user.type(form.getByLabelText("Record address"), "https://her.example.org/MWI4567");
    await user.click(form.getByRole("radio", { name: "Related" }));
    await user.click(form.getByRole("button", { name: "Link it" }));
    await waitFor(() => expect(routes.callsTo("POST /findings/f-ring/evidence")).toHaveLength(1));
    expect(routes.callsTo("POST /findings/f-ring/evidence")[0]?.body).toEqual({
      kind: "record_link",
      stance: "supports",
      relation: "related",
      reference: "MWI4567",
      url: "https://her.example.org/MWI4567",
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
