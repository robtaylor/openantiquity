import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../../test/apiRoutes.js";
import {
  EXPERT,
  evidenceFixture,
  OTHER,
  seenFixture,
  squareFixture,
  suggestionsFixture,
} from "../../../test/fixtures/findingPage.js";
import { meFixture } from "../../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../../test/shellHarness.js";
import type { Me } from "../../account/api.js";
import { useAccountUi } from "../../account/requireAccount.js";
import { resetDraftsForTests } from "../../drafts/store.js";
import type { FindingDetail } from "../types.js";
import type { ActivityEvent } from "./followUps.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

const MEMBER = meFixture({ handle: "BrightBank3", display_name: "Gertrude Bell" });

beforeEach(() => {
  useAccountUi.setState({ sheet: null, waiting: [] });
  localStorage.clear();
  resetDraftsForTests();
});

/** A dig in September that moved the finding up, a visit in June, and an old map that isn't a follow-up. */
function withFollowUps(overrides: Partial<FindingDetail> = {}): FindingDetail {
  return seenFixture({
    evidence: [
      evidenceFixture({ id: 1, kind: "historic_map" }),
      evidenceFixture({
        id: 2,
        kind: "excavation",
        title: "Trial trench across the ditch",
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
    ...overrides,
  });
}

const EVENTS: ActivityEvent[] = [
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
    details: { evidence_id: 2, evidence_kind: "excavation" },
  },
];

function serve(finding: FindingDetail, me: Me | null = MEMBER): ApiRoutes {
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : signedOutResponse()),
    "GET /findings/f-ring": () => json(finding),
    "GET /findings/f-ring/comments": () => json({ items: [], next_cursor: null }),
    "GET /findings/f-ring/suggested-records": () => json(suggestionsFixture([])),
    "GET /findings/f-ring/mentions": () => json({ items: [], next_cursor: null }),
    "GET /activity": () => json({ items: EVENTS, next_cursor: null }),
  });
}

async function open(routes: ApiRoutes, finding: FindingDetail) {
  void routes;
  renderShell(`/f/${finding.public_id}`);
  await mapReady();
  const panel = within(await screen.findByRole("complementary", { name: finding.title }));
  const section = within(await panel.findByRole("region", { name: "Timeline" }));
  return { panel, section };
}

describe("the follow-up timeline", () => {
  it("lists what happened on the ground in date order, with who, what it found, a link and the move it made", async () => {
    const finding = withFollowUps();
    const routes = serve(finding);
    const { section } = await open(routes, finding);
    const list = within(section.getByRole("list", { name: "What happened, oldest first" }));
    const [visit, dig, ...rest] = list.getAllByRole("listitem");
    expect(rest).toHaveLength(0);

    const theVisit = within(visit as HTMLElement);
    expect(theVisit.getByText("12 June 2026")).toBeVisible();
    expect(theVisit.getByText("Site visit")).toBeVisible();
    expect(theVisit.getByText(`Logged by ${OTHER.display_name}`)).toBeVisible();
    expect(theVisit.getByText("Couldn't tell")).toBeVisible();
    expect(theVisit.getByText("A low bank, just visible in the grass.")).toBeVisible();
    expect(theVisit.queryByRole("link")).toBeNull();

    const theDig = within(dig as HTMLElement);
    expect(theDig.getByText("1 September 2026")).toBeVisible();
    expect(theDig.getByText("Trial trench across the ditch")).toBeVisible();
    expect(theDig.getByText(`By Wessex Archaeology, logged by ${EXPERT.display_name}`)).toBeVisible();
    expect(theDig.getByText("Found it")).toBeVisible();
    // Named for its entry, so it stands apart in a list of the page's links.
    expect(
      theDig.getByRole("link", { name: "Open the link for Excavation, 1 September 2026 (opens in a new tab)" }),
    ).toHaveAttribute("href", "https://reports.example.org/trench");
    // The dig moved it up, and the label says so in words as well as colour.
    expect(await theDig.findByText(/It moved the finding up to/)).toHaveTextContent("Checked on the ground");
    expect(theVisit.queryByText(/It moved the finding up/)).toBeNull();

    // The moves come from the finding's own follow-ups and steps in the public feed.
    const [call] = routes.callsTo("GET /activity");
    expect(call?.url.searchParams.get("finding")).toBe("f-ring");
    expect(call?.url.searchParams.getAll("kind")).toEqual(["followup_logged", "tier_changed"]);
  });

  it("links nothing that isn't a web address", async () => {
    const finding = withFollowUps();
    const [first, dig, visit] = finding.evidence;
    if (!first || !dig || !visit) throw new Error("the fixture has three items");
    const unsafe = { ...finding, evidence: [first, { ...dig, url: "javascript:alert(1)" }, visit] };
    const { section } = await open(serve(unsafe), unsafe);
    expect(await section.findByText("Trial trench across the ditch")).toBeVisible();
    expect(section.queryByRole("link")).toBeNull();
  });

  it("says what goes there when nothing has happened yet, and asks the feed nothing", async () => {
    const finding = seenFixture({ evidence: [evidenceFixture({ id: 1, kind: "historic_map" })] });
    const routes = serve(finding);
    const { section } = await open(routes, finding);
    expect(
      section.getByText(/Nothing yet\. A site visit, a survey, a dig or a new heritage record goes here/),
    ).toBeVisible();
    expect(routes.callsTo("GET /activity")).toHaveLength(0);
  });

  it("still lists the entries when the moves couldn't be loaded, and tries again", async () => {
    const finding = withFollowUps();
    const routes = serve(finding);
    let fail = true;
    routes.on("GET /activity", () =>
      fail ? apiError(503, "unavailable", "The server is busy.") : json({ items: EVENTS, next_cursor: null }),
    );
    const { section } = await open(routes, finding);
    expect(await section.findByRole("alert")).toHaveTextContent(
      "Which of these moved it up the ladder couldn't be loaded. The server is busy.",
    );
    expect(section.getAllByRole("listitem")).toHaveLength(2);
    fail = false;
    await userEvent.setup().click(section.getByRole("button", { name: "Try again" }));
    expect(await section.findByText(/It moved the finding up to/)).toBeVisible();
  });

  it("adds an entry through the evidence form, which reminds people of the rules before a visit", async () => {
    const user = userEvent.setup();
    const finding = withFollowUps();
    const { panel, section } = await open(serve(finding), finding);
    await user.click(section.getByRole("button", { name: "Add to the timeline" }));
    // Only the kinds that are follow-ups, each explained beside it.
    const chooser = within(section.getByRole("heading", { name: "What happened?" }).parentElement as HTMLElement);
    expect(chooser.queryByRole("button", { name: "Old map" })).toBeNull();
    const visit = chooser.getByRole("button", { name: "Site visit" });
    expect(visit).toHaveAccessibleDescription(/Notes from someone who has been to look/);
    await user.click(visit);
    const form = within(await panel.findByRole("form", { name: "Add site visit" }));
    expect(form.getByRole("note")).toHaveTextContent(/landowner's permission/);
    expect(section.queryByRole("heading", { name: "What happened?" })).toBeNull();
    // Focus follows to the form that opened, in the evidence section.
    await waitFor(() => expect(panel.getByRole("heading", { name: "Add site visit" })).toHaveFocus());
  });

  it("keeps the person's place: focus goes into the chooser, and back to the button on Cancel or Escape", async () => {
    const user = userEvent.setup();
    const finding = withFollowUps();
    const { section } = await open(serve(finding), finding);
    await user.click(section.getByRole("button", { name: "Add to the timeline" }));
    expect(section.getByRole("heading", { name: "What happened?" })).toHaveFocus();
    await user.click(section.getByRole("button", { name: "Cancel" }));
    expect(section.getByRole("button", { name: "Add to the timeline" })).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(section.getByRole("heading", { name: "What happened?" })).toHaveFocus();
    await user.tab();
    await user.keyboard("{Escape}");
    expect(section.queryByRole("heading", { name: "What happened?" })).toBeNull();
    expect(section.getByRole("button", { name: "Add to the timeline" })).toHaveFocus();
  });

  it("isn't offered to add to for someone who sees only the square", async () => {
    const finding = squareFixture({ evidence: withFollowUps().evidence });
    const { section } = await open(serve(finding, null), finding);
    expect(section.getAllByRole("listitem")).toHaveLength(2);
    await waitFor(() => expect(section.queryByRole("button", { name: "Add to the timeline" })).toBeNull());
  });
});
