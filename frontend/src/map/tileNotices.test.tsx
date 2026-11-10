import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FakeMap } from "../test/fakeMapLibre.js";
import { metaFixture } from "../test/fixtures/meta.js";
import { liveMaps, mapReady, renderShell, setUpShellTests } from "../test/shellHarness.js";
import { DEM_TROUBLE_KEY, overlayTroubleKey, useMapStore, viewTroubleKey } from "./store.js";
import { RETRY_DELAY_MS, SETTLE_MS } from "./tileErrors.js";
import { noticesFor } from "./tileNotices.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

setUpShellTests();

afterEach(() => {
  vi.useRealTimers();
});

const TILE = { tileID: "14/8106/5452" };

function failTiles(map: FakeMap, sourceId: string, count: number, status = 500): void {
  act(() => {
    for (let i = 0; i < count; i++) map.fire("error", { sourceId, tile: TILE, error: { status } });
  });
}

function loadTiles(map: FakeMap, sourceId: string, count: number): void {
  act(() => {
    for (let i = 0; i < count; i++) map.fire("sourcedata", { sourceId, tile: TILE, dataType: "source" });
  });
}

function wait(ms: number): void {
  act(() => vi.advanceTimersByTime(ms));
}

/** Fail a source's tiles, let the map try once more by itself, and fail them again. */
function failTwice(map: FakeMap, sourceId: string, count = 6): void {
  failTiles(map, sourceId, count);
  wait(SETTLE_MS);
  wait(RETRY_DELAY_MS);
  failTiles(map, sourceId, count);
  wait(SETTLE_MS);
}

async function ready(path = "/?panel=layers"): Promise<FakeMap> {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  renderShell(path);
  const map = await mapReady();
  vi.useFakeTimers();
  return map;
}

describe("an overlay whose tiles fail", () => {
  it("is left on when one tile among many fails", async () => {
    // Records stand for every overlay drawn from tiles. Findings come from the API: see findingsOverlay.test.tsx.
    const map = await ready();
    loadTiles(map, "overlay-records", 6);
    failTiles(map, "overlay-records", 1);
    loadTiles(map, "overlay-records", 6);
    wait(SETTLE_MS + RETRY_DELAY_MS + SETTLE_MS);

    expect(useMapStore.getState().failing[overlayTroubleKey("records")]).toBeFalsy();
    expect(map.isVisible("records-squares")).toBe(true);
    expect(map.refreshTiles).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("is tried once more unprompted, then switched off with a notice that offers another attempt", async () => {
    const map = await ready();
    const panel = screen.getByRole("complementary", { name: "Layers" });
    const row = panel.querySelector('[data-overlay="records"]') as HTMLElement;

    failTiles(map, "overlay-records", 8, 502);
    wait(SETTLE_MS);
    // Nothing is said, or switched off, on the strength of the first failure.
    expect(map.isVisible("records-squares")).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
    wait(RETRY_DELAY_MS);
    expect(map.refreshTiles).toHaveBeenCalledTimes(1);
    expect(map.refreshTiles).toHaveBeenCalledWith("overlay-records");

    failTiles(map, "overlay-records", 8, 502);
    wait(SETTLE_MS);
    expect(map.isVisible("records-squares")).toBe(false);
    // The notice is on screen whether or not the layer panel is open.
    const notice = screen.getByRole("alert");
    expect(notice).toHaveTextContent("The Heritage records layer isn't loading, so it's switched off for now.");
    expect(within(row).getByText(/This layer isn't loading right now/)).toBeInTheDocument();
    expect(within(row).queryByRole("slider")).toBeNull();
    // Its sources are no longer credited, as nothing of theirs is showing.
    expect(within(panel).queryByText(/Historic England/)).toBeNull();

    fireEvent.click(within(notice).getByRole("button", { name: "Try again" }));
    expect(map.refreshTiles).toHaveBeenCalledTimes(2);
    expect(map.isVisible("records-squares")).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(within(row).queryByText(/isn't loading/)).toBeNull();
    expect(within(row).getByRole("slider", { name: "Heritage records opacity" })).toBeInTheDocument();

    // An attempt that was asked for and fails is reported straight away, with no second silent retry.
    failTiles(map, "overlay-records", 8, 502);
    wait(SETTLE_MS);
    expect(map.isVisible("records-squares")).toBe(false);
    expect(screen.getByRole("alert")).toHaveTextContent("Heritage records");
    expect(map.refreshTiles).toHaveBeenCalledTimes(2);
  });

  it("can be tried again from its row in the layer panel, which also clears the notice", async () => {
    const map = await ready();
    failTwice(map, "overlay-records");
    expect(screen.getByRole("alert")).toHaveTextContent("The Heritage records layer isn't loading");
    const row = document.querySelector('[data-overlay="records"]') as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Try again" }));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(map.refreshTiles).toHaveBeenLastCalledWith("overlay-records");
    expect(map.isVisible("records-squares")).toBe(true);
  });

  it("fetches the TileJSON again for an overlay declared by address, which reloading tiles never does", async () => {
    const map = await ready();
    const osm = metaFixture.layers.overlays.find((overlay) => overlay.type === "openmaptiles");
    if (osm?.type !== "openmaptiles") throw new Error("The fixture has no OpenMapTiles overlay");
    const source = map.getSource("overlay-osm");
    if (!source) throw new Error("The fake map has no OpenStreetMap source");

    // The TileJSON fails: an error for the source with no tile.
    act(() => map.fire("error", { sourceId: "overlay-osm", error: { status: 503 } }));
    wait(SETTLE_MS);
    wait(RETRY_DELAY_MS);
    expect(source.setUrl).toHaveBeenCalledTimes(1);
    expect(source.setUrl).toHaveBeenCalledWith(osm.tilejson);
    act(() => map.fire("error", { sourceId: "overlay-osm", error: { status: 503 } }));
    wait(SETTLE_MS);

    const notice = screen.getByRole("alert");
    expect(notice).toHaveTextContent("The OpenStreetMap layer isn't loading");
    expect(map.isVisible("osm-road-major")).toBe(false);

    fireEvent.click(within(notice).getByRole("button", { name: "Try again" }));
    expect(source.setUrl).toHaveBeenCalledTimes(2);
    expect(map.refreshTiles).not.toHaveBeenCalledWith("overlay-osm");
    expect(map.isVisible("osm-road-major")).toBe(true);
  });
});

describe("a view whose tiles fail", () => {
  it("says so on the map and offers another attempt, where it used to leave a blank map and a console warning", async () => {
    const map = await ready("/");
    failTwice(map, "view-composite");

    const notice = screen.getByRole("alert");
    expect(notice).toHaveTextContent("The Composite layer isn't loading.");
    expect(useMapStore.getState().failing[viewTroubleKey("composite")]).toBe(true);
    // The view is not switched off: there is nothing better to show in its place.
    expect(map.isVisible("view-composite")).toBe(true);
    expect(map.refreshTiles).toHaveBeenCalledTimes(1);

    fireEvent.click(within(notice).getByRole("button", { name: "Try again" }));
    expect(map.refreshTiles).toHaveBeenCalledTimes(2);
    expect(map.refreshTiles).toHaveBeenLastCalledWith("view-composite");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(useMapStore.getState().failing[viewTroubleKey("composite")]).toBe(false);
  });

  it("takes the notice away by itself when the tiles start arriving again", async () => {
    const map = await ready("/");
    failTwice(map, "view-composite");
    expect(screen.getByRole("alert")).toBeInTheDocument();

    wait(15_000);
    loadTiles(map, "view-composite", 9);
    wait(SETTLE_MS);
    expect(screen.queryByRole("alert")).toBeNull();
    // Recovering is not a request to try again, so nothing is reloaded.
    expect(map.refreshTiles).toHaveBeenCalledTimes(1);
  });

  it("drops the notice when the failing view is no longer the one on screen", async () => {
    const map = await ready("/");
    failTwice(map, "view-composite");
    expect(screen.getByRole("alert")).toBeInTheDocument();
    act(() => useMapStore.getState().setMainView("slope"));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(useMapStore.getState().failing[viewTroubleKey("composite")]).toBe(false);
  });

  it("reports the elevation data while raking light or 3D is using it", async () => {
    const map = await ready("/");
    act(() => useMapStore.getState().setMainView("raking"));
    failTwice(map, "dem");
    expect(screen.getByRole("alert")).toHaveTextContent("The height data isn't loading");
    expect(useMapStore.getState().failing[DEM_TROUBLE_KEY]).toBe(true);
  });

  it("reports a failing view in the comparison pane too", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    renderShell("/");
    await mapReady();
    act(() => useMapStore.getState().toggleCompare());
    await waitFor(() => expect(liveMaps()).toHaveLength(2));
    const compare = liveMaps()[1] as FakeMap;
    await waitFor(() => expect(compare.listenerCount("move")).toBeGreaterThan(0));
    vi.useFakeTimers();

    failTwice(compare, "view-osm_standard");
    expect(screen.getByRole("alert")).toHaveTextContent("The OpenStreetMap layer isn't loading.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(compare.refreshTiles).toHaveBeenLastCalledWith("view-osm_standard");
  });
});

describe("noticesFor", () => {
  it("mentions only what is on screen", () => {
    const base = {
      ...useMapStore.getInitialState(),
      mainView: "composite",
      compareView: null,
      overlays: { osm: { visible: true, opacity: 1 }, records: { visible: false, opacity: 1 } },
      failing: {
        [overlayTroubleKey("osm")]: true,
        [overlayTroubleKey("records")]: true,
        [viewTroubleKey("composite")]: true,
        [viewTroubleKey("slope")]: true,
        [DEM_TROUBLE_KEY]: true,
      },
    };
    // The records overlay is switched off, slope is not showing, and nothing is using the elevation data.
    expect([...noticesFor(metaFixture, base).keys()]).toEqual(["overlay:osm", viewTroubleKey("composite")]);
    expect([...noticesFor(metaFixture, { ...base, compareView: "slope" }).keys()]).toContain(viewTroubleKey("slope"));
    expect([...noticesFor(metaFixture, { ...base, terrain: { enabled: true, exaggeration: 1.5 } }).keys()]).toContain(
      DEM_TROUBLE_KEY,
    );
    expect([...noticesFor(metaFixture, { ...base, mainView: "raking" }).keys()]).toContain(DEM_TROUBLE_KEY);
  });
});
