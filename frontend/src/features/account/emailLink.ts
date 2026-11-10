/**
 * The emailed sign-in link's token, from the moment the page loads to the
 * moment it is exchanged.
 *
 * The link is `/signin/email?next=…#token=…`. The token is in the fragment so
 * that no server log or `Referer` ever holds it. `captureEmailLinkToken()`
 * runs before the app renders: it takes the token out of the address bar at
 * once and keeps it in memory, and nowhere else. It is never put in storage,
 * a log line or any request but `POST /auth/email/verify`.
 *
 * `exchangeEmailLink(token, confirm)` makes that request at most once for each
 * token and answer, however many times React mounts the page, because a link
 * works only once.
 */

import { type Me, verifyEmailLink } from "./api.js";

export const EMAIL_LINK_PATH = "/signin/email";
const TOKEN_KEY = "token";

let captured: string | null = null;
const exchanges = new Map<string, Promise<Me>>();

/** True for the paths the router shows the link page at: it ignores case and a trailing slash. */
export function isEmailLinkPath(pathname: string): boolean {
  return pathname.toLowerCase().replace(/\/+$/, "") === EMAIL_LINK_PATH;
}

/**
 * If the fragment holds a token, take the fragment out of the address,
 * whatever the path, so the token never lingers there. Keep the token only
 * on the link page. Safe to call more than once.
 */
export function captureEmailLinkToken(win: Window = window): void {
  const { pathname, search, hash } = win.location;
  if (hash.length < 2) return;
  const fragment = new URLSearchParams(hash.slice(1));
  const onLinkPage = isEmailLinkPath(pathname);
  if (!onLinkPage && !fragment.has(TOKEN_KEY)) return;
  // On the link page whatever was in the fragment goes, token or not.
  win.history.replaceState(win.history.state, "", `${pathname}${search}`);
  const token = fragment.get(TOKEN_KEY);
  if (onLinkPage && token) captured = token;
}

/** The captured token, or null when the page was opened without one. */
export function emailLinkToken(): string | null {
  return captured;
}

/** Forget the token: it was spent, refused, or the person said it wasn't theirs. */
export function forgetEmailLinkToken(): void {
  if (captured !== null) {
    exchanges.delete(`${captured}:false`);
    exchanges.delete(`${captured}:true`);
  }
  captured = null;
}

/**
 * Exchange `token` for a session. Calls with the same token and the same
 * `confirm` share one request. A failed attempt can be made again, because
 * a refused link was not spent.
 */
export function exchangeEmailLink(token: string, confirm: boolean): Promise<Me> {
  const key = `${token}:${confirm}`;
  const existing = exchanges.get(key);
  if (existing) return existing;
  const attempt = verifyEmailLink(token, confirm);
  exchanges.set(key, attempt);
  attempt.catch(() => {
    if (exchanges.get(key) === attempt) exchanges.delete(key);
  });
  return attempt;
}

/** For tests: start again as if the page had just loaded. */
export function resetEmailLinkForTests(): void {
  captured = null;
  exchanges.clear();
}
