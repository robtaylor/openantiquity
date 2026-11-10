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
 * signed out; a change in another tab is picked up; and whenever the person
 * changes, every query whose answer depends on the viewer is dropped and
 * asked again, so a protected finding's exact position goes with the session.
 */

import { type QueryClient, type QueryKey, queryOptions, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { onUnauthorised } from "../../api/client.js";
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

/** Someone has just signed in, or their details changed: tell the whole app. */
export function signedIn(client: QueryClient, me: Me): void {
  setSession(client, me);
  tellOtherTabs();
}

/** Nobody is signed in any more, after signing out or deleting the account. */
export function signedOut(client: QueryClient): void {
  setSession(client, null);
  tellOtherTabs();
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

/** Mount once, near the root, inside the query client. */
export function useSessionSync(onSignedOutUnexpectedly?: () => void): void {
  const client = useQueryClient();
  const latest = useRef(onSignedOutUnexpectedly);
  latest.current = onSignedOutUnexpectedly;

  // A 401 from any request: the server says nobody is signed in.
  useEffect(
    () =>
      onUnauthorised(() => {
        const before = client.getQueryData<Me | null>(accountKeys.me);
        setSession(client, null);
        if (before) {
          toast("You've been signed out. Sign in again to save.", {
            action: latest.current ? { label: "Sign in", onClick: () => latest.current?.() } : undefined,
          });
        }
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
  // A new handle is the same person, so it is told apart by when the account was made.
  useEffect(() => {
    const identity = (me: Me | null | undefined): string | null | undefined =>
      me === undefined ? undefined : (me?.created_at ?? null);
    let person = identity(client.getQueryData<Me | null>(accountKeys.me));
    return client.getQueryCache().subscribe((event) => {
      if (event.type !== "updated" || !isMeKey(event.query.queryKey)) return;
      const next = identity(event.query.state.data as Me | null | undefined);
      if (next === undefined) return;
      if (person !== undefined && next !== person) {
        void client.resetQueries({ predicate: (query) => !viewerIndependent(query.queryKey) });
      }
      person = next;
    });
  }, [client]);
}
