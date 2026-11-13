import { describe, expect, it } from "vitest";
import { nearFrom, pickNext } from "./queue.js";
import type { ReviewCard } from "./types.js";

function card(publicId: string): ReviewCard {
  return {
    public_id: publicId,
    place: { lon: -1.85, lat: 51.42, grid_ref: "SU 1 2" },
    view_state: {},
    shape_revision: 0,
  };
}

describe("pickNext", () => {
  it("takes the first card not already passed", () => {
    const page = { items: [card("a"), card("b"), card("c")], next_cursor: null };
    expect(pickNext(page, new Set(["a"]), false)).toEqual({ kind: "card", card: card("b") });
  });

  it("goes on to the next page when every card on this one has been passed", () => {
    const page = { items: [card("a")], next_cursor: "p2" };
    expect(pickNext(page, new Set(["a"]), false)).toEqual({ kind: "page", cursor: "p2" });
  });

  it("starts again from the top once, because answers move the queue under its pages", () => {
    const page = { items: [card("a")], next_cursor: null };
    expect(pickNext(page, new Set(["a"]), false)).toEqual({ kind: "restart" });
    expect(pickNext(page, new Set(["a"]), true)).toEqual({ kind: "empty" });
  });

  it("is empty when the server has nothing", () => {
    expect(pickNext({ items: [], next_cursor: null }, new Set(), true)).toEqual({ kind: "empty" });
  });
});

describe("nearFrom", () => {
  it("rounds the map's centre to about a hundred metres, so a small pan asks for the same queue", () => {
    expect(nearFrom({ lng: -1.854213, lat: 51.428649 })).toEqual([-1.854, 51.429]);
  });

  it("gives nothing for a centre the server would refuse", () => {
    expect(nearFrom({ lng: Number.NaN, lat: 51 })).toBeNull();
    expect(nearFrom({ lng: 0, lat: 95 })).toBeNull();
  });
});
