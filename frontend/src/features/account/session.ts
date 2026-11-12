/**
 * Who is signed in. This module is the only place that knows.
 *
 * `useSession()` answers from `GET /auth/me`, held in TanStack Query under
 * `accountKeys.me`: `status` is "loading", "signed-out", "signed-in", or
 * "unknown" when the server couldn't be asked. `ready` is true when the
 * person is signed in and through the welcome step, so may save.
 *
 * `signedIn(client, me)` and `signedOut(client)` are how a sign-in, sign-out
 * or deletion tells the whole app at once. `useSessionSync()`, mounted once
 * by the account layer, keeps the answer true: a 401 from any request means
 * signed out; a 403 `onboarding_required` from any request means the welcome
 * step is owed, so the session is asked for again and the welcome sheet
 * opens; a change in another tab is picked up; and whenever the person
 * changes, every query whose answer depends on the viewer is dropped and
 * asked again, so a protected finding's exact position goes with the session,
 * and every listener given to `onPersonChanged` is told.
 */

import { type QueryClient, type QueryKey, queryOptions, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { onForbidden, onUnauthorised } from "../../api/client.js";
import { META_QUERY_KEY } from "../../api/useMeta.js";
import { toast } from "../../ui/toastStore.js";
import { accountKeys, fetchMe, type Me } from "./api.js";

export type SessionStatus = "loading" | "signed-out" | "signed-in" | "unknown";

export interface Session {
  status: SessionStatus;
  /** The signed-in person, or null. */
  me: Me | null;
  /** Signed in and through the welcome step: allowed to save. */
  ready: boolean;
  /** Signed in, but the welcome step (age band and terms) is still owed. */
  needsWelcome: boolean;
  /** "member", "trusted", "expert", "moderator" or "admin" when signed in. */
  role: string | null;
  /** Why the session couldn't be asked for, when `status` is "unknown". */
  error: Error | null;
  /** Ask the server again. */
  refetch: () => void;
}

export const meQuery = queryOptions({
  queryKey: accountKeys.me,
  queryFn: ({ signal }) => fetchMe(signal),
  // The session changes only through this module, which updates the cache
  // itself, so the answer is kept until something says otherwise.
  staleTime: Number.POSITIVE_INFINITY,
  retry: false,
});

export function sessionFrom(me: Me | null | undefined, error: Error | null): Omit<Session, "refetch"> {
  if (me === undefined) {
    return {
      status: error ? "unknown" : "loading",
      me: null,
      ready: false,
      needsWelcome: false,
      role: null,
      error,
    };
  }
  if (me === null)
    return { status: "signed-out", me: null, ready: false, needsWelcome: false, role: null, error: null };
  return {
    status: "signed-in",
    me,
    ready: !me.needs_welcome,
    needsWelcome: me.needs_welcome,
    role: me.role,
    error: null,
  };
}

export function useSession(): Session {
  const query = useQuery(meQuery);
  return { ...sessionFrom(query.data, query.error), refetch: () => void query.refetch() };
}

/** The key other tabs watch. Its value is only a nonce: nothing about the person is stored. */
const SESSION_SIGNAL_KEY = "fieldclub.session-changed";

function tellOtherTabs(): void {
  try {
    window.localStorage.setItem(SESSION_SIGNAL_KEY, `${Date.now()}-${Math.random()}`);
  } catch {
    // A blocked store only means other tabs find out when they next ask.
  }
}

/**
 * Put the answer in the cache. A `GET /auth/me` still in flight was asked
 * before this change, so it is cancelled rather than left to overwrite it.
 */
function setSession(client: QueryClient, me: Me | null): void {
  void client.cancelQueries({ queryKey: accountKeys.me, exact: true });
  client.setQueryData(accountKeys.me, me);
}

const signedInHereListeners = new Set<(me: Me) => void>();

/**
 * Hear whenever someone signs in from this tab, by the development sign-in
 * or an emailed link, rather than a change arriving from another tab or a
 * profile being saved. A provider's sign-in returns as a page load instead.
 * Returns a function that stops listening.
 */
export function onSignedInHere(listener: (me: Me) => void): () => void {
  signedInHereListeners.add(listener);
  return () => signedInHereListeners.delete(listener);
}

/** Someone has just signed in, or their details changed: tell the whole app. */
export function signedIn(client: QueryClient, me: Me): void {
  const before = client.getQueryData<Me | null>(accountKeys.me);
  setSession(client, me);
  tellOtherTabs();
  if (!before || accountIdentity(before) !== accountIdentity(me)) {
    for (const listener of [...signedInHereListeners]) listener(me);
  }
}

/** Nobody is signed in any more, after signing out or deleting the account. */
export function signedOut(client: QueryClient): void {
  setSession(client, null);
  tellOtherTabs();
}

/**
 * What tells one account from another, for as long as it exists: the
 * person's own id, which never changes (docs/ARCHITECTURE.md, "Accounts").
 * Prefixed, so it can never be taken for the creation time that drafts were
 * once keyed to (`formerAccountIdentity`).
 */
export function accountIdentity(me: Me): string {
  return `person:${me.id}`;
}

/**
 * What told accounts apart before `Me` carried an id: when the account was
 * made. Drafts kept under it are moved to `accountIdentity` when the person
 * signs in (`adoptFormerDrafts`).
 */
export function formerAccountIdentity(me: Me): string {
  return me.created_at;
}

function isMeKey(key: QueryKey): boolean {
  return key.length === accountKeys.me.length && key[0] === accountKeys.me[0] && key[1] === accountKeys.me[1];
}

/** True for queries whose answer is the same whoever is asking. */
function viewerIndependent(key: QueryKey): boolean {
  const [head, second] = key;
  return (
    head === META_QUERY_KEY[0] ||
    (head === accountKeys.me[0] && (second === accountKeys.me[1] || second === accountKeys.handleSuggestion[1]))
  );
}

const personListeners = new Set<() => void>();

/**
 * Hear whenever the person changes: a sign-in, a sign-out, or another
 * account. A feature that keeps something one viewer was allowed to see
 * outside the query cache, such as a finding's exact place, forgets it here,
 * at the same moment the viewer's queries are dropped. Returns a function
 * that stops listening.
 */
export function onPersonChanged(listener: () => void): () => void {
  personListeners.add(listener);
  return () => personListeners.delete(listener);
}

export interface SessionSyncHandlers {
  /** Someone who was signed in has been signed out by the server, such as when the session ran out. */
  onSignedOutUnexpectedly?: () => void;
  /** A save was refused because the welcome step is still owed. */
  onWelcomeNeeded?: () => void;
}

/** Mount once, near the root, inside the query client. */
export function useSessionSync(handlers: SessionSyncHandlers = {}): void {
  const client = useQueryClient();
  const latest = useRef(handlers);
  latest.current = handlers;

  // A 401 from any request: the server says nobody is signed in.
  useEffect(
    () =>
      onUnauthorised(() => {
        const before = client.getQueryData<Me | null>(accountKeys.me);
        setSession(client, null);
        if (before) {
          toast("You've been signed out. Sign in again to save.", {
            action: latest.current.onSignedOutUnexpectedly
              ? { label: "Sign in", onClick: () => latest.current.onSignedOutUnexpectedly?.() }
              : undefined,
          });
        }
      }),
    [client],
  );

  // A 403 onboarding_required from any request: the welcome step is owed, whatever the cache says.
  useEffect(
    () =>
      onForbidden((error) => {
        if (error.code !== "onboarding_required") return;
        void client.invalidateQueries({ queryKey: accountKeys.me, exact: true });
        latest.current.onWelcomeNeeded?.();
      }),
    [client],
  );

  // Another tab signed in or out.
  useEffect(() => {
    function onStorage(event: StorageEvent): void {
      if (event.key === SESSION_SIGNAL_KEY) void client.invalidateQueries({ queryKey: accountKeys.me });
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [client]);

  // Whenever the person changes, what the viewer may see changes with them.
  // A new handle is the same person, so it is told apart by the account's id.
  useEffect(() => {
    const identity = (me: Me | null | undefined): string | null | undefined =>
      me === undefined ? undefined : me === null ? null : accountIdentity(me);
    let person = identity(client.getQueryData<Me | null>(accountKeys.me));
    return client.getQueryCache().subscribe((event) => {
      if (event.type !== "updated" || !isMeKey(event.query.queryKey)) return;
      const next = identity(event.query.state.data as Me | null | undefined);
      if (next === undefined) return;
      if (person !== undefined && next !== person) {
        for (const listener of [...personListeners]) listener();
        void client.resetQueries({ predicate: (query) => !viewerIndependent(query.queryKey) });
      }
      person = next;
    });
  }, [client]);
}
