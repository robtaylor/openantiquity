import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client.js";
import { GEO_RESULTS, GRIDREF_RESULT } from "../../test/fixtures/records.js";
import { cameraFor, groupResults, isSearchTimeout } from "./api.js";

describe("groupResults", () => {
  it("groups by kind in the order each kind first appears, and numbers the results as shown", () => {
    const { groups, ordered } = groupResults(GEO_RESULTS);
    expect(groups.map((group) => group.label)).toEqual(["Places", "Heritage records", "Findings"]);
    expect(ordered.map((result) => result.label)).toEqual([
      "Avebury",
      "Avebury Trusloe",
      "West Kennet Avenue",
      "Enclosure near the avenue",
    ]);
    expect(groups[1]?.items.map((item) => item.index)).toEqual([2]);
  });
});

describe("cameraFor", () => {
  it("goes to the middle of a result's box, or to its point", () => {
    const record = GEO_RESULTS[1];
    if (!record?.bbox) throw new Error("fixture record has a box");
    const [west, south, east, north] = record.bbox as [number, number, number, number];
    expect(cameraFor(record)).toEqual({ lng: (west + east) / 2, lat: (south + north) / 2, zoom: 16 });
    expect(cameraFor(GRIDREF_RESULT)).toEqual({ lng: GRIDREF_RESULT.lon, lat: GRIDREF_RESULT.lat, zoom: 17 });
  });
});

describe("isSearchTimeout", () => {
  it("recognises the server's timeout and a gateway's", () => {
    expect(isSearchTimeout(new ApiError(503, "search_timeout", "slow"))).toBe(true);
    expect(isSearchTimeout(new ApiError(504, "http_504", "gateway"))).toBe(true);
    expect(isSearchTimeout(new ApiError(500, "internal_error", "no"))).toBe(false);
  });
});
