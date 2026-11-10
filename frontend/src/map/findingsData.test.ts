// @vitest-environment node
import { describe, expect, it } from "vitest";
import { type FindingFeature, type FindingProperties, SENSITIVITIES } from "../features/findings/types.js";
import { findingsData as fixture } from "../test/fixtures/findings.js";
import { findingsMapData } from "./findingsData.js";

function finding(lon: number, lat: number, properties: Partial<FindingProperties>): FindingFeature {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [lon, lat] },
    properties: { public_id: "f1", tier: "seen", state: "open", obscured: false, ...properties },
  };
}

function collection(...features: FindingFeature[]) {
  return findingsMapData({ type: "FeatureCollection", features });
}

// About 700 m east and 500 m north of the south-west corner of SU1069, the
// square that holds the southern half of the Avebury henge.
const AVEBURY: [number, number] = [-1.8476, 51.4245];

describe("findingsMapData", () => {
  it("keeps an exact finding as a point, with only what the markers use", () => {
    const { features } = collection(finding(...AVEBURY, { title: "Ring ditch", sensitivity: "open" }));
    expect(features).toEqual([
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: AVEBURY },
        properties: { public_id: "f1", tier: "seen", state: "open" },
      },
    ]);
  });

  it("turns an obscured finding into its one-kilometre square and never a point", () => {
    const { features } = collection(finding(...AVEBURY, { obscured: true, square: "SU1069" }));
    expect(features).toHaveLength(1);
    const [square] = features;
    expect(square?.geometry.type).toBe("Polygon");
    expect(square?.properties).toEqual({ square: "SU1069", tier: "seen", state: "open", count: 1 });
    expect(square?.geometry.type === "Polygon" && square.geometry.coordinates[0]).toHaveLength(5);
  });

  it("draws by `obscured` alone, whatever the sensitivity level", () => {
    for (const sensitivity of SENSITIVITIES) {
      const exact = collection(finding(...AVEBURY, { sensitivity, obscured: false }));
      const hidden = collection(finding(...AVEBURY, { sensitivity, obscured: true }));
      expect(
        exact.features.map((f) => f.geometry.type),
        sensitivity,
      ).toEqual(["Point"]);
      expect(
        hidden.features.map((f) => f.geometry.type),
        sensitivity,
      ).toEqual(["Polygon"]);
    }
  });

  it("merges repeats of one finding and counts different findings in a square", () => {
    const { features } = collection(
      finding(...AVEBURY, { obscured: true, tier: "probable", public_id: "f1" }),
      finding(...AVEBURY, { obscured: true, tier: "probable", public_id: "f1" }),
      finding(...AVEBURY, { obscured: true, tier: "spotted", public_id: "f2" }),
    );
    expect(features).toHaveLength(1);
    expect(features[0]?.properties).toMatchObject({ tier: "probable", count: 2 });
  });

  it("keeps ruled-out squares apart so they can be hidden", () => {
    const { features } = collection(
      finding(...AVEBURY, { obscured: true, state: "open", public_id: "f1" }),
      finding(...AVEBURY, { obscured: true, state: "ruled_out", public_id: "f2" }),
    );
    expect(features.map((f) => f.properties.state)).toEqual(["open", "ruled_out"]);
  });

  it("drops an obscured finding off both grids rather than show its point", () => {
    expect(collection(finding(2.35, 48.86, { obscured: true })).features).toEqual([]);
  });

  it("uses the Irish grid in Ireland", () => {
    const { features } = collection(finding(-5.9305779, 54.5965219, { obscured: true }));
    expect(features[0]?.properties).toMatchObject({ square: "J3374" });
  });

  it("draws the fixture's findings as points and squares as each one says", () => {
    const { features } = findingsMapData(fixture);
    const points = features.filter((f) => f.geometry.type === "Point");
    const squares = features.filter((f) => f.geometry.type === "Polygon");
    const exactIds = fixture.features.filter((f) => !f.properties.obscured).map((f) => f.properties.public_id);
    expect(points.map((f) => (f.properties as { public_id: string }).public_id)).toEqual(exactIds);
    expect(squares.length).toBeGreaterThan(0);
  });
});
