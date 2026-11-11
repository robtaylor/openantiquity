import { describe, expect, it } from "vitest";
import { dropIndex, moveTo } from "./order.js";

const items = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }];
const ids = (list: ReadonlyArray<{ id: number }>) => list.map((item) => item.id);

describe("moveTo", () => {
  it("moves an item down, and names the item it now follows", () => {
    const moved = moveTo(items, 1, 2);
    expect(moved && ids(moved.items)).toEqual([2, 3, 1, 4]);
    expect(moved?.after).toBe(3);
  });

  it("moves an item to the top, which follows nothing", () => {
    const moved = moveTo(items, 3, 0);
    expect(moved && ids(moved.items)).toEqual([3, 1, 2, 4]);
    expect(moved?.after).toBeNull();
  });

  it("moves an item to the end", () => {
    const moved = moveTo(items, 2, 3);
    expect(moved && ids(moved.items)).toEqual([1, 3, 4, 2]);
    expect(moved?.after).toBe(4);
  });

  it("does nothing for a place it already has, a place off the list, or an item it doesn't hold", () => {
    expect(moveTo(items, 2, 1)).toBeNull();
    expect(moveTo(items, 2, -1)).toBeNull();
    expect(moveTo(items, 2, 4)).toBeNull();
    expect(moveTo(items, 9, 0)).toBeNull();
  });

  it("leaves the list it was given alone", () => {
    moveTo(items, 1, 3);
    expect(ids(items)).toEqual([1, 2, 3, 4]);
  });
});

describe("dropIndex", () => {
  it("is the place an item dragged over the top half of another takes", () => {
    // Dragging item 0 over the top half of item 2 puts it before item 2, which is place 1 once it has left.
    expect(dropIndex(0, 2, "before")).toBe(1);
    expect(dropIndex(0, 2, "after")).toBe(2);
    expect(dropIndex(3, 1, "before")).toBe(1);
    expect(dropIndex(3, 1, "after")).toBe(2);
  });
});
