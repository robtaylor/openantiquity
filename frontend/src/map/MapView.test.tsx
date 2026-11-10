import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FakeMap } from "../test/fakeMapLibre.js";
import { metaFixture } from "../test/fixtures/meta.js";
import { liveMaps, mapReady, metaResponse, renderShell, setUpShellTests } from "../test/shellHarness.js";
import { TERRAIN_SETTLE_MS } from "./MapPane.js";
import { SWIPE_MARGIN } from "./MapView.js";
import { useMapStore } from "./store.js";
import { viewLayerId } from "./style.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

afterEach(() => {
  vi.useRealTimers();
});

async function startComparing(): Promise<{ main: FakeMap; compare: FakeMap }> {
  const main = await mapReady();
  act(() => useMapStore.getState().toggleCompare());
  await waitFor(() => expect(liveMaps()).toHaveLength(2));
  const compare = liveMaps()[1] as FakeMap;
  // The second map is handed over, and the two are linked, once its style is in.
  await waitFor(() => expect(compare.listenerCount("move")).toBeGreaterThan(0));
  return { main, compare };
}

/** Count how many times the camera in the store changes while `action` runs. */
function cameraWrites(action: () => void): number {
  let writes = 0;
  const stop = useMapStore.subscribe((next, previous) => {
    if (next.camera !== previous.camera) writes += 1;
  });
  try {
    action();
  } finally {
    stop();
  }
  return writes;
}

describe("comparing two layers", () => {
  it("survives being switched off in the same breath as the second map finishes loading", async () => {
    renderShell("/?panel=layers");
    const main = await mapReady();

    // Hold the second map's style back, so the test decides when it arrives.
    FakeMap.autoStyle = false;
    act(() => useMapStore.getState().toggleCompare());
    const compare = liveMaps()[1];
    if (!compare) throw new Error("The comparison map was not created");

    // A double press: the style arrives, and the comparison is switched off before React has drawn again.
    act(() => {
      compare.fire("styledata", { dataType: "style" });
      useMapStore.getState().toggleCompare();
    });

    expect(compare.removed).toBe(true);
    expect(main.removed).toBe(false);
    expect(liveMaps()).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Layers" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("goes quiet on a map it has removed, whatever that map fires afterwards", async () => {
    renderShell();
    const { main, compare } = await startComparing();
    act(() => useMapStore.getState().toggleCompare());
    expect(compare.removed).toBe(true);
    // MapLibre keeps calling the listeners of a removed map. None of them may touch it.
    expect(() => {
      compare.fire("move");
      compare.fire("moveend");
      compare.fire("sourcedata", { sourceId: "overlay-findings", isSourceLoaded: true });
      compare.fire("error", { sourceId: "overlay-records", error: { status: 500 } });
      compare.fire("styledata", { dataType: "style" });
    }).not.toThrow();
    // And the surviving map is no longer tied to it.
    const before = compare.jumpTo.mock.calls.length;
    act(() => main.userMove({ zoom: 11 }));
    expect(compare.jumpTo.mock.calls.length).toBe(before);
  });

  it("records the camera once per gesture, whichever side is dragged", async () => {
    renderShell();
    const { main, compare } = await startComparing();
    const frames = Array.from({ length: 30 }, (_, i) => ({ lng: -1.85 - i * 0.001 }));

    // Dragging the right-hand map used to write the camera to the store on every frame.
    expect(cameraWrites(() => act(() => compare.userDrag(frames)))).toBe(1);
    expect(main.getCenter().lng).toBeCloseTo(-1.879, 6);
    expect(useMapStore.getState().camera.lng).toBeCloseTo(-1.879, 6);

    expect(cameraWrites(() => act(() => main.userDrag(frames.map((frame) => ({ lng: frame.lng + 0.5 })))))).toBe(1);
    expect(compare.getCenter().lng).toBeCloseTo(-1.379, 6);
    expect(useMapStore.getState().camera.lng).toBeCloseTo(-1.379, 6);
  });

  it("keeps the divide's grip inside the map, and tells the handle how far it may go", async () => {
    // jsdom lays nothing out, so the map is as wide as the window: 1024, less the 56 px rail.
    renderShell();
    await startComparing();
    const usable = window.innerWidth - 56;
    const least = Math.round((SWIPE_MARGIN / usable) * 100);
    const divide = screen.getByRole("slider", { name: "Comparison divide" });
    expect(divide).toHaveAttribute("aria-valuemin", String(least));
    expect(divide).toHaveAttribute("aria-valuemax", String(100 - least));

    divide.focus();
    fireEvent.keyDown(divide, { key: "Home" });
    expect(useMapStore.getState().swipe).toBeCloseTo(SWIPE_MARGIN / usable, 6);
    expect(divide).toHaveAttribute("aria-valuenow", String(least));
    fireEvent.keyDown(divide, { key: "End" });
    expect(useMapStore.getState().swipe).toBeCloseTo(1 - SWIPE_MARGIN / usable, 6);

    // A drag past the edge stops at the same limit.
    fireEvent.pointerDown(divide, { pointerId: 1, clientX: 500 });
    fireEvent.pointerMove(divide, { pointerId: 1, clientX: -200 });
    expect(useMapStore.getState().swipe).toBeCloseTo(SWIPE_MARGIN / usable, 6);
    fireEvent.pointerUp(divide, { pointerId: 1 });

    // At the left limit there is no room for the left-hand layer's name, so it is left out.
    const labels = document.querySelectorAll(".fc-swipe__label");
    expect([...labels].map((label) => label.textContent)).toEqual(["OpenStreetMap"]);
  });
});

describe("a fault in the map", () => {
  it("is shown in place of the map, leaves the shell standing, and can be recovered from", async () => {
    const user = userEvent.setup();
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    renderShell();
    const map = await mapReady();

    // A style that has lost a layer makes the next change of view throw inside React.
    map.dropLayer(viewLayerId("slope"));
    act(() => useMapStore.getState().setMainView("slope"));

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The map has stopped");
    expect(alert).toHaveTextContent(`The map has no layer "${viewLayerId("slope")}"`);
    expect(error).toHaveBeenCalled();
    expect(map.removed).toBe(true);
    // Everything around the map is still there.
    expect(screen.getByRole("navigation", { name: "Modes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark a finding" })).toBeInTheDocument();
    expect(screen.getByTestId("status-gridref")).toBeInTheDocument();

    await user.click(within(alert).getByRole("button", { name: "Start the map again" }));
    const again = await mapReady();
    expect(again).not.toBe(map);
    expect(again.isVisible(viewLayerId("slope"))).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says the layer catalogue is at fault when MapLibre refuses the style built from it", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    FakeMap.autoStyle = false;
    renderShell();
    await waitFor(() => expect(liveMaps()).toHaveLength(1));
    const map = liveMaps()[0] as FakeMap;
    // MapLibre reports a style it will not load as an error with no source, and never fires "styledata".
    act(() => map.fire("error", { error: { message: "layers.records-squares.paint.icon-color: color expected" } }));
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The map's layers couldn't be set up");
    expect(alert).toHaveTextContent("icon-color: color expected");
    expect(alert).not.toHaveTextContent("WebGL");
    expect(within(alert).getByRole("button", { name: "Reload the page" })).toBeInTheDocument();
  });

  it("says the layer catalogue is at fault, not the browser, when no style can be built from it", async () => {
    // A tile address that is neither absolute nor root-relative gets past parseMeta and stops buildStyle.
    const meta = structuredClone(metaFixture);
    const view = meta.layers.views[0];
    if (view?.type !== "raster") throw new Error("The fixture's first view should be a raster view");
    view.tiles = ["tiles/lidar/{z}/{x}/{y}.png"];
    harness.fetchMock().mockImplementationOnce(async () => metaResponse(meta));
    renderShell();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The map's layers couldn't be set up");
    expect(alert).toHaveTextContent("neither absolute nor root-relative");
    expect(alert).not.toHaveTextContent("WebGL");
    expect(FakeMap.instances).toHaveLength(0);
  });

  it("blames the browser when the map cannot get a graphics context, and can try again", async () => {
    const user = userEvent.setup();
    FakeMap.failNext = new Error("Failed to initialize WebGL");
    renderShell();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The map can't be drawn here");
    expect(alert).toHaveTextContent("WebGL");
    expect(alert).toHaveTextContent("Failed to initialize WebGL");
    expect(FakeMap.instances).toHaveLength(0);

    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    await mapReady();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("3D terrain", () => {
  it("rebuilds the terrain once after the height slider settles, clearing the old one first", async () => {
    renderShell("/?panel=layers");
    const map = await mapReady();
    act(() => useMapStore.getState().setTerrainEnabled(true));
    // Switching 3D on is immediate.
    expect(map.setTerrain).toHaveBeenCalledTimes(1);
    expect(map.setTerrain).toHaveBeenLastCalledWith({ source: "dem-terrain", exaggeration: 1.5 });

    vi.useFakeTimers();
    const slider = screen.getByRole("slider", { name: "Height exaggeration" });
    for (const value of ["1.75", "2", "2.25", "2.5", "2.75", "3"]) {
      fireEvent.change(slider, { target: { value } });
      act(() => vi.advanceTimersByTime(TERRAIN_SETTLE_MS - 50));
    }
    // Six steps of the slider, and the terrain has not been rebuilt once.
    expect(map.setTerrain).toHaveBeenCalledTimes(1);
    expect(useMapStore.getState().terrain.exaggeration).toBe(3);

    act(() => vi.advanceTimersByTime(TERRAIN_SETTLE_MS));
    // One rebuild: the old terrain is cleared, which is what frees its buffers, then the new one is set.
    expect(map.setTerrain.mock.calls.slice(1)).toEqual([[null], [{ source: "dem-terrain", exaggeration: 3 }]]);

    // Sliding back to the value the map already has cancels the rebuild that was waiting.
    fireEvent.change(slider, { target: { value: "4" } });
    fireEvent.change(slider, { target: { value: "3" } });
    act(() => vi.advanceTimersByTime(TERRAIN_SETTLE_MS * 2));
    expect(map.setTerrain).toHaveBeenCalledTimes(3);

    // Switching 3D off does not wait.
    fireEvent.change(slider, { target: { value: "5" } });
    act(() => useMapStore.getState().setTerrainEnabled(false));
    expect(map.setTerrain).toHaveBeenLastCalledWith(null);
    act(() => vi.advanceTimersByTime(TERRAIN_SETTLE_MS * 2));
    expect(map.setTerrain).toHaveBeenCalledTimes(4);
  });
});

describe("zoom buttons and the compass", () => {
  it("zooms in and out a level at a time, and stops at the map's limits", async () => {
    const user = userEvent.setup();
    renderShell();
    const map = await mapReady();
    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(map.easeTo).toHaveBeenLastCalledWith(expect.objectContaining({ zoom: 15 }), expect.anything());
    // A second press goes on from where the first is heading, not from where the map has got to.
    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(map.easeTo).toHaveBeenLastCalledWith(expect.objectContaining({ zoom: 16 }), expect.anything());
    await user.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(map.easeTo).toHaveBeenLastCalledWith(expect.objectContaining({ zoom: 15 }), expect.anything());

    act(() => useMapStore.getState().requestCamera({ zoom: 20 }));
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeEnabled();
    act(() => useMapStore.getState().requestCamera({ zoom: 0 }));
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeDisabled();
  });

  it("goes where it was asked when the buttons are pressed faster than the map can move", async () => {
    const user = userEvent.setup();
    renderShell();
    const map = await mapReady();
    // Each ease now takes time, and each new press cuts the last one short part-way.
    FakeMap.instantEase = false;
    const zoomIn = screen.getByRole("button", { name: "Zoom in" });
    await user.click(zoomIn);
    await user.click(zoomIn);
    await user.click(zoomIn);
    // Three levels up from 14, not three levels up from wherever each ease had got to.
    expect(map.easeTo.mock.calls.map(([target]) => target.zoom)).toEqual([15, 16, 17]);
    expect(useMapStore.getState().camera.zoom).toBe(17);
    act(() => map.finishEase());
    expect(map.getZoom()).toBe(17);
    expect(useMapStore.getState().camera.zoom).toBe(17);
    expect(screen.getByTestId("status-zoom")).toHaveTextContent("z17.0");
  });

  it("takes the map's word for where it is when a person's own gesture cuts a requested move short", async () => {
    const user = userEvent.setup();
    renderShell();
    const map = await mapReady();
    FakeMap.instantEase = false;
    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(useMapStore.getState().camera.zoom).toBe(15);
    // Half way through the ease, the person grabs the map.
    act(() => map.userMove({ lng: -1.9 }));
    expect(map.getZoom()).toBe(14.5);
    expect(useMapStore.getState().camera).toMatchObject({ zoom: 14.5, lng: -1.9 });
  });

  it("shows a compass when the map is turned, which puts it back north-up and leaves the tilt", async () => {
    const user = userEvent.setup();
    renderShell();
    const map = await mapReady();
    expect(screen.queryByRole("button", { name: "Reset to north-up" })).toBeNull();

    // A two-finger twist on a phone turns the map.
    act(() => map.userMove({ bearing: -46.2 }));
    const compass = screen.getByRole("button", { name: "Reset to north-up" });
    // The needle points to where north now is on screen: 46 degrees clockwise of straight up.
    expect(within(compass).getByTestId("compass-needle")).toHaveStyle({ transform: "rotate(46.2deg)" });

    await user.click(compass);
    expect(map.easeTo).toHaveBeenLastCalledWith(expect.objectContaining({ bearing: 0 }), expect.anything());
    expect(screen.queryByRole("button", { name: "Reset to north-up" })).toBeNull();

    // Tilt alone leaves nothing for the compass to do.
    act(() => map.userMove({ pitch: 40 }));
    expect(screen.queryByRole("button", { name: "Reset to north-up" })).toBeNull();

    // Turned while tilted into 3D, the compass turns the map and keeps the 3D view.
    act(() => map.userMove({ bearing: 30, pitch: 60 }));
    await user.click(screen.getByRole("button", { name: "Reset to north-up" }));
    expect(map.easeTo).toHaveBeenLastCalledWith(expect.objectContaining({ bearing: 0, pitch: 60 }), expect.anything());
    expect(map.getPitch()).toBe(60);
    expect(useMapStore.getState().camera).toMatchObject({ bearing: 0, pitch: 60 });
  });

  it("turns the sun dial with the map, so the sun stays on the side the light comes from", async () => {
    renderShell("/#m=14/51.4286/-1.8542/0/0&v=raking&s=90/25");
    window.history.replaceState(null, "", "/#m=14/51.4286/-1.8542/0/0&v=raking&s=90/25");
    const map = await mapReady();
    act(() => useMapStore.getState().applyPermalink({ mainView: "raking", sun: { azimuth: 90, altitude: 25 } }));
    const north = (): { x: number; y: number } => {
      const text = screen.getByTestId("sundial-north");
      return { x: Number(text.getAttribute("x")), y: Number(text.getAttribute("y")) };
    };
    const sun = (): string | null => document.querySelector(".fc-sundial__sun")?.getAttribute("transform") ?? null;

    // North up: N at the top, and light from the east drawn on the right.
    expect(north().x).toBeCloseTo(50, 6);
    expect(north().y).toBeLessThan(50);
    expect(sun()).toBe("translate(87 50)");

    // Turn the map so east is at the top. North is now to the left, and the eastern sun at the top.
    act(() => map.userMove({ bearing: 90 }));
    expect(north().x).toBeLessThan(50);
    expect(north().y).toBeCloseTo(50, 6);
    expect(sun()).toBe("translate(50 13)");
    // What the light does to the ground has not changed, so neither has what a screen reader is told.
    expect(screen.getByRole("slider", { name: "Sun direction" })).toHaveAttribute("aria-valuenow", "90");
  });
});
