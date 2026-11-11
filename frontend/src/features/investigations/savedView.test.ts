import { beforeEach, describe, expect, it } from "vitest";
import { parseMeta } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { NO_COVER } from "../../map/visibleArea.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { captureView, showSavedView, type ViewSource, viewLayers } from "./savedView.js";

const meta = parseMeta(metaFixture);
const raking = meta.layers.views.find((view) => view.type === "raking");
const raster = meta.layers.views.filter((view) => view.type === "raster");
const [first, second] = raster;
if (!raking || !first || !second) throw new Error("The meta fixture needs raking light and two other views");

function source(overrides: Partial<ViewSource> = {}): ViewSource {
  return {
    camera: { lng: -1.8542123456, lat: 51.4286987654, zoom: 16.123, bearing: 12.34, pitch: 0 },
    mainView: first?.id ?? "",
    compareView: null,
    sun: { azimuth: 315, altitude: 20 },
    hillshadeExaggeration: 3,
    terrain: { enabled: false, exaggeration: 1.5 },
    ...overrides,
  };
}

describe("captureView", () => {
  it("keeps the middle of the uncovered map, the layer and the light, rounded", () => {
    expect(captureView(meta, source(), NO_COVER)).toEqual({
      centre: [-1.854212, 51.428699],
      zoom: 16.12,
      bearing: 12.3,
      pitch: 0,
      layer: first.id,
      sun_azimuth: 315,
      sun_altitude: 20,
    });
  });

  it("keeps the centre of what shows, not of the window, when a panel covers part of the map", () => {
    const covered = captureView(meta, source({ camera: { ...source().camera, bearing: 0 } }), {
      left: 0,
      right: 400,
      top: 0,
      bottom: 0,
    });
    // The uncovered middle is 200 px west of the map's centre.
    expect(covered.centre[0]).toBeLessThan(-1.8542);
    expect(covered.centre[1]).toBeCloseTo(51.4287, 4);
  });

  it("keeps the comparison layer, and the exaggeration the picture depends on", () => {
    const compared = captureView(meta, source({ compareView: second.id }), NO_COVER);
    expect(compared.compare_layer).toBe(second.id);
    expect(compared.exaggeration).toBeUndefined();
    expect(captureView(meta, source({ mainView: raking.id }), NO_COVER).exaggeration).toBe(3);
    const tilted = captureView(
      meta,
      source({ camera: { ...source().camera, pitch: 55 }, terrain: { enabled: true, exaggeration: 2 } }),
      NO_COVER,
    );
    expect(tilted).toMatchObject({ pitch: 55, exaggeration: 2 });
  });
});

describe("showSavedView", () => {
  beforeEach(() => {
    useMapStore.getState().initialise(meta);
  });

  it("puts the map back with its layer, comparison, light and place", () => {
    showSavedView(meta, {
      centre: [-1.9, 51.5],
      zoom: 15,
      layer: raking.id,
      compare_layer: second.id,
      sun_azimuth: 90,
      sun_altitude: 30,
      exaggeration: 4,
    });
    const state = useMapStore.getState();
    expect(state.mainView).toBe(raking.id);
    expect(state.compareView).toBe(second.id);
    expect(state.sun).toEqual({ azimuth: 90, altitude: 30 });
    expect(state.hillshadeExaggeration).toBe(4);
    expect(state.camera).toMatchObject({ lng: -1.9, lat: 51.5, zoom: 15 });
  });

  it("turns a comparison off for a view that had none, and skips a layer the catalogue no longer has", () => {
    useMapStore.getState().setCompareView(second.id);
    showSavedView(meta, { centre: [-1.9, 51.5], zoom: 15, layer: "retired-layer" });
    const state = useMapStore.getState();
    expect(state.compareView).toBeNull();
    expect(state.mainView).toBe(meta.layers.views.find((view) => view.default)?.id ?? state.mainView);
  });
});

describe("viewLayers", () => {
  it("names the layers by their titles", () => {
    expect(viewLayers(meta, { centre: [0, 0], layer: first.id })).toBe(first.title);
    expect(viewLayers(meta, { centre: [0, 0], layer: first.id, compare_layer: second.id })).toBe(
      `${first.title}, compared with ${second.title}`,
    );
    expect(viewLayers(meta, { centre: [0, 0], layer: "gone" })).toBeNull();
  });
});
