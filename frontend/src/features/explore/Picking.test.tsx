import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useFindingHighlight } from "../../map/findingHighlight.js";
import {
  FINDING_HIGHLIGHT_LAYERS,
  FINDING_POINT_LAYERS,
  FINDING_SHAPE_LAYERS,
  RECORD_LAYERS,
} from "../../map/overlayLayers.js";
import type { FakeMap } from "../../test/fakeMapLibre.js";
import { json, mapReady, renderShell, setUpShellTests, usePhoneLayout } from "../../test/shellHarness.js";
import { useSelectedFinding } from "../findings/selection.js";

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
  useSelectedFinding.getState().clear();
  useFindingHighlight.setState({ publicId: null });
});

const TAP = { x: 300, y: 200 };
const RECORD = { id: 101, properties: { id: 101, source: "nhle-scheduled" }, layer: { id: RECORD_LAYERS.squares } };

/** Findings the server sends, with titles the chooser names them by. */
const FINDINGS = [
  { id: "road-a", title: "Roman road by the down", feature_class: "road", tier: "probable" },
  { id: "road-b", title: "Hollow way to the ford", feature_class: "trackway", tier: "seen" },
  { id: "barrow", title: "Bowl barrow on the ridge", feature_class: "round_barrow", tier: "spotted" },
  { id: "field", title: "Field system on the slope", feature_class: "field_system", tier: "seen" },
];

function serveFindings(): void {
  harness.answer("/findings", () =>
    json({
      type: "FeatureCollection",
      features: FINDINGS.map(({ id, title, feature_class, tier }, index) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [-1.85 + index * 0.001, 51.43] },
        properties: { public_id: id, title, feature_class, tier, state: "open", obscured: false },
      })),
    }),
  );
}

function line(id: string, size: number, at = TAP) {
  return { properties: { public_id: id, shape: "line", size }, layer: { id: FINDING_SHAPE_LAYERS.lines }, at };
}

function areaEdge(id: string, size: number, at = TAP) {
  return { properties: { public_id: id, shape: "area", size }, layer: { id: FINDING_SHAPE_LAYERS.areaEdges }, at };
}

function marker(id: string, map: FakeMap, at = TAP) {
  const ground = map.unproject([at.x, at.y]);
  return {
    properties: { public_id: id },
    layer: { id: FINDING_POINT_LAYERS.points },
    geometry: { type: "Point", coordinates: [ground.lng, ground.lat] },
    at,
  };
}

function tap(map: FakeMap, pointerType: "mouse" | "touch" = "mouse", at = TAP): void {
  act(() => map.click(at.x, at.y, { pointerType }));
}

async function openMap() {
  serveFindings();
  renderShell("/?panel=none", <Address />);
  const map = await mapReady();
  // The chooser names findings by what the overlay drew.
  await waitFor(() => expect(harness.requestsTo("/findings")).toBeGreaterThan(0));
  await act(async () => new Promise((resolve) => setTimeout(resolve, 0)));
  return map;
}

function chooser() {
  return screen.getByRole("dialog", { name: /findings here$/ });
}

describe("picking one of overlapping findings", () => {
  it("opens the one finding in reach at once", async () => {
    const map = await openMap();
    map.rendered = [line("road-a", 5000)];
    tap(map);
    await waitFor(() => expect(address()).toBe("/f/road-a"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens the chooser between two alike, names each, highlights the focused one, and opens the one chosen", async () => {
    const user = userEvent.setup();
    const map = await openMap();
    map.rendered = [line("road-a", 5000), line("road-b", 4000)];
    tap(map);
    const dialog = within(await screen.findByRole("dialog", { name: "2 findings here" }));
    const entries = dialog.getAllByRole("button", { name: /, / });
    expect(entries.map((entry) => entry.getAttribute("aria-label"))).toEqual([
      "Hollow way to the ford, Seen by others, Trackway or hollow way",
      "Roman road by the down, Probable, Road",
    ]);
    // The first entry has focus, and its shape is highlighted on the map.
    expect(entries[0]).toHaveFocus();
    expect(useFindingHighlight.getState().publicId).toBe("road-b");
    await waitFor(() => expect(JSON.stringify(map.filters.get(FINDING_HIGHLIGHT_LAYERS.shape))).toContain('"road-b"'));
    await user.keyboard("{ArrowDown}");
    expect(entries[1]).toHaveFocus();
    expect(useFindingHighlight.getState().publicId).toBe("road-a");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(address()).toBe("/f/road-a"));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(useFindingHighlight.getState().publicId).toBeNull();
  });

  it("closes the chooser with Escape and puts focus back on the map", async () => {
    const user = userEvent.setup();
    const map = await openMap();
    map.getCanvas().tabIndex = 0;
    map.rendered = [line("road-a", 5000), line("road-b", 4000)];
    tap(map);
    await screen.findByRole("dialog", { name: "2 findings here" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(map.getCanvas()).toHaveFocus());
    expect(address()).toBe("/");
  });

  it("gives a mouse a narrow reach, so a road 10 px off is out of it", async () => {
    const map = await openMap();
    // One road under the tap and another 10 px off: in a finger's reach, out of a mouse's.
    map.rendered = [line("road-a", 5000), line("road-b", 4000, { x: TAP.x + 10, y: TAP.y })];
    tap(map, "mouse");
    await waitFor(() => expect(address()).toBe("/f/road-a"));
  });

  it("gives a finger a wider reach, so at the same spot it is offered both roads", async () => {
    const map = await openMap();
    map.rendered = [line("road-a", 5000), line("road-b", 4000, { x: TAP.x + 10, y: TAP.y })];
    tap(map, "touch");
    expect(await screen.findByRole("dialog", { name: "2 findings here" })).toBeInTheDocument();
  });

  it("lets a marker inside an area win over the area's edge", async () => {
    const map = await openMap();
    map.rendered = [areaEdge("field", 1e6, { x: TAP.x + 10, y: TAP.y }), marker("barrow", map)];
    tap(map, "touch");
    await waitFor(() => expect(address()).toBe("/f/barrow"));
  });

  it("opens nothing of an area tapped away from its edge", async () => {
    const map = await openMap();
    map.rendered = [areaEdge("field", 1e6, { x: TAP.x + 60, y: TAP.y })];
    tap(map, "touch");
    await act(async () => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(address()).toBe("/");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("lets a finding in reach win over a record under the tap", async () => {
    const map = await openMap();
    map.rendered = [RECORD, line("road-a", 5000, { x: TAP.x + 10, y: TAP.y })];
    tap(map, "touch");
    await waitFor(() => expect(address()).toBe("/f/road-a"));
  });

  it("leaves a record to open as before when no finding is in reach", async () => {
    const map = await openMap();
    map.rendered = [RECORD, line("road-a", 5000, { x: TAP.x + 40, y: TAP.y })];
    tap(map, "touch");
    await waitFor(() => expect(address()).toBe("/r/101"));
  });

  it("lists at most eight, then offers them all in Explore", async () => {
    const user = userEvent.setup();
    const map = await openMap();
    map.rendered = Array.from({ length: 10 }, (_, index) => marker(`f-${index}`, map, { x: TAP.x + index, y: TAP.y }));
    tap(map, "touch");
    const dialog = within(await screen.findByRole("dialog", { name: "10 findings here" }));
    expect(dialog.getAllByRole("listitem")).toHaveLength(8);
    await user.click(dialog.getByRole("button", { name: "Show all in Explore" }));
    await waitFor(() => expect(address()).toBe("/"));
    expect(await screen.findByRole("complementary", { name: "Explore" })).toBeInTheDocument();
  });

  it("is a short sheet on a phone, on the side of the screen away from the tap", async () => {
    usePhoneLayout();
    const map = await openMap();
    const at = { x: 100, y: 80 };
    map.rendered = [line("road-a", 5000, at), line("road-b", 4000, at)];
    tap(map, "touch", at);
    await screen.findByRole("dialog", { name: "2 findings here" });
    expect(chooser()).toHaveClass("fc-chooser--sheet");
    expect(chooser()).toHaveAttribute("data-place", "sheet-bottom");
  });
});

describe("the pointer on a computer", () => {
  async function rest(map: FakeMap): Promise<void> {
    act(() => map.fire("mousemove", { point: TAP, lngLat: map.unproject([TAP.x, TAP.y]), originalEvent: {} }));
    await act(async () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
  }

  it("highlights what a click would open, or says how many a click would offer", async () => {
    const map = await openMap();
    map.rendered = [line("road-a", 5000)];
    await rest(map);
    expect(useFindingHighlight.getState().publicId).toBe("road-a");
    expect(map.getCanvas()).toHaveClass("fc-canvas--finding");

    map.rendered = [line("road-a", 5000), line("road-b", 4000), areaEdge("field", 1e6)];
    await rest(map);
    expect(useFindingHighlight.getState().publicId).toBeNull();
    expect(screen.getByText("3 findings here")).toBeInTheDocument();

    map.rendered = [];
    await rest(map);
    expect(screen.queryByText("3 findings here")).toBeNull();
    expect(map.getCanvas()).not.toHaveClass("fc-canvas--finding");
  });
});

describe("the Explore list", () => {
  it("highlights a finding's shape on the map while its row has focus", async () => {
    renderShell("/");
    await mapReady();
    const list = await screen.findByRole("list", { name: "Findings in view" });
    const [row] = await within(list).findAllByRole("link");
    if (!row) throw new Error("The list is empty");
    const publicId = row.getAttribute("href")?.replace("/f/", "");
    fireEvent.focus(row);
    expect(useFindingHighlight.getState().publicId).toBe(publicId);
    fireEvent.blur(row);
    expect(useFindingHighlight.getState().publicId).toBeNull();
  });
});
