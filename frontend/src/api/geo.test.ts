// @vitest-environment node
import { describe, expect, it } from "vitest";
import { parseGeoPoint } from "./geo.js";

describe("parseGeoPoint", () => {
  it("reads the nearest place, and treats a missing or broken one as none", () => {
    const answer = { grid_ref: "SU 1023 6996", nation: "england", elevation: 162.4 };
    expect(
      parseGeoPoint({ ...answer, place: { name: "Avebury", kind: "village", distance_m: 640, source: null } }),
    ).toEqual({ ...answer, place: { name: "Avebury", kind: "village", distance_m: 640 } });
    expect(parseGeoPoint({ ...answer, place: null }).place).toBeNull();
    expect(parseGeoPoint(answer).place).toBeNull();
    expect(parseGeoPoint({ ...answer, place: { name: "Avebury" } }).place).toBeNull();
  });
});
