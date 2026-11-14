import { type QueryClient, useQueryClient } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FINDING_SHAPE_LAYERS } from "../../map/overlayLayers.js";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import {
  EXPERT,
  FINDER,
  FINDER_ACTIONS,
  finderView,
  lineFixture,
  MODERATOR_ACTIONS,
  OTHER,
  pageFixture,
  SIGNED_OUT_ACTIONS,
  shapeSuggestionFixture,
  suggestionsFixture,
} from "../../test/fixtures/findingPage.js";
import { meFixture } from "../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import type { Me } from "../account/api.js";
import { activityKeys } from "../activity/keys.js";
import { useSelectedFinding } from "../findings/selection.js";
import { useMarkStore } from "../mark/markStore.js";
import { SUGGESTION_LAYERS, SUGGESTION_SOURCE } from "./SuggestedChanges.js";
import type { FindingDetail } from "./types.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

const MEMBER = meFixture({ handle: OTHER.handle, display_name: OTHER.display_name });
const THE_FINDER = meFixture({ handle: FINDER.handle, display_name: FINDER.display_name });

beforeEach(() => {
  localStorage.clear();
  useSelectedFinding.getState().clear();
  useMarkStore.getState().start();
});

function Address() {
  const location = useLocation();
  return <output data-testid="address">{location.pathname}</output>;
}

function address(): string {
  return screen.getByTestId("address").textContent ?? "";
}

function serve(finding: FindingDetail, me: Me | null = MEMBER): ApiRoutes {
  const path = `/findings/${finding.public_id}`;
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : signedOutResponse()),
    [`GET ${path}`]: () => json(finding),
    [`GET ${path}/comments`]: () => json({ items: [], next_cursor: null }),
    [`GET ${path}/suggested-records`]: () => json(suggestionsFixture([])),
    [`GET ${path}/observations`]: () => json({ items: [], next_cursor: null }),
  });
}

async function openPage(finding: FindingDetail, me: Me | null = MEMBER, routes = serve(finding, me)) {
  renderShell(`/f/${finding.public_id}`, <Address />);
  await mapReady();
  const panel = within(await screen.findByRole("complementary", { name: finding.title }));
  return { panel, routes };
}

describe("the byline", () => {
  it("says who found it and when, and no keeper while the finder keeps it", async () => {
    const { panel } = await openPage(pageFixture());
    expect(panel.getByText(/Found by/)).toHaveTextContent("Found by Ada Lovelace on 1 November 2026");
    expect(panel.queryByText(/Kept by/)).toBeNull();
  });

  it("adds who keeps it once it has been handed on, and the finder is still named", async () => {
    const { panel } = await openPage(pageFixture({ keeper: OTHER }));
    expect(panel.getByText(/Found by/)).toHaveTextContent("Found by Ada Lovelace on 1 November 2026");
    expect(panel.getByText(/Kept by/)).toHaveTextContent("Kept by Mary Anning");
    expect(panel.getByRole("link", { name: "Mary Anning" })).toHaveAttribute("href", `/u/${OTHER.handle}`);
  });
});

describe("the tool's address for someone who isn't the keeper", () => {
  async function openTool(finding: FindingDetail, me: Me | null) {
    serve(finding, me);
    renderShell(`/mark/finding/${finding.public_id}`, <Address />);
    await mapReady();
    return within(await screen.findByRole("complementary", { name: "Change the shape" }));
  }

  it("says only the keeper changes the shape, and offers a suggestion where the server allows one", async () => {
    const user = userEvent.setup();
    const panel = await openTool(pageFixture(), MEMBER);
    expect(await panel.findByText(/Only the keeper of a marking can change its shape/)).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "Suggest a change" }));
    await waitFor(() => expect(address()).toBe("/mark/suggest/f-ring"));
  });

  it("offers no suggestion where the server doesn't allow one", async () => {
    const panel = await openTool(pageFixture({ actions: SIGNED_OUT_ACTIONS }), null);
    expect(await panel.findByText(/Only the keeper of a marking can change its shape/)).toBeInTheDocument();
    expect(panel.queryByRole("button", { name: "Suggest a change" })).toBeNull();
  });

  it("still opens the tool for the keeper", async () => {
    const panel = await openTool(finderView({ actions: FINDER_ACTIONS }), THE_FINDER);
    expect(await panel.findByRole("button", { name: "Save the shape" })).toBeInTheDocument();
  });
});

const SUGGESTIONS_PATH = "/findings/f-ring/suggestions";

function keeperLine(suggestions = [shapeSuggestionFixture()], revision = 3): FindingDetail {
  return lineFixture({ actions: FINDER_ACTIONS }, { revision, suggestions });
}

function suggestionCard(panel: ReturnType<typeof within>, by = "Mary Anning") {
  const list = panel.getByRole("list", { name: "Suggested changes" });
  const card = within(list)
    .getAllByRole("listitem")
    .find((item) => item.textContent?.includes(by));
  if (!card) throw new Error(`No suggestion by ${by}`);
  return within(card);
}

describe("suggested changes, for the keeper", () => {
  it("lists each with who, when and what it does, with Accept and Decline", async () => {
    const { panel } = await openPage(keeperLine(), THE_FINDER);
    expect(panel.getByRole("heading", { name: "Suggested changes" })).toBeInTheDocument();
    const card = suggestionCard(panel);
    expect(card.getByText(/Mary Anning/)).toBeInTheDocument();
    expect(card.getByText(/10 November 2026/)).toBeInTheDocument();
    expect(card.getByText("Draws it further. It would be 355 m long.")).toBeInTheDocument();
    expect(card.queryByText(/earlier shape/)).toBeNull();
    expect(card.getByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(card.getByRole("button", { name: "Decline" })).toBeInTheDocument();
    expect(card.queryByRole("button", { name: "Withdraw it" })).toBeNull();
  });

  it("accepts one on the revision the keeper sees, and shows the shape it made", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openPage(keeperLine(), THE_FINDER);
    const changed = lineFixture({ actions: FINDER_ACTIONS }, { revision: 4 });
    changed.location.shape.changes = [
      { kind: "drawn", on: "2026-11-01" },
      { kind: "extended", on: "2026-11-14", added_length_m: 150, suggested_by: OTHER },
    ];
    routes.on(`POST ${SUGGESTIONS_PATH}/71/accept`, () => json(changed));
    routes.on("GET /findings/f-ring", () => json(changed));
    await user.click(suggestionCard(panel).getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(routes.callsTo(`POST ${SUGGESTIONS_PATH}/71/accept`)).toHaveLength(1));
    expect(routes.callsTo(`POST ${SUGGESTIONS_PATH}/71/accept`)[0]?.body).toEqual({ shape_revision: 3 });
    expect(await screen.findByText(/The suggested change is accepted/)).toBeInTheDocument();
    await waitFor(() => expect(panel.queryByRole("heading", { name: "Suggested changes" })).toBeNull());
    // The timeline names who suggested it.
    expect(panel.getByText("Suggested by Mary Anning")).toBeInTheDocument();
  });

  it("says beside the suggestion why an accept was refused, in the server's words, and keeps it", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openPage(keeperLine(), THE_FINDER);
    routes.on(`POST ${SUGGESTIONS_PATH}/71/accept`, () =>
      apiError(
        422,
        "looked_at_moved",
        "This change keeps 40% of the ground others gave second looks on within 25 m. It has to keep 80%.",
      ),
    );
    await user.click(suggestionCard(panel).getByRole("button", { name: "Accept" }));
    expect(await suggestionCard(panel).findByRole("alert")).toHaveTextContent(
      "This change keeps 40% of the ground others gave second looks on within 25 m. It has to keep 80%.",
    );
    expect(suggestionCard(panel).getByRole("button", { name: "Accept" })).toBeInTheDocument();
  });

  it("asks first before accepting one made on an earlier shape, saying it replaces the changes since", async () => {
    const user = userEvent.setup();
    const behind = shapeSuggestionFixture({ behind: true, base_revision: 2 });
    const { panel, routes } = await openPage(keeperLine([behind]), THE_FINDER);
    routes.on(`POST ${SUGGESTIONS_PATH}/71/accept`, () =>
      json(lineFixture({ actions: FINDER_ACTIONS }, { revision: 4 })),
    );
    const card = suggestionCard(panel);
    expect(card.getByText(/Made on an earlier shape/)).toBeInTheDocument();
    await user.click(card.getByRole("button", { name: "Accept" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Accept a suggestion made on an earlier shape?" }));
    expect(dialog.getByText(/replaces the changes made to the shape since/)).toBeInTheDocument();
    expect(routes.callsTo(`POST ${SUGGESTIONS_PATH}/71/accept`)).toHaveLength(0);
    await user.click(dialog.getByRole("button", { name: "Accept it" }));
    await waitFor(() => expect(routes.callsTo(`POST ${SUGGESTIONS_PATH}/71/accept`)).toHaveLength(1));
  });

  it("declines one and asks for the page again", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openPage(keeperLine(), THE_FINDER);
    routes.on(`POST ${SUGGESTIONS_PATH}/71/decline`, () => json({ ...shapeSuggestionFixture(), state: "declined" }));
    routes.on("GET /findings/f-ring", () => json(keeperLine([])));
    await user.click(suggestionCard(panel).getByRole("button", { name: "Decline" }));
    await waitFor(() => expect(routes.callsTo(`POST ${SUGGESTIONS_PATH}/71/decline`)).toHaveLength(1));
    expect(await screen.findByText("The suggestion is declined.")).toBeInTheDocument();
    await waitFor(() => expect(panel.queryByRole("heading", { name: "Suggested changes" })).toBeNull());
  });

  it("shows one on the map, dashed beneath the shape, and takes it off again", async () => {
    const user = userEvent.setup();
    renderShell("/f/f-ring", <Address />);
    serve(keeperLine(), THE_FINDER);
    const map = await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Ring ditch by the long barrow" }));
    const show = suggestionCard(panel).getByRole("button", { name: "Show on the map" });
    await user.click(show);
    expect(show).toHaveAttribute("aria-pressed", "true");
    const data = map.sourceData(SUGGESTION_SOURCE) as { features: Array<{ geometry: unknown }> };
    expect(data.features).toHaveLength(1);
    expect(data.features[0]?.geometry).toEqual(shapeSuggestionFixture().outline);
    expect(map.getLayer(SUGGESTION_LAYERS.line)).toBeDefined();
    // Under the finding's own line and wider than it, so both show along their whole length.
    const order = map.getStyle().layers.map((layer) => layer.id);
    const own = order.indexOf(FINDING_SHAPE_LAYERS.lines);
    expect(own).toBeGreaterThan(-1);
    for (const id of Object.values(SUGGESTION_LAYERS)) expect(order.indexOf(id)).toBeLessThan(own);
    const width = (id: string) => map.getStyle().layers.find((layer) => layer.id === id)?.paint?.["line-width"];
    expect(width(SUGGESTION_LAYERS.line)).toBeGreaterThanOrEqual(8);
    await user.click(show);
    expect(show).toHaveAttribute("aria-pressed", "false");
    expect((map.sourceData(SUGGESTION_SOURCE) as { features: unknown[] }).features).toHaveLength(0);
  });
});

describe("suggesting from the finding's page", () => {
  it("offers a suggestion to someone the server lets suggest, and opens the tool for it", async () => {
    const user = userEvent.setup();
    const { panel } = await openPage(lineFixture(), MEMBER);
    await user.click(panel.getByRole("button", { name: "Suggest a change" }));
    await waitFor(() => expect(address()).toBe("/mark/suggest/f-ring"));
  });

  it("doesn't offer one to the keeper, who changes the shape", async () => {
    const { panel } = await openPage(keeperLine([]), THE_FINDER);
    expect(panel.getByRole("button", { name: "Change the shape" })).toBeInTheDocument();
    expect(panel.queryByRole("button", { name: "Suggest a change" })).toBeNull();
  });
});

describe("refusals the keeper meets", () => {
  it("says beside a suggestion that the shape changed while they looked, and shows it as it now is", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openPage(keeperLine(), THE_FINDER);
    routes.on(`POST ${SUGGESTIONS_PATH}/71/accept`, () =>
      apiError(
        409,
        "shape_changed",
        "The shape was changed somewhere else. Reload the finding and make your change again.",
      ),
    );
    const fetched = routes.callsTo("GET /findings/f-ring").length;
    routes.on("GET /findings/f-ring", () => json(keeperLine([shapeSuggestionFixture({ behind: true })], 4)));
    await user.click(suggestionCard(panel).getByRole("button", { name: "Accept" }));
    expect(await suggestionCard(panel).findByRole("alert")).toHaveTextContent(
      /The shape was changed while you were looking/,
    );
    await waitFor(() => expect(routes.callsTo("GET /findings/f-ring").length).toBeGreaterThan(fetched));
    expect(await suggestionCard(panel).findByText(/Made on an earlier shape/)).toBeInTheDocument();
  });

  it("says in the server's words when the person offered keeps it already", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openPage(finderView({ keeper: OTHER, actions: FINDER_ACTIONS }), THE_FINDER);
    routes.on(`PUT ${OFFER_PATH}`, () => apiError(422, "already_keeper", "They keep this marking already."));
    await user.click(panel.getByRole("button", { name: "Hand it on" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Hand it on" }));
    await user.type(dialog.getByLabelText("Their handle"), OTHER.handle);
    await user.click(dialog.getByRole("button", { name: "Offer it" }));
    expect(await dialog.findByRole("alert")).toHaveTextContent("They keep this marking already.");
  });
});

describe("suggested changes, for others", () => {
  it("lists them with no Accept or Decline, and lets the suggester withdraw their own", async () => {
    const user = userEvent.setup();
    const mine = shapeSuggestionFixture();
    const theirs = shapeSuggestionFixture({ id: 72, by: EXPERT, kind: "reshaped", length_m: 230 });
    const { panel, routes } = await openPage(lineFixture({}, { suggestions: [theirs, mine] }), MEMBER);
    routes.on(`DELETE ${SUGGESTIONS_PATH}/71`, () => new Response(null, { status: 204 }));
    routes.on("GET /findings/f-ring", () => json(lineFixture({}, { suggestions: [theirs] })));
    expect(panel.queryByRole("button", { name: "Accept" })).toBeNull();
    expect(panel.queryByRole("button", { name: "Decline" })).toBeNull();
    expect(suggestionCard(panel, "Dr Ditch").queryByRole("button", { name: "Withdraw it" })).toBeNull();
    await user.click(suggestionCard(panel).getByRole("button", { name: "Withdraw it" }));
    await waitFor(() => expect(routes.callsTo(`DELETE ${SUGGESTIONS_PATH}/71`)).toHaveLength(1));
    expect(await screen.findByText("Your suggestion is withdrawn.")).toBeInTheDocument();
  });

  it("shows nothing of them when the server sends none, as to a signed-out reader", async () => {
    const { panel } = await openPage(lineFixture({ actions: SIGNED_OUT_ACTIONS }), null);
    expect(panel.queryByRole("heading", { name: "Suggested changes" })).toBeNull();
    expect(panel.queryByRole("button", { name: "Suggest a change" })).toBeNull();
  });
});

const OFFER_PATH = "/findings/f-ring/keeping/offer";
const OFFERED = { offered_to: OTHER, offered_at: "2026-11-12T08:00:00Z" };

describe("handing a marking on", () => {
  it("offers it by handle from the keeper's tools, and shows the offer until it is taken back", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openPage(finderView(), THE_FINDER);
    routes.on(`PUT ${OFFER_PATH}`, () => json(finderView({ keeping: OFFERED })));
    routes.on(`DELETE ${OFFER_PATH}`, () => new Response(null, { status: 204 }));
    await user.click(panel.getByRole("button", { name: "Hand it on" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Hand it on" }));
    await user.type(dialog.getByLabelText("Their handle"), "KeenLynchet7");
    await user.click(dialog.getByRole("button", { name: "Offer it" }));
    await waitFor(() => expect(routes.callsTo(`PUT ${OFFER_PATH}`)).toHaveLength(1));
    expect(routes.callsTo(`PUT ${OFFER_PATH}`)[0]?.body).toEqual({ handle: "KeenLynchet7" });
    expect(await panel.findByText(/Offered to/)).toHaveTextContent("Offered to Mary Anning on 12 November 2026");

    routes.on("GET /findings/f-ring", () => json(finderView()));
    await user.click(panel.getByRole("button", { name: "Take back the offer" }));
    await waitFor(() => expect(routes.callsTo(`DELETE ${OFFER_PATH}`)).toHaveLength(1));
    await waitFor(() => expect(panel.queryByText(/Offered to/)).toBeNull());
  });

  it("says one thing for every handle that can't be offered it, whatever the server's reason", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openPage(finderView(), THE_FINDER);
    const said: string[] = [];
    for (const message of ["Nobody has that handle.", "That account can't be offered anything."]) {
      routes.on(`PUT ${OFFER_PATH}`, () => apiError(404, "user_not_found", message));
      await user.click(panel.getByRole("button", { name: "Hand it on" }));
      const dialog = within(await screen.findByRole("dialog", { name: "Hand it on" }));
      await user.type(dialog.getByLabelText("Their handle"), "SomeoneElse");
      await user.click(dialog.getByRole("button", { name: "Offer it" }));
      said.push((await dialog.findByRole("alert")).textContent ?? "");
      expect(dialog.queryByText(message)).toBeNull();
      await user.click(dialog.getByRole("button", { name: "Cancel" }));
    }
    expect(said[0]).toBe(said[1]);
    expect(said[0]).toMatch(/can't be offered/);
  });

  it("asks the person offered, who takes it on", async () => {
    const user = userEvent.setup();
    const offered = pageFixture({
      keeping: OFFERED,
      actions: { ...pageFixture().actions, take_keeping: { allowed: true, reason: null } },
    });
    const { panel, routes } = await openPage(offered, MEMBER);
    routes.on("POST /findings/f-ring/keeping/accept", () =>
      json(
        pageFixture({
          keeper: OTHER,
          actions: { ...FINDER_ACTIONS, withdraw: { allowed: false, reason: "not_finder" } },
        }),
      ),
    );
    expect(panel.getByText(/You've been asked to keep this marking/)).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "Take it on" }));
    await waitFor(() => expect(routes.callsTo("POST /findings/f-ring/keeping/accept")).toHaveLength(1));
    expect(await screen.findByText(/You keep it now/)).toBeInTheDocument();
    await waitFor(() => expect(panel.getByText(/Kept by/)).toHaveTextContent("Kept by Mary Anning"));
    expect(panel.queryByRole("button", { name: "Take it on" })).toBeNull();
  });

  it("lets the person offered say no thanks", async () => {
    const user = userEvent.setup();
    const offered = pageFixture({
      keeping: OFFERED,
      actions: { ...pageFixture().actions, take_keeping: { allowed: true, reason: null } },
    });
    const { panel, routes } = await openPage(offered, MEMBER);
    routes.on(`DELETE ${OFFER_PATH}`, () => new Response(null, { status: 204 }));
    routes.on("GET /findings/f-ring", () => json(pageFixture()));
    await user.click(panel.getByRole("button", { name: "No thanks" }));
    await waitFor(() => expect(routes.callsTo(`DELETE ${OFFER_PATH}`)).toHaveLength(1));
    await waitFor(() => expect(panel.queryByRole("button", { name: "Take it on" })).toBeNull());
  });

  it("shows nothing of an offer, nor any keeping control, to someone the actions don't name", async () => {
    // A moderator is sent the offer, and may do nothing with it.
    const { panel } = await openPage(pageFixture({ keeping: OFFERED, actions: MODERATOR_ACTIONS }), MEMBER);
    expect(panel.queryByText(/Offered to/)).toBeNull();
    expect(panel.queryByText(/asked to keep/)).toBeNull();
    for (const name of ["Hand it on", "Take it on", "No thanks", "Offer it to someone", "Remove the marking"]) {
      expect(panel.queryByRole("button", { name })).toBeNull();
    }
  });
});

describe("focus when a control goes", () => {
  function panelTitle(): Element | null {
    return document.querySelector(".fc-panel__title");
  }

  it("moves to the next card's first control when a suggestion is declined by keyboard", async () => {
    const user = userEvent.setup();
    const first = shapeSuggestionFixture();
    const second = shapeSuggestionFixture({ id: 72, by: EXPERT, kind: "reshaped", length_m: 230 });
    const { panel, routes } = await openPage(keeperLine([first, second]), THE_FINDER);
    routes.on(`POST ${SUGGESTIONS_PATH}/71/decline`, () => json({ ...first, state: "declined" }));
    routes.on("GET /findings/f-ring", () => json(keeperLine([second])));
    suggestionCard(panel).getByRole("button", { name: "Decline" }).focus();
    await user.keyboard("{Enter}");
    await waitFor(() =>
      expect(suggestionCard(panel, "Dr Ditch").getByRole("button", { name: "Accept" })).toHaveFocus(),
    );
  });

  it("moves to the panel's title when the last suggestion is accepted by keyboard", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openPage(keeperLine(), THE_FINDER);
    routes.on(`POST ${SUGGESTIONS_PATH}/71/accept`, () => json(keeperLine([], 4)));
    suggestionCard(panel).getByRole("button", { name: "Accept" }).focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(panel.queryByRole("heading", { name: "Suggested changes" })).toBeNull());
    await waitFor(() => expect(panelTitle()).toHaveFocus());
  });

  it("moves to the panel's title when the suggester withdraws their only one by keyboard", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openPage(lineFixture({}, { suggestions: [shapeSuggestionFixture()] }), MEMBER);
    routes.on(`DELETE ${SUGGESTIONS_PATH}/71`, () => new Response(null, { status: 204 }));
    routes.on("GET /findings/f-ring", () => json(lineFixture()));
    suggestionCard(panel).getByRole("button", { name: "Withdraw it" }).focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(panelTitle()).toHaveFocus());
  });

  for (const answer of ["Take it on", "No thanks"] as const) {
    it(`moves to the panel's title after "${answer}" by keyboard`, async () => {
      const user = userEvent.setup();
      const offered = pageFixture({
        keeping: OFFERED,
        actions: { ...pageFixture().actions, take_keeping: { allowed: true, reason: null } },
      });
      const { panel, routes } = await openPage(offered, MEMBER);
      routes.on("POST /findings/f-ring/keeping/accept", () =>
        json(pageFixture({ keeper: OTHER, actions: FINDER_ACTIONS })),
      );
      routes.on(`DELETE ${OFFER_PATH}`, () => new Response(null, { status: 204 }));
      routes.on("GET /findings/f-ring", () => json(pageFixture()));
      panel.getByRole("button", { name: answer }).focus();
      await user.keyboard("{Enter}");
      await waitFor(() => expect(panel.queryByRole("button", { name: "Take it on" })).toBeNull());
      await waitFor(() => expect(panelTitle()).toHaveFocus());
    });
  }

  it('moves to "Hand it on" after "Take back the offer" by keyboard', async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openPage(finderView({ keeping: OFFERED }), THE_FINDER);
    routes.on(`DELETE ${OFFER_PATH}`, () => new Response(null, { status: 204 }));
    routes.on("GET /findings/f-ring", () => json(finderView()));
    panel.getByRole("button", { name: "Take back the offer" }).focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(panel.queryByText(/Offered to/)).toBeNull());
    await waitFor(() => expect(panel.getByRole("button", { name: "Hand it on" })).toHaveFocus());
  });
});

const FEED = activityKeys.feed(null, []);
const seeded: { client: QueryClient | null } = { client: null };

/** Puts a page of the feed in the cache, as having opened it would, and hands the test the client. */
function Seed() {
  const client = useQueryClient();
  seeded.client = client;
  if (!client.getQueryData(FEED)) client.setQueryData(FEED, { pages: [], pageParams: [] });
  return null;
}

describe("lists that change with keeping", () => {
  function feedInvalidated(): boolean {
    return seeded.client?.getQueryState(FEED)?.isInvalidated === true;
  }

  async function openSeeded(finding: FindingDetail, me: Me) {
    const routes = serve(finding, me);
    renderShell(`/f/${finding.public_id}`, <Seed />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: finding.title }));
    return { panel, routes };
  }

  it("asks for the activity feed again after an accept", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openSeeded(keeperLine(), THE_FINDER);
    routes.on(`POST ${SUGGESTIONS_PATH}/71/accept`, () => json(keeperLine([], 4)));
    expect(feedInvalidated()).toBe(false);
    await user.click(suggestionCard(panel).getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(feedInvalidated()).toBe(true));
  });

  it("asks for the activity feed again after a decline", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await openSeeded(keeperLine(), THE_FINDER);
    routes.on(`POST ${SUGGESTIONS_PATH}/71/decline`, () => json({ ...shapeSuggestionFixture(), state: "declined" }));
    await user.click(suggestionCard(panel).getByRole("button", { name: "Decline" }));
    await waitFor(() => expect(feedInvalidated()).toBe(true));
  });

  it("asks for the activity feed again once a marking is taken on", async () => {
    const user = userEvent.setup();
    const offered = pageFixture({
      keeping: OFFERED,
      actions: { ...pageFixture().actions, take_keeping: { allowed: true, reason: null } },
    });
    const { panel, routes } = await openSeeded(offered, MEMBER);
    routes.on("POST /findings/f-ring/keeping/accept", () =>
      json(pageFixture({ keeper: OTHER, actions: FINDER_ACTIONS })),
    );
    await user.click(panel.getByRole("button", { name: "Take it on" }));
    await waitFor(() => expect(feedInvalidated()).toBe(true));
  });
});
