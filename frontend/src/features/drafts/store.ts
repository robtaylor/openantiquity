/**
 * Drafts: work done by someone who isn't signed in, kept in this browser.
 *
 * Marking a finding, answering a second look and scanning a square all work
 * signed out (docs/UI.md "Behaviour"). The result is a draft in
 * `localStorage`, because signing in with a provider reloads the page and
 * nothing in memory survives it. Drafts never reach the server until they are
 * saved through their kind's saver (`savers.ts`).
 *
 * A draft is `{id, kind, data, createdAt, updatedAt, state}`. `kind` names
 * the feature that owns it (`DRAFT_KINDS`), and `data` is that feature's own
 * JSON, which its saver checks when it reads it back. `state` is "waiting",
 * "saving" while a saver has it, or "failed" with a `failure` reason.
 *
 *     putDraft(DRAFT_KINDS.finding, data)      // add; pass an id to replace
 *     useDrafts(DRAFT_KINDS.finding)           // read, in a component
 *     discardDraft(id)
 *
 * The store is `{version: 1, drafts: [...]}` under `fieldclub.drafts`.
 * Reading survives damage: an unreadable store is copied aside to
 * `fieldclub.drafts.unreadable` and reading starts empty, and an entry that
 * can't be read is dropped on its own. Writing survives a full or blocked
 * store: the drafts are kept in memory for the life of the page and
 * `draftsArePersisted()` turns false. A change made in another tab arrives
 * through the browser's `storage` event.
 */

import { useMemo, useSyncExternalStore } from "react";
import { isRecord } from "../../api/guards.js";

export const DRAFTS_STORAGE_KEY = "fieldclub.drafts";
export const DRAFTS_UNREADABLE_KEY = "fieldclub.drafts.unreadable";
export const DRAFTS_VERSION = 1;

/** The kinds the app has. Each feature registers the saver for its own. */
export const DRAFT_KINDS = {
  finding: "finding",
  observation: "observation",
  square: "square",
} as const;

export type DraftState = "waiting" | "saving" | "failed";

export interface DraftFailure {
  /** The API's error code, or a code of the drafts module's own. */
  code: string;
  /** Plain words, for the person. */
  message: string;
}

export interface Draft {
  id: string;
  kind: string;
  data: unknown;
  createdAt: string;
  updatedAt: string;
  state: DraftState;
  failure?: DraftFailure;
  /** Which tab is saving it, and since when, while `state` is "saving". */
  claim?: { tab: string; at: number };
}

interface StoredDrafts {
  version: typeof DRAFTS_VERSION;
  drafts: Draft[];
}

const STATES: readonly DraftState[] = ["waiting", "saving", "failed"];

function newId(): string {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function readDraft(value: unknown): Draft | null {
  if (!isRecord(value)) return null;
  const { id, kind, data, createdAt, updatedAt, state, failure, claim } = value;
  if (typeof id !== "string" || id === "" || typeof kind !== "string" || kind === "") return null;
  if (typeof createdAt !== "string" || typeof updatedAt !== "string" || !("data" in value)) return null;
  const draft: Draft = {
    id,
    kind,
    data,
    createdAt,
    updatedAt,
    // An unknown state from some other build is safest treated as not yet saved.
    state: STATES.includes(state as DraftState) ? (state as DraftState) : "waiting",
  };
  if (draft.state === "failed") {
    draft.failure =
      isRecord(failure) && typeof failure.code === "string" && typeof failure.message === "string"
        ? { code: failure.code, message: failure.message }
        : { code: "unknown", message: "This draft couldn't be saved." };
  }
  if (draft.state === "saving") {
    if (isRecord(claim) && typeof claim.tab === "string" && typeof claim.at === "number") {
      draft.claim = { tab: claim.tab, at: claim.at };
    } else {
      draft.state = "waiting";
    }
  }
  return draft;
}

/** The drafts in a stored value, or null when the value can't be read at all. */
export function parseStoredDrafts(raw: string): Draft[] | null {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  // A newer build's drafts are left for it: this build can't know their shape.
  if (!isRecord(value) || value.version !== DRAFTS_VERSION || !Array.isArray(value.drafts)) return null;
  return value.drafts.map(readDraft).filter((draft): draft is Draft => draft !== null);
}

// --------------------------------------------------------------------------
// Where drafts live: localStorage, or memory when that fails
// --------------------------------------------------------------------------

/** The drafts as this page last knew them. */
let memory: Draft[] = [];
/** True once memory holds changes the browser refused to store. */
let memoryAhead = false;
/** False when there is no usable localStorage, or it refused the last write. */
let persisted = true;
let loaded = false;
const listeners = new Set<() => void>();

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Read the drafts as they are stored now, which another tab may have changed. */
function load(): Draft[] {
  const store = storage();
  if (!store) {
    persisted = false;
    return memory;
  }
  if (memoryAhead) return memory;
  let raw: string | null;
  try {
    raw = store.getItem(DRAFTS_STORAGE_KEY);
  } catch {
    persisted = false;
    return memory;
  }
  if (raw === null) return [];
  const drafts = parseStoredDrafts(raw);
  if (drafts !== null) return drafts;
  try {
    store.setItem(DRAFTS_UNREADABLE_KEY, raw);
    store.removeItem(DRAFTS_STORAGE_KEY);
  } catch {
    // Nothing more can be done with it.
  }
  return [];
}

/** Read the store again, and tell listeners only if something changed. */
function refresh(): void {
  const next = load();
  const changed = !loaded || JSON.stringify(next) !== JSON.stringify(memory);
  loaded = true;
  if (!changed) return;
  memory = next;
  for (const listener of [...listeners]) listener();
}

function write(drafts: Draft[]): void {
  memory = drafts;
  loaded = true;
  const value: StoredDrafts = { version: DRAFTS_VERSION, drafts };
  const store = storage();
  try {
    if (!store) throw new Error("No localStorage");
    store.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(value));
    memoryAhead = false;
    persisted = true;
  } catch {
    memoryAhead = true;
    persisted = false;
  }
  for (const listener of [...listeners]) listener();
}

function onStorage(event: StorageEvent): void {
  // `key` is null when another tab cleared the whole store.
  if (event.key === DRAFTS_STORAGE_KEY || event.key === null) refresh();
}

// --------------------------------------------------------------------------
// Reading and changing drafts
// --------------------------------------------------------------------------

export function listDrafts(): readonly Draft[] {
  if (!loaded) memory = load();
  loaded = true;
  return memory;
}

/** The drafts as stored right now, read afresh rather than from memory. */
export function readFreshDrafts(): readonly Draft[] {
  refresh();
  return memory;
}

/**
 * Change the stored drafts in one step: read them fresh, apply `change`, and
 * store the result. Returns what was stored.
 */
export function updateDrafts(change: (drafts: readonly Draft[]) => Draft[]): readonly Draft[] {
  const next = change(load());
  write(next);
  return next;
}

/** Add a draft of `kind`, or replace the one with `id`. It waits to be saved. */
export function putDraft(kind: string, data: unknown, id?: string): Draft {
  if (!kind) throw new Error("A draft needs a kind");
  let json: string | undefined;
  try {
    json = JSON.stringify(data, (_key, value: unknown) => {
      if (typeof value === "number" && !Number.isFinite(value)) throw new Error("not finite");
      return value;
    });
  } catch {
    json = undefined;
  }
  if (json === undefined) throw new Error("A draft's data must be plain JSON");
  const now = new Date().toISOString();
  let draft: Draft | undefined;
  updateDrafts((drafts) => {
    const existing = id === undefined ? undefined : drafts.find((item) => item.id === id);
    draft = {
      id: existing?.id ?? id ?? newId(),
      kind,
      data: JSON.parse(json) as unknown,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
      state: "waiting",
    };
    const made = draft;
    return existing ? drafts.map((item) => (item.id === made.id ? made : item)) : [...drafts, made];
  });
  if (!draft) throw new Error("putDraft stored nothing");
  return draft;
}

export function discardDraft(id: string): Draft | undefined {
  let removed: Draft | undefined;
  updateDrafts((drafts) => {
    removed = drafts.find((draft) => draft.id === id);
    return drafts.filter((draft) => draft.id !== id);
  });
  return removed;
}

/** Put back a draft that was discarded, for "Undo". */
export function restoreDraft(draft: Draft): void {
  updateDrafts((drafts) => (drafts.some((item) => item.id === draft.id) ? [...drafts] : [...drafts, draft]));
}

/** Let a failed draft be saved again. */
export function retryDraft(id: string): Draft | undefined {
  let retried: Draft | undefined;
  updateDrafts((drafts) =>
    drafts.map((draft) => {
      if (draft.id !== id || draft.state !== "failed") return draft;
      const { failure: _failure, ...rest } = draft;
      retried = { ...rest, state: "waiting" };
      return retried;
    }),
  );
  return retried;
}

/** False when drafts are only in memory and will be lost when the page goes. */
export function draftsArePersisted(): boolean {
  listDrafts();
  return persisted;
}

export function subscribeDrafts(listener: () => void): () => void {
  if (listeners.size === 0) window.addEventListener("storage", onStorage);
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) window.removeEventListener("storage", onStorage);
  };
}

/** Every draft, or those of one kind, kept up to date. */
export function useDrafts(kind?: string): readonly Draft[] {
  const all = useSyncExternalStore(subscribeDrafts, listDrafts, listDrafts);
  return useMemo(() => (kind === undefined ? all : all.filter((draft) => draft.kind === kind)), [all, kind]);
}

/** For tests: forget everything held in memory, as a fresh page load would. */
export function resetDraftsForTests(): void {
  memory = [];
  memoryAhead = false;
  persisted = true;
  loaded = false;
  for (const listener of [...listeners]) listener();
}
