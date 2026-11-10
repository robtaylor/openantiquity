// @vitest-environment node
import { describe, expect, it } from "vitest";
import { findingsData } from "../../test/fixtures/findings.js";
import { FindingsResponseError, parseFindingCollection, SENSITIVITIES } from "./types.js";

function feature(properties: Record<string, unknown>, coordinates: unknown = [-1.85, 51.43]) {
  return { type: "Feature", geometry: { type: "Point", coordinates }, properties };
}

const BASE = { public_id: "f1", tier: "seen", state: "open" };

describe("parseFindingCollection", () => {
  it("knows three levels of sensitivity", () => {
    expect(SENSITIVITIES).toEqual(["open", "protected", "restricted"]);
  });

  it("keeps each level as the server sent it", () => {
    const parsed = parseFindingCollection({
      type: "FeatureCollection",
      features: SENSITIVITIES.map((sensitivity, i) => feature({ ...BASE, public_id: `f${i}`, sensitivity })),
    });
    expect(parsed.features.map((f) => f.properties.sensitivity)).toEqual(["open", "protected", "restricted"]);
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
    expect([...levels].sort()).toEqual(["open", "protected", "restricted"]);
    // Signed out, protected and restricted findings both arrive generalised.
    for (const f of parsed.features) {
      expect(f.properties.obscured, f.properties.public_id).toBe(f.properties.sensitivity !== "open");
    }
  });
});
