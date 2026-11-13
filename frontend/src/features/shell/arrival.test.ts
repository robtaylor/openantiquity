// @vitest-environment node
import { beforeEach, describe, expect, it } from "vitest";
import { beginVisits, firstArrival, leftFor } from "./arrival.js";

beforeEach(() => {
  leftFor("/somewhere-else");
});

describe("what a page does on arriving", () => {
  it("is done once for a visit, however often the page is mounted", () => {
    expect(firstArrival("/r/7", "go to the record")).toBe(true);
    // The Layers panel opened over the page and closed again: the address is the same.
    leftFor("/r/7");
    expect(firstArrival("/r/7", "go to the record")).toBe(false);
  });

  it("is done again on coming back from another address", () => {
    expect(firstArrival("/r/7", "go to the record")).toBe(true);
    leftFor("/");
    expect(firstArrival("/r/7", "go to the record")).toBe(true);
  });

  it("is done at the next address without waiting to be told the last was left", () => {
    expect(firstArrival("/r/7", "go to the record")).toBe(true);
    expect(firstArrival("/r/8", "go to the record")).toBe(true);
    expect(firstArrival("/r/7", "go to the record")).toBe(true);
  });

  it("is done again by a shell that has just started", () => {
    expect(firstArrival("/r/7", "go to the record")).toBe(true);
    beginVisits();
    expect(firstArrival("/r/7", "go to the record")).toBe(true);
  });

  it("keeps each thing a page does apart", () => {
    expect(firstArrival("/f/a", "go to the finding")).toBe(true);
    expect(firstArrival("/f/a", "say it was carried on")).toBe(true);
    expect(firstArrival("/f/a", "go to the finding")).toBe(false);
  });
});
