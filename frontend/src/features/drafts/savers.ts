/**
 * How each kind of draft is saved, and the run that saves them.
 *
 * A feature registers one saver for its kind, at start-up:
 *
 *     registerDraftSaver({
 *       kind: DRAFT_KINDS.finding,
 *       label: "Finding",
 *       parse: (data) => (isFindingDraft(data) ? data : null),
 *       save: (data, { draftId }) => createFinding(data, draftId),
 *       describe: (data) => `${data.featureLabel} near ${data.gridRef}`,
 *     });
 *
 * `parse` checks what was read back from storage, which may be old or
 * damaged, and returns null for data it can't use. `save` sends it, and
 * throws to fail (an `ApiError` gives the reason shown to the person).
 * `draftId` is stable for the draft's life, for a saver that can send an
 * idempotency key.
 *
 * `saveWaitingDrafts()` saves every waiting draft whose kind has a saver,
 * each exactly once. One run happens at a time in a page, and across tabs a
 * Web Lock makes one tab wait for another; each draft is also claimed in
 * storage before it is sent, so a second runner skips it. A saved draft is
 * removed. A failed one is kept with its reason. A 401 or
 * `onboarding_required` stops the run and leaves the rest waiting, because
 * every save after it would fail the same way.
 */

import { useSyncExternalStore } from "react";
import { ApiError } from "../../api/client.js";
import { type Draft, type DraftFailure, readFreshDrafts, updateDrafts } from "./store.js";

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
let saversVersion = 0;
const saverListeners = new Set<() => void>();

function savingsChanged(): void {
  saversVersion += 1;
  for (const listener of [...saverListeners]) listener();
}

/** Register the saver for a kind. Returns a function that removes it. */
export function registerDraftSaver<T>(saver: DraftSaver<T>): () => void {
  if (savers.has(saver.kind)) throw new Error(`A saver for "${saver.kind}" drafts is already registered`);
  const stored = saver as unknown as DraftSaver;
  savers.set(saver.kind, stored);
  savingsChanged();
  return () => {
    if (savers.get(saver.kind) === stored) {
      savers.delete(saver.kind);
      savingsChanged();
    }
  };
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

/** A draft claimed by a tab that hasn't finished after this long is taken to be lost. */
export const CLAIM_LEASE_MS = 120_000;
const LOCK_NAME = "fieldclub.drafts.save";
const TAB = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Math.random());

const UNREADABLE: DraftFailure = {
  code: "draft_unreadable",
  message: "This draft couldn't be read back, so it can't be saved.",
};

function failureFrom(error: unknown): DraftFailure {
  if (error instanceof ApiError) return { code: error.code, message: error.message };
  return { code: "save_failed", message: "Something went wrong while saving it." };
}

function isDue(draft: Draft, now: number): boolean {
  if (!saverFor(draft.kind)) return false;
  if (draft.state === "waiting") return true;
  return draft.state === "saving" && (draft.claim === undefined || now - draft.claim.at > CLAIM_LEASE_MS);
}

/** Mark `id` as being saved by this tab, if it is still due. True when the claim was won. */
function claim(id: string): Draft | null {
  const now = Date.now();
  let claimed: Draft | null = null;
  updateDrafts((drafts) =>
    drafts.map((draft) => {
      if (draft.id !== id || !isDue(draft, now)) return draft;
      const { failure: _failure, ...rest } = draft;
      claimed = { ...rest, state: "saving", claim: { tab: TAB, at: now } };
      return claimed;
    }),
  );
  // Without a lock, another tab could have written in between. Read back to be sure.
  const check = readFreshDrafts().find((draft) => draft.id === id);
  return claimed !== null && check?.claim?.tab === TAB ? claimed : null;
}

function finish(id: string, outcome: "saved" | "release" | DraftFailure): void {
  updateDrafts((drafts) => {
    if (outcome === "saved") return drafts.filter((draft) => draft.id !== id);
    return drafts.map((draft) => {
      if (draft.id !== id || draft.claim?.tab !== TAB) return draft;
      const { claim: _claim, failure: _failure, ...rest } = draft;
      return outcome === "release" ? { ...rest, state: "waiting" } : { ...rest, state: "failed", failure: outcome };
    });
  });
}

async function withLock<T>(task: () => Promise<T>): Promise<T> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  if (locks && typeof locks.request === "function") return locks.request(LOCK_NAME, task);
  return task();
}

async function run(): Promise<SaveReport> {
  return withLock(async () => {
    const report: SaveReport = { saved: 0, failed: 0, stopped: null };
    const tried = new Set<string>();
    for (;;) {
      // Read afresh each time: another tab, or the person, may have changed things.
      const now = Date.now();
      const next = readFreshDrafts().find((draft) => !tried.has(draft.id) && isDue(draft, now));
      if (!next) return report;
      tried.add(next.id);
      const saver = saverFor(next.kind);
      const draft = claim(next.id);
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
      finish(draft.id, "saved");
      report.saved += 1;
    }
  });
}

let running: Promise<SaveReport> | null = null;
const reportListeners = new Set<(report: SaveReport) => void>();

/** Hear the outcome of every run that saved or failed something, once per run. */
export function onDraftsSaved(listener: (report: SaveReport) => void): () => void {
  reportListeners.add(listener);
  return () => {
    reportListeners.delete(listener);
  };
}

/**
 * Save every waiting draft that has a saver. Calls made while a run is going
 * share it, so a component that asks twice causes one run.
 */
export function saveWaitingDrafts(): Promise<SaveReport> {
  if (running) return running;
  const current = run().then((report) => {
    if (report.saved > 0 || report.failed > 0) for (const listener of [...reportListeners]) listener(report);
    return report;
  });
  running = current;
  const clear = (): void => {
    if (running === current) running = null;
  };
  current.then(clear, clear);
  return current;
}

/** For tests: forget every saver. */
export function resetSaversForTests(): void {
  savers.clear();
  savingsChanged();
}
