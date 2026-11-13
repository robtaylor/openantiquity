import { focusManager, useQueryClient } from "@tanstack/react-query";
import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { FINDER, finderView, pageFixture, suggestionsFixture } from "../../test/fixtures/findingPage.js";
import { offset } from "../../test/fixtures/findings.js";
import { meFixture } from "../../test/fixtures/me.js";
import {
  json,
  mapReady,
  renderShell,
  setUpShellTests,
  signedOutResponse,
  usePhoneLayout,
} from "../../test/shellHarness.js";
import { signedOut } from "../account/session.js";
import type { FindingDetail } from "../finding/types.js";
import { useSelectedFinding } from "../findings/selection.js";
import { changeBody, LOOKED_AT_LAYER, LOOKED_AT_SOURCE } from "./ChangeShapePanel.js";
import { useMarkStore } from "./markStore.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();
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

const POINTS = [offset(-100, 0), offset(0, 20), offset(100, 0)];
const LOOKED_AT = { type: "LineString" as const, coordinates: POINTS.map(({ lon, lat }) => [lon, lat]) };

/** The finder's line of three points, at shape revision 3, with second looks given on it. */
function lineFinding(overrides: Partial<FindingDetail> = {}): FindingDetail {
  const base = finderView();
  return {
    ...base,
    location: {
      ...base.location,
      outline: LOOKED_AT,
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
        looked_at: LOOKED_AT,
      },
    },
    ...overrides,
  };
}

function serve(finding: FindingDetail, me = THE_FINDER): ApiRoutes {
  const path = `/findings/${finding.public_id}`;
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => json(me),
    [`GET ${path}`]: () => json(finding),
    [`GET ${path}/comments`]: () => json({ items: [], next_cursor: null }),
    [`GET ${path}/suggested-records`]: () => json(suggestionsFixture([])),
    [`GET ${path}/observations`]: () => json({ items: [], next_cursor: null }),
  });
}

function changePanel() {
  return within(screen.getByRole("complementary", { name: "Change the shape" }));
}

function handles(): HTMLElement[] {
  return screen.queryAllByTestId("path-handle");
}

async function openChange(finding: FindingDetail, routes = serve(finding)) {
  renderShell(`/mark/finding/${finding.public_id}`, <Address />);
  const map = await mapReady();
  await screen.findByRole("complementary", { name: "Change the shape" });
  await waitFor(() => expect(handles()).toHaveLength(finding.location.path?.points.length ?? 1));
  return { map, routes };
}

describe("opening the tool on a saved finding", () => {
  it("is offered on the finding's page when the server says it may be edited, and opens with the saved path", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    serve(finding);
    renderShell(`/f/${finding.public_id}`, <Address />);
    await mapReady();
    const page = within(await screen.findByRole("complementary", { name: finding.title }));
    await user.click(page.getByRole("button", { name: "Change the shape" }));
    expect(address()).toBe(`/mark/finding/${finding.public_id}`);
    await waitFor(() => expect(handles()).toHaveLength(3));
    expect(changePanel().getByRole("region", { name: "How to mark it" })).toHaveTextContent(
      /Select an end point and press “Continue from this end”/,
    );
    expect(useMarkStore.getState().drawing).toBe(false);
  });

  it("isn't offered to someone the server doesn't let edit it, even the finder's handle", async () => {
    const finding = lineFinding({ actions: { ...finderView().actions, edit: { allowed: false, reason: "x" } } });
    serve(finding);
    renderShell(`/f/${finding.public_id}`);
    await mapReady();
    const page = within(await screen.findByRole("complementary", { name: finding.title }));
    expect(page.queryByRole("button", { name: "Change the shape" })).toBeNull();
  });

  it("says on the finding's page that an old shape of several parts can be replaced but not changed", async () => {
    const finding = lineFinding({
      location: {
        ...lineFinding().location,
        path: null,
        outline: {
          type: "MultiLineString",
          coordinates: [
            [
              [-1.855, 51.428],
              [-1.854, 51.429],
            ],
            [
              [-1.853, 51.43],
              [-1.852, 51.431],
            ],
          ],
        },
      },
    });
    serve(finding);
    renderShell(`/f/${finding.public_id}`);
    await mapReady();
    const page = within(await screen.findByRole("complementary", { name: finding.title }));
    expect(page.getByRole("button", { name: "Change the shape" })).toBeInTheDocument();
    expect(page.getByText(/can't be changed point by point/)).toHaveTextContent(
      "Its shape was drawn before the drawing tool and can't be changed point by point. You can draw a new one to replace it.",
    );
  });

  it("says nothing of replacing on the page of a shape that can be changed point by point", async () => {
    const finding = lineFinding();
    serve(finding);
    renderShell(`/f/${finding.public_id}`);
    await mapReady();
    const page = within(await screen.findByRole("complementary", { name: finding.title }));
    expect(page.getByRole("button", { name: "Change the shape" })).toBeInTheDocument();
    expect(page.queryByText(/can't be changed point by point/)).toBeNull();
  });

  it("says so, and draws nothing, at the tool's address for someone who may not change it", async () => {
    const finding = lineFinding({ actions: pageFixture().actions });
    serve(finding, meFixture());
    renderShell(`/mark/finding/${finding.public_id}`);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Change the shape" }));
    expect(await panel.findByText(/Only the person who marked a finding can change its shape/)).toBeInTheDocument();
    expect(handles()).toHaveLength(0);
  });

  it("opens a finding of one point as that point, ready to be carried on into a line", async () => {
    const finding = finderView();
    await openChange(finding);
    expect(useMarkStore.getState().shape.present.points).toEqual([
      { lon: finding.location.lon, lat: finding.location.lat, kind: "corner" },
    ]);
  });

  it("draws the ground second looks were given on as a faint line under the path, and takes it away after", async () => {
    const user = userEvent.setup();
    const { map } = await openChange(lineFinding());
    const data = map.sourceData(LOOKED_AT_SOURCE) as { features: Array<{ geometry: unknown }> };
    expect(data.features).toHaveLength(1);
    expect(data.features[0]?.geometry).toEqual(LOOKED_AT);
    expect(map.getLayer(LOOKED_AT_LAYER)).toBeDefined();
    expect(changePanel().getByText(/The faint line is where others gave second looks/)).toBeInTheDocument();
    await user.click(changePanel().getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(address()).toBe("/f/f-ring"));
    expect((map.sourceData(LOOKED_AT_SOURCE) as { features: unknown[] }).features).toHaveLength(0);
  });
});

describe("saving a changed shape", () => {
  it("sends the whole path with the revision it started from, and opens the finding's page", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const { map, routes } = await openChange(finding);
    routes.on(`PATCH /findings/${finding.public_id}`, () => json(lineFinding()));
    await user.click(screen.getByRole("button", { name: /^Point 3 of 3/ }));
    await user.click(changePanel().getByRole("button", { name: "Continue from this end" }));
    act(() => map.click(600, 200));
    await user.click(changePanel().getByRole("button", { name: "Finish" }));
    await user.click(changePanel().getByRole("button", { name: "Save the shape" }));
    await waitFor(() => expect(routes.callsTo(`PATCH /findings/${finding.public_id}`)).toHaveLength(1));
    const body = routes.callsTo(`PATCH /findings/${finding.public_id}`)[0]?.body as {
      path: { closed: boolean; points: unknown[] };
      path_revision: number;
      location?: unknown;
    };
    expect(body.path_revision).toBe(3);
    expect(body.path.closed).toBe(false);
    expect(body.path.points).toHaveLength(4);
    expect(body).not.toHaveProperty("location");
    await waitFor(() => expect(address()).toBe(`/f/${finding.public_id}`));
    expect(await screen.findByText("The new shape is saved.")).toBeInTheDocument();
  });

  it("sends a finding of one point carried on into a line as a path from revision 0", async () => {
    const user = userEvent.setup();
    const finding = finderView();
    const { map, routes } = await openChange(finding);
    routes.on(`PATCH /findings/${finding.public_id}`, () => json(finding));
    await user.click(screen.getByRole("button", { name: /^Point 1 of 1/ }));
    await user.click(changePanel().getByRole("button", { name: "Continue from this end" }));
    act(() => map.click(600, 200));
    await user.click(changePanel().getByRole("button", { name: "Finish" }));
    await user.click(changePanel().getByRole("button", { name: "Save the shape" }));
    await waitFor(() => expect(routes.callsTo(`PATCH /findings/${finding.public_id}`)).toHaveLength(1));
    const body = routes.callsTo(`PATCH /findings/${finding.public_id}`)[0]?.body as Record<string, unknown>;
    expect(body.path_revision).toBe(0);
    expect((body.path as { points: unknown[] }).points).toHaveLength(2);
  });

  it("shows the finding again as it now is when the shape was changed elsewhere, and says so", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const { routes } = await openChange(finding);
    const moved = lineFinding();
    const extra = offset(200, 0);
    moved.location.path?.points.push({ lon: extra.lon, lat: extra.lat, kind: "smooth" });
    moved.location.shape.revision = 4;
    routes.on(`PATCH /findings/${finding.public_id}`, () =>
      apiError(409, "shape_changed", "The shape was changed after you opened it."),
    );
    routes.on(`GET /findings/${finding.public_id}`, () => json(moved));
    await user.click(screen.getByRole("button", { name: /^Point 2 of 3/ }));
    await user.click(changePanel().getByRole("button", { name: "Delete point" }));
    expect(handles()).toHaveLength(2);
    await user.click(changePanel().getByRole("button", { name: "Save the shape" }));
    expect(
      await changePanel().findByText(
        "The shape was changed somewhere else while you had it open. This is it as it is now.",
      ),
    ).toBeInTheDocument();
    await waitFor(() => expect(handles()).toHaveLength(4));
    expect(address()).toBe(`/mark/finding/${finding.public_id}`);

    // The next save starts from the revision now shown.
    routes.on(`PATCH /findings/${finding.public_id}`, () => json(moved));
    await user.click(changePanel().getByRole("button", { name: "Save the shape" }));
    await waitFor(() => expect(routes.callsTo(`PATCH /findings/${finding.public_id}`)).toHaveLength(2));
    const second = routes.callsTo(`PATCH /findings/${finding.public_id}`)[1]?.body as { path_revision?: number };
    expect(second?.path_revision).toBe(4);
  });

  it("says beside the path why a change that moves what others looked at is refused, and keeps the change", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const { routes } = await openChange(finding);
    const message = "Only 40% of what others looked at would be left within 250 m, and three-quarters has to stay.";
    routes.on(`PATCH /findings/${finding.public_id}`, () => apiError(422, "looked_at_moved", message));
    await user.click(screen.getByRole("button", { name: /^Point 1 of 3/ }));
    await user.click(changePanel().getByRole("button", { name: "Delete point" }));
    await user.click(changePanel().getByRole("button", { name: "Save the shape" }));
    expect(await changePanel().findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByTestId("path-problem")).toHaveTextContent(message);
    expect(handles()).toHaveLength(2);
    expect(address()).toBe(`/mark/finding/${finding.public_id}`);
  });
});

/** The finder's line as another tab left it: a fourth point, at revision 4. */
function extendedElsewhere(): FindingDetail {
  const moved = lineFinding();
  const extra = offset(200, 0);
  moved.location.path?.points.push({ lon: extra.lon, lat: extra.lat, kind: "smooth" });
  moved.location.shape.revision = 4;
  return moved;
}

/** The window losing focus and gaining it again, which asks for the finding again. */
function refocus(): void {
  act(() => {
    focusManager.setFocused(false);
    focusManager.setFocused(true);
  });
}

describe("the finding changing elsewhere while its shape is open", () => {
  it("names the revision the change began on, not the finding's as it is now", () => {
    const now = extendedElsewhere();
    const path = { closed: false, points: POINTS.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })) };
    expect(changeBody(now, path, 3)).toMatchObject({ path_revision: 3 });
  });

  it("takes up the newer shape when nothing has been changed here", async () => {
    const finding = lineFinding();
    const { routes } = await openChange(finding);
    routes.on(`GET /findings/${finding.public_id}`, () => json(extendedElsewhere()));
    refocus();
    await waitFor(() => expect(handles()).toHaveLength(4));
    expect(changePanel().queryByText(/changed somewhere else/)).toBeNull();
    expect(changePanel().getByRole("button", { name: "Save the shape" })).toBeEnabled();
  });

  it("keeps a change in progress with its undo, says it can't be saved over the newer shape, and offers to take that up", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const { routes } = await openChange(finding);
    await user.click(screen.getByRole("button", { name: /^Point 2 of 3/ }));
    await user.click(changePanel().getByRole("button", { name: "Delete point" }));
    expect(handles()).toHaveLength(2);
    const fetched = routes.callsTo(`GET /findings/${finding.public_id}`).length;
    routes.on(`GET /findings/${finding.public_id}`, () => json(extendedElsewhere()));
    refocus();
    await waitFor(() => expect(routes.callsTo(`GET /findings/${finding.public_id}`).length).toBeGreaterThan(fetched));
    expect(
      await changePanel().findByText(
        "The shape was changed somewhere else while you had it open, so what is here can't be saved over it.",
      ),
    ).toBeInTheDocument();
    expect(handles()).toHaveLength(2);
    expect(changePanel().getByRole("button", { name: "Undo" })).toBeEnabled();
    expect(changePanel().getByRole("button", { name: "Save the shape" })).toBeDisabled();
    expect(routes.callsTo(`PATCH /findings/${finding.public_id}`)).toHaveLength(0);

    await user.click(changePanel().getByRole("button", { name: "Show it as it is now" }));
    await waitFor(() => expect(handles()).toHaveLength(4));
    expect(changePanel().queryByText(/can't be saved over it/)).toBeNull();
    expect(changePanel().getByRole("button", { name: "Undo" })).toBeDisabled();

    // A save from here starts from the revision now shown.
    routes.on(`PATCH /findings/${finding.public_id}`, () => json(extendedElsewhere()));
    await user.click(screen.getByRole("button", { name: /^Point 4 of 4/ }));
    await user.click(changePanel().getByRole("button", { name: "Delete point" }));
    await user.click(changePanel().getByRole("button", { name: "Save the shape" }));
    await waitFor(() => expect(routes.callsTo(`PATCH /findings/${finding.public_id}`)).toHaveLength(1));
    const body = routes.callsTo(`PATCH /findings/${finding.public_id}`)[0]?.body as { path_revision?: number };
    expect(body.path_revision).toBe(4);
  });
});

describe("leaving the tool", () => {
  for (const [how, label] of [
    ["Cancel", "Cancel"],
    ["the panel's close button", "Close panel"],
  ] as const) {
    it(`throws the change away on ${how}, so the tool opens again on the saved shape`, async () => {
      const user = userEvent.setup();
      const finding = lineFinding();
      const { routes } = await openChange(finding);
      await user.click(screen.getByRole("button", { name: /^Point 2 of 3/ }));
      await user.click(changePanel().getByRole("button", { name: "Delete point" }));
      expect(handles()).toHaveLength(2);
      await user.click(changePanel().getByRole("button", { name: label }));
      await waitFor(() => expect(address()).toBe(`/f/${finding.public_id}`));
      const page = within(await screen.findByRole("complementary", { name: finding.title }));
      await user.click(page.getByRole("button", { name: "Change the shape" }));
      await waitFor(() => expect(handles()).toHaveLength(3));
      expect(changePanel().queryByText(/Carrying on from changes/)).toBeNull();
      expect(changePanel().getByRole("button", { name: "Undo" })).toBeDisabled();
      expect(routes.callsTo(`PATCH /findings/${finding.public_id}`)).toHaveLength(0);
    });
  }

  it("says so when it picks up a change left unsaved some other way, and can throw it away", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    act(() => {
      const mark = useMarkStore.getState();
      mark.edit(`finding:${finding.public_id}:3`, {
        closed: false,
        points: POINTS.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
      });
      mark.remove(1);
    });
    serve(finding);
    renderShell(`/mark/finding/${finding.public_id}`, <Address />);
    await mapReady();
    expect(await changePanel().findByText("Carrying on from changes you hadn't saved.")).toBeInTheDocument();
    expect(handles()).toHaveLength(2);
    await user.click(changePanel().getByRole("button", { name: "Discard them" }));
    await waitFor(() => expect(handles()).toHaveLength(3));
    expect(changePanel().queryByText(/Carrying on from changes/)).toBeNull();
  });

  it("says nothing of carrying on when the tool opens on the saved shape", async () => {
    await openChange(lineFinding());
    expect(changePanel().queryByText(/Carrying on from changes/)).toBeNull();
  });
});

function SignOutHere() {
  const client = useQueryClient();
  return (
    <button type="button" onClick={() => signedOut(client)}>
      Sign out for the test
    </button>
  );
}

describe("the exact path and signing out", () => {
  it("forgets the path being changed when the finder signs out, and draws nothing for the next reader", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    const routes = serve(finding);
    renderShell(
      `/mark/finding/${finding.public_id}`,
      <>
        <Address />
        <SignOutHere />
      </>,
    );
    await mapReady();
    await waitFor(() => expect(handles()).toHaveLength(3));
    routes.on("GET /auth/me", () => signedOutResponse());
    routes.on(`GET /findings/${finding.public_id}`, () => json(lineFinding({ actions: pageFixture().actions })));
    await user.click(screen.getByRole("button", { name: "Sign out for the test" }));
    expect(
      await changePanel().findByText(/Only the person who marked a finding can change its shape/),
    ).toBeInTheDocument();
    expect(useMarkStore.getState().shape.present.points).toHaveLength(0);
    expect(useMarkStore.getState().editing).toBeNull();
    expect(handles()).toHaveLength(0);
    expect(screen.queryByTestId("mark-path")).toBeNull();
  });

  it("draws no path at the tool's address for a reader who may not change the finding, whatever the tool holds", async () => {
    const finding = lineFinding({ actions: pageFixture().actions });
    act(() =>
      useMarkStore.getState().edit(`finding:${finding.public_id}:3`, {
        closed: false,
        points: POINTS.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
      }),
    );
    serve(finding, meFixture());
    renderShell(`/mark/finding/${finding.public_id}`);
    const map = await mapReady();
    expect(
      await changePanel().findByText(/Only the person who marked a finding can change its shape/),
    ).toBeInTheDocument();
    expect(handles()).toHaveLength(0);
    expect(screen.queryByTestId("mark-path")).toBeNull();
    expect(screen.queryByTestId("reticle")).toBeNull();
    // A tap adds nothing.
    act(() => map.click(400, 300));
    expect(useMarkStore.getState().shape.present.points).toHaveLength(3);
  });
});

describe("replacing an old shape of several parts", () => {
  function oldShapeFinding(): FindingDetail {
    return lineFinding({
      location: {
        ...lineFinding().location,
        path: null,
        outline: {
          type: "MultiLineString",
          coordinates: [
            [
              [-1.855, 51.428],
              [-1.854, 51.429],
            ],
            [
              [-1.853, 51.43],
              [-1.852, 51.431],
            ],
          ],
        },
      },
    });
  }

  it("saves nothing, and says why, until a new shape of two points or more is drawn", async () => {
    const user = userEvent.setup();
    const finding = oldShapeFinding();
    const { map, routes } = await openChange(finding);
    await user.click(changePanel().getByRole("button", { name: "Save the shape" }));
    expect(await changePanel().findByRole("alert")).toHaveTextContent(
      "Draw the new shape first, or cancel to leave it as it was.",
    );
    expect(routes.callsTo(`PATCH /findings/${finding.public_id}`)).toHaveLength(0);
    expect(address()).toBe(`/mark/finding/${finding.public_id}`);

    routes.on(`PATCH /findings/${finding.public_id}`, () => json(lineFinding()));
    await user.click(screen.getByRole("button", { name: /^Point 1 of 1/ }));
    await user.click(changePanel().getByRole("button", { name: "Continue from this end" }));
    act(() => map.click(600, 200));
    await user.click(changePanel().getByRole("button", { name: "Finish" }));
    await user.click(changePanel().getByRole("button", { name: "Save the shape" }));
    await waitFor(() => expect(routes.callsTo(`PATCH /findings/${finding.public_id}`)).toHaveLength(1));
    const body = routes.callsTo(`PATCH /findings/${finding.public_id}`)[0]?.body as { path: { points: unknown[] } };
    expect(body.path.points).toHaveLength(2);
  });

  it("never sends the removal of an old shape from what the tool holds of it", () => {
    const finding = oldShapeFinding();
    const only = {
      closed: false,
      points: [{ lon: finding.location.lon, lat: finding.location.lat, kind: "corner" as const }],
    };
    expect(changeBody(finding, only, 3)).toBeNull();
  });
});

describe("leaving the page while changing a shape", () => {
  function asksBeforeLeaving(): boolean {
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    return event.defaultPrevented;
  }

  it("asks only while there is a change not saved, and not after Cancel", async () => {
    const user = userEvent.setup();
    const finding = lineFinding();
    await openChange(finding);
    expect(asksBeforeLeaving()).toBe(false);
    await user.click(screen.getByRole("button", { name: /^Point 2 of 3/ }));
    await user.click(changePanel().getByRole("button", { name: "Delete point" }));
    expect(asksBeforeLeaving()).toBe(true);
    await user.click(changePanel().getByRole("button", { name: "Undo" }));
    expect(asksBeforeLeaving()).toBe(false);
    await user.click(changePanel().getByRole("button", { name: "Redo" }));
    expect(asksBeforeLeaving()).toBe(true);
    await user.click(changePanel().getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(address()).toBe(`/f/${finding.public_id}`));
    expect(asksBeforeLeaving()).toBe(false);
  });
});

describe("changing a shape on a phone", () => {
  it("floats the compact bar while points are added, as marking does", async () => {
    const user = userEvent.setup();
    usePhoneLayout();
    await openChange(lineFinding());
    await user.click(screen.getByRole("button", { name: /^Point 3 of 3/ }));
    await user.click(changePanel().getByRole("button", { name: "Continue from this end" }));
    const floating = await screen.findByRole("region", { name: "Selected point" });
    expect(floating.closest(".fc-mark-float")).not.toBeNull();
  });
});
