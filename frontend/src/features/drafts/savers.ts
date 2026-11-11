/**
 * How each kind of draft is saved, and the run that saves them.
 *
 * A feature defines its kind once, at start-up, and uses what comes back:
 *
 *     export const findingDrafts = defineDraftKind<FindingDraft>({
 *       kind: DRAFT_KINDS.finding,
 *       label: "Finding",
 *       parse: (data) => (isFindingDraft(data) ? data : null),
 *       save: (data, { draftId }) => createFinding(data, draftId),
 *       describe: (data) => `${data.featureLabel} near ${data.gridRef}`,
 *     });
 *
 *     findingDrafts.put(data)            // typed: data must be a FindingDraft
 *     useKindDrafts(findingDrafts)       // in a component: this kind's drafts, typed
 *
 * `parse` checks what was read back from storage, which may be old or
 * damaged, and returns null for data it can't use. `save` sends it, and
 * throws to fail (an `ApiError` gives the reason shown to the person).
 * `draftId` is stable for the draft's life, for a saver that can send an
 * idempotency key. Defining the same saver object twice, as a hot reload
 * does, is harmless; a second, different saver for a kind is refused.
 *
 * `saveWaitingDrafts(account)` saves every waiting draft of `account`'s
 * whose kind has a saver, each exactly once. One run happens at a time in a
 * page, and across tabs a Web Lock makes one tab wait for another; each
 * draft is also claimed in storage before it is sent, so a second runner
 * skips it. A saved draft is removed, unless it was changed while it was
 * being sent, when it waits to be sent again. A failed one is kept with its
 * reason. A 401 or `onboarding_required` stops the run and leaves the rest
 * waiting, because every save after it would fail the same way.
 */

import { useMemo, useSyncExternalStore } from "react";
import { ApiError } from "../../api/client.js";
import {
  type Draft,
  type DraftFailure,
  hasStaleStoredCopy,
  isBeingSaved,
  isOwnDraft,
  putDraft,
  readFreshDrafts,
  updateDrafts,
  useDrafts,
} from "./store.js";

export { CLAIM_LEASE_MS } from "./store.js";

export interface DraftSaver<T = unknown> {
  kind: string;
  /** What one of these is called, such as "Finding". */
  label: string;
  parse: (data: unknown) => T | null;
  save: (data: T, context: { draftId: string }) => Promise<void>;
  /** One line about this draft, such as "Round barrow near SU 123 456". */
  describe?: (data: T) => string;
}

const savers = new Map<string, DraftSaver>();
/** The object each kind was registered with, to tell a repeat from a rival. */
const registered = new Map<string, unknown>();
let saversVersion = 0;
const saverListeners = new Set<() => void>();

function saversChanged(): void {
  saversVersion += 1;
  for (const listener of [...saverListeners]) listener();
}

/**
 * Register the saver for a kind. Returns a function that removes it.
 * Registering the same object again does nothing. A different saver for a
 * kind that has one throws, except under a development server's hot reload,
 * where the new module's saver replaces the old one.
 */
export function registerDraftSaver<T>(saver: DraftSaver<T>): () => void {
  const stored = saver as unknown as DraftSaver;
  const unregister = (): void => {
    if (registered.get(saver.kind) === saver) {
      savers.delete(saver.kind);
      registered.delete(saver.kind);
      saversChanged();
    }
  };
  const existing = registered.get(saver.kind);
  if (existing === saver) return unregister;
  // Vitest has `import.meta.hot` too, and its tests want the refusal.
  const hotReload = import.meta.hot !== undefined && import.meta.env.MODE !== "test";
  if (existing !== undefined && !hotReload) {
    throw new Error(`A saver for "${saver.kind}" drafts is already registered`);
  }
  savers.set(saver.kind, stored);
  registered.set(saver.kind, saver);
  saversChanged();
  return unregister;
}

/** A draft of one kind, with its data read by that kind's saver. */
export type KindDraft<T> = Omit<Draft, "data"> & { data: T };

export interface DraftKind<T> {
  readonly kind: string;
  /** Add a draft, or replace the one with `id`. Throws as `putDraft` does. */
  put: (data: T, id?: string) => Draft;
  /** This kind's data in `draft`, or null when it isn't this kind's or can't be read. */
  read: (draft: Draft) => T | null;
  unregister: () => void;
}

/** Register a kind's saver and get back functions bound to that kind and its data's type. */
export function defineDraftKind<T>(saver: DraftSaver<T>): DraftKind<T> {
  const unregister = registerDraftSaver(saver);
  return {
    kind: saver.kind,
    put: (data, id) => putDraft(saver.kind, data, id),
    read: (draft) => (draft.kind === saver.kind ? saver.parse(draft.data) : null),
    unregister,
  };
}

/** A kind's drafts whose data can be read, with that data typed, kept up to date. */
export function useKindDrafts<T>(draftKind: DraftKind<T>): readonly KindDraft<T>[] {
  const drafts = useDrafts(draftKind.kind);
  return useMemo(
    () =>
      drafts.flatMap((draft): KindDraft<T>[] => {
        const data = draftKind.read(draft);
        return data === null ? [] : [{ ...draft, data }];
      }),
    [drafts, draftKind],
  );
}

export function saverFor(kind: string): DraftSaver | undefined {
  return savers.get(kind);
}

/** Changes whenever a saver is registered or removed. */
export function useSaversVersion(): number {
  return useSyncExternalStore(
    (listener) => {
      saverListeners.add(listener);
      return () => saverListeners.delete(listener);
    },
    () => saversVersion,
  );
}

/** What the person sees a draft called. */
export function draftLabel(draft: Draft): { label: string; description: string | null } {
  const saver = saverFor(draft.kind);
  if (!saver) return { label: "Draft", description: null };
  const data = saver.parse(draft.data);
  return { label: saver.label, description: data !== null && saver.describe ? saver.describe(data) : null };
}

// --------------------------------------------------------------------------
// Saving
// --------------------------------------------------------------------------

export interface SaveReport {
  saved: number;
  failed: number;
  /** Set when the run stopped early, leaving the rest waiting. */
  stopped: "signed_out" | "welcome_needed" | null;
}

const LOCK_NAME = "fieldclub.drafts.save";
const TAB = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Math.random());

const UNREADABLE: DraftFailure = {
  code: "draft_unreadable",
  message: "This draft couldn't be read back, so it can't be saved.",
};

const STORAGE_FULL: DraftFailure = {
  code: "storage_full",
  message: "This browser's storage is full, so it couldn't be saved safely. Discard something and try again.",
};

function failureFrom(error: unknown): DraftFailure {
  if (error instanceof ApiError) {
    const failure: DraftFailure = { code: error.code, message: error.message };
    if (error.fields.length > 0) failure.fields = error.fields.map((problem) => problem.field);
    return failure;
  }
  return { code: "save_failed", message: "Something went wrong while saving it." };
}

/** True when `draft` is `account`'s, has a saver, and nobody is saving it. */
export function isDue(draft: Draft, account: string, now = Date.now()): boolean {
  if (!saverFor(draft.kind) || !isOwnDraft(draft, account)) return false;
  return draft.state === "waiting" || (draft.state === "saving" && !isBeingSaved(draft, now));
}

/** Mark `id` as being saved by this tab, if it is still due. Returns the claimed draft, or null. */
function claim(id: string, account: string): Draft | null {
  const now = Date.now();
  let claimed: Draft | null = null;
  updateDrafts((drafts) =>
    drafts.map((draft) => {
      if (draft.id !== id || !isDue(draft, account, now)) return draft;
      const { failure: _failure, ...rest } = draft;
      claimed = { ...rest, state: "saving", claim: { tab: TAB, at: now } };
      return claimed;
    }),
  );
  if (claimed !== null && hasStaleStoredCopy(id)) {
    // Other tabs would still see it waiting, and could send it too.
    finish(id, STORAGE_FULL);
    return null;
  }
  // Without a lock, another tab could have written in between. Read back to be sure.
  const check = readFreshDrafts().find((draft) => draft.id === id);
  return claimed !== null && check?.claim?.tab === TAB ? claimed : null;
}

/**
 * Settle this tab's claim on `id`. A save is recorded by removing the draft,
 * but only if it is still the version that was sent: one changed meanwhile
 * goes back to waiting, so the change is saved too.
 */
function finish(id: string, outcome: { saved: string } | "release" | DraftFailure): void {
  updateDrafts((drafts) =>
    drafts.flatMap((draft): Draft[] => {
      if (draft.id !== id) return [draft];
      const ours = draft.claim?.tab === TAB;
      if (typeof outcome === "object" && "saved" in outcome && ours && draft.updatedAt === outcome.saved) return [];
      if (!ours) return [draft];
      const { claim: _claim, failure: _failure, ...rest } = draft;
      if (outcome === "release" || "saved" in outcome) return [{ ...rest, state: "waiting" }];
      return [{ ...rest, state: "failed", failure: outcome }];
    }),
  );
}

/**
 * Run `task` holding the lock every tab takes before writing drafts on its
 * own account (saving, or taking over drafts at sign-in). Tabs don't see
 * each other's writes at once, so without it one tab could write over
 * another's claim.
 */
export async function withDraftsLock<T>(task: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  if (locks && typeof locks.request === "function") return locks.request(LOCK_NAME, task);
  return task();
}

async function run(account: string): Promise<SaveReport> {
  return withDraftsLock(async () => {
    const report: SaveReport = { saved: 0, failed: 0, stopped: null };
    // Each version of a draft is tried once a run. A draft changed after it was sent is a new version.
    const tried = new Set<string>();
    const version = (draft: Draft): string => `${draft.id}@${draft.updatedAt}`;
    for (;;) {
      // Read afresh each time: another tab, or the person, may have changed things.
      const now = Date.now();
      const next = readFreshDrafts().find((draft) => !tried.has(version(draft)) && isDue(draft, account, now));
      if (!next) return report;
      tried.add(version(next));
      const saver = saverFor(next.kind);
      const draft = claim(next.id, account);
      if (!saver || !draft) continue;
      const data = saver.parse(draft.data);
      if (data === null) {
        finish(draft.id, UNREADABLE);
        report.failed += 1;
        continue;
      }
      try {
        await saver.save(data, { draftId: draft.id });
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.code === "onboarding_required")) {
          finish(draft.id, "release");
          report.stopped = error.status === 401 ? "signed_out" : "welcome_needed";
          return report;
        }
        finish(draft.id, failureFrom(error));
        report.failed += 1;
        continue;
      }
      finish(draft.id, { saved: draft.updatedAt });
      report.saved += 1;
    }
  });
}

let running: { account: string; report: Promise<SaveReport> } | null = null;
const reportListeners = new Set<(report: SaveReport) => void>();

/** Hear the outcome of every run that saved or failed something, once per run. */
export function onDraftsSaved(listener: (report: SaveReport) => void): () => void {
  reportListeners.add(listener);
  return () => {
    reportListeners.delete(listener);
  };
}

/**
 * Save every waiting draft of `account`'s that has a saver. Calls made for
 * the same account while a run is going share it, so a component that asks
 * twice causes one run. A call for someone else waits for that run to end.
 */
export function saveWaitingDrafts(account: string): Promise<SaveReport> {
  if (running?.account === account) return running.report;
  const before = running?.report.catch(() => undefined) ?? Promise.resolve();
  const report = before
    .then(() => run(account))
    .then((result) => {
      if (result.saved > 0 || result.failed > 0) for (const listener of [...reportListeners]) listener(result);
      return result;
    });
  const current = { account, report };
  running = current;
  const clear = (): void => {
    if (running === current) running = null;
  };
  report.then(clear, clear);
  return report;
}

/** For tests: forget every saver. */
export function resetSaversForTests(): void {
  savers.clear();
  registered.clear();
  saversChanged();
}
