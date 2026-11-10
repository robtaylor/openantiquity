/**
 * Drafts: work done by someone who isn't signed in, kept in this browser.
 *
 * Marking a finding, answering a second look and scanning a square all work
 * signed out (docs/UI.md "Behaviour"). The result is a draft in
 * `localStorage`, because signing in with a provider reloads the page and
 * nothing in memory survives it. Drafts never reach the server until they are
 * saved through their kind's saver (`savers.ts`).
 *
 * A draft is `{id, kind, data, owner, createdAt, updatedAt, state}`. `kind`
 * names the feature that owns it (`DRAFT_KINDS`), and `data` is that
 * feature's own JSON, which its saver checks when it reads it back. `state`
 * is "waiting", "saving" while a saver has it, or "failed" with a `failure`
 * reason. A feature normally goes through `defineDraftKind` in `savers.ts`,
 * which types `data`; underneath, it is:
 *
 *     putDraft(DRAFT_KINDS.finding, data)      // add; pass an id to replace
 *     useDrafts(DRAFT_KINDS.finding)           // read, in a component
 *     discardDraft(id)
 *
 * Whose a draft is. A browser can be shared, so each draft records who made
 * it: `{account}` for someone signed in (`setDraftsViewer`), or
 * `{signedOut: epoch}` for someone who wasn't. The epoch is a random value
 * kept with the drafts. When someone signs in, the signed-out drafts of the
 * current epoch become theirs (`adoptSignedOutDrafts`) and a new epoch
 * starts, so signed-out work left from before is never taken to be the next
 * person's. Only a person's own drafts are saved without asking.
 *
 * The store is `{version: 2, epoch, drafts: [...]}` under `fieldclub.drafts`.
 * Reading survives damage: an unreadable store is copied aside under
 * `fieldclub.drafts.unreadable.<time>` (never over an earlier copy) and
 * reading starts empty, and an entry that can't be read is dropped on its
 * own. An older version is migrated. A newer version belongs to a newer
 * build, so it is left alone, and this page keeps its own drafts in memory.
 * Writing survives a full or blocked store: whatever the browser refuses is
 * kept in memory for the life of the page, everything else (removals above
 * all) is still stored, and `draftsArePersisted()` turns false. A change made
 * in another tab arrives through the browser's `storage` event.
 */

import { useMemo, useSyncExternalStore } from "react";
import { isRecord } from "../../api/guards.js";

export const DRAFTS_STORAGE_KEY = "fieldclub.drafts";
/** Unreadable stores are copied aside under this prefix, one key per copy. */
export const DRAFTS_UNREADABLE_KEY = "fieldclub.drafts.unreadable";
export const DRAFTS_VERSION = 2;
/** At most this many unreadable copies are kept. A later one is dropped, never an earlier one. */
export const MAX_UNREADABLE_COPIES = 3;
/** The longest a draft's data may be, as JSON. A feature's draft is a few kilobytes. */
export const MAX_DRAFT_CHARS = 100_000;
/** A draft claimed by a tab that hasn't finished after this long is taken to be lost. */
export const CLAIM_LEASE_MS = 120_000;

/** The kinds the app has. Each feature registers the saver for its own. */
export const DRAFT_KINDS = {
  finding: "finding",
  observation: "observation",
  square: "square",
} as const;

export type DraftState = "waiting" | "saving" | "failed";

/** Who made a draft: an account, or someone signed out during `epoch`. */
export type DraftOwner = { account: string } | { signedOut: string };

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
  /** Null for a draft stored before owners were recorded: nobody can say whose it is. */
  owner: DraftOwner | null;
  createdAt: string;
  updatedAt: string;
  state: DraftState;
  failure?: DraftFailure;
  /** Which tab is saving it, and since when, while `state` is "saving". */
  claim?: { tab: string; at: number };
}

/** A draft's data that isn't plain JSON. */
export class DraftDataError extends Error {
  constructor(message = "A draft's data must be plain JSON") {
    super(message);
    this.name = "DraftDataError";
  }
}

/** A draft too big to keep in the browser. The feature should say so, and keep it on screen. */
export class DraftTooLargeError extends Error {
  readonly size: number;
  constructor(size: number) {
    super(`This draft is too big to keep in the browser (${size} characters, at most ${MAX_DRAFT_CHARS}).`);
    this.name = "DraftTooLargeError";
    this.size = size;
  }
}

/** A draft that is being saved at this moment, so can't be changed until that finishes. */
export class DraftBusyError extends Error {
  constructor() {
    super("This draft is being saved. Try again in a moment.");
    this.name = "DraftBusyError";
  }
}

interface StoredDrafts {
  version: typeof DRAFTS_VERSION;
  epoch: string;
  drafts: Draft[];
}

const STATES: readonly DraftState[] = ["waiting", "saving", "failed"];

function newId(): string {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function readOwner(value: unknown): DraftOwner | null {
  if (!isRecord(value)) return null;
  if (typeof value.account === "string" && value.account !== "") return { account: value.account };
  if (typeof value.signedOut === "string" && value.signedOut !== "") return { signedOut: value.signedOut };
  return null;
}

function readDraft(value: unknown): Draft | null {
  if (!isRecord(value)) return null;
  const { id, kind, data, createdAt, updatedAt, state, failure, claim, owner } = value;
  if (typeof id !== "string" || id === "" || typeof kind !== "string" || kind === "") return null;
  if (typeof createdAt !== "string" || typeof updatedAt !== "string" || !("data" in value)) return null;
  const draft: Draft = {
    id,
    kind,
    data,
    owner: readOwner(owner),
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

/**
 * How to bring a store of version `n` up to `n + 1`. Each takes the parsed
 * value and returns the next version's. Add one whenever `DRAFTS_VERSION`
 * goes up.
 */
const MIGRATIONS: Readonly<Record<number, (value: Record<string, unknown>) => Record<string, unknown>>> = {
  // Version 1 had no owners and no epoch. Nobody can say whose its drafts are.
  1: (value) => ({
    ...value,
    version: 2,
    epoch: newId(),
    drafts: Array.isArray(value.drafts)
      ? value.drafts.map((draft: unknown) => (isRecord(draft) ? { ...draft, owner: null } : draft))
      : value.drafts,
  }),
};

export type ParsedDrafts =
  | { status: "ok"; epoch: string; drafts: Draft[] }
  /** Written by a newer build, which this one leaves alone. */
  | { status: "newer" }
  | { status: "unreadable" };

/** Read a stored value, migrating an older version. */
export function parseStoredDrafts(raw: string): ParsedDrafts {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return { status: "unreadable" };
  }
  if (!isRecord(value) || typeof value.version !== "number" || !Number.isInteger(value.version)) {
    return { status: "unreadable" };
  }
  if (value.version > DRAFTS_VERSION) return { status: "newer" };
  let current: Record<string, unknown> = value;
  while (typeof current.version === "number" && current.version < DRAFTS_VERSION) {
    const migrate = MIGRATIONS[current.version];
    if (!migrate) return { status: "unreadable" };
    current = migrate(current);
  }
  const { epoch, drafts } = current;
  if (current.version !== DRAFTS_VERSION || !Array.isArray(drafts)) return { status: "unreadable" };
  return {
    status: "ok",
    epoch: typeof epoch === "string" && epoch !== "" ? epoch : newId(),
    drafts: drafts.map(readDraft).filter((draft): draft is Draft => draft !== null),
  };
}

// --------------------------------------------------------------------------
// Where drafts live: localStorage, and memory for what it won't take
// --------------------------------------------------------------------------

/** The drafts as this page last knew them. */
let memory: Draft[] = [];
/** The signed-out epoch, as this page last knew it. */
let epoch = newId();
/**
 * Drafts whose latest version the browser refused to store, by id. They live
 * only in this page, and are laid over what storage holds whenever it is read.
 */
const unstored = new Map<string, Draft>();
/** Each stored draft's JSON as last written or read, to tell what a write changes. */
let lastStored = new Map<string, string>();
/** True when there is no usable localStorage. */
let blocked = false;
/** True while storage holds a newer build's drafts, which this page leaves alone. */
let foreign = false;
let loaded = false;
/** Who is signed in, for stamping new drafts. Null when nobody is, or it isn't known yet. */
let viewer: string | null = null;
const listeners = new Set<() => void>();

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function notify(): void {
  for (const listener of [...listeners]) listener();
}

function unreadableKeys(store: Storage): string[] {
  const keys: string[] = [];
  for (let index = 0; index < store.length; index++) {
    const key = store.key(index);
    if (key !== null && (key === DRAFTS_UNREADABLE_KEY || key.startsWith(`${DRAFTS_UNREADABLE_KEY}.`))) keys.push(key);
  }
  return keys;
}

/** Keep a copy of a store that can't be read, without replacing an earlier copy. */
function setAside(store: Storage, raw: string): void {
  try {
    if (unreadableKeys(store).length < MAX_UNREADABLE_COPIES) {
      store.setItem(`${DRAFTS_UNREADABLE_KEY}.${new Date().toISOString()}`, raw);
    }
    store.removeItem(DRAFTS_STORAGE_KEY);
  } catch {
    // Nothing more can be done with it.
  }
}

function withUnstored(drafts: Draft[]): Draft[] {
  if (unstored.size === 0) return drafts;
  const ids = new Set(drafts.map((draft) => draft.id));
  const merged = drafts.map((draft) => unstored.get(draft.id) ?? draft);
  for (const draft of unstored.values()) if (!ids.has(draft.id)) merged.push(draft);
  return merged;
}

/** Read the drafts as they are stored now, which another tab may have changed. */
function load(): Draft[] {
  const store = storage();
  let raw: string | null;
  try {
    if (!store) throw new Error("No localStorage");
    raw = store.getItem(DRAFTS_STORAGE_KEY);
  } catch {
    blocked = true;
    return memory;
  }
  blocked = false;
  foreign = false;
  if (raw === null) {
    lastStored = new Map();
    return withUnstored([]);
  }
  const parsed = parseStoredDrafts(raw);
  if (parsed.status === "newer") {
    foreign = true;
    return memory;
  }
  if (parsed.status === "unreadable") {
    setAside(store, raw);
    lastStored = new Map();
    return withUnstored([]);
  }
  epoch = parsed.epoch;
  lastStored = new Map(parsed.drafts.map((draft) => [draft.id, JSON.stringify(draft)]));
  return withUnstored(parsed.drafts);
}

/** Read the store again, and tell listeners only if something changed. */
function refresh(): void {
  const next = load();
  const changed = !loaded || JSON.stringify(next) !== JSON.stringify(memory);
  loaded = true;
  if (!changed) return;
  memory = next;
  notify();
}

function tryStore(store: Storage, drafts: Draft[]): boolean {
  const value: StoredDrafts = { version: DRAFTS_VERSION, epoch, drafts };
  try {
    store.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

/**
 * Store `drafts`. When the browser refuses, store as much as it will take:
 * the drafts this write changed are held back one at a time, largest first,
 * each keeping its earlier stored version if it had one. A removal makes the
 * store smaller, so it is always stored if anything can be.
 */
function write(drafts: Draft[]): void {
  memory = drafts;
  loaded = true;
  const store = storage();
  if (!store) blocked = true;
  if (blocked || foreign || !store) {
    notify();
    return;
  }
  const json = new Map(drafts.map((draft) => [draft.id, JSON.stringify(draft)]));
  const changed = drafts
    .filter((draft) => json.get(draft.id) !== lastStored.get(draft.id))
    .sort((a, b) => (json.get(b.id)?.length ?? 0) - (json.get(a.id)?.length ?? 0));
  const heldBack = new Set<string>();
  const storable = (): Draft[] =>
    drafts.flatMap((draft): Draft[] => {
      if (!heldBack.has(draft.id)) return [draft];
      const earlier = lastStored.get(draft.id);
      return earlier === undefined ? [] : [JSON.parse(earlier) as Draft];
    });
  let stored = tryStore(store, drafts);
  for (const draft of changed) {
    if (stored) break;
    heldBack.add(draft.id);
    stored = tryStore(store, storable());
  }
  unstored.clear();
  if (stored) {
    const kept = storable();
    lastStored = new Map(kept.map((draft) => [draft.id, JSON.stringify(draft)]));
    for (const draft of drafts) if (heldBack.has(draft.id)) unstored.set(draft.id, draft);
  } else {
    // Not even the smallest version would go in: everything is in memory now.
    for (const draft of drafts) unstored.set(draft.id, draft);
  }
  notify();
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

/** True while `draft` is claimed by a tab whose claim hasn't run out. */
export function isBeingSaved(draft: Draft, now = Date.now()): boolean {
  return draft.state === "saving" && draft.claim !== undefined && now - draft.claim.at <= CLAIM_LEASE_MS;
}

/**
 * True when the browser wouldn't store `id`'s latest version but still holds
 * an earlier one, which other tabs see. A claim on such a draft wouldn't
 * reach them, so it mustn't be sent.
 */
export function hasStaleStoredCopy(id: string): boolean {
  return unstored.has(id) && lastStored.has(id);
}

/**
 * Add a draft of `kind`, or replace the one with `id`. It waits to be saved.
 * Throws `DraftDataError` for data that isn't plain JSON, `DraftTooLargeError`
 * for data over `MAX_DRAFT_CHARS`, and `DraftBusyError` while the draft is
 * being saved. A replaced draft keeps its owner.
 */
export function putDraft(kind: string, data: unknown, id?: string): Draft {
  if (!kind) throw new DraftDataError("A draft needs a kind");
  let json: string | undefined;
  try {
    json = JSON.stringify(data, (_key, value: unknown) => {
      if (typeof value === "number" && !Number.isFinite(value)) throw new Error("not finite");
      return value;
    });
  } catch {
    json = undefined;
  }
  if (json === undefined) throw new DraftDataError();
  if (json.length > MAX_DRAFT_CHARS) throw new DraftTooLargeError(json.length);
  const parsed = JSON.parse(json) as unknown;
  const now = new Date().toISOString();
  let draft: Draft | undefined;
  updateDrafts((drafts) => {
    const existing = id === undefined ? undefined : drafts.find((item) => item.id === id);
    if (existing && isBeingSaved(existing)) throw new DraftBusyError();
    draft = {
      id: existing?.id ?? id ?? newId(),
      kind,
      data: parsed,
      owner: existing ? existing.owner : viewer === null ? { signedOut: epoch } : { account: viewer },
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

/** Discard every draft in this browser, and any unreadable copies set aside. */
export function discardAllDrafts(): void {
  updateDrafts(() => []);
  const store = storage();
  if (!store) return;
  try {
    for (const key of unreadableKeys(store)) store.removeItem(key);
  } catch {
    // A blocked store holds nothing to clear.
  }
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

// --------------------------------------------------------------------------
// Whose drafts are whose
// --------------------------------------------------------------------------

/** Tell the store who is signed in, so new drafts are stamped with them. Null for nobody, or not known. */
export function setDraftsViewer(account: string | null): void {
  viewer = account;
}

/** True when `account` made `draft`. */
export function isOwnDraft(draft: Draft, account: string): boolean {
  return draft.owner !== null && "account" in draft.owner && draft.owner.account === account;
}

/**
 * `account` has just signed in: the drafts made signed out in this epoch are
 * theirs, and a new epoch starts. Returns how many were taken over. Nothing
 * is written when there is nothing to take over, as when another tab got
 * there first.
 */
export function adoptSignedOutDrafts(account: string): number {
  const isCurrent = (draft: Draft): boolean =>
    draft.owner !== null && "signedOut" in draft.owner && draft.owner.signedOut === epoch;
  if (!readFreshDrafts().some(isCurrent)) return 0;
  let adopted = 0;
  updateDrafts((drafts) => {
    const taken = drafts.map((draft) => {
      if (!isCurrent(draft)) return draft;
      adopted += 1;
      return { ...draft, owner: { account } };
    });
    epoch = newId();
    return taken;
  });
  return adopted;
}

/** The person says these drafts are theirs: "Save as mine". */
export function claimDraftsAsOwn(ids: readonly string[], account: string): void {
  const wanted = new Set(ids);
  updateDrafts((drafts) => drafts.map((draft) => (wanted.has(draft.id) ? { ...draft, owner: { account } } : draft)));
}

/** False when some drafts are only in memory and will be lost when the page goes. */
export function draftsArePersisted(): boolean {
  listDrafts();
  return !blocked && !foreign && unstored.size === 0;
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
  epoch = newId();
  unstored.clear();
  lastStored = new Map();
  blocked = false;
  foreign = false;
  loaded = false;
  viewer = null;
  notify();
}
