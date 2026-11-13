// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  decodePermalink,
  encodePermalink,
  LIMITS,
  normalisePermalinkState,
  type PermalinkState,
  wrapDegrees,
} from "./permalink.js";

const BASE: PermalinkState = {
  camera: { lng: -1.8542, lat: 51.4286, zoom: 14, bearing: 0, pitch: 0 },
  mainView: "composite",
  compareView: null,
  sun: { azimuth: 315, altitude: 35 },
  hillshadeExaggeration: 0.5,
  terrain: { enabled: false, exaggeration: 1.5 },
  overlays: {
    osm: { visible: true, opacity: 0.8 },
    records: { visible: false, opacity: 1 },
    findings: { visible: true, opacity: 1 },
    coverage: { visible: false, opacity: 0.6 },
  },
  showRuledOut: false,
  showRecordCounts: false,
};

const BUSY: PermalinkState = {
  camera: { lng: -5.00362, lat: 56.79683, zoom: 15.75, bearing: -32.5, pitch: 60 },
  mainView: "raking",
  compareView: "os-6inch 1888/2",
  sun: { azimuth: 47, altitude: 16 },
  hillshadeExaggeration: 0.85,
  terrain: { enabled: true, exaggeration: 2.25 },
  overlays: {
    osm: { visible: false, opacity: 0.35 },
    findings: { visible: true, opacity: 0.5 },
  },
  showRuledOut: true,
  showRecordCounts: true,
};

describe("encodePermalink", () => {
  it("writes a readable hash", () => {
    expect(encodePermalink(BASE)).toBe(
      "#m=14/51.4286/-1.8542/0/0&v=composite&s=315/35&x=0.5&t=0/1.5&o=osm:80,records:100:h,findings:100,coverage:60:h",
    );
  });

  it("includes the comparison view, 3D and ruled-out flag when set", () => {
    const hash = encodePermalink(BUSY);
    expect(hash).toContain("&c=os-6inch%201888%2F2&");
    expect(hash).toContain("&t=1/2.25&");
    expect(hash.endsWith("&r=1")).toBe(true);
  });

  it("writes record counts only when they are on", () => {
    expect(encodePermalink(BUSY)).toContain("&rc=1");
    expect(encodePermalink(BASE)).not.toContain("rc=");
  });

  it("never writes negative zero", () => {
    const hash = encodePermalink({ ...BASE, camera: { ...BASE.camera, bearing: -0.01, lng: -0.0000001 } });
    expect(hash).toContain("m=14/51.4286/0/0/0");
  });
});

describe("decodePermalink", () => {
  it("round-trips a default state", () => {
    expect(decodePermalink(encodePermalink(BASE))).toEqual(BASE);
  });

  it("round-trips a busy state", () => {
    expect(decodePermalink(encodePermalink(BUSY))).toEqual(BUSY);
  });

  it("round-trips the hash itself", () => {
    for (const state of [BASE, BUSY]) {
      const hash = encodePermalink(state);
      expect(encodePermalink(decodePermalink(hash) as PermalinkState)).toBe(hash);
    }
  });

  it("round-trips unrounded input to the rounded state", () => {
    const messy: PermalinkState = {
      ...BASE,
      camera: { lng: -1.854212345, lat: 51.428612345, zoom: 14.123456, bearing: 370.04, pitch: 99 },
      sun: { azimuth: 359.7, altitude: 2 },
      hillshadeExaggeration: 30,
      terrain: { enabled: true, exaggeration: 0.1 },
      overlays: { osm: { visible: true, opacity: 0.333333 } },
    };
    const expected = normalisePermalinkState(messy);
    expect(expected.camera).toEqual({
      // Six places, about ten centimetres: at the closest zoom a fifth place alone moved a shared view 47 px.
      lng: -1.854212,
      lat: 51.428612,
      zoom: 14.12,
      bearing: 10,
      pitch: LIMITS.pitch.max,
    });
    expect(expected.sun).toEqual({ azimuth: 0, altitude: LIMITS.sunAltitude.min });
    expect(expected.hillshadeExaggeration).toBe(LIMITS.hillshadeExaggeration.max);
    expect(expected.terrain.exaggeration).toBe(LIMITS.terrainExaggeration.min);
    expect(expected.overlays.osm?.opacity).toBe(0.33);
    expect(decodePermalink(encodePermalink(messy))).toEqual(expected);
  });

  it("takes record counts as off unless a link that names a view or a place says they're on", () => {
    expect(decodePermalink("#m=9/51.4/-1.8/0/0&v=composite&rc=1").showRecordCounts).toBe(true);
    expect(decodePermalink("#m=9/51.4/-1.8/0/0&v=composite").showRecordCounts).toBe(false);
    expect(decodePermalink("#m=9/51.4/-1.8/0/0&rc=0").showRecordCounts).toBe(false);
    expect(decodePermalink("#s=315/20").showRecordCounts).toBeUndefined();
  });

  it("returns nothing for an empty hash", () => {
    expect(decodePermalink("")).toEqual({});
    expect(decodePermalink("#")).toEqual({});
  });

  it("keeps what it can from a damaged hash", () => {
    const decoded = decodePermalink(
      "#m=14/abc/-1.8/0/0&v=slope&s=400/200&x=nope&t=1&o=osm:fifty,findings:40:h,:20&junk",
    );
    expect(decoded.camera).toBeUndefined();
    expect(decoded.mainView).toBe("slope");
    expect(decoded.compareView).toBeNull();
    expect(decoded.sun).toEqual({ azimuth: 40, altitude: LIMITS.sunAltitude.max });
    expect(decoded.hillshadeExaggeration).toBeUndefined();
    expect(decoded.terrain).toBeUndefined();
    expect(decoded.overlays).toEqual({ findings: { visible: false, opacity: 0.4 } });
  });

  it("allows no zoom the map itself would refuse", () => {
    // The map is created with LIMITS.zoom, so a link can never leave the URL saying one zoom and the map showing another.
    // 22 is close enough to draw round something a couple of metres across: at 20 its points crowd each other.
    expect(LIMITS.zoom).toEqual({ min: 0, max: 22 });
    expect(decodePermalink("#m=24/51.4286/-1.8542/0/0").camera?.zoom).toBe(22);
    expect(decodePermalink("#m=21.5/51.4286/-1.8542/0/0").camera?.zoom).toBe(21.5);
    expect(decodePermalink("#m=-3/51.4286/-1.8542/0/0").camera?.zoom).toBe(0);
  });

  it("rejects cameras that are off the globe and clamps the rest", () => {
    expect(decodePermalink("#m=14/95/0/0/0").camera).toBeUndefined();
    expect(decodePermalink("#m=14/50/181/0/0").camera).toBeUndefined();
    expect(decodePermalink("#m=40/50/-2/190/89").camera).toEqual({
      zoom: LIMITS.zoom.max,
      lat: 50,
      lng: -2,
      bearing: -170,
      pitch: LIMITS.pitch.max,
    });
  });

  it("ignores malformed percent escapes", () => {
    expect(decodePermalink("#v=%E0%A4%A").mainView).toBeUndefined();
  });

  it("accepts a hash without the leading #", () => {
    expect(decodePermalink("v=slope").mainView).toBe("slope");
  });
});

describe("wrapDegrees", () => {
  it("wraps into [0, 360)", () => {
    expect(wrapDegrees(-90)).toBe(270);
    expect(wrapDegrees(360)).toBe(0);
    expect(wrapDegrees(725)).toBe(5);
  });
});
