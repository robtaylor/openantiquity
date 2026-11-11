// @vitest-environment node
import { describe, expect, it } from "vitest";
import { effectiveFilters, filterableStates, filtersKey, hasFilters, NO_FILTERS } from "./filters.js";

const STATES = ["open", "known", "disputed", "ruled_out", "withdrawn"];

describe("effectiveFilters", () => {
  it("asks for the server's default when nothing is chosen and ruled-out findings are shown", () => {
    expect(effectiveFilters(NO_FILTERS, true, STATES)).toEqual({ ...NO_FILTERS, empty: false });
  });

  it("leaves ruled-out findings out while the map hides them", () => {
    expect(effectiveFilters(NO_FILTERS, false, STATES).state).toEqual(["disputed", "known", "open"]);
  });

  it("keeps a chosen state, without ruled out while it is hidden", () => {
    const chosen = { ...NO_FILTERS, state: ["ruled_out", "known"] };
    expect(effectiveFilters(chosen, false, STATES).state).toEqual(["known"]);
    expect(effectiveFilters(chosen, true, STATES).state).toEqual(["known", "ruled_out"]);
  });

  it("says there is nothing to ask for when only hidden ruled-out findings are chosen", () => {
    expect(effectiveFilters({ ...NO_FILTERS, state: ["ruled_out"] }, false, STATES).empty).toBe(true);
  });

  it("asks for everything before the states are known", () => {
    expect(effectiveFilters(NO_FILTERS, false, [])).toEqual({ ...NO_FILTERS, empty: false });
  });

  it("sorts and de-duplicates, so the same choice makes the same key", () => {
    const a = effectiveFilters({ ...NO_FILTERS, tier: ["seen", "probable", "seen"] }, true, STATES);
    const b = effectiveFilters({ ...NO_FILTERS, tier: ["probable", "seen"] }, true, STATES);
    expect(a.tier).toEqual(["probable", "seen"]);
    expect(filtersKey(a)).toBe(filtersKey(b));
  });
});

describe("the rest", () => {
  it("never offers withdrawn as a state to filter by", () => {
    expect(filterableStates(STATES.map((id) => ({ id }))).map((state) => state.id)).not.toContain("withdrawn");
  });

  it("knows when any filter is on", () => {
    expect(hasFilters(NO_FILTERS)).toBe(false);
    expect(hasFilters({ ...NO_FILTERS, feature_class: ["moat"] })).toBe(true);
  });
});
