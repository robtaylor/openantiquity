/**
 * Where to go after sign-in: a path on this site, and nothing else.
 *
 * `safeNext(raw)` returns `raw` when it is a relative path on this site and
 * `/` otherwise, by the rules in docs/ARCHITECTURE.md "Accounts", which the
 * backend's `fieldclub.auth.redirects.safe_next` also follows. The path must
 * be printable ASCII starting with exactly one slash, and still start that
 * way, with no backslash, no `.` or `..` segment and no control or invisible
 * character, however many times it is percent-decoded. A `next` is only ever
 * used through the router's own navigation, never by assigning to `location`.
 *
 * `nextFromLocation(location)` is the `next` for "come back to where I am".
 */

export const DEFAULT_NEXT = "/";
export const MAX_NEXT_LENGTH = 2000;
/** The query parameter a failed provider sign-in comes back with. */
export const SIGNIN_ERROR_PARAM = "signin_error";
/** Paths of the sign-in pages themselves, which are never somewhere to come back to. */
const SIGNIN_PREFIX = "/signin";
const DECODE_ROUNDS = 3;

/** Controls, format characters (zero-width, bidirectional overrides), and line and paragraph separators. */
const FORBIDDEN_DECODED = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u;
const PRINTABLE_ASCII = /^[\x21-\x7e]+$/;

function looksLocal(path: string, raw: boolean): boolean {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\")) return false;
  if (raw ? !PRINTABLE_ASCII.test(path) : FORBIDDEN_DECODED.test(path)) return false;
  // The path part alone, without query or fragment.
  const end = path.search(/[?#]/);
  const pathPart = end === -1 ? path : path.slice(0, end);
  return !pathPart.split("/").some((segment) => segment === "." || segment === "..");
}

export function safeNext(raw: string | null | undefined): string {
  if (!raw || raw.length > MAX_NEXT_LENGTH || !looksLocal(raw, true)) return DEFAULT_NEXT;
  let value = raw;
  for (let round = 0; round < DECODE_ROUNDS; round++) {
    let decoded: string;
    try {
      decoded = decodeURIComponent(value);
    } catch {
      // Malformed encoding: nothing legitimate in the app makes one.
      return DEFAULT_NEXT;
    }
    if (decoded === value) return raw;
    if (!looksLocal(decoded, false)) return DEFAULT_NEXT;
    value = decoded;
  }
  // Still changing after every round: encoded more deeply than anything legitimate.
  return DEFAULT_NEXT;
}

/** A query string without `signin_error`, with its `?`, or empty. */
export function withoutSigninError(search: string): string {
  const params = new URLSearchParams(search);
  params.delete(SIGNIN_ERROR_PARAM);
  const rest = params.toString();
  return rest ? `?${rest}` : "";
}

export interface PathParts {
  pathname: string;
  search: string;
  hash: string;
}

/** The `next` that brings someone back to this view: same panel, same map position. */
export function nextFromLocation({ pathname, search, hash }: PathParts): string {
  if (pathname === SIGNIN_PREFIX || pathname.startsWith(`${SIGNIN_PREFIX}/`)) return DEFAULT_NEXT;
  return safeNext(`${pathname}${withoutSigninError(search)}${hash}`);
}
