import { describe, expect, it } from "vitest";
import { ADA } from "../../test/fixtures/investigations.js";
import type { Item } from "./api.js";
import { itemName } from "./Items.js";

function item(overrides: Partial<Item>): Item {
  return {
    id: 1,
    kind: "note",
    title: null,
    note: null,
    position: 0,
    added_by: ADA,
    created_at: "2026-11-10T09:00:00Z",
    ...overrides,
  };
}

describe("itemName", () => {
  it("names a note by its first line, without its Markdown", () => {
    expect(itemName(item({ note: "## The [north bank](https://example.org) *runs*\nmore" }))).toBe(
      "The north bank runs",
    );
  });

  it("names a long hostile note quickly", () => {
    const start = performance.now();
    itemName(item({ note: "[a](".repeat(2500) }));
    expect(performance.now() - start).toBeLessThan(50);
  });

  it("keeps the title of a view held back near a protected finding, and says it is held back", () => {
    expect(itemName(item({ kind: "view", title: "From the north", unavailable: "near_protected" }))).toBe(
      "From the north",
    );
    expect(itemName(item({ kind: "profile", unavailable: "near_protected" }))).toBe("Height profile");
    expect(itemName(item({ kind: "finding", unavailable: "hidden" }))).toBe("Finding no longer shown");
  });
});
