import { useQueryClient } from "@tanstack/react-query";
import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import {
  FINDER,
  FINDER_ACTIONS,
  OTHER,
  pageFixture,
  shapeSuggestionFixture,
  suggestionsFixture,
} from "../../test/fixtures/findingPage.js";
import { offset } from "../../test/fixtures/findings.js";
import { meFixture } from "../../test/fixtures/me.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { json, mapReady, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import type { Me } from "../account/api.js";
import { signedOut } from "../account/session.js";
import type { FindingDetail } from "../finding/types.js";
import { useSelectedFinding } from "../findings/selection.js";
import { LOOKED_AT_SOURCE } from "./ChangeShapePanel.js";
import { editingKey } from "./editingKey.js";
import { useMarkStore } from "./markStore.js";

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

function SignOutHere() {
  const client = useQueryClient();
  return (
    <button type="button" onClick={() => signedOut(client)}>
      Sign out for the test
    </button>
  );
}

function address(): string {
  return screen.getByTestId("address").textContent ?? "";
}

const POINTS = [offset(-100, 0), offset(0, 20), offset(100, 0)];
const LINE = { type: "LineString" as const, coordinates: POINTS.map(({ lon, lat }) => [lon, lat]) };

/** The finder's line of three points at shape revision 3, as a member who may suggest sees it. */
function lineFinding(overrides: Partial<FindingDetail> = {}): FindingDetail {
  const base = pageFixture();
  return {
    ...base,
    location: {
      ...base.location,
      outline: LINE,
      path: {
        closed: false,
        curve: "catmull-rom-centripetal-1",
        points: POINTS.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
      },
      shape: {
        kind: "line",
        length_m: 205,
        revision: 3,
        extent: [POINTS[0]?.lon ?? 0, POINTS[0]?.lat ?? 0, POINTS[2]?.lon ?? 0, POINTS[1]?.lat ?? 0],
        changes: [{ kind: "drawn", on: "2026-11-01" }],
        added_since_looked_m: null,
        // The server never sends a suggester this. Were it ever sent, the tool still wouldn't draw it.
        looked_at: LINE,
        suggestions: [],
      },
    },
    ...overrides,
  };
}

function serve(findings: FindingDetail[], me: Me = MEMBER): ApiRoutes {
  const routes: Record<string, () => Response> = { "GET /auth/me": () => json(me) };
  for (const finding of findings) {
    const path = `/findings/${finding.public_id}`;
    routes[`GET ${path}`] = () => json(finding);
    routes[`GET ${path}/comments`] = () => json({ items: [], next_cursor: null });
    routes[`GET ${path}/suggested-records`] = () => json(suggestionsFixture([]));
    routes[`GET ${path}/observations`] = () => json({ items: [], next_cursor: null });
  }
  return routeApi(harness.fetchMock(), routes);
}

function panelNamed(name: string) {
  return within(screen.getByRole("complementary", { name }));
}

function suggestPanel() {
  return panelNamed("Suggest a change");
}

function handles(): HTMLElement[] {
  return screen.queryAllByTestId("path-handle");
}

async function openSuggest(finding = lineFinding(), routes = serve([finding])) {
  renderShell(`/mark/suggest/${finding.public_id}`, <Address />);
  const map = await mapReady();
  await screen.findByRole("complementary", { name: "Suggest a change" });
  await waitFor(() => expect(handles()).toHaveLength(finding.location.path?.points.length ?? 1));
  return { map, routes };
}

/** Carry the line on from its east end by one tap, then stop adding. */
async function extend(user: ReturnType<typeof userEvent.setup>, map: Awaited<ReturnType<typeof mapReady>>) {
  await user.click(screen.getByRole("button", { name: /^Point 3 of 3/ }));
  await user.click(suggestPanel().getByRole("button", { name: "Continue from this end" }));
  act(() => map.click(600, 200));
  await user.click(suggestPanel().getByRole("button", { name: "Finish" }));
}

describe("suggesting a change", () => {
  it("opens the drawing tool on the shape, under its own key, and draws no ground second looks covered", async () => {
    const finding = lineFinding();
    const { map } = await openSuggest(finding);
    expect(useMarkStore.getState().editing).toBe(editingKey(finding, "suggest"));
    expect(useMarkStore.getState().editing).not.toBe(editingKey(finding));
    expect(map.getSource(LOOKED_AT_SOURCE)).toBeUndefined();
    expect(suggestPanel().queryByText(/second looks/)).toBeNull();
    expect(suggestPanel().getByText(/Its keeper sees it drawn over the shape as it is/)).toBeInTheDocument();
  });

  it("sends the whole path with the revision it began on, and goes back to the finding", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const { map, routes } = await openSuggest(finding);
    routes.on(`POST /findings/${finding.public_id}/suggestions`, () => json({}, 201));
    await extend(user, map);
    await user.click(suggestPanel().getByRole("button", { name: "Send the suggestion" }));
    await waitFor(() => expect(routes.callsTo(`POST /findings/${finding.public_id}/suggestions`)).toHaveLength(1));
    const body = routes.callsTo(`POST /findings/${finding.public_id}/suggestions`)[0]?.body as {
      path: { closed: boolean; points: unknown[] };
      path_revision: number;
    };
    expect(body.path_revision).toBe(3);
    expect(body.path.points).toHaveLength(4);
    // Nothing is sent to the finding itself: only its keeper changes it.
    expect(routes.callsTo(`PATCH /findings/${finding.public_id}`)).toHaveLength(0);
    await waitFor(() => expect(address()).toBe(`/f/${finding.public_id}`));
    expect(await screen.findByText(/Your suggestion is sent/)).toBeInTheDocument();
    expect(useMarkStore.getState().editing).toBeNull();
  });

  it("sends nothing until the shape has been changed", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const { routes } = await openSuggest(finding);
    await user.click(suggestPanel().getByRole("button", { name: "Send the suggestion" }));
    expect(await suggestPanel().findByText(/Change the shape first/)).toBeInTheDocument();
    expect(routes.callsTo(`POST /findings/${finding.public_id}/suggestions`)).toHaveLength(0);
  });

  it("says beside the path why the server refused the shape, and keeps the suggestion", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const { map, routes } = await openSuggest(finding);
    routes.on(`POST /findings/${finding.public_id}/suggestions`, () =>
      apiError(422, "line_too_long", "A line can be at most 20 km long."),
    );
    await extend(user, map);
    await user.click(suggestPanel().getByRole("button", { name: "Send the suggestion" }));
    expect(await screen.findByTestId("path-problem")).toHaveTextContent("A line can be at most 20 km long.");
    expect(address()).toBe(`/mark/suggest/${finding.public_id}`);
    expect(useMarkStore.getState().shape.present.points).toHaveLength(4);
  });

  it("throws the suggestion away on Cancel and goes back to the finding", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const { map } = await openSuggest(finding);
    await extend(user, map);
    await user.click(suggestPanel().getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(address()).toBe(`/f/${finding.public_id}`));
    expect(useMarkStore.getState().editing).toBeNull();
    expect(screen.queryByTestId("mark-path")).toBeNull();
  });

  it("tells the keeper they change it themselves, and offers that instead", async () => {
    const user = userEvent.setup();
    const finding = lineFinding({ actions: FINDER_ACTIONS });
    serve([finding], THE_FINDER);
    renderShell(`/mark/suggest/${finding.public_id}`, <Address />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Suggest a change" }));
    expect(await panel.findByText(/so you change its shape yourself/)).toBeInTheDocument();
    expect(handles()).toHaveLength(0);
    await user.click(panel.getByRole("button", { name: "Change the shape" }));
    await waitFor(() => expect(address()).toBe(`/mark/finding/${finding.public_id}`));
  });
});

/** The keeper's line as it is after they changed it while the suggestion was drawn: revision 4, bent north. */
function changedByKeeper(): FindingDetail {
  const moved = lineFinding();
  const north = offset(0, 60);
  const middle = moved.location.path?.points[1];
  if (middle) Object.assign(middle, { lon: north.lon, lat: north.lat });
  moved.location.shape.revision = 4;
  return moved;
}

describe("a suggestion the server refuses", () => {
  for (const [what, status, code, message] of [
    [
      "too many waiting",
      409,
      "too_many_suggestions",
      "This finding has 20 suggestions waiting for its keeper. Try again once some are answered.",
    ],
    ["the shape as it is", 422, "suggestion_unchanged", "The suggested shape is the shape the finding has now."],
    ["the hourly limit", 429, "rate_limited", "You're doing that too often. Try again shortly."],
  ] as const) {
    it(`says why for ${what}, in the server's words, and keeps the drawing`, async () => {
      const user = userEvent.setup();
      const finding = lineFinding();
      const { map, routes } = await openSuggest(finding);
      routes.on(`POST /findings/${finding.public_id}/suggestions`, () => apiError(status, code, message));
      await extend(user, map);
      await user.click(suggestPanel().getByRole("button", { name: "Send the suggestion" }));
      expect(await screen.findByText(`The suggestion couldn't be sent. ${message}`)).toBeInTheDocument();
      expect(address()).toBe(`/mark/suggest/${finding.public_id}`);
      expect(useMarkStore.getState().shape.present.points).toHaveLength(4);
      expect(suggestPanel().getByRole("button", { name: "Undo" })).toBeEnabled();
    });
  }
});

describe("a suggestion of the person's own already waiting", () => {
  it("is named before they draw, and the message after sending says it was replaced", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    finding.location.shape.suggestions = [shapeSuggestionFixture({ by: OTHER })];
    const { map, routes } = await openSuggest(finding);
    expect(
      suggestPanel().getByText("You already have a suggestion waiting on this marking. Sending this one replaces it."),
    ).toBeInTheDocument();
    routes.on(`POST /findings/${finding.public_id}/suggestions`, () => json({}, 201));
    await extend(user, map);
    await user.click(suggestPanel().getByRole("button", { name: "Send the suggestion" }));
    expect(await screen.findByText(/Your suggestion is sent, in place of your earlier one/)).toBeInTheDocument();
  });

  it("isn't named for someone else's suggestion", async () => {
    const finding = lineFinding();
    finding.location.shape.suggestions = [shapeSuggestionFixture({ by: FINDER })];
    await openSuggest(finding);
    expect(suggestPanel().queryByText(/already have a suggestion/)).toBeNull();
  });
});

describe("a shape the keeper changed while the suggestion was drawn", () => {
  async function refusedOnce(user: ReturnType<typeof userEvent.setup>) {
    const finding = lineFinding();
    const { map, routes } = await openSuggest(finding);
    routes.on(`POST /findings/${finding.public_id}/suggestions`, () =>
      apiError(409, "shape_changed", "The shape was changed after you opened it."),
    );
    routes.on(`GET /findings/${finding.public_id}`, () => json(changedByKeeper()));
    await extend(user, map);
    const listsBefore = harness.requestsTo("/findings");
    await user.click(suggestPanel().getByRole("button", { name: "Send the suggestion" }));
    expect(
      await suggestPanel().findByText(/Your suggestion hasn't been sent, and your drawing is still here/),
    ).toBeInTheDocument();
    return { finding, routes, listsBefore };
  }

  it("keeps the drawing and its undo, says it wasn't sent, and shows the shape as it now is", async () => {
    const user = userEvent.setup();
    const { listsBefore } = await refusedOnce(user);
    expect(useMarkStore.getState().shape.present.points).toHaveLength(4);
    expect(handles()).toHaveLength(4);
    expect(suggestPanel().getByRole("button", { name: "Undo" })).toBeEnabled();
    // The map asks again for the findings in view, so the keeper's shape as it now is is drawn.
    await waitFor(() => expect(harness.requestsTo("/findings")).toBeGreaterThan(listsBefore));
    await user.click(suggestPanel().getByRole("button", { name: "Undo" }));
    expect(useMarkStore.getState().shape.present.points).toHaveLength(3);
  });

  it("says so, and keeps the drawing, when the shape as it now is can't be loaded either", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const { map, routes } = await openSuggest(finding);
    routes.on(`POST /findings/${finding.public_id}/suggestions`, () =>
      apiError(409, "shape_changed", "The shape was changed after you opened it."),
    );
    // The connection drops before the finding can be asked for again.
    routes.on(`GET /findings/${finding.public_id}`, () => apiError(503, "unavailable", "Try again."));
    await extend(user, map);
    await user.click(suggestPanel().getByRole("button", { name: "Send the suggestion" }));

    // Nothing on the page knows the new shape, so the notice can't show. The person is still told.
    expect(await screen.findByText(/your suggestion wasn't sent\. Your drawing is still here/)).toBeInTheDocument();
    expect(useMarkStore.getState().shape.present.points).toHaveLength(4);
    expect(suggestPanel().getByRole("button", { name: "Undo" })).toBeEnabled();
    expect(suggestPanel().getByRole("button", { name: "Send the suggestion" })).toBeEnabled();
  });

  it("sends the drawing as it is against the shape as it now is, at the person's word", async () => {
    const user = userEvent.setup();
    const { finding, routes } = await refusedOnce(user);
    routes.on(`POST /findings/${finding.public_id}/suggestions`, () => json({}, 201));
    await user.click(suggestPanel().getByRole("button", { name: "Send it against the shape as it is now" }));
    await waitFor(() => expect(routes.callsTo(`POST /findings/${finding.public_id}/suggestions`)).toHaveLength(2));
    const body = routes.callsTo(`POST /findings/${finding.public_id}/suggestions`)[1]?.body as {
      path: { points: unknown[] };
      path_revision: number;
    };
    expect(body.path_revision).toBe(4);
    expect(body.path.points).toHaveLength(4);
    await waitFor(() => expect(address()).toBe(`/f/${finding.public_id}`));
  });

  it("asks before it starts again from the shape as it now is", async () => {
    const user = userEvent.setup();
    await refusedOnce(user);
    await user.click(suggestPanel().getByRole("button", { name: "Start again from the shape as it is now" }));
    expect(suggestPanel().getByText(/Starting again throws away what you drew/)).toBeInTheDocument();
    expect(suggestPanel().getByRole("button", { name: "Keep my drawing" })).toHaveFocus();
    await user.click(suggestPanel().getByRole("button", { name: "Keep my drawing" }));
    expect(useMarkStore.getState().shape.present.points).toHaveLength(4);
    await user.click(suggestPanel().getByRole("button", { name: "Start again from the shape as it is now" }));
    await user.click(suggestPanel().getByRole("button", { name: "Discard it and start again" }));
    await waitFor(() => expect(useMarkStore.getState().editing).toBe("suggest:f-ring:4"));
    expect(useMarkStore.getState().shape.present.points).toHaveLength(3);
    expect(suggestPanel().queryByText(/hasn't been sent/)).toBeNull();
  });
});

describe("arriving at the tool with what it holds set aside", () => {
  for (const kind of ["suggest", "finding"] as const) {
    it(`opens the tool on it again at ${kind === "suggest" ? "Suggest a change" : "Change the shape"}`, async () => {
      const finding = lineFinding(kind === "finding" ? { actions: FINDER_ACTIONS } : {});
      act(() => {
        const mark = useMarkStore.getState();
        mark.edit(editingKey(finding, kind), {
          closed: false,
          points: POINTS.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
        });
        mark.move(0, [POINTS[0]?.lon ?? 0, (POINTS[0]?.lat ?? 0) + 0.0002]);
        // As "Mark a finding" leaves it while it asks, and Back then Forward come here again.
        useMarkStore.setState({ setAside: true });
      });
      serve([finding], kind === "finding" ? THE_FINDER : MEMBER);
      renderShell(`/mark/${kind}/${finding.public_id}`, <Address />);
      await mapReady();
      await waitFor(() => expect(handles()).toHaveLength(3));
      expect(useMarkStore.getState().setAside).toBe(false);
    });
  }
});

describe("a suggestion in hand that can no longer be sent", () => {
  function holdSuggestion(finding: FindingDetail): void {
    act(() => {
      const mark = useMarkStore.getState();
      mark.edit(editingKey(finding, "suggest"), {
        closed: false,
        points: POINTS.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
      });
      mark.move(0, [POINTS[0]?.lon ?? 0, (POINTS[0]?.lat ?? 0) + 0.0002]);
    });
  }

  it("says it wasn't sent and offers to discard it, once the finding takes no suggestions", async () => {
    const user = userEvent.setup();
    const withdrawn = lineFinding({
      actions: { ...pageFixture().actions, suggest: { allowed: false, reason: "finding_withdrawn" } },
    });
    holdSuggestion(withdrawn);
    serve([withdrawn]);
    renderShell(`/mark/suggest/${withdrawn.public_id}`, <Address />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Suggest a change" }));
    expect(
      await panel.findByText(/Your suggested change to this shape wasn't sent, and it can't be sent now/),
    ).toBeInTheDocument();
    expect(useMarkStore.getState().shape.present.points).toHaveLength(3);
    await user.click(panel.getByRole("button", { name: "Discard your suggestion" }));
    expect(useMarkStore.getState().editing).toBeNull();
    expect(panel.queryByText(/wasn't sent/)).toBeNull();
  });

  it("carries the drawing over to 'Change the shape' for someone who now keeps the marking", async () => {
    const user = userEvent.setup();
    const kept = lineFinding({ keeper: OTHER, actions: FINDER_ACTIONS });
    holdSuggestion(kept);
    const moved = useMarkStore.getState().shape.present;
    serve([kept]);
    renderShell(`/mark/suggest/${kept.public_id}`, <Address />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Suggest a change" }));
    await user.click(await panel.findByRole("button", { name: "Change the shape with your drawing" }));
    await waitFor(() => expect(address()).toBe(`/mark/finding/${kept.public_id}`));
    expect(useMarkStore.getState().editing).toBe(editingKey(kept));
    expect(useMarkStore.getState().shape.present).toBe(moved);
    await waitFor(() => expect(handles()).toHaveLength(3));
    expect(panelNamed("Change the shape").getByRole("button", { name: "Undo" })).toBeEnabled();
  });

  it("offers to discard an unsaved change at 'Change the shape' once the person no longer keeps the marking", async () => {
    const user = userEvent.setup();
    const handedOn = lineFinding({ keeper: OTHER });
    act(() => {
      const mark = useMarkStore.getState();
      mark.edit(editingKey(handedOn), {
        closed: false,
        points: POINTS.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
      });
      mark.move(0, [POINTS[0]?.lon ?? 0, (POINTS[0]?.lat ?? 0) + 0.0002]);
    });
    serve([handedOn]);
    renderShell(`/mark/finding/${handedOn.public_id}`, <Address />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Change the shape" }));
    expect(
      await panel.findByText(/Your change to this shape wasn't saved, and it can't be saved now/),
    ).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "Discard your change" }));
    expect(useMarkStore.getState().editing).toBeNull();
  });
});

describe("an unfinished suggestion", () => {
  for (const how of ["the panel's Close", "Escape"] as const) {
    it(`is kept on ${how}, drawn dashed on the map, and taken back to from there`, async () => {
      const user = userEvent.setup();
      const finding = lineFinding();
      const { map } = await openSuggest(finding);
      await extend(user, map);
      if (how === "Escape") await user.keyboard("{Escape}");
      else await user.click(suggestPanel().getByRole("button", { name: "Close panel" }));
      await waitFor(() => expect(address()).toBe(`/f/${finding.public_id}`));
      expect(useMarkStore.getState().shape.present.points).toHaveLength(4);
      expect(screen.getByTestId("mark-path")).toHaveAttribute("data-unsaved", "true");
      expect(handles()).toHaveLength(0);

      await user.click(screen.getByRole("button", { name: "Carry on with your suggested change" }));
      await waitFor(() => expect(address()).toBe(`/mark/suggest/${finding.public_id}`));
      expect(await suggestPanel().findByText("Carrying on with the change you hadn't sent.")).toBeInTheDocument();
      await waitFor(() => expect(handles()).toHaveLength(4));
    });
  }

  it("is asked about before 'Mark a finding' takes the map from it, and nothing is added meanwhile", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const { map } = await openSuggest(finding);
    await extend(user, map);
    await user.click(suggestPanel().getByRole("button", { name: "Close panel" }));
    await waitFor(() => expect(address()).toBe(`/f/${finding.public_id}`));
    await user.click(screen.getByRole("button", { name: "Mark a finding" }));
    const mark = within(await screen.findByRole("complementary", { name: "Mark a finding" }));
    expect(
      await mark.findByText(
        "You have a suggested change to a finding's shape that isn't sent. Marking a finding would discard it.",
      ),
    ).toBeInTheDocument();
    act(() => map.click(300, 300));
    expect(useMarkStore.getState().shape.present.points).toHaveLength(4);
    expect(useMarkStore.getState().editing).toBe(editingKey(finding, "suggest"));

    await user.click(mark.getByRole("button", { name: "Go back to it" }));
    await waitFor(() => expect(address()).toBe(`/mark/suggest/${finding.public_id}`));
    await waitFor(() => expect(handles()).toHaveLength(4));
  });

  it("is discarded when 'Mark a finding' is told to, and marking starts afresh", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const { map } = await openSuggest(finding);
    await extend(user, map);
    await user.click(suggestPanel().getByRole("button", { name: "Close panel" }));
    await user.click(screen.getByRole("button", { name: "Mark a finding" }));
    const mark = within(await screen.findByRole("complementary", { name: "Mark a finding" }));
    await user.click(await mark.findByRole("button", { name: "Discard it and start here" }));
    expect(useMarkStore.getState().editing).toBeNull();
    expect(useMarkStore.getState().shape.present.points).toHaveLength(0);
    act(() => map.click(300, 300));
    expect(useMarkStore.getState().shape.present.points).toHaveLength(1);
  });

  it("is asked about before 'Change the shape' of a finding the person keeps takes it", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const own = lineFinding({ public_id: "f-own", title: "Bank by the brook", keeper: OTHER, actions: FINDER_ACTIONS });
    serve([finding, own]);
    const mark = useMarkStore.getState();
    mark.edit(editingKey(finding, "suggest"), {
      closed: false,
      points: POINTS.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
    });
    mark.move(0, [POINTS[0]?.lon ?? 0, (POINTS[0]?.lat ?? 0) + 0.0002]);
    renderShell(`/mark/finding/${own.public_id}`, <Address />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Change the shape" }));
    expect(
      await panel.findByText(
        "You have a suggested change to a finding's shape that isn't sent. Changing this shape would discard it.",
      ),
    ).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "Go back to it" }));
    await waitFor(() => expect(address()).toBe(`/mark/suggest/${finding.public_id}`));
  });

  it("isn't lost to a suggestion on another finding without being asked about", async () => {
    const user = userEvent.setup();
    const mark = useMarkStore.getState();
    for (const { lon, lat } of [offset(400, 300), offset(450, 340)]) mark.add([lon, lat], metaFixture.shapes);
    mark.finish();
    const finding = lineFinding();
    serve([finding]);
    renderShell(`/mark/suggest/${finding.public_id}`, <Address />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Suggest a change" }));
    expect(
      await panel.findByText("You have an unfinished marking. Suggesting a change would discard it."),
    ).toBeInTheDocument();
    expect(useMarkStore.getState().shape.present.points).toHaveLength(2);
    await user.click(panel.getByRole("button", { name: "Discard it and suggest a change" }));
    await waitFor(() => expect(useMarkStore.getState().editing).toBe(editingKey(finding, "suggest")));
  });

  it("is forgotten when the person signs out", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    serve([finding]);
    renderShell(
      `/mark/suggest/${finding.public_id}`,
      <>
        <Address />
        <SignOutHere />
      </>,
    );
    const map = await mapReady();
    await waitFor(() => expect(handles()).toHaveLength(3));
    await extend(user, map);
    await user.click(suggestPanel().getByRole("button", { name: "Close panel" }));
    await waitFor(() => expect(address()).toBe(`/f/${finding.public_id}`));
    await user.click(screen.getByRole("button", { name: "Sign out for the test" }));
    await waitFor(() => expect(useMarkStore.getState().editing).toBeNull());
    expect(screen.queryByTestId("mark-path")).toBeNull();
  });
});
