import { beforeEach, describe, expect, it } from "vitest";
import type { Meta } from "../api/meta.js";
import { metaFixture } from "../test/fixtures/meta.js";
import { decodePermalink, encodePermalink, LIMITS } from "./permalink.js";
import {
  DEFAULT_SUN,
  DEM_TROUBLE_KEY,
  defaultsFromMeta,
  MapStateError,
  mergePermalink,
  overlayTroubleKey,
  pickCompareView,
  selectPermalinkState,
  TERRAIN_PITCH,
  useMapStore,
  viewTroubleKey,
} from "./store.js";

const store = () => useMapStore.getState();

beforeEach(() => {
  useMapStore.setState(useMapStore.getInitialState(), true);
});

describe("before initialise", () => {
  it("is not ready and refuses changes that need the catalogue", () => {
    expect(store().meta).toBeNull();
    expect(() => store().setMainView("composite")).toThrow(MapStateError);
    expect(() => store().toggleCompare()).toThrow(MapStateError);
    expect(() => store().setOverlayVisible("osm", false)).toThrow(MapStateError);
  });
});

describe("initialise", () => {
  it("takes its defaults from the meta document", () => {
    store().initialise(metaFixture);
    const state = store();
    expect(state.meta).toBe(metaFixture);
    expect(state.mainView).toBe("composite");
    expect(state.compareView).toBeNull();
    expect(state.camera).toEqual({ lng: -1.8542, lat: 51.4286, zoom: 14, bearing: 0, pitch: 0 });
    expect(state.sun).toEqual(DEFAULT_SUN);
    expect(state.terrain.enabled).toBe(false);
    expect(state.overlays).toEqual({
      osm: { visible: true, opacity: 0.8 },
      records: { visible: true, opacity: 1 },
      findings: { visible: true, opacity: 1 },
      coverage: { visible: false, opacity: 1 },
    });
  });

  it("falls back to the first view when none is marked default", () => {
    const meta: Meta = {
      ...metaFixture,
      layers: {
        ...metaFixture.layers,
        views: metaFixture.layers.views.map(({ default: _default, ...view }) => view) as Meta["layers"]["views"],
      },
    };
    store().initialise(meta);
    expect(store().mainView).toBe(meta.layers.views[0]?.id);
  });

  it("restores a permalink over the defaults", () => {
    const link = decodePermalink(
      "#m=16.5/51.1788/-1.8263/-20/45&v=raking&c=osm_standard&s=90/16&x=0.8&t=1/2.5&o=osm:40:h,coverage:70&r=1",
    );
    store().initialise(metaFixture, link);
    const state = store();
    expect(state.camera).toEqual({ lng: -1.8263, lat: 51.1788, zoom: 16.5, bearing: -20, pitch: 45 });
    expect(state.mainView).toBe("raking");
    expect(state.compareView).toBe("osm_standard");
    expect(state.sun).toEqual({ azimuth: 90, altitude: 16 });
    expect(state.hillshadeExaggeration).toBe(0.8);
    expect(state.terrain).toEqual({ enabled: true, exaggeration: 2.5 });
    expect(state.overlays.osm).toEqual({ visible: false, opacity: 0.4 });
    expect(state.overlays.coverage).toEqual({ visible: true, opacity: 0.7 });
    // Overlays the link does not mention keep their defaults.
    expect(state.overlays.findings).toEqual({ visible: true, opacity: 1 });
    expect(state.showRuledOut).toBe(true);
  });

  it("ignores ids the catalogue does not have", () => {
    store().initialise(metaFixture, decodePermalink("#v=retired&c=also-gone&o=mystery:50,osm:30"));
    const state = store();
    expect(state.mainView).toBe("composite");
    expect(state.compareView).toBeNull();
    expect(state.overlays.mystery).toBeUndefined();
    expect(state.overlays.osm).toEqual({ visible: true, opacity: 0.3 });
  });

  it("does not compare a view with itself", () => {
    store().initialise(metaFixture, decodePermalink("#v=slope&c=slope"));
    expect(store().compareView).toBeNull();
  });

  it("round-trips through the permalink", () => {
    store().initialise(metaFixture);
    store().setMainView("raking");
    store().setCompareView("slope");
    store().setSun({ azimuth: 200, altitude: 15 });
    store().setOverlayOpacity("osm", 0.45);
    store().setOverlayVisible("records", false);
    store().setTerrainExaggeration(3);
    const hash = encodePermalink(selectPermalinkState(store()));
    const before = selectPermalinkState(store());

    useMapStore.setState(useMapStore.getInitialState(), true);
    store().initialise(metaFixture, decodePermalink(hash));
    expect(selectPermalinkState(store())).toEqual(before);
  });
});

describe("views", () => {
  beforeEach(() => store().initialise(metaFixture));

  it("switches the main view", () => {
    store().setMainView("slope");
    expect(store().mainView).toBe("slope");
    expect(() => store().setMainView("nope")).toThrow(MapStateError);
  });

  it("toggles a comparison against a view from another group", () => {
    store().setSwipe(0.9);
    store().toggleCompare();
    expect(store().compareView).toBe("osm_standard");
    expect(store().swipe).toBe(0.5);
    store().toggleCompare();
    expect(store().compareView).toBeNull();
  });

  it("swaps the two when one is chosen for the other's slot", () => {
    store().setCompareView("slope");
    store().setMainView("slope");
    expect([store().mainView, store().compareView]).toEqual(["slope", "composite"]);
    store().setCompareView("slope");
    expect([store().mainView, store().compareView]).toEqual(["composite", "slope"]);
    store().swapViews();
    expect([store().mainView, store().compareView]).toEqual(["slope", "composite"]);
  });

  it("refuses to compare a view with itself", () => {
    expect(() => store().setCompareView("composite")).toThrow(MapStateError);
    expect(() => store().setCompareView("nope")).toThrow(MapStateError);
  });

  it("clamps the swipe position", () => {
    store().setSwipe(1.4);
    expect(store().swipe).toBe(1);
    store().setSwipe(-3);
    expect(store().swipe).toBe(0);
    expect(() => store().setSwipe(Number.NaN)).toThrow(MapStateError);
  });
});

describe("overlays", () => {
  beforeEach(() => store().initialise(metaFixture));

  it("sets visibility and opacity independently", () => {
    store().setOverlayVisible("coverage", true);
    store().setOverlayOpacity("coverage", 0.3);
    expect(store().overlays.coverage).toEqual({ visible: true, opacity: 0.3 });
    store().setOverlayOpacity("coverage", 7);
    expect(store().overlays.coverage?.opacity).toBe(1);
    expect(store().overlays.osm).toEqual({ visible: true, opacity: 0.8 });
  });

  it("rejects unknown overlays and bad numbers", () => {
    expect(() => store().setOverlayVisible("nope", true)).toThrow(MapStateError);
    expect(() => store().setOverlayOpacity("osm", Number.NaN)).toThrow(MapStateError);
  });

  it("tracks overlays whose tiles are failing", () => {
    const key = overlayTroubleKey("records");
    expect(key).toBe("overlay:records");
    store().setSourceFailing(key, true);
    expect(store().failing[key]).toBe(true);
    const snapshot = store().failing;
    store().setSourceFailing(key, true);
    expect(store().failing).toBe(snapshot);
    store().setSourceFailing(key, false);
    expect(store().failing[key]).toBe(false);
  });

  it("counts each request to try a failing source again, and only for a source that is failing", () => {
    const key = overlayTroubleKey("records");
    store().retrySource(key);
    expect(store().retries[key]).toBeUndefined();
    store().setSourceFailing(key, true);
    store().retrySource(key);
    expect(store().failing[key]).toBe(false);
    expect(store().retries[key]).toBe(1);
    // A mark cleared by the source itself recovering is not a request to try again.
    store().setSourceFailing(key, true);
    store().setSourceFailing(key, false);
    expect(store().retries[key]).toBe(1);
  });

  it("tracks views and elevation data that are failing to load, and forgets them on a fresh start", () => {
    const key = viewTroubleKey("composite");
    expect(key).toBe("view:composite");
    store().setSourceFailing(key, true);
    store().setSourceFailing(DEM_TROUBLE_KEY, true);
    expect(store().failing).toEqual({ [key]: true, [DEM_TROUBLE_KEY]: true });
    const snapshot = store().failing;
    store().setSourceFailing(key, true);
    expect(store().failing).toBe(snapshot);
    store().setSourceFailing(key, false);
    expect(store().failing[key]).toBe(false);

    store().initialise(metaFixture);
    expect(store().failing).toEqual({});
  });
});

describe("sun and terrain", () => {
  beforeEach(() => store().initialise(metaFixture));

  it("wraps azimuth and clamps altitude", () => {
    store().setSun({ azimuth: -45 });
    expect(store().sun).toEqual({ azimuth: 315, altitude: DEFAULT_SUN.altitude });
    store().setSun({ azimuth: 725, altitude: 200 });
    expect(store().sun).toEqual({ azimuth: 5, altitude: LIMITS.sunAltitude.max });
    store().setSun({ altitude: -5 });
    expect(store().sun.altitude).toBe(LIMITS.sunAltitude.min);
    expect(() => store().setSun({ azimuth: Number.POSITIVE_INFINITY })).toThrow(MapStateError);
  });

  it("clamps hillshade exaggeration", () => {
    store().setHillshadeExaggeration(40);
    expect(store().hillshadeExaggeration).toBe(LIMITS.hillshadeExaggeration.max);
    store().setHillshadeExaggeration(0);
    expect(store().hillshadeExaggeration).toBe(LIMITS.hillshadeExaggeration.min);
  });

  it("tilts the camera when 3D goes on and levels it when 3D goes off", () => {
    const requests = store().cameraRequest;
    store().setTerrainEnabled(true);
    expect(store().terrain.enabled).toBe(true);
    expect(store().camera.pitch).toBe(TERRAIN_PITCH);
    expect(store().cameraRequest).toBe(requests + 1);

    store().setTerrainExaggeration(99);
    expect(store().terrain).toEqual({ enabled: true, exaggeration: LIMITS.terrainExaggeration.max });

    store().setTerrainEnabled(false);
    expect(store().camera.pitch).toBe(0);
    expect(store().cameraRequest).toBe(requests + 2);
    store().setTerrainEnabled(false);
    expect(store().cameraRequest).toBe(requests + 2);
  });

  it("keeps a pitch the user already chose", () => {
    store().setCamera({ ...store().camera, pitch: 40 });
    store().setTerrainEnabled(true);
    expect(store().camera.pitch).toBe(40);
  });
});

describe("camera", () => {
  beforeEach(() => store().initialise(metaFixture));

  it("records where the map is without asking it to move", () => {
    const requests = store().cameraRequest;
    store().setCamera({ lng: -2, lat: 52, zoom: 12, bearing: 10, pitch: 0 });
    expect(store().camera.zoom).toBe(12);
    expect(store().cameraRequest).toBe(requests);
    const same = store().camera;
    store().setCamera({ lng: -2, lat: 52, zoom: 12, bearing: 10, pitch: 0 });
    expect(store().camera).toBe(same);
  });

  it("asks the map to move on request and when a permalink names a camera", () => {
    const requests = store().cameraRequest;
    store().requestCamera({ zoom: 9 });
    expect(store().camera).toMatchObject({ zoom: 9, lng: -1.8542 });
    expect(store().cameraRequest).toBe(requests + 1);
    store().applyPermalink(decodePermalink("#m=11/52.5/-3.2/0/0&v=slope"));
    expect(store().camera).toMatchObject({ zoom: 11, lat: 52.5, lng: -3.2 });
    expect(store().mainView).toBe("slope");
    expect(store().cameraRequest).toBe(requests + 2);
    store().applyPermalink({ sun: { azimuth: 10, altitude: 20 } });
    expect(store().cameraRequest).toBe(requests + 2);
  });

  it("zooms by whole levels, building on a zoom already asked for, and stops at the limits", () => {
    const requests = store().cameraRequest;
    store().zoomBy(1);
    store().zoomBy(1);
    expect(store().camera.zoom).toBe(16);
    expect(store().cameraRequest).toBe(requests + 2);
    store().zoomBy(-1);
    expect(store().camera.zoom).toBe(15);

    store().requestCamera({ zoom: LIMITS.zoom.max - 0.4 });
    const before = store().cameraRequest;
    store().zoomBy(1);
    expect(store().camera.zoom).toBe(LIMITS.zoom.max);
    // At the limit there is nowhere to go, so the map is not asked to move.
    store().zoomBy(1);
    expect(store().cameraRequest).toBe(before + 1);
    expect(() => store().zoomBy(Number.NaN)).toThrow(MapStateError);
  });

  it("turns the map north-up on request, keeps its tilt, and asks nothing of a map that already is", () => {
    const requests = store().cameraRequest;
    store().resetNorth();
    expect(store().cameraRequest).toBe(requests);
    store().setCamera({ ...store().camera, bearing: -46.2, pitch: 60 });
    store().resetNorth();
    expect(store().camera).toMatchObject({ bearing: 0, pitch: 60, zoom: 14 });
    expect(store().cameraRequest).toBe(requests + 1);
    // Tilted but already north-up: nothing to do.
    store().resetNorth();
    expect(store().cameraRequest).toBe(requests + 1);
  });
});

describe("helpers", () => {
  it("picks a comparison view, preferring another group", () => {
    expect(pickCompareView(metaFixture, "composite")).toBe("osm_standard");
    expect(pickCompareView(metaFixture, "osm_standard")).toBe("composite");
    const lidarOnly: Meta = {
      ...metaFixture,
      layers: { ...metaFixture.layers, views: metaFixture.layers.views.filter((view) => view.group === "lidar") },
    };
    expect(pickCompareView(lidarOnly, "composite")).toBe("local_relief");
    const single: Meta = {
      ...metaFixture,
      layers: { ...metaFixture.layers, views: metaFixture.layers.views.slice(0, 1) },
    };
    expect(pickCompareView(single, "composite")).toBeNull();
  });

  it("merges without touching the base", () => {
    const base = defaultsFromMeta(metaFixture);
    const copy = structuredClone(base);
    const merged = mergePermalink(base, { overlays: { osm: { visible: false, opacity: 2 } } }, metaFixture);
    expect(base).toEqual(copy);
    expect(merged.overlays.osm).toEqual({ visible: false, opacity: 1 });
  });
});
