import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DRAFTS_STORAGE_KEY,
  DRAFTS_UNREADABLE_KEY,
  discardDraft,
  draftsArePersisted,
  listDrafts,
  putDraft,
  resetDraftsForTests,
  restoreDraft,
  retryDraft,
  updateDrafts,
  useDrafts,
} from "./store.js";

beforeEach(() => {
  window.localStorage.clear();
  resetDraftsForTests();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function stored(): unknown {
  const raw = window.localStorage.getItem(DRAFTS_STORAGE_KEY);
  return raw === null ? null : JSON.parse(raw);
}

describe("putDraft and listDrafts", () => {
  it("keeps a draft in localStorage in a versioned envelope", () => {
    const draft = putDraft("finding", { featureClass: "enclosure" });
    expect(draft).toMatchObject({ kind: "finding", data: { featureClass: "enclosure" }, state: "waiting" });
    expect(listDrafts()).toEqual([draft]);
    expect(stored()).toEqual({ version: 1, drafts: [draft] });
  });

  it("replaces a draft given its id, keeping when it was made", () => {
    const first = putDraft("finding", { n: 1 });
    const second = putDraft("finding", { n: 2 }, first.id);
    expect(listDrafts()).toHaveLength(1);
    expect(second).toMatchObject({ id: first.id, createdAt: first.createdAt, data: { n: 2 } });
  });

  it("reads what an earlier page load stored, as a reload would", () => {
    const draft = putDraft("square", { square: "SU1069" });
    resetDraftsForTests();
    expect(listDrafts()).toEqual([draft]);
  });

  it("refuses data that can't be stored as JSON", () => {
    expect(() => putDraft("finding", { at: Number.NaN })).toThrow(/plain JSON/);
    expect(() => putDraft("", {})).toThrow(/kind/);
  });

  it("discards, restores and retries", () => {
    const draft = putDraft("finding", { n: 1 });
    updateDrafts((drafts) =>
      drafts.map((item) => ({ ...item, state: "failed", failure: { code: "x", message: "No." } })),
    );
    expect(retryDraft(draft.id)?.state).toBe("waiting");
    expect(listDrafts()[0]?.failure).toBeUndefined();
    const gone = discardDraft(draft.id);
    expect(listDrafts()).toEqual([]);
    if (!gone) throw new Error("discardDraft returned nothing");
    restoreDraft(gone);
    expect(listDrafts().map((item) => item.id)).toEqual([draft.id]);
  });
});

describe("reading damaged or old data", () => {
  it.each([
    ["not JSON", "{not json"],
    ["a bare list from an older build", JSON.stringify([{ id: "a" }])],
    ["a newer version", JSON.stringify({ version: 99, drafts: [] })],
    ["drafts that aren't a list", JSON.stringify({ version: 1, drafts: "x" })],
  ])("starts empty from %s and keeps the unreadable copy", (_label, raw) => {
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, raw);
    expect(listDrafts()).toEqual([]);
    expect(window.localStorage.getItem(DRAFTS_UNREADABLE_KEY)).toBe(raw);
    // And the next write doesn't fail on it.
    putDraft("finding", {});
    expect(listDrafts()).toHaveLength(1);
  });

  it("drops only the entries it can't read, and puts a draft caught mid-save back to waiting", () => {
    const good = {
      id: "good",
      kind: "finding",
      data: { n: 1 },
      createdAt: "2026-11-10T10:00:00.000Z",
      updatedAt: "2026-11-10T10:00:00.000Z",
      state: "saving",
      claim: { tab: "t", at: 1 },
    };
    window.localStorage.setItem(
      DRAFTS_STORAGE_KEY,
      JSON.stringify({ version: 1, drafts: [good, { id: 3 }, null, { ...good, id: "odd", state: "lost" }] }),
    );
    const drafts = listDrafts();
    expect(drafts.map((draft) => draft.id)).toEqual(["good", "odd"]);
    expect(drafts[0]?.state).toBe("saving");
    expect(drafts[1]?.state).toBe("waiting");
  });
});

describe("a full or blocked store", () => {
  it("keeps drafts in memory when the browser refuses to store them, and says so", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    const draft = putDraft("finding", { n: 1 });
    expect(listDrafts()).toEqual([draft]);
    expect(draftsArePersisted()).toBe(false);
  });

  it("works with no localStorage at all", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    resetDraftsForTests();
    const draft = putDraft("finding", { n: 1 });
    expect(listDrafts()).toEqual([draft]);
    expect(draftsArePersisted()).toBe(false);
  });
});

describe("useDrafts", () => {
  it("sees changes made here and in other tabs", () => {
    const { result } = renderHook(() => useDrafts());
    expect(result.current).toEqual([]);
    act(() => {
      putDraft("finding", { n: 1 });
    });
    expect(result.current).toHaveLength(1);

    // Another tab writes, and the browser tells this one.
    const other = {
      version: 1,
      drafts: [
        ...(listDrafts() as unknown[]),
        {
          id: "from-another-tab",
          kind: "square",
          data: {},
          createdAt: "2026-11-10T10:00:00.000Z",
          updatedAt: "2026-11-10T10:00:00.000Z",
          state: "waiting",
        },
      ],
    };
    const raw = JSON.stringify(other);
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, raw);
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: DRAFTS_STORAGE_KEY, newValue: raw }));
    });
    expect(result.current.map((draft) => draft.id)).toContain("from-another-tab");
  });

  it("filters by kind, and keeps the same list while nothing changes", () => {
    putDraft("finding", {});
    putDraft("square", {});
    const { result, rerender } = renderHook(() => useDrafts("square"));
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
    expect(first.map((draft) => draft.kind)).toEqual(["square"]);
  });
});
