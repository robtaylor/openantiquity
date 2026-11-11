import { describe, expect, it } from "vitest";
import { squareWords, whereRef } from "./square.js";

describe("squareWords", () => {
  it("spaces a square's reference like a grid reference", () => {
    expect(squareWords("SU1069")).toBe("SU 10 69");
    expect(squareWords("SU 10 69")).toBe("SU 10 69");
    // An Irish square has one letter.
    expect(squareWords("V2624")).toBe("V 26 24");
  });

  it("leaves anything else alone", () => {
    expect(squareWords("SU 1025 6996")).toBe("SU 1025 6996");
    expect(squareWords("")).toBe("");
  });
});

describe("whereRef", () => {
  it("gives the square for a viewer sent only that, and the grid reference otherwise", () => {
    expect(whereRef({ obscured: true, square: "SU1069", grid_ref: "SU 10 69" })).toBe("SU 10 69");
    expect(whereRef({ obscured: true, square: null, grid_ref: "SU1069" })).toBe("SU 10 69");
    expect(whereRef({ obscured: false, square: null, grid_ref: "SU 1025 6996" })).toBe("SU 1025 6996");
  });
});
