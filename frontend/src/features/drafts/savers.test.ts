import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client.js";
import {
  CLAIM_LEASE_MS,
  type DraftSaver,
  draftLabel,
  onDraftsSaved,
  registerDraftSaver,
  resetSaversForTests,
  saveWaitingDrafts,
} from "./savers.js";
import { DRAFTS_STORAGE_KEY, listDrafts, putDraft, resetDraftsForTests, updateDrafts } from "./store.js";

/** A kind of draft no feature has: proof that the machinery works for any kind. */
const PROBE = "probe";
interface Probe {
  note: string;
}

function isProbe(data: unknown): data is Probe {
  return typeof data === "object" && data !== null && typeof (data as { note?: unknown }).note === "string";
}

function probeSaver(save: DraftSaver<Probe>["save"]): DraftSaver<Probe> {
  return {
    kind: PROBE,
    label: "Probe",
    parse: (data) => (isProbe(data) ? data : null),
    save,
    describe: (data) => `Probe saying ${data.note}`,
  };
}

const unregister: Array<() => void> = [];

beforeEach(() => {
  window.localStorage.clear();
  resetDraftsForTests();
  resetSaversForTests();
});

afterEach(() => {
  for (const stop of unregister.splice(0)) stop();
  vi.useRealTimers();
});

function register(saver: DraftSaver<Probe>): void {
  unregister.push(registerDraftSaver(saver));
}

describe("saveWaitingDrafts", () => {
  it("saves each waiting draft once and removes it, even when asked twice at the same moment", async () => {
    const save = vi.fn(async (_data: Probe, _context: { draftId: string }) => {});
    register(probeSaver(save));
    const first = putDraft(PROBE, { note: "one" });
    const second = putDraft(PROBE, { note: "two" });

    // As React's strict mode would: two effects, back to back.
    const [a, b] = await Promise.all([saveWaitingDrafts(), saveWaitingDrafts()]);
    expect(a).toBe(b);
    expect(a).toEqual({ saved: 2, failed: 0, stopped: null });
    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenCalledWith({ note: "one" }, { draftId: first.id });
    expect(save).toHaveBeenCalledWith({ note: "two" }, { draftId: second.id });
    expect(listDrafts()).toEqual([]);

    // Nothing is left to save.
    await saveWaitingDrafts();
    expect(save).toHaveBeenCalledTimes(2);
  });

  it("saves drafts stored before a reload, as after a provider's round trip", async () => {
    putDraft(PROBE, { note: "before the round trip" });
    resetDraftsForTests();
    const save = vi.fn(async () => {});
    register(probeSaver(save));
    await saveWaitingDrafts();
    expect(save).toHaveBeenCalledOnce();
    expect(listDrafts()).toEqual([]);
  });

  it("keeps a draft that fails, with the reason, and goes on to the next", async () => {
    register(
      probeSaver(async (data) => {
        if (data.note === "bad") throw new ApiError(422, "validation_error", "The note is too long.");
      }),
    );
    const bad = putDraft(PROBE, { note: "bad" });
    putDraft(PROBE, { note: "good" });
    const report = await saveWaitingDrafts();
    expect(report).toEqual({ saved: 1, failed: 1, stopped: null });
    expect(listDrafts()).toEqual([
      expect.objectContaining({
        id: bad.id,
        state: "failed",
        failure: { code: "validation_error", message: "The note is too long." },
      }),
    ]);
    expect(listDrafts()[0]?.claim).toBeUndefined();

    // A failed draft waits for the person to try again.
    await saveWaitingDrafts();
    expect(listDrafts()[0]?.state).toBe("failed");
  });

  it("gives a plain reason for a failure that isn't from the API", async () => {
    register(
      probeSaver(async () => {
        throw new TypeError("x is undefined");
      }),
    );
    putDraft(PROBE, { note: "a" });
    await saveWaitingDrafts();
    expect(listDrafts()[0]?.failure).toEqual({ code: "save_failed", message: "Something went wrong while saving it." });
  });

  it.each([
    [new ApiError(401, "unauthorised", "Sign in first."), "signed_out"],
    [new ApiError(403, "onboarding_required", "Finish the welcome step."), "welcome_needed"],
  ] as const)("stops at %s and leaves every draft waiting", async (error, stopped) => {
    const save = vi.fn(async () => {
      throw error;
    });
    register(probeSaver(save));
    putDraft(PROBE, { note: "a" });
    putDraft(PROBE, { note: "b" });
    const report = await saveWaitingDrafts();
    expect(report).toEqual({ saved: 0, failed: 0, stopped });
    expect(save).toHaveBeenCalledOnce();
    expect(listDrafts().map((draft) => draft.state)).toEqual(["waiting", "waiting"]);
  });

  it("marks a draft it can't read back as failed, without sending it", async () => {
    const save = vi.fn(async () => {});
    register(probeSaver(save));
    putDraft(PROBE, { wrong: true });
    const report = await saveWaitingDrafts();
    expect(report.failed).toBe(1);
    expect(save).not.toHaveBeenCalled();
    expect(listDrafts()[0]?.failure?.code).toBe("draft_unreadable");
  });

  it("leaves drafts with no saver waiting, and saves them once a saver arrives", async () => {
    putDraft(PROBE, { note: "a" });
    expect(await saveWaitingDrafts()).toEqual({ saved: 0, failed: 0, stopped: null });
    expect(listDrafts()[0]?.state).toBe("waiting");
    const save = vi.fn(async () => {});
    register(probeSaver(save));
    await saveWaitingDrafts();
    expect(save).toHaveBeenCalledOnce();
  });

  it("skips a draft another tab is saving, and takes it over when that tab has gone quiet", async () => {
    const save = vi.fn(async () => {});
    register(probeSaver(save));
    const draft = putDraft(PROBE, { note: "a" });
    updateDrafts((drafts) =>
      drafts.map((item) => ({ ...item, state: "saving", claim: { tab: "another-tab", at: Date.now() } })),
    );
    await saveWaitingDrafts();
    expect(save).not.toHaveBeenCalled();

    updateDrafts((drafts) =>
      drafts.map((item) => ({ ...item, claim: { tab: "another-tab", at: Date.now() - CLAIM_LEASE_MS - 1 } })),
    );
    await saveWaitingDrafts();
    expect(save).toHaveBeenCalledWith({ note: "a" }, { draftId: draft.id });
    expect(listDrafts()).toEqual([]);
  });

  it("doesn't send a draft that another tab claimed between reading and claiming", async () => {
    const save = vi.fn(async () => {});
    register(probeSaver(save));
    putDraft(PROBE, { note: "a" });
    // Another tab's claim lands in storage just as this one writes its own.
    const setItem = Storage.prototype.setItem;
    let raced = false;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) {
      setItem.call(this, key, value);
      if (key === DRAFTS_STORAGE_KEY && !raced && value.includes('"saving"')) {
        raced = true;
        setItem.call(this, key, value.replace(/"tab":"[^"]+"/, '"tab":"another-tab"'));
      }
    });
    await saveWaitingDrafts();
    expect(save).not.toHaveBeenCalled();
  });

  it("tells listeners once per run that did something", async () => {
    register(probeSaver(async () => {}));
    const heard = vi.fn();
    const stop = onDraftsSaved(heard);
    putDraft(PROBE, { note: "a" });
    await Promise.all([saveWaitingDrafts(), saveWaitingDrafts()]);
    await saveWaitingDrafts();
    stop();
    expect(heard).toHaveBeenCalledOnce();
    expect(heard).toHaveBeenCalledWith({ saved: 1, failed: 0, stopped: null });
  });
});

describe("registerDraftSaver", () => {
  it("refuses a second saver for the same kind", () => {
    register(probeSaver(async () => {}));
    expect(() => registerDraftSaver(probeSaver(async () => {}))).toThrow(/already registered/);
  });

  it("names a draft by its saver", () => {
    const draft = putDraft(PROBE, { note: "hello" });
    expect(draftLabel(draft)).toEqual({ label: "Draft", description: null });
    register(probeSaver(async () => {}));
    expect(draftLabel(draft)).toEqual({ label: "Probe", description: "Probe saying hello" });
  });
});
