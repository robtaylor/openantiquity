import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  adoptDraftsAfterSignIn,
  adoptFormerDrafts,
  claimDraftsAsOwn,
  DRAFTS_STORAGE_KEY,
  DRAFTS_UNREADABLE_KEY,
  DraftTooLargeError,
  discardAllDrafts,
  discardDraft,
  draftsArePersisted,
  listAllDrafts,
  listDrafts,
  listOthersDrafts,
  noteSignInStarted,
  putDraft,
  resetDraftsForTests,
  restoreDraft,
  retryDraft,
  SIGN_IN_MAX_MS,
  sendHeldDraft,
  setDraftsViewer,
  updateDrafts,
  useAllDrafts,
  useDrafts,
  VISIT_DRAFT_MAX_AGE_MS,
} from "./store.js";

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetDraftsForTests();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function stored(): { version: number; drafts: Array<Record<string, unknown>> } | null {
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
    expect(stored()).toEqual({ version: 3, drafts: [draft] });
  });

  it("stamps a draft with who made it: the account, or this tab's signed-out visit", () => {
    const signedOut = putDraft("finding", {});
    expect(signedOut.owner).toEqual({ signedOut: expect.any(String) });
    // The visit is this tab's, not the browser's: it is kept beside the tab, never with the drafts.
    expect(JSON.stringify(stored())).toContain(Object.values(signedOut.owner ?? {})[0]);
    expect(window.sessionStorage.getItem("fieldclub.drafts.visit")).toBe(
      (signedOut.owner as { signedOut: string }).signedOut,
    );
    setDraftsViewer("account-a");
    const signedIn = putDraft("finding", {});
    expect(signedIn.owner).toEqual({ account: "account-a" });
    // Editing keeps the owner.
    expect(putDraft("finding", { n: 2 }, signedOut.id).owner).toEqual(signedOut.owner);
  });

  it("writes nothing when there is nothing to take over, so it can't write over another tab's claim", () => {
    putDraft("finding", {});
    noteSignInStarted("provider");
    adoptDraftsAfterSignIn("account-a", ["provider"]);
    noteSignInStarted("provider");
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    expect(adoptDraftsAfterSignIn("account-a", ["provider"])).toBe(0);
    expect(setItem).not.toHaveBeenCalledWith(DRAFTS_STORAGE_KEY, expect.anything());
  });

  it("moves drafts kept under an account's former identity to its id, and no one else's", () => {
    // Drafts were once keyed to when the account was made. The person's id replaces it at sign-in.
    setDraftsViewer("2026-11-01T10:00:00Z");
    putDraft("finding", { n: 1 });
    setDraftsViewer("2026-10-01T09:00:00Z");
    putDraft("finding", { n: 2 });
    setDraftsViewer(null);
    expect(adoptFormerDrafts("2026-11-01T10:00:00Z", "person:42")).toBe(1);
    expect(listAllDrafts().map((draft) => draft.owner)).toEqual([
      { account: "person:42" },
      { account: "2026-10-01T09:00:00Z" },
    ]);
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    expect(adoptFormerDrafts("2026-11-01T10:00:00Z", "person:42")).toBe(0);
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });

  it("replaces a draft given its id, keeping when it was made", () => {
    const first = putDraft("finding", { n: 1 });
    const second = putDraft("finding", { n: 2 }, first.id);
    expect(listAllDrafts()).toHaveLength(1);
    expect(second).toMatchObject({ id: first.id, createdAt: first.createdAt, data: { n: 2 } });
  });

  it("reads what an earlier page load stored, as a reload would", () => {
    const draft = putDraft("square", { square: "SU1069" });
    resetDraftsForTests();
    expect(listAllDrafts()).toEqual([draft]);
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
    expect(listAllDrafts()[0]?.failure).toBeUndefined();
    const gone = discardDraft(draft.id);
    expect(listAllDrafts()).toEqual([]);
    if (!gone) throw new Error("discardDraft returned nothing");
    restoreDraft(gone);
    expect(listAllDrafts().map((item) => item.id)).toEqual([draft.id]);
  });
});

describe("reading damaged or old data", () => {
  it.each([
    ["not JSON", "{not json"],
    ["a bare list from an older build", JSON.stringify([{ id: "a" }])],
    ["drafts that aren't a list", JSON.stringify({ version: 2, drafts: "x" })],
  ])("starts empty from %s and keeps the unreadable copy", (_label, raw) => {
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, raw);
    expect(listAllDrafts()).toEqual([]);
    expect(unreadableCopies()).toEqual([raw]);
    // And the next write doesn't fail on it.
    putDraft("finding", {});
    expect(listAllDrafts()).toHaveLength(1);
  });

  it("never writes an unreadable copy over an earlier one", () => {
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, "{bad1");
    listAllDrafts();
    vi.useFakeTimers({ now: Date.now() + 1000, toFake: ["Date"] });
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, "{bad2");
    resetDraftsForTests();
    listAllDrafts();
    vi.useRealTimers();
    expect(unreadableCopies()).toEqual(["{bad1", "{bad2"]);
  });

  it("leaves a newer build's drafts alone, and keeps this page's own in memory", () => {
    const newer = JSON.stringify({ version: 4, drafts: [{ anything: true }] });
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, newer);
    expect(listAllDrafts()).toEqual([]);
    const draft = putDraft("finding", { n: 1 });
    expect(listAllDrafts()).toEqual([draft]);
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
    expect(listAllDrafts()).toEqual([{ ...old, owner: null }]);
    putDraft("finding", {});
    expect(stored()?.version).toBe(3);
  });

  it("migrates version 2, whose signed-out drafts were the whole browser's, to nobody's", () => {
    const old = {
      id: "left",
      kind: "observation",
      data: { public_id: "ABC123" },
      owner: { signedOut: "browser-epoch" },
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      state: "waiting",
    };
    window.localStorage.setItem(
      DRAFTS_STORAGE_KEY,
      JSON.stringify({ version: 2, epoch: "browser-epoch", drafts: [old] }),
    );
    expect(listAllDrafts()).toEqual([old]);
    expect(listDrafts()).toEqual([]);
    noteSignInStarted("provider");
    expect(adoptDraftsAfterSignIn("person:B", ["provider"])).toBe(0);
    putDraft("finding", {});
    expect(stored()).not.toHaveProperty("epoch");
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
        version: 3,
        drafts: [good, { id: 3 }, null, { ...good, id: "odd", state: "lost" }],
      }),
    );
    const drafts = listAllDrafts();
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
    expect(listAllDrafts()).toEqual([draft]);
    expect(draftsArePersisted()).toBe(false);
  });

  it("refuses a draft too big to keep, and goes on working", () => {
    const small = putDraft("finding", { n: 1 });
    expect(() => putDraft("finding", { text: "x".repeat(6_000_000) })).toThrow(DraftTooLargeError);
    expect(listAllDrafts()).toEqual([small]);
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
    expect(listAllDrafts().map((draft) => draft.id)).toEqual([saved.id, big.id]);
    expect(draftsArePersisted()).toBe(false);
    expect(stored()?.drafts.map((draft) => draft.id)).toEqual([saved.id]);

    // Saving the first removes it, and the removal reaches storage.
    discardDraft(saved.id);
    expect(stored()?.drafts).toEqual([]);
    expect(listAllDrafts().map((draft) => draft.id)).toEqual([big.id]);

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
    expect(listAllDrafts()[0]?.data).toEqual({ note: "big-one" });
  });

  it("works with no localStorage at all", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    resetDraftsForTests();
    const draft = putDraft("finding", { n: 1 });
    expect(listAllDrafts()).toEqual([draft]);
    expect(draftsArePersisted()).toBe(false);
  });
});

describe("discardAllDrafts", () => {
  it("discards every draft and the unreadable copies", () => {
    window.localStorage.setItem(DRAFTS_STORAGE_KEY, "{bad");
    listAllDrafts();
    putDraft("finding", {});
    discardAllDrafts();
    expect(listAllDrafts()).toEqual([]);
    expect(unreadableCopies()).toEqual([]);
    expect(stored()?.drafts).toEqual([]);
  });
});

describe("useDrafts", () => {
  it("sees changes made here and in other tabs", () => {
    const { result } = renderHook(() => useAllDrafts());
    expect(result.current).toEqual([]);
    act(() => {
      putDraft("finding", { n: 1 });
    });
    expect(result.current).toHaveLength(1);

    // Another tab writes, and the browser tells this one.
    const other = {
      version: 3,
      drafts: [
        ...(listAllDrafts() as unknown[]),
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

describe("whose drafts are whose (Decision 0022)", () => {
  it("shows a signed-out visitor only the drafts this tab made, and keeps them through a reload", () => {
    const mine = putDraft("finding", { n: 1 });
    resetDraftsForTests();
    expect(listDrafts().map((draft) => draft.id)).toEqual([mine.id]);
    // A new tab is a new visit: the draft is someone else's as far as it can tell.
    resetDraftsForTests({ newTab: true });
    expect(listDrafts()).toEqual([]);
    expect(listOthersDrafts().map((draft) => draft.id)).toEqual([mine.id]);
  });

  it("takes this visit's drafts for an account only after a sign-in that started in this tab", () => {
    const finding = putDraft("finding", { n: 1 });
    const answer = putDraft("observation", { public_id: "ABC123", answer: { visible: "yes" }, reveal: true });
    noteSignInStarted("provider");
    // The provider sends the person back: a page load in the same tab.
    resetDraftsForTests();
    expect(adoptDraftsAfterSignIn("person:A", ["provider"])).toBe(2);
    setDraftsViewer("person:A");
    const drafts = listDrafts();
    expect(drafts.map((draft) => draft.owner)).toEqual([{ account: "person:A" }, { account: "person:A" }]);
    // The finding is saved without asking. The second look waits until the person says to send it.
    expect(drafts.find((draft) => draft.id === finding.id)?.held).toBeUndefined();
    expect(drafts.find((draft) => draft.id === answer.id)?.held).toBe(true);
    sendHeldDraft(answer.id, "person:B");
    expect(listAllDrafts().find((draft) => draft.id === answer.id)?.held).toBe(true);
    sendHeldDraft(answer.id, "person:A");
    expect(listAllDrafts().find((draft) => draft.id === answer.id)?.held).toBeUndefined();
  });

  it("never takes drafts left from before for someone who arrives already signed in", () => {
    // Someone answers a second look signed out, asks for the comparison, and leaves without signing in.
    putDraft("observation", { public_id: "ABC123", answer: { visible: "yes" }, reveal: true });
    // The next person opens the site in that browser: a new tab, already signed in.
    resetDraftsForTests({ newTab: true });
    expect(adoptDraftsAfterSignIn("person:B", ["provider"])).toBe(0);
    setDraftsViewer("person:B");
    expect(listDrafts()).toEqual([]);
    expect(listOthersDrafts()).toHaveLength(1);
    expect(listOthersDrafts()[0]?.owner).not.toEqual({ account: "person:B" });
    // Even in the same tab, with no sign-in started here, nothing is taken.
    resetDraftsForTests();
    putDraft("finding", {});
    expect(adoptDraftsAfterSignIn("person:B", ["provider", "email", "dev"])).toBe(0);
  });

  it("takes nothing after a sign-in started too long ago, or another way, or after this tab's visit ended", () => {
    vi.useFakeTimers({ now: new Date("2026-11-12T09:00:00Z") });
    try {
      putDraft("finding", {});
      noteSignInStarted("provider");
      vi.setSystemTime(Date.now() + SIGN_IN_MAX_MS + 1);
      expect(adoptDraftsAfterSignIn("person:A", ["provider"])).toBe(0);

      noteSignInStarted("email");
      expect(adoptDraftsAfterSignIn("person:A", ["provider"])).toBe(0);

      // A draft older than a day isn't taken to be this visit's, however the sign-in went.
      noteSignInStarted("provider");
      vi.setSystemTime(Date.now() + VISIT_DRAFT_MAX_AGE_MS);
      noteSignInStarted("provider");
      expect(adoptDraftsAfterSignIn("person:A", ["provider"])).toBe(0);
      expect(listDrafts()).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("starts a new visit when someone signs out, so the next person in the tab gets nothing of before", () => {
    setDraftsViewer(null);
    const before = putDraft("finding", { n: 1 });
    noteSignInStarted("dev");
    setDraftsViewer("person:A");
    expect(adoptDraftsAfterSignIn("person:A", ["dev"])).toBe(1);
    const theirs = putDraft("finding", { n: 2 });
    // A sign-out, the session running out or a ban: the account layer says nobody is signed in.
    setDraftsViewer(null);
    expect(listDrafts()).toEqual([]);
    const next = putDraft("finding", { n: 3 });
    expect(next.owner).not.toEqual(before.owner);
    noteSignInStarted("dev");
    setDraftsViewer("person:B");
    expect(adoptDraftsAfterSignIn("person:B", ["dev"])).toBe(1);
    expect(listDrafts().map((draft) => draft.id)).toEqual([next.id]);
    expect(
      listOthersDrafts()
        .map((draft) => draft.id)
        .sort(),
    ).toEqual([before.id, theirs.id].sort());
    // A's own drafts are A's again when A is back.
    setDraftsViewer("person:A");
    expect(
      listDrafts()
        .map((draft) => draft.id)
        .sort(),
    ).toEqual([before.id, theirs.id].sort());
  });

  it("lets a signed-in person claim drafts left here, which are then sent as theirs", () => {
    const left = putDraft("observation", { public_id: "ABC123", answer: { visible: "no" }, reveal: false });
    resetDraftsForTests({ newTab: true });
    setDraftsViewer("person:B");
    claimDraftsAsOwn([left.id], "person:B");
    expect(listDrafts()).toEqual([{ ...left, owner: { account: "person:B" } }]);
    expect(listDrafts()[0]?.held).toBeUndefined();
  });

  it("is told who is there only once it is known, so a page load isn't taken for a change of person", () => {
    const draft = putDraft("finding", {});
    resetDraftsForTests();
    setDraftsViewer(undefined);
    setDraftsViewer(null);
    expect(listDrafts().map((item) => item.id)).toEqual([draft.id]);
  });
});
