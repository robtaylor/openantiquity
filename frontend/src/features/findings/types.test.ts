// @vitest-environment node
import { describe, expect, it } from "vitest";
import { findingsData } from "../../test/fixtures/findings.js";
import { FindingsResponseError, levelsBeside, parseFindingCollection, SENSITIVITIES } from "./types.js";

function feature(properties: Record<string, unknown>, coordinates: unknown = [-1.85, 51.43]) {
  return { type: "Feature", geometry: { type: "Point", coordinates }, properties };
}

const BASE = { public_id: "f1", tier: "seen", state: "open" };

describe("parseFindingCollection", () => {
  it("knows two levels of sensitivity", () => {
    expect(SENSITIVITIES).toEqual(["open", "protected"]);
  });

  it("finds the level above and below", () => {
    expect(levelsBeside("open", 1)).toEqual(["protected"]);
    expect(levelsBeside("protected", 1)).toEqual([]);
    expect(levelsBeside("protected", -1)).toEqual(["open"]);
  });

  it("keeps each level as the server sent it", () => {
    const parsed = parseFindingCollection({
      type: "FeatureCollection",
      features: SENSITIVITIES.map((sensitivity, i) => feature({ ...BASE, public_id: `f${i}`, sensitivity })),
    });
    expect(parsed.features.map((f) => f.properties.sensitivity)).toEqual(["open", "protected"]);
  });

  it("leaves out a level it does not know, and still draws the finding", () => {
    const parsed = parseFindingCollection({
      type: "FeatureCollection",
      features: [feature({ ...BASE, sensitivity: "secret" })],
    });
    expect(parsed.features).toHaveLength(1);
    expect(parsed.features[0]?.properties.sensitivity).toBeUndefined();
  });

  it("takes only true as obscured, so the server is the one that hides a position", () => {
    const parsed = parseFindingCollection({
      type: "FeatureCollection",
      features: [true, "true", 1, false, undefined].map((obscured, i) =>
        feature({ ...BASE, public_id: `f${i}`, obscured }),
      ),
    });
    expect(parsed.features.map((f) => f.properties.obscured)).toEqual([true, false, false, false, false]);
  });

  it("keeps an exact finding's line or area, and never an obscured one's", () => {
    const line = {
      type: "LineString",
      coordinates: [
        [-1.85, 51.43],
        [-1.84, 51.44],
      ],
    };
    const area = {
      type: "Polygon",
      coordinates: [
        [
          [-1.85, 51.43],
          [-1.84, 51.43],
          [-1.84, 51.44],
          [-1.85, 51.43],
        ],
      ],
    };
    const parsed = parseFindingCollection({
      type: "FeatureCollection",
      features: [
        feature({ ...BASE, public_id: "line", shape: line }),
        feature({ ...BASE, public_id: "area", shape: area }),
        feature({ ...BASE, public_id: "hidden", obscured: true, shape: line }),
        feature({ ...BASE, public_id: "odd", shape: { type: "GeometryCollection", geometries: [] } }),
        feature({ ...BASE, public_id: "broken", shape: { type: "LineString", coordinates: [[-1.85]] } }),
        feature({ ...BASE, public_id: "none", shape: null }),
      ],
    });
    expect(parsed.features.map((f) => [f.properties.public_id, f.properties.shape?.type ?? null])).toEqual([
      ["line", "LineString"],
      ["area", "Polygon"],
      ["hidden", null],
      ["odd", null],
      ["broken", null],
      ["none", null],
    ]);
  });

  it("drops a feature it cannot draw and keeps the rest", () => {
    const parsed = parseFindingCollection({
      type: "FeatureCollection",
      features: [
        feature(BASE),
        feature({ tier: "seen" }),
        feature({ ...BASE, public_id: "" }),
        feature(BASE, ["a", "b"]),
        feature(BASE, [200, 51]),
        { type: "Feature", geometry: { type: "Polygon", coordinates: [] }, properties: BASE },
        null,
      ],
    });
    expect(parsed.features).toHaveLength(1);
  });

  it("refuses a reply that is not a feature collection", () => {
    expect(() => parseFindingCollection({ items: [] })).toThrow(FindingsResponseError);
    expect(() => parseFindingCollection(null)).toThrow(FindingsResponseError);
  });

  it("reads the fixture whole, with every level in it", () => {
    const parsed = parseFindingCollection(JSON.parse(JSON.stringify(findingsData)));
    expect(parsed.features).toHaveLength(findingsData.features.length);
    const levels = new Set(parsed.features.map((f) => f.properties.sensitivity));
    expect([...levels].sort()).toEqual(["open", "protected"]);
    // Signed out, protected findings arrive generalised.
    for (const f of parsed.features) {
      expect(f.properties.obscured, f.properties.public_id).toBe(f.properties.sensitivity !== "open");
    }
  });
});
