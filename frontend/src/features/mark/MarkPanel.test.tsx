import { useQueryClient } from "@tanstack/react-query";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useMapStore } from "../../map/store.js";
import { apiError, routeApi } from "../../test/apiRoutes.js";
import { createdFinding } from "../../test/fixtures/findings.js";
import { meFixture } from "../../test/fixtures/me.js";
import {
  json,
  mapReady,
  renderShell,
  setUpShellTests,
  signedOutResponse,
  usePhoneLayout,
} from "../../test/shellHarness.js";
import { useAccountUi } from "../account/requireAccount.js";
import { signedIn } from "../account/session.js";
import {
  DRAFTS_STORAGE_KEY,
  listDrafts,
  noteSignInStarted,
  resetDraftsForTests,
  updateDrafts,
} from "../drafts/store.js";
import type { FindingCreate } from "../findings/types.js";
import { findingDrafts } from "./findingDrafts.js";
import { MARK_PATH_SOURCE, SVG_MAX_POINTS } from "./MarkLayer.js";
import { useMarkStore } from "./markStore.js";
import { HANDLES_MAX_IN_VIEW, LONG_PRESS_MS, NUDGE_FAST_PX, NUDGE_PX } from "./PathHandles.js";
import { history, type Path } from "./path.js";
import { usePendingFindings } from "./pending.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

function Address() {
  const location = useLocation();
  return <output data-testid="address">{location.pathname}</output>;
}

function address(): string {
  return screen.getByTestId("address").textContent ?? "";
}

beforeEach(() => {
  window.localStorage.clear();
  resetDraftsForTests();
  useAccountUi.setState(useAccountUi.getInitialState(), true);
  useMarkStore.getState().start();
  usePendingFindings.setState({ pending: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function panel() {
  return within(screen.getByRole("complementary", { name: "Mark a finding" }));
}

/** The first point of the marking, as a pair. */
function point(): [number, number] {
  const [first] = useMarkStore.getState().shape.present.points;
  if (!first) throw new Error("No mark has been placed");
  return [first.lon, first.lat];
}

function points() {
  return useMarkStore.getState().shape.present.points;
}

function handles(): HTMLElement[] {
  return screen.queryAllByTestId("path-handle");
}

function handle(index: number): HTMLElement {
  return screen.getByRole("button", { name: new RegExp(`^Point ${index + 1} of \\d+`) });
}

function guidance() {
  return panel().getByRole("region", { name: "How to mark it" });
}

async function openMarking(signedIn = true) {
  const routes = routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (signedIn ? json(meFixture()) : signedOutResponse()),
  });
  renderShell("/mark", <Address />);
  const map = await mapReady();
  return { map, routes };
}

describe("marking by tapping", () => {
  it("takes taps at once: the first places a point, and a second adds one and leaves the first where it was", async () => {
    const { map } = await openMarking();
    expect(map.getCanvas()).toHaveClass("fc-canvas--placing");
    expect(screen.getByTestId("reticle")).toBeInTheDocument();
    expect(guidance()).toHaveTextContent("Click the map where the feature is. One click marks a spot.");
    expect(panel().getByRole("status")).toHaveTextContent("Nothing placed yet.");

    act(() => map.click(300, 200));
    const first = point();
    expect(first[0]).toBeCloseTo(map.unproject([300, 200]).lng, 9);
    expect(handle(0)).toHaveAccessibleName(/^Point 1 of 1, straight, SU \d{4} \d{4}\./);
    expect(panel().getByText(/^SU \d{4} \d{4}$/)).toBeInTheDocument();
    expect(guidance()).toHaveTextContent(/This is a spot\. Click again to draw a line from it, or drag the point/);

    act(() => map.click(320, 260));
    expect(points()).toHaveLength(2);
    expect(point()).toEqual(first);
    expect(handles()).toHaveLength(2);
    expect(guidance()).toHaveTextContent(
      /Click to carry the line on, or click the first point to close it into a shape/,
    );
    expect(panel().getByRole("status")).toHaveTextContent(
      /^2 points, \d+ m\. Click the map to add the next one at the south end\./,
    );
  });

  it("turns off double-click and box zoom while marking, so a double click is one point, and turns them back on after", async () => {
    const { map } = await openMarking();
    expect(map.doubleClickZoom.isEnabled()).toBe(false);
    expect(map.boxZoom.isEnabled()).toBe(false);
    act(() => map.click(300, 200));
    act(() => map.click(300, 200));
    expect(points()).toHaveLength(1);

    // Escape stops drawing, keeping the point. A second leaves.
    fireEvent.keyDown(handle(0), { key: "Escape" });
    expect(useMarkStore.getState().drawing).toBe(false);
    expect(points()).toHaveLength(1);
    expect(address()).toBe("/mark");
    fireEvent.keyDown(handle(0), { key: "Escape" });
    await waitFor(() => expect(address()).toBe("/"));
    expect(map.doubleClickZoom.isEnabled()).toBe(true);
    expect(map.boxZoom.isEnabled()).toBe(true);
    expect(map.getCanvas()).not.toHaveClass("fc-canvas--placing");
  });

  it("drags a point with a pointer, without moving the map, as one step to undo", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    act(() => map.click(450, 300));
    const target = handle(1);
    fireEvent.pointerDown(target, { pointerId: 1, button: 0, pointerType: "touch", clientX: 450, clientY: 300 });
    fireEvent.pointerMove(target, { pointerId: 1, pointerType: "touch", clientX: 460, clientY: 320 });
    fireEvent.pointerMove(target, { pointerId: 1, pointerType: "touch", clientX: 470, clientY: 330 });
    fireEvent.pointerUp(target, { pointerId: 1, pointerType: "touch", clientX: 470, clientY: 330 });
    fireEvent.click(target, { detail: 1 });
    // The fake map's container sits at the top left of the page, so client and map pixels agree.
    const moved = points()[1];
    expect(map.project([moved?.lon ?? 0, moved?.lat ?? 0]).x).toBeCloseTo(470, 6);
    expect(map.project([moved?.lon ?? 0, moved?.lat ?? 0]).y).toBeCloseTo(330, 6);
    expect(map.project(point()).x).toBeCloseTo(400, 6);
    expect(points()).toHaveLength(2);
    // A move after the pointer is lifted does nothing.
    fireEvent.pointerMove(target, { pointerId: 1, pointerType: "touch", clientX: 10, clientY: 10 });
    expect(map.project([points()[1]?.lon ?? 0, points()[1]?.lat ?? 0]).x).toBeCloseTo(470, 6);

    await user.click(panel().getByRole("button", { name: "Undo" }));
    expect(map.project([points()[1]?.lon ?? 0, points()[1]?.lat ?? 0]).x).toBeCloseTo(450, 6);
    await user.click(panel().getByRole("button", { name: "Redo" }));
    expect(map.project([points()[1]?.lon ?? 0, points()[1]?.lat ?? 0]).x).toBeCloseTo(470, 6);
  });

  it("nudges a point with the arrow keys, further with Shift, and steps along the path with [ and ]", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    act(() => map.click(450, 300));
    // The path is one tab stop, on the active end.
    expect(handle(1)).toHaveAttribute("tabindex", "0");
    expect(handle(0)).toHaveAttribute("tabindex", "-1");
    handle(1).focus();
    await user.keyboard("{ArrowRight}");
    const nudged = () => map.project([points()[1]?.lon ?? 0, points()[1]?.lat ?? 0]);
    expect(nudged().x).toBeCloseTo(450 + NUDGE_PX, 6);
    await user.keyboard("{Shift>}{ArrowUp}{/Shift}");
    expect(nudged().y).toBeCloseTo(300 - NUDGE_FAST_PX, 6);
    expect(useMarkStore.getState().selected).toBe(1);
    await user.keyboard("[[");
    expect(useMarkStore.getState().selected).toBe(0);
    expect(handle(0)).toHaveFocus();
    expect(handle(0)).toHaveAttribute("tabindex", "0");
    await user.keyboard("{Delete}");
    expect(points()).toHaveLength(1);
    expect(map.project(point()).x).toBeCloseTo(450 + NUDGE_PX, 6);
  });

  it("puts focus on the neighbouring handle when the focused one is deleted, and on the cross's button when none is left", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    act(() => map.click(450, 300));
    act(() => map.click(500, 300));
    act(() => useMarkStore.getState().finish());
    // The last point: focus goes back to the one before it.
    handle(2).focus();
    await user.keyboard("{Delete}");
    expect(points()).toHaveLength(2);
    await waitFor(() => expect(handle(1)).toHaveFocus());
    // The first: focus goes to the one that took its place.
    handle(0).focus();
    await user.keyboard("{Delete}");
    expect(points()).toHaveLength(1);
    await waitFor(() => expect(handle(0)).toHaveFocus());
    // The only one: there are no handles left, and a point can be put down again at once.
    await user.keyboard("{Delete}");
    expect(points()).toHaveLength(0);
    const add = panel().getByRole("button", { name: "Add a point at the cross" });
    await waitFor(() => expect(add).toHaveFocus());
    expect(add).toBeEnabled();
  });

  it("closes the shape with a tap on the first point, or on its handle, or with the button", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(380, 280));
    act(() => map.click(420, 280));
    expect(panel().getByRole("button", { name: "Close the shape" })).toBeDisabled();
    act(() => map.click(440, 330));
    // A tap within reach of the first point closes it.
    act(() => map.click(389, 289));
    expect(useMarkStore.getState().shape.present.closed).toBe(true);
    expect(points()).toHaveLength(3);
    expect(panel().getByRole("status")).toHaveTextContent(/^A closed shape of 3 points, \d+ m round\.$/);
    expect(guidance()).toHaveTextContent("Drag a point to move it, and select one to change or delete it.");
    expect(screen.getByTestId("mark-path")).toHaveAttribute("data-shape", "polygon");
    // Closed, a tap adds nothing.
    act(() => map.click(500, 500));
    expect(points()).toHaveLength(3);

    // Undo opens it again; a tap on the first point's handle closes it.
    await user.click(panel().getByRole("button", { name: "Undo" }));
    expect(useMarkStore.getState().shape.present.closed).toBe(false);
    await user.click(handle(0));
    expect(useMarkStore.getState().shape.present.closed).toBe(true);

    await user.click(panel().getByRole("button", { name: "Undo" }));
    await user.click(panel().getByRole("button", { name: "Close the shape" }));
    expect(useMarkStore.getState().shape.present.closed).toBe(true);
  });

  it("draws a mixed path and closes it by keyboard alone", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    const add = panel().getByRole("button", { name: "Add a point at the cross" });
    add.focus();
    await user.keyboard("{Enter}");
    // The button stays put as the first point goes down, so focus stays on it.
    expect(panel().getByRole("button", { name: "Add a point at the cross" })).toBe(add);
    expect(add).toHaveFocus();
    act(() => map.userMove({ lng: map.getCenter().lng + 0.002 }));
    await user.keyboard("{Enter}");
    act(() => map.userMove({ lat: map.getCenter().lat + 0.002 }));
    // The next point is curved: the arrow keys move along the chips.
    panel().getByRole("radio", { name: "Straight" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(panel().getByRole("radio", { name: "Curved" })).toHaveAttribute("aria-checked", "true");
    add.focus();
    await user.keyboard("{Enter}");
    expect(points().map((each) => each.kind)).toEqual(["corner", "corner", "smooth"]);
    expect(add).toHaveFocus();
    panel().getByRole("radio", { name: "Curved" }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(panel().getByRole("radio", { name: "Straight" })).toHaveAttribute("aria-checked", "true");

    panel().getByRole("button", { name: "Close the shape" }).focus();
    await user.keyboard("{Enter}");
    expect(useMarkStore.getState().shape.present.closed).toBe(true);
    expect(panel().getByRole("button", { name: "Add a point at the cross" })).toBeDisabled();
  });

  it("makes the first point curved too when Curved is chosen before the second, so a ring closes smoothly", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    expect(points().map((each) => each.kind)).toEqual(["corner"]);

    await user.click(panel().getByRole("radio", { name: "Curved" }));
    expect(points().map((each) => each.kind)).toEqual(["smooth"]);
    act(() => map.click(450, 340));
    act(() => map.click(400, 380));
    await user.click(panel().getByRole("button", { name: "Close the shape" }));

    expect(useMarkStore.getState().shape.present.closed).toBe(true);
    expect(points().map((each) => each.kind)).toEqual(["smooth", "smooth", "smooth"]);
  });

  it("finishes with Enter on the map, then carries on from the start", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    act(() => map.click(450, 300));
    fireEvent.keyDown(map.getCanvas(), { key: "Enter" });
    expect(useMarkStore.getState().drawing).toBe(false);
    act(() => map.click(500, 300));
    expect(points()).toHaveLength(2);
    expect(guidance()).toHaveTextContent(/Select an end point and press “Continue from this end”/);

    await user.click(handle(0));
    expect(panel().getByText(/^Point 1 of 2, straight, SU \d{4} \d{4}$/)).toBeInTheDocument();
    await user.click(panel().getByRole("button", { name: "Continue from this end" }));
    // The map moves to that end, so carrying on from where you stopped is one press.
    expect(map.easeTo).toHaveBeenCalledWith({ center: [points()[0]?.lon, points()[0]?.lat] });
    expect(panel().getByRole("status")).toHaveTextContent(/at the west end\.$/);
    act(() => map.click(300, 300));
    expect(points()).toHaveLength(3);
    expect(map.project([points()[0]?.lon ?? 0, points()[0]?.lat ?? 0]).x).toBeCloseTo(300, 6);
  });

  it("adds the other kind with Shift-click, switches a point's kind with Shift-click on it, and inserts with Alt-click", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    act(() => map.click(450, 300, { shiftKey: true }));
    act(() => map.click(500, 300));
    expect(points().map((each) => each.kind)).toEqual(["corner", "smooth", "corner"]);
    await user.keyboard("{Shift>}");
    await user.click(handle(0));
    await user.keyboard("{/Shift}");
    expect(points()[0]?.kind).toBe("smooth");
    expect(useMarkStore.getState().selected).toBeNull();

    // An Alt-click near the line, between the first two points, puts a point there.
    act(() => map.click(425, 303, { altKey: true }));
    expect(points()).toHaveLength(4);
    expect(map.project([points()[1]?.lon ?? 0, points()[1]?.lat ?? 0]).x).toBeCloseTo(425, 6);
    // Away from the line it does nothing.
    act(() => map.click(425, 400, { altKey: true }));
    expect(points()).toHaveLength(4);
  });

  it("switches a point's kind with a long press on its handle, and the press doesn't then select it", async () => {
    const vibrate = vi.fn();
    Object.defineProperty(navigator, "vibrate", { value: vibrate, configurable: true });
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    const target = handle(0);
    fireEvent.pointerDown(target, { pointerId: 3, button: 0, pointerType: "touch", clientX: 400, clientY: 300 });
    // A finger's wobble under the 8 px slop is still a press.
    fireEvent.pointerMove(target, { pointerId: 3, pointerType: "touch", clientX: 407, clientY: 300 });
    expect(map.project(point()).x).toBeCloseTo(400, 6);
    await act(() => new Promise((resolve) => setTimeout(resolve, LONG_PRESS_MS + 50)));
    expect(points()[0]?.kind).toBe("smooth");
    expect(target).toHaveAttribute("data-kind", "smooth");
    expect(vibrate).toHaveBeenCalled();
    fireEvent.pointerUp(target, { pointerId: 3, pointerType: "touch", clientX: 407, clientY: 300 });
    fireEvent.click(target, { detail: 1 });
    expect(useMarkStore.getState().selected).toBeNull();
    // The point stayed where it was.
    expect(map.project(point()).x).toBeCloseTo(400, 6);
    // A press that moves is a drag, and switches nothing.
    fireEvent.pointerDown(target, { pointerId: 4, button: 0, pointerType: "touch", clientX: 400, clientY: 300 });
    fireEvent.pointerMove(target, { pointerId: 4, pointerType: "touch", clientX: 420, clientY: 300 });
    await act(() => new Promise((resolve) => setTimeout(resolve, LONG_PRESS_MS + 50)));
    fireEvent.pointerUp(target, { pointerId: 4, pointerType: "touch", clientX: 420, clientY: 300 });
    expect(points()[0]?.kind).toBe("smooth");
    expect(fireEvent.contextMenu(target)).toBe(false);
    Reflect.deleteProperty(navigator, "vibrate");
  });

  for (const pointerType of ["touch", "pen"] as const) {
    it(`drags a point once a ${pointerType} moves past 8 px, and switches nothing`, async () => {
      const { map } = await openMarking();
      act(() => map.click(400, 300));
      const target = handle(0);
      fireEvent.pointerDown(target, { pointerId: 5, button: 0, pointerType, clientX: 400, clientY: 300 });
      fireEvent.pointerMove(target, { pointerId: 5, pointerType, clientX: 409, clientY: 300 });
      await act(() => new Promise((resolve) => setTimeout(resolve, LONG_PRESS_MS + 50)));
      fireEvent.pointerUp(target, { pointerId: 5, pointerType, clientX: 409, clientY: 300 });
      expect(points()[0]?.kind).toBe("corner");
      expect(map.project(point()).x).toBeCloseTo(409, 6);
    });
  }

  it("never long-presses for a mouse: a pause before a drag still drags, and switches nothing", async () => {
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    const target = handle(0);
    fireEvent.pointerDown(target, { pointerId: 8, button: 0, pointerType: "mouse", clientX: 400, clientY: 300 });
    await act(() => new Promise((resolve) => setTimeout(resolve, LONG_PRESS_MS + 50)));
    expect(points()[0]?.kind).toBe("corner");
    fireEvent.pointerMove(target, { pointerId: 8, pointerType: "mouse", clientX: 460, clientY: 300 });
    fireEvent.pointerUp(target, { pointerId: 8, pointerType: "mouse", clientX: 460, clientY: 300 });
    expect(points()[0]?.kind).toBe("corner");
    expect(map.project(point()).x).toBeCloseTo(460, 6);
  });

  it("drags a point once a mouse moves past 3 px", async () => {
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    const target = handle(0);
    fireEvent.pointerDown(target, { pointerId: 6, button: 0, pointerType: "mouse", clientX: 400, clientY: 300 });
    fireEvent.pointerMove(target, { pointerId: 6, pointerType: "mouse", clientX: 404, clientY: 300 });
    fireEvent.pointerUp(target, { pointerId: 6, pointerType: "mouse", clientX: 404, clientY: 300 });
    expect(map.project(point()).x).toBeCloseTo(404, 6);
  });

  it("closes the shape on a finger's tap on the first point that wobbles up to 8 px, and moves nothing", async () => {
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    act(() => map.click(450, 300));
    act(() => map.click(450, 350));
    const target = handle(0);
    fireEvent.pointerDown(target, { pointerId: 7, button: 0, pointerType: "touch", clientX: 400, clientY: 300 });
    fireEvent.pointerMove(target, { pointerId: 7, pointerType: "touch", clientX: 406, clientY: 305 });
    fireEvent.pointerUp(target, { pointerId: 7, pointerType: "touch", clientX: 406, clientY: 305 });
    fireEvent.click(target, { detail: 1 });
    expect(useMarkStore.getState().shape.present.closed).toBe(true);
    expect(map.project(point()).x).toBeCloseTo(400, 6);
    expect(map.project(point()).y).toBeCloseTo(300, 6);
  });

  it("changes the selected point from its bar", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    act(() => map.click(450, 300));
    act(() => map.click(500, 300));
    await user.click(handle(1));
    const bar = within(panel().getByRole("region", { name: "Selected point" }));
    await user.click(bar.getByRole("button", { name: "Make it curved" }));
    expect(points()[1]?.kind).toBe("smooth");
    expect(bar.getByText(/^Point 2 of 3, curved/)).toBeInTheDocument();
    await user.click(bar.getByRole("button", { name: "Insert a point after" }));
    expect(points()).toHaveLength(4);
    expect(map.project([points()[2]?.lon ?? 0, points()[2]?.lat ?? 0]).x).toBeCloseTo(475, 0);
    expect(useMarkStore.getState().selected).toBe(2);
    await user.click(bar.getByRole("button", { name: "Next point" }));
    expect(useMarkStore.getState().selected).toBe(3);
    expect(bar.getByRole("button", { name: "Next point" })).toBeDisabled();
    expect(bar.getByRole("button", { name: "Insert a point after" })).toBeDisabled();
    await user.click(bar.getByRole("button", { name: "Previous point" }));
    await user.click(bar.getByRole("button", { name: "Delete point" }));
    expect(points()).toHaveLength(3);
    await user.click(bar.getByRole("button", { name: "Done" }));
    expect(panel().queryByRole("region", { name: "Selected point" })).toBeNull();
  });

  it("draws a long path with the map, not SVG, and keeps handles only for the ends and the selected point when many are in view", async () => {
    const { map } = await openMarking();
    const many: Path = {
      closed: false,
      points: Array.from({ length: SVG_MAX_POINTS + 1 }, (_, i) => {
        const at = map.unproject([100 + i * 4, 300 + (i % 2) * 4]);
        return { lon: at.lng, lat: at.lat, kind: "corner" as const };
      }),
    };
    act(() => useMarkStore.setState({ shape: history(many) }));
    expect(screen.queryByTestId("mark-path")).toBeNull();
    const data = map.sourceData(MARK_PATH_SOURCE) as { features: Array<{ geometry: { type: string } }> };
    expect(data.features).toHaveLength(1);
    expect(data.features[0]?.geometry.type).toBe("LineString");
    expect(SVG_MAX_POINTS + 1).toBeGreaterThan(HANDLES_MAX_IN_VIEW);
    expect(handles()).toHaveLength(2);
    expect(panel().getByRole("status")).toHaveTextContent(/Zoom in to change points\.$/);
  });
});

describe("the guidance", () => {
  it("names the keys once the map has keyboard focus", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    expect(guidance()).toHaveTextContent(/Shift-click adds the other kind of point/);
    handle(0).focus();
    await user.keyboard("{ArrowRight}");
    expect(guidance()).toHaveTextContent(/On a point, the arrow keys move it, Shift moves it further, \[ and \] step/);
  });

  it("says tap on a phone, and names the long press", async () => {
    usePhoneLayout();
    const { map } = await openMarking();
    expect(guidance()).toHaveTextContent("Tap the map where the feature is. One tap marks a spot.");
    expect(guidance()).toHaveTextContent("Press and hold a point to switch it between straight and curved.");
    // The drawing bar floats above the sheet's peek stop, outside the sheet.
    const floating = screen.getByRole("region", { name: "Drawing" });
    expect(panel().queryByRole("region", { name: "Drawing" })).toBeNull();
    act(() => map.click(400, 300));
    expect(within(floating).getByRole("status")).toHaveTextContent("1 point. Tap again to draw a line from it.");
    expect(guidance()).toHaveTextContent(/This is a spot\. Tap again/);
    // Once drawing stops the bars move into the sheet, which rises for the form, and the map is clear again.
    fireEvent.click(within(floating).getByRole("button", { name: "Finish" }));
    expect(screen.queryByRole("region", { name: "Drawing" })).toBe(panel().getByRole("region", { name: "Drawing" }));
    await waitFor(() =>
      expect(screen.getByRole("complementary", { name: "Mark a finding" })).toHaveAttribute("data-stop", "half"),
    );
  });

  it("invites a spot of a linear class to carry on into a line", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    fireEvent.keyDown(handle(0), { key: "Escape" });
    await user.click(panel().getByRole("radio", { name: /^Road/ }));
    await user.click(panel().getByRole("button", { name: "Draw it as a line" }));
    expect(useMarkStore.getState().drawing).toBe(true);
    act(() => map.click(450, 300));
    expect(points()).toHaveLength(2);
    expect(panel().queryByText(/A feature like this runs along the ground/)).toBeNull();
  });
});

describe("the form", () => {
  it("asks only for the class, explains a protected class's level, and carries the finds notice", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("button", { name: "Save finding" }));
    expect(panel().getByRole("alert")).toHaveTextContent("Choose what it looks like.");

    await user.click(panel().getByRole("radio", { name: "Round barrow or mound" }));
    expect(panel().queryByText("Choose what it looks like.")).toBeNull();
    expect(panel().getByText(/only signed-in members will see exactly where it is/)).toBeInTheDocument();
    await user.click(panel().getByRole("radio", { name: "Enclosure" }));
    expect(panel().queryByText(/only signed-in members/)).toBeNull();

    expect(panel().getByText(/This map is for earthworks, not objects/)).toBeInTheDocument();
    expect(panel().getByLabelText("Period")).toHaveValue("unknown");
    expect(panel().getByLabelText("Title")).toHaveAttribute(
      "placeholder",
      expect.stringMatching(/^Enclosure in SU \d{2} \d{2}$/),
    );
  });
});

describe("saving, signed in", () => {
  it("shows the mark at once, sends what the finder was looking at, and opens the finding's page", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking();
    let answer: (response: Response) => void = () => {};
    routes.on(
      "POST /findings",
      (call) =>
        new Promise<Response>((resolve) => {
          answer = resolve;
          void call;
        }),
    );
    act(() => useMapStore.getState().setSun({ azimuth: 120, altitude: 15 }));
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("radio", { name: "Enclosure" }));
    await user.type(panel().getByLabelText("Note (optional)"), "Faint ring by the barn.");
    await user.click(panel().getByRole("button", { name: "Save finding" }));

    // Optimistic: on the map before the server has answered.
    expect(await screen.findByRole("img", { name: /^Enclosure in SU \d{2} \d{2}, saving$/ })).toBeInTheDocument();
    const [call] = routes.callsTo("POST /findings");
    const body = call?.body as FindingCreate;
    expect(body).toMatchObject({
      location: { type: "Point", coordinates: point() },
      feature_class: "enclosure",
      period: "unknown",
      title: expect.stringMatching(/^Enclosure in SU \d{2} \d{2}$/),
      description: "Faint ring by the barn.",
      view_state: { layer: "composite", sun_azimuth: 120, sun_altitude: 15, zoom: 14, bearing: 0, pitch: 0 },
    });

    expect(body.client_ref).toEqual(expect.any(String));

    act(() => answer(json(createdFinding(body, "abc123"), 201)));
    await waitFor(() => expect(address()).toBe("/f/abc123"));
    await waitFor(() => expect(usePendingFindings.getState().pending).toEqual([]));
    expect(routes.callsTo("POST /findings")).toHaveLength(1);
  });

  it("sends two points or more as a path with no location, and the server chooses the anchor", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking();
    routes.on("POST /findings", (call) => json(createdFinding(call.body as FindingCreate, "bank1"), 201));
    act(() => map.click(400, 300));
    act(() => map.click(450, 300, { shiftKey: true }));
    act(() => map.click(500, 320));
    await user.click(panel().getByRole("radio", { name: "Linear bank or ditch" }));
    const drawn = points();
    await user.click(panel().getByRole("button", { name: "Save finding" }));
    await waitFor(() => expect(address()).toBe("/f/bank1"));
    const body = routes.callsTo("POST /findings")[0]?.body as FindingCreate;
    expect(body).not.toHaveProperty("location");
    expect(body).not.toHaveProperty("outline");
    expect(body.path).toEqual({ closed: false, points: drawn });
    expect(body.path?.points.map((each) => each.kind)).toEqual(["corner", "smooth", "corner"]);
    expect(body.title).toMatch(/^Linear bank or ditch in SU \d{2} \d{2}$/);
  });

  it("says beside the drawing tool when the server refuses the shape", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking();
    routes.on("POST /findings", () =>
      apiError(422, "shape_crosses_itself", "A closed shape's edge can't cross itself."),
    );
    act(() => map.click(400, 300));
    act(() => map.click(450, 350));
    act(() => map.click(450, 300));
    act(() => map.click(400, 350));
    await user.click(panel().getByRole("button", { name: "Close the shape" }));
    await user.click(panel().getByRole("radio", { name: "Enclosure" }));
    await user.click(panel().getByRole("button", { name: "Save finding" }));
    expect(await panel().findByRole("alert")).toHaveTextContent("A closed shape's edge can't cross itself.");
    // Moving a point is a change to the shape, which clears it.
    act(() => useMarkStore.getState().move(3, [points()[3]?.lon ?? 0, (points()[3]?.lat ?? 0) + 0.001]));
    expect(panel().queryByRole("alert")).toBeNull();
  });

  it("takes the mark back when the server refuses the place, says why and what to do, and keeps the form", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking();
    routes.on("POST /findings", () => apiError(422, "outside_british_isles", "That position is outside them."));
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("radio", { name: "Moat" }));
    await user.type(panel().getByLabelText("Title"), "Square moat");
    await user.click(panel().getByRole("button", { name: "Save finding" }));

    const toast = await screen.findByText(/Your finding couldn't be saved\. OpenAntiquity covers the land/);
    expect(usePendingFindings.getState().pending).toEqual([]);
    expect(screen.queryByRole("img", { name: /saving$/ })).toBeNull();
    expect(address()).toBe("/mark");
    expect(panel().getByRole("radio", { name: "Moat" })).toHaveAttribute("aria-checked", "true");
    expect(panel().getByLabelText("Title")).toHaveValue("Square moat");
    expect(panel().getByRole("alert")).toHaveTextContent(/Move the mark onto it/);
    // Sending the same place again would be refused the same way, so the toast doesn't offer it.
    const toastBox = toast.closest(".fc-toast") as HTMLElement;
    expect(within(toastBox).queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("says beside the title when the server refuses one that says where a protected finding is", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking();
    routes.on("POST /findings", () =>
      json(
        {
          error: {
            code: "position_in_text",
            message: "A protected finding's title and description can't say where it is.",
            details: [{ field: "body.title", message: "The title gives a position finer than the 1 km square." }],
          },
        },
        422,
      ),
    );
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("radio", { name: "Round barrow or mound" }));
    await user.type(panel().getByLabelText("Title"), "Barrow at SU 1025 6996");
    await user.click(panel().getByRole("button", { name: "Save finding" }));

    const title = panel().getByLabelText("Title");
    await waitFor(() => expect(title).toHaveAttribute("aria-invalid", "true"));
    await waitFor(() => expect(title).toHaveFocus());
    expect(
      panel().getByText(/Take the grid reference, coordinates or three-word address out of the title\./),
    ).toBeInTheDocument();
    expect(panel().getByLabelText("Note (optional)")).not.toHaveAttribute("aria-invalid");
    const toast = await screen.findByText(/Your finding couldn't be saved\./);
    expect(within(toast.closest(".fc-toast") as HTMLElement).queryByRole("button", { name: "Try again" })).toBeNull();
    await user.type(title, "!");
    expect(title).not.toHaveAttribute("aria-invalid");
  });

  it("says beside the note when a draft saved after sign-in was refused for a position in it", async () => {
    const draft = findingDrafts.put({
      point: [-1.8542, 51.4286],
      feature_class: "round_barrow",
      period: "unknown",
      title: "Round barrow or mound in SU 10 69",
      description: "Clearest at SU 1025 6996",
      path: null,
      view_state: {},
    });
    updateDrafts((drafts) =>
      drafts.map((each) => ({
        ...each,
        state: "failed",
        failure: { code: "position_in_text", message: "It says where it is.", fields: ["body.description"] },
      })),
    );
    // Made before a provider's sign-in from this tab, which sends the person back here.
    noteSignInStarted("provider");
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    renderShell(`/mark/${draft.id}`);
    await mapReady();
    const note = await panel().findByLabelText("Note (optional)");
    await waitFor(() => expect(note).toHaveAttribute("aria-invalid", "true"));
    expect(panel().getByText(/out of the note\./)).toBeInTheDocument();
    expect(panel().getByLabelText("Title")).not.toHaveAttribute("aria-invalid");
  });

  it("offers to try again after a failure that may pass, and sends the same finding", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking();
    routes.on("POST /findings", () => apiError(503, "unavailable", "The server is busy."));
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("radio", { name: "Moat" }));
    await user.click(panel().getByRole("button", { name: "Save finding" }));
    const toast = await screen.findByText(/Your finding couldn't be saved\. The server is busy\./);

    routes.on("POST /findings", (call) => json(createdFinding(call.body as FindingCreate, "moat1"), 201));
    const toastBox = toast.closest(".fc-toast") as HTMLElement;
    await user.click(within(toastBox).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(address()).toBe("/f/moat1"));
    const [first, second] = routes.callsTo("POST /findings").map((call) => (call.body as FindingCreate).client_ref);
    expect(routes.callsTo("POST /findings")).toHaveLength(2);
    // Tried again, it is the same finding to the server, so a save that went through unheard isn't made twice.
    expect(second).toBe(first);
  });
});

describe("a draft kept before paths", () => {
  it("opens with its outline as an all-corner path, and saves it as a path", async () => {
    const user = userEvent.setup();
    const ring = [
      [-1.855, 51.428],
      [-1.853, 51.428],
      [-1.853, 51.43],
      [-1.855, 51.428],
    ];
    // Stored by the outline tool: a placed point and an outline, and no path.
    const kept = findingDrafts.put({
      point: [-1.8542, 51.4286],
      path: null,
      feature_class: "enclosure",
      period: "unknown",
      title: "Enclosure in SU 10 69",
      description: null,
      view_state: {},
    });
    updateDrafts((drafts) =>
      drafts.map((each) => {
        const { path: _path, ...old } = each.data as Record<string, unknown>;
        return { ...each, data: { ...old, outline: { type: "Polygon", coordinates: [ring] } } };
      }),
    );
    // Made before a provider's sign-in from this tab, so it waits for Save (Decision 0024).
    noteSignInStarted("provider");
    const routes = routeApi(harness.fetchMock(), {
      "GET /auth/me": () => json(meFixture()),
      "POST /findings": (call) => json(createdFinding(call.body as FindingCreate, "ring1"), 201),
    });
    renderShell(`/mark/${kept.id}`, <Address />);
    await mapReady();
    await panel().findByRole("button", { name: "Save finding" });
    expect(useMarkStore.getState().shape.present).toEqual({
      closed: true,
      points: ring.slice(0, -1).map(([lon, lat]) => ({ lon, lat, kind: "corner" })),
    });
    expect(handles()).toHaveLength(3);
    expect(panel().getByRole("status")).toHaveTextContent(/^A closed shape of 3 points/);

    await user.click(panel().getByRole("button", { name: "Save finding" }));
    await waitFor(() => expect(routes.callsTo("POST /findings")).toHaveLength(1));
    const body = routes.callsTo("POST /findings")[0]?.body as FindingCreate;
    expect(body.path?.closed).toBe(true);
    expect(body.path?.points).toHaveLength(3);
    expect(body).not.toHaveProperty("location");
    expect(body).not.toHaveProperty("outline");
    await waitFor(() => expect(address()).toBe("/f/ring1"));
  });
});

function SignInHere() {
  const client = useQueryClient();
  return (
    <button type="button" onClick={() => signedIn(client, meFixture())}>
      Sign in for the test
    </button>
  );
}

describe("the person changing", () => {
  it("keeps a new marking, which is the person's own and no saved finding's", async () => {
    const user = userEvent.setup();
    const routes = routeApi(harness.fetchMock(), { "GET /auth/me": () => signedOutResponse() });
    renderShell("/mark", <SignInHere />);
    const map = await mapReady();
    act(() => map.click(400, 300));
    act(() => useMarkStore.getState().setTitle("Drawn before signing in"));
    routes.on("GET /auth/me", () => json(meFixture()));
    await user.click(screen.getByRole("button", { name: "Sign in for the test" }));
    await screen.findByRole("button", { name: "Save finding" });
    expect(points()).toHaveLength(1);
    expect(useMarkStore.getState().title).toBe("Drawn before signing in");
  });

  it("takes up again a draft still open in the panel once the store has forgotten it", async () => {
    const draft = findingDrafts.put({
      point: [-1.8542, 51.4286],
      feature_class: "round_barrow",
      period: "unknown",
      title: "Round barrow or mound in SU 10 69",
      description: "",
      path: null,
      view_state: {},
    });
    routeApi(harness.fetchMock(), { "GET /auth/me": () => signedOutResponse() });
    renderShell(`/mark/${draft.id}`);
    await mapReady();
    await panel().findByRole("button", { name: "Save finding" });
    // What the store does when the person changes.
    act(() => useMarkStore.getState().start());
    await waitFor(() => expect(useMarkStore.getState().draftId).toBe(draft.id));
    expect(await panel().findByRole("button", { name: "Save finding" })).toBeInTheDocument();
    expect(points()).toHaveLength(1);
  });
});

/** True when leaving the page now would bring up the browser's "leave this page?". */
function asksBeforeLeaving(): boolean {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

describe("leaving the page with a line drawn", () => {
  it("asks once a line of two points is drawn, and not once it is kept as a draft", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking(false);
    expect(asksBeforeLeaving()).toBe(false);
    act(() => map.click(400, 300));
    expect(asksBeforeLeaving()).toBe(false);
    act(() => map.click(450, 300));
    expect(asksBeforeLeaving()).toBe(true);
    await user.click(panel().getByRole("radio", { name: "Hillfort" }));
    await user.click(panel().getByRole("button", { name: "Save finding" }));
    expect(await screen.findByRole("dialog", { name: "Sign in" })).toBeInTheDocument();
    expect(asksBeforeLeaving()).toBe(false);
    // A change to the draft isn't kept until it is saved again.
    await user.click(within(screen.getByRole("dialog", { name: "Sign in" })).getByRole("button", { name: "Close" }));
    act(() => useMarkStore.getState().move(1, [points()[1]?.lon ?? 0, (points()[1]?.lat ?? 0) + 0.001]));
    expect(asksBeforeLeaving()).toBe(true);
  });

  it("doesn't ask once the line is saved", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking();
    routes.on("POST /findings", (call) => json(createdFinding(call.body as FindingCreate, "abc123"), 201));
    act(() => map.click(400, 300));
    act(() => map.click(450, 300));
    expect(asksBeforeLeaving()).toBe(true);
    await user.click(panel().getByRole("radio", { name: "Hillfort" }));
    await user.click(panel().getByRole("button", { name: "Save finding" }));
    await waitFor(() => expect(address()).toBe("/f/abc123"));
    expect(asksBeforeLeaving()).toBe(false);
  });
});

describe("saving, signed out", () => {
  it("sends a draft taken over at sign-in when Save is pressed on its own form", async () => {
    const user = userEvent.setup();
    const draft = findingDrafts.put({
      point: [-1.8542, 51.4286],
      feature_class: "round_barrow",
      period: "unknown",
      title: "Round barrow or mound in SU 10 69",
      description: "",
      path: null,
      view_state: {},
    });
    // Made before a provider's sign-in from this tab, which sends the person back here.
    noteSignInStarted("provider");
    const routes = routeApi(harness.fetchMock(), {
      "GET /auth/me": () => json(meFixture()),
      "POST /findings": (call) => json(createdFinding(call.body as FindingCreate, "abc123"), 201),
    });
    renderShell(`/mark/${draft.id}`, <Address />);
    await mapReady();

    // Taken over and held: nothing is sent until the person says so (Decision 0024).
    const save = await panel().findByRole("button", { name: "Save finding" });
    await waitFor(() => expect(listDrafts()[0]?.held).toBe(true));
    expect(routes.callsTo("POST /findings")).toHaveLength(0);

    // Pressing Save on the draft's own form is the person saying so.
    await user.click(save);
    await waitFor(() => expect(routes.callsTo("POST /findings")).toHaveLength(1));
    await waitFor(() => expect(address()).toBe("/f/abc123"));
    expect(listDrafts()).toEqual([]);
  });

  it("keeps it as a draft at its own address and opens the sign-in sheet, sending nothing", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking(false);
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("radio", { name: "Hillfort" }));
    await user.click(panel().getByRole("button", { name: "Save finding" }));

    expect(await screen.findByRole("dialog", { name: "Sign in" })).toBeInTheDocument();
    const [draft] = listDrafts();
    expect(draft).toMatchObject({ kind: "finding", data: { feature_class: "hillfort", point: point() } });
    expect(address()).toBe(`/mark/${draft?.id}`);
    expect(window.localStorage.getItem(DRAFTS_STORAGE_KEY)).toContain("hillfort");
    expect(routes.callsTo("POST /findings")).toHaveLength(0);

    // Closing the sheet keeps the draft, marked as not saved yet.
    await user.click(within(screen.getByRole("dialog", { name: "Sign in" })).getByRole("button", { name: "Close" }));
    expect(panel().getByText("Not saved yet", { selector: ".fc-draft-badge" })).toBeInTheDocument();
    expect(await screen.findByText(/Kept in this browser as a draft until you sign in/)).toBeInTheDocument();
  });
});
