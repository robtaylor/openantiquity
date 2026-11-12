import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client.js";
import {
  CLAIM_LEASE_MS,
  type DraftSaver,
  defineDraftKind,
  draftLabel,
  onDraftsSaved,
  registerDraftSaver,
  resetSaversForTests,
  saveWaitingDrafts,
  useKindDrafts,
} from "./savers.js";
import {
  adoptDraftsAfterSignIn,
  DRAFTS_STORAGE_KEY,
  DraftBusyError,
  listAllDrafts,
  noteSignInStarted,
  putDraft,
  resetDraftsForTests,
  sendHeldDraft,
  setDraftsViewer,
  updateDrafts,
} from "./store.js";

/** The signed-in person, by `accountIdentity`. */
const ME = "person:42";
const SOMEONE_ELSE = "person:7";

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
  setDraftsViewer(ME);
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
    const [a, b] = await Promise.all([saveWaitingDrafts(ME), saveWaitingDrafts(ME)]);
    expect(a).toBe(b);
    expect(a).toEqual({ saved: 2, failed: 0, stopped: null });
    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenCalledWith({ note: "one" }, { draftId: first.id });
    expect(save).toHaveBeenCalledWith({ note: "two" }, { draftId: second.id });
    expect(listAllDrafts()).toEqual([]);

    // Nothing is left to save.
    await saveWaitingDrafts(ME);
    expect(save).toHaveBeenCalledTimes(2);
  });

  it("saves drafts stored before a reload, as after a provider's round trip", async () => {
    putDraft(PROBE, { note: "before the round trip" });
    resetDraftsForTests();
    const save = vi.fn(async () => {});
    register(probeSaver(save));
    await saveWaitingDrafts(ME);
    expect(save).toHaveBeenCalledOnce();
    expect(listAllDrafts()).toEqual([]);
  });

  it("keeps a draft that fails, with the reason, and goes on to the next", async () => {
    register(
      probeSaver(async (data) => {
        if (data.note === "bad") throw new ApiError(422, "validation_error", "The note is too long.");
      }),
    );
    const bad = putDraft(PROBE, { note: "bad" });
    putDraft(PROBE, { note: "good" });
    const report = await saveWaitingDrafts(ME);
    expect(report).toEqual({ saved: 1, failed: 1, stopped: null });
    expect(listAllDrafts()).toEqual([
      expect.objectContaining({
        id: bad.id,
        state: "failed",
        failure: { code: "validation_error", message: "The note is too long." },
      }),
    ]);
    expect(listAllDrafts()[0]?.claim).toBeUndefined();

    // A failed draft waits for the person to try again.
    await saveWaitingDrafts(ME);
    expect(listAllDrafts()[0]?.state).toBe("failed");
  });

  it("gives a plain reason for a failure that isn't from the API", async () => {
    register(
      probeSaver(async () => {
        throw new TypeError("x is undefined");
      }),
    );
    putDraft(PROBE, { note: "a" });
    await saveWaitingDrafts(ME);
    expect(listAllDrafts()[0]?.failure).toEqual({
      code: "save_failed",
      message: "Something went wrong while saving it.",
    });
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
    const report = await saveWaitingDrafts(ME);
    expect(report).toEqual({ saved: 0, failed: 0, stopped });
    expect(save).toHaveBeenCalledOnce();
    expect(listAllDrafts().map((draft) => draft.state)).toEqual(["waiting", "waiting"]);
  });

  it("marks a draft it can't read back as failed, without sending it", async () => {
    const save = vi.fn(async () => {});
    register(probeSaver(save));
    putDraft(PROBE, { wrong: true });
    const report = await saveWaitingDrafts(ME);
    expect(report.failed).toBe(1);
    expect(save).not.toHaveBeenCalled();
    expect(listAllDrafts()[0]?.failure?.code).toBe("draft_unreadable");
  });

  it("leaves drafts with no saver waiting, and saves them once a saver arrives", async () => {
    putDraft(PROBE, { note: "a" });
    expect(await saveWaitingDrafts(ME)).toEqual({ saved: 0, failed: 0, stopped: null });
    expect(listAllDrafts()[0]?.state).toBe("waiting");
    const save = vi.fn(async () => {});
    register(probeSaver(save));
    await saveWaitingDrafts(ME);
    expect(save).toHaveBeenCalledOnce();
  });

  it("skips a draft another tab is saving, and takes it over when that tab has gone quiet", async () => {
    const save = vi.fn(async () => {});
    register(probeSaver(save));
    const draft = putDraft(PROBE, { note: "a" });
    updateDrafts((drafts) =>
      drafts.map((item) => ({ ...item, state: "saving", claim: { tab: "another-tab", at: Date.now() } })),
    );
    await saveWaitingDrafts(ME);
    expect(save).not.toHaveBeenCalled();

    updateDrafts((drafts) =>
      drafts.map((item) => ({ ...item, claim: { tab: "another-tab", at: Date.now() - CLAIM_LEASE_MS - 1 } })),
    );
    await saveWaitingDrafts(ME);
    expect(save).toHaveBeenCalledWith({ note: "a" }, { draftId: draft.id });
    expect(listAllDrafts()).toEqual([]);
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
    await saveWaitingDrafts(ME);
    expect(save).not.toHaveBeenCalled();
  });

  it("tells listeners once per run that did something", async () => {
    register(probeSaver(async () => {}));
    const heard = vi.fn();
    const stop = onDraftsSaved(heard);
    putDraft(PROBE, { note: "a" });
    await Promise.all([saveWaitingDrafts(ME), saveWaitingDrafts(ME)]);
    await saveWaitingDrafts(ME);
    stop();
    expect(heard).toHaveBeenCalledOnce();
    expect(heard).toHaveBeenCalledWith({ saved: 1, failed: 0, stopped: null });
  });
});

describe("an edit while a draft is being saved", () => {
  it("is refused while the save is going, so nothing is lost", async () => {
    let release: () => void = () => {};
    const sent: string[] = [];
    register(
      probeSaver(async (data) => {
        sent.push(data.note);
        await new Promise<void>((resolve) => {
          release = resolve;
        });
      }),
    );
    const draft = putDraft(PROBE, { note: "first" });
    const run = saveWaitingDrafts(ME);
    await vi.waitFor(() => expect(sent).toEqual(["first"]));
    expect(listAllDrafts()[0]?.state).toBe("saving");
    expect(() => putDraft(PROBE, { note: "edited" }, draft.id)).toThrow(DraftBusyError);
    release();
    await run;
    expect(listAllDrafts()).toEqual([]);
  });

  it("that lands anyway is kept and sent too, rather than removed with the old save", async () => {
    let release: () => void = () => {};
    const sent: string[] = [];
    register(
      probeSaver(async (data) => {
        sent.push(data.note);
        if (sent.length === 1)
          await new Promise<void>((resolve) => {
            release = resolve;
          });
      }),
    );
    putDraft(PROBE, { note: "first" });
    const run = saveWaitingDrafts(ME);
    await vi.waitFor(() => expect(sent).toEqual(["first"]));
    // As another tab of an older build might: a new version, written over the claim.
    updateDrafts((drafts) =>
      drafts.map((item) => ({ ...item, data: { note: "edited" }, updatedAt: "2099-01-01T00:00:00.000Z" })),
    );
    release();
    const report = await run;
    expect(sent).toEqual(["first", "edited"]);
    expect(report.saved).toBe(2);
    expect(listAllDrafts()).toEqual([]);
  });
});

describe("whose drafts are saved", () => {
  it("saves only the signed-in person's own drafts", async () => {
    const save = vi.fn(async (_data: Probe) => {});
    register(probeSaver(save));
    setDraftsViewer(SOMEONE_ELSE);
    putDraft(PROBE, { note: "theirs" });
    setDraftsViewer(ME);
    putDraft(PROBE, { note: "mine" });
    expect(await saveWaitingDrafts(ME)).toEqual({ saved: 1, failed: 0, stopped: null });
    expect(save.mock.calls.map(([data]) => data.note)).toEqual(["mine"]);
    expect(listAllDrafts().map((draft) => (draft.data as Probe).note)).toEqual(["theirs"]);
  });

  it("makes the drafts this tab made signed out the person's after a sign-in from this tab, and no earlier ones", async () => {
    const save = vi.fn(async (_data: Probe) => {});
    register(probeSaver(save));
    setDraftsViewer(null);
    putDraft(PROBE, { note: "left by someone" });
    // Someone left that in an earlier visit. This tab's visit is a new one.
    updateDrafts((drafts) => drafts.map((draft) => ({ ...draft, owner: { signedOut: "an-old-visit" } })));
    putDraft(PROBE, { note: "just now" });
    noteSignInStarted("provider");
    expect(adoptDraftsAfterSignIn(ME, ["provider"])).toBe(1);
    await saveWaitingDrafts(ME);
    expect(save.mock.calls.map(([data]) => data.note)).toEqual(["just now"]);
    expect(listAllDrafts()).toHaveLength(1);
  });

  it("holds a second look adopted at sign-in until the person says to send it", async () => {
    const save = vi.fn(async (_data: Probe) => {});
    register(probeSaver(save));
    register({ ...probeSaver(save), kind: "observation", label: "Second look" });
    setDraftsViewer(null);
    const answer = putDraft("observation", { note: "yes, I can see it" });
    noteSignInStarted("provider");
    expect(adoptDraftsAfterSignIn(ME, ["provider"])).toBe(1);
    expect(await saveWaitingDrafts(ME)).toEqual({ saved: 0, failed: 0, stopped: null });
    expect(save).not.toHaveBeenCalled();
    sendHeldDraft(answer.id, ME);
    expect(await saveWaitingDrafts(ME)).toEqual({ saved: 1, failed: 0, stopped: null });
  });
});

describe("defineDraftKind", () => {
  it("gives a kind's put and its drafts typed data", () => {
    const probes = defineDraftKind<Probe>(probeSaver(async () => {}));
    unregister.push(probes.unregister);
    const draft = probes.put({ note: "typed" });
    putDraft(PROBE, { wrong: true });
    putDraft("other", { note: "not a probe" });
    const { result } = renderHook(() => useKindDrafts(probes));
    expect(result.current.map((item) => item.data.note)).toEqual(["typed"]);
    expect(probes.read(draft)).toEqual({ note: "typed" });
    // @ts-expect-error: a probe's data needs a note
    expect(() => probes.put({ text: "untyped" })).not.toThrow();
  });
});

describe("registerDraftSaver", () => {
  it("refuses a second saver for the same kind", () => {
    register(probeSaver(async () => {}));
    expect(() => registerDraftSaver(probeSaver(async () => {}))).toThrow(/already registered/);
  });

  it("does nothing when the same saver is registered again, as a hot reload does", () => {
    const saver = probeSaver(async () => {});
    register(saver);
    expect(() => register(saver)).not.toThrow();
  });

  it("names a draft by its saver", () => {
    const draft = putDraft(PROBE, { note: "hello" });
    expect(draftLabel(draft)).toEqual({ label: "Draft", description: null });
    register(probeSaver(async () => {}));
    expect(draftLabel(draft)).toEqual({ label: "Probe", description: "Probe saying hello" });
  });
});
