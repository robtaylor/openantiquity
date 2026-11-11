import { beforeEach, describe, expect, it } from "vitest";
import { SQUARE_SPOT, squareAt, squareEastOf } from "../../test/fixtures/squares.js";
import { parseKept, SCAN_STORAGE_KEY, useScanStore } from "./scanStore.js";
import { parseSquareDraft } from "./squareDrafts.js";
import { surveyBody } from "./useFinishSquare.js";

const SQUARE = squareAt(...SQUARE_SPOT);
const store = () => useScanStore.getState();

beforeEach(() => {
  sessionStorage.clear();
  store().reset();
});

describe("the scan store", () => {
  it("counts a result, and passes the square so it doesn't come up again", () => {
    store().ask([-1.854, 51.429]);
    store().show(SQUARE);
    expect(store().startedAt).not.toBeNull();
    store().finish({ square: SQUARE.square, grid_ref: SQUARE.grid_ref, result: "nothing" });
    expect(store().finished?.result).toBe("nothing");
    expect(store().done).toHaveLength(1);
    expect(store().passed).toEqual([SQUARE.square]);
  });

  it("counts a square once, with its latest result", () => {
    store().show(SQUARE);
    store().finish({ square: SQUARE.square, grid_ref: SQUARE.grid_ref, result: "nothing" });
    store().finish({ square: SQUARE.square, grid_ref: SQUARE.grid_ref, result: "marked" });
    expect(store().done.map((entry) => entry.result)).toEqual(["marked"]);
  });

  it("takes back a refused result, so the square isn't counted and may come up again", () => {
    store().show(SQUARE);
    store().finish({ square: SQUARE.square, grid_ref: SQUARE.grid_ref, result: "nothing" });
    store().undo(SQUARE.square);
    expect(store().done).toEqual([]);
    expect(store().passed).toEqual([]);
    expect(store().finished).toBeNull();
  });

  it("passes a skipped square without counting it", () => {
    store().show(SQUARE);
    store().pass();
    expect(store().passed).toEqual([SQUARE.square]);
    expect(store().done).toEqual([]);
  });

  it("asking for the next square clears the current one", () => {
    store().show(SQUARE);
    store().ask(null);
    expect(store().current).toBeNull();
    expect(store().ticket).toBe(1);
  });

  it("keeps the square and the count in this tab over a reload, and reads back only what it can use", () => {
    store().show(SQUARE);
    store().finish({ square: SQUARE.square, grid_ref: SQUARE.grid_ref, result: "nothing" });
    const kept = parseKept(sessionStorage.getItem(SCAN_STORAGE_KEY));
    expect(kept?.current?.square).toBe(SQUARE.square);
    expect(kept?.done).toHaveLength(1);
    expect(parseKept("not json")).toBeNull();
    expect(
      parseKept(JSON.stringify({ current: { square: 1 }, done: [{ square: "SU1069" }], passed: [3, "SU1170"] })),
    ).toEqual({ current: null, startedAt: null, finished: null, done: [], passed: ["SU1170"] });
  });
});

describe("a result's body", () => {
  it("counts the findings for a square marked, none otherwise, and the whole seconds spent", () => {
    expect(surveyBody("marked", 3, 1_000, 61_400)).toEqual({ result: "marked", findings_count: 3, seconds: 60 });
    expect(surveyBody("nothing", 3, 1_000, 2_000)).toEqual({ result: "nothing", findings_count: 0, seconds: 1 });
    expect(surveyBody("skipped", 0, null)).toEqual({ result: "skipped", findings_count: 0 });
  });

  it("keeps within the server's limits", () => {
    expect(surveyBody("marked", 500, 0, 10 ** 12)).toEqual({ result: "marked", findings_count: 100, seconds: 86_400 });
  });
});

describe("a square draft", () => {
  it("reads back what it stored, and nothing it can't send", () => {
    const data = { square: squareEastOf(1).square, survey: { result: "nothing", findings_count: 0, seconds: 40 } };
    expect(parseSquareDraft(data)).toEqual(data);
    expect(parseSquareDraft({ ...data, survey: { result: "skipped", findings_count: 0 } })).toBeNull();
    expect(parseSquareDraft({ square: "", survey: data.survey })).toBeNull();
    expect(parseSquareDraft({ square: "SU1069", survey: { result: "marked" } })).toBeNull();
  });
});
