import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  adoptSignedOutDrafts,
  DRAFTS_STORAGE_KEY,
  DRAFTS_UNREADABLE_KEY,
  DraftTooLargeError,
  discardAllDrafts,
  discardDraft,
  draftsArePersisted,
  listDrafts,
  putDraft,
  resetDraftsForTests,
  restoreDraft,
  retryDraft,
  setDraftsViewer,
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

function stored(): { version: number; epoch: string; drafts: Array<Record<string, unknown>> } | null {
  const raw = window.localStorage.getItem(DRAFTS_STORAGE_KEY);
  return raw === null ? null : JSON.parse(raw);
}

function unreadableCopies(): string[] {
  return Object.keys(window.localStorage)
    .filter((key) => key.startsWith(DRAFTS_UNREADABLE_KEY))
    .sort()
    .map((key) => window.localStorage.getItem(key) ?? "");
}

describe("putDraft and listDrafts", () => {
  it("keeps a draft in localStorage in a versioned envelope", () => {
    const draft = putDraft("finding", { featureClass: "enclosure" });
    expect(draft).toMatchObject({ kind: "finding", data: { featureClass: "enclosure" }, state: "waiting" });
    expect(listDrafts()).toEqual([draft]);
    expect(stored()).toEqual({ version: 2, epoch: expect.any(String), drafts: [draft] });
  });

  it("stamps a draft with who made it: the account, or the signed-out epoch", () => {
    const signedOut = putDraft("finding", {});
    expect(signedOut.owner).toEqual({ signedOut: stored()?.epoch });
    setDraftsViewer("account-a");
    const signedIn = putDraft("finding", {});
    expect(signedIn.owner).toEqual({ account: "account-a" });
    // Editing keeps the owner.
    expect(putDraft("finding", { n: 2 }, signedOut.id).owner).toEqual(signedOut.owner);
  });

  it("starts a new epoch when someone signs in, so earlier signed-out drafts aren't taken for theirs", () => {
    const before = putDraft("finding", {});
    expect(adoptSignedOutDrafts("account-a")).toBe(1);
    expect(listDrafts()[0]?.owner).toEqual({ account: "account-a" });
    const after = putDraft("finding", {});
    expect(after.owner).not.toEqual(before.owner);
    expect(adoptSignedOutDrafts("account-b")).toBe(1);
    expect(listDrafts().map((draft) => draft.owner)).toEqual([{ account: "account-a" }, { account: "account-b" }]);
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
    ["drafts that aren't a list", JSON.stringify({ version: 2, drafts: "x" })],
  ])("starts empty from %s and keeps the unreadable copy", (_label, raw) => {
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, raw);
    expect(listDrafts()).toEqual([]);
    expect(unreadableCopies()).toEqual([raw]);
    // And the next write doesn't fail on it.
    putDraft("finding", {});
    expect(listDrafts()).toHaveLength(1);
  });

  it("never writes an unreadable copy over an earlier one", () => {
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, "{bad1");
    listDrafts();
    vi.useFakeTimers({ now: Date.now() + 1000, toFake: ["Date"] });
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, "{bad2");
    resetDraftsForTests();
    listDrafts();
    vi.useRealTimers();
    expect(unreadableCopies()).toEqual(["{bad1", "{bad2"]);
  });

  it("leaves a newer build's drafts alone, and keeps this page's own in memory", () => {
    const newer = JSON.stringify({ version: 3, drafts: [{ anything: true }] });
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, newer);
    expect(listDrafts()).toEqual([]);
    const draft = putDraft("finding", { n: 1 });
    expect(listDrafts()).toEqual([draft]);
    expect(draftsArePersisted()).toBe(false);
    expect(window.localStorage.getItem(DRAFTS_STORAGE_KEY)).toBe(newer);
    expect(unreadableCopies()).toEqual([]);
  });

  it("migrates version 1, whose drafts have no owner", () => {
    const old = {
      id: "old",
      kind: "finding",
      data: { n: 1 },
      createdAt: "2026-11-10T10:00:00.000Z",
      updatedAt: "2026-11-10T10:00:00.000Z",
      state: "waiting",
    };
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify({ version: 1, drafts: [old] }));
    expect(listDrafts()).toEqual([{ ...old, owner: null }]);
    putDraft("finding", {});
    expect(stored()?.version).toBe(2);
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
      JSON.stringify({
        version: 2,
        epoch: "e",
        drafts: [good, { id: 3 }, null, { ...good, id: "odd", state: "lost" }],
      }),
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

  it("refuses a draft too big to keep, and goes on working", () => {
    const small = putDraft("finding", { n: 1 });
    expect(() => putDraft("finding", { text: "x".repeat(6_000_000) })).toThrow(DraftTooLargeError);
    expect(listDrafts()).toEqual([small]);
    expect(draftsArePersisted()).toBe(true);
  });

  it("still stores removals and claims when the browser won't take one draft", () => {
    const setItem = Storage.prototype.setItem;
    // A store that is nearly full: anything holding the big draft won't fit.
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) {
      if (value.includes("big-one")) throw new DOMException("full", "QuotaExceededError");
      setItem.call(this, key, value);
    });
    const saved = putDraft("finding", { n: 1 });
    const big = putDraft("finding", { note: "big-one" });
    expect(listDrafts().map((draft) => draft.id)).toEqual([saved.id, big.id]);
    expect(draftsArePersisted()).toBe(false);
    expect(stored()?.drafts.map((draft) => draft.id)).toEqual([saved.id]);

    // Saving the first removes it, and the removal reaches storage.
    discardDraft(saved.id);
    expect(stored()?.drafts).toEqual([]);
    expect(listDrafts().map((draft) => draft.id)).toEqual([big.id]);

    // An edit that fits again is stored, and all is well.
    putDraft("finding", { note: "small now" }, big.id);
    expect(draftsArePersisted()).toBe(true);
    expect(stored()?.drafts.map((draft) => draft.id)).toEqual([big.id]);
  });

  it("keeps an earlier stored version of a draft whose change won't fit", () => {
    const setItem = Storage.prototype.setItem;
    const draft = putDraft("finding", { note: "short" });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) {
      if (value.includes("big-one")) throw new DOMException("full", "QuotaExceededError");
      setItem.call(this, key, value);
    });
    putDraft("finding", { note: "big-one" }, draft.id);
    expect(stored()?.drafts[0]?.data).toEqual({ note: "short" });
    expect(listDrafts()[0]?.data).toEqual({ note: "big-one" });
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

describe("discardAllDrafts", () => {
  it("discards every draft and the unreadable copies", () => {
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, "{bad");
    listDrafts();
    putDraft("finding", {});
    discardAllDrafts();
    expect(listDrafts()).toEqual([]);
    expect(unreadableCopies()).toEqual([]);
    expect(stored()?.drafts).toEqual([]);
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
      version: 2,
      epoch: "e",
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
