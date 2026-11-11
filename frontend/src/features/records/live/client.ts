import { isRecord } from "../../../api/guards.js";
import { type LiveArea, type LiveSource, liveRequestUrl } from "./catalogue.js";
import { type LiveAnswer, LiveResponseError, parseLiveAnswer } from "./parse.js";

/**
 * Asking a live source, from this browser, for one area. The request goes
 * straight to the publisher with no cookies, and its answer stays in this
 * page: nothing from it is sent to Field Club's server (Decision 0007).
 */

/** How long a live source has to answer. */
export const LIVE_TIMEOUT_MS = 12_000;
/** An answer bigger than this, by its stated length, is not read. */
const MAX_ANSWER_BYTES = 5_000_000;

/**
 * Why a live source gave nothing. "refused": the browser got no answer it
 * may read, which is how a source that doesn't allow other sites to ask it
 * looks from here, and also how a dropped connection looks. "failed": it
 * answered, but with an error or with something that can't be read.
 */
export type LiveFailureKind = "refused" | "failed";

export class LiveSourceError extends Error {
  readonly kind: LiveFailureKind;

  constructor(kind: LiveFailureKind, message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "LiveSourceError";
    this.kind = kind;
  }
}

function isAbort(error: unknown): boolean {
  return isRecord(error) && error.name === "AbortError";
}

/** Abort when either signal does. `AbortSignal.any` is not in every browser this supports. */
function either(signal: AbortSignal | undefined, timeout: AbortController): AbortSignal {
  if (!signal) return timeout.signal;
  if (signal.aborted) timeout.abort();
  else signal.addEventListener("abort", () => timeout.abort(), { once: true });
  return timeout.signal;
}

export async function fetchLiveRecords(source: LiveSource, area: LiveArea, signal?: AbortSignal): Promise<LiveAnswer> {
  const url = liveRequestUrl(source, area);
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), LIVE_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      mode: "cors",
      credentials: "omit",
      referrerPolicy: "strict-origin-when-cross-origin",
      headers: { Accept: "application/json, application/geo+json" },
      signal: either(signal, timeout),
    });
  } catch (cause) {
    // Cancelled by the page: the view moved on, and nothing went wrong.
    if (signal?.aborted) throw cause;
    if (isAbort(cause)) throw new LiveSourceError("failed", "It didn't answer in time.", { cause });
    throw new LiveSourceError("refused", "It didn't answer this browser.", { cause });
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) throw new LiveSourceError("failed", `It answered with an error (${response.status}).`);
  const length = Number(response.headers.get("Content-Length") ?? 0);
  if (length > MAX_ANSWER_BYTES) throw new LiveSourceError("failed", "Its answer was too big to show.");
  let body: unknown;
  try {
    body = await response.json();
  } catch (cause) {
    if (signal?.aborted) throw cause;
    throw new LiveSourceError("failed", "Its answer couldn't be read.", { cause });
  }
  try {
    return parseLiveAnswer(body, source);
  } catch (cause) {
    if (cause instanceof LiveResponseError)
      throw new LiveSourceError("failed", "Its answer couldn't be read.", { cause });
    throw cause;
  }
}
