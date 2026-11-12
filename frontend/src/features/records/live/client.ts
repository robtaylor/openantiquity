import { isRecord } from "../../../api/guards.js";
import { type LiveArea, type LiveSource, liveRequestUrl } from "./catalogue.js";
import { type LiveAnswer, LiveResponseError, parseLiveAnswer } from "./parse.js";

/**
 * Asking a live source, from this browser, for one area. The request goes
 * straight to the publisher with no cookies, and its answer stays in this
 * page: nothing from it is sent to OpenAntiquity's server (Decision 0007).
 */

/** How long a live source has to send its whole answer, from asking to the last byte. */
export const LIVE_TIMEOUT_MS = 12_000;
/** An answer bigger than this is not read past this many bytes, whatever length it states. */
export const MAX_ANSWER_BYTES = 5_000_000;

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

class AnswerTooBig extends Error {
  constructor() {
    super("The answer was too big to read");
    this.name = "AnswerTooBig";
  }
}

/**
 * The body as text, read as it arrives and given up once it passes `limit`
 * bytes, so a source that sends without stating a length can't fill the
 * page's memory. Reading stops when `signal` aborts, even where the body
 * isn't tied to the request's own signal.
 */
async function readCapped(response: Response, limit: number, signal: AbortSignal): Promise<string> {
  const reader = response.body?.getReader();
  if (!reader) {
    const text = await response.text();
    if (new TextEncoder().encode(text).length > limit) throw new AnswerTooBig();
    return text;
  }
  const stop = () => void reader.cancel().catch(() => undefined);
  signal.addEventListener("abort", stop, { once: true });
  const decoder = new TextDecoder();
  let size = 0;
  let text = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (signal.aborted) throw new DOMException("The answer took too long", "AbortError");
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel().catch(() => undefined);
        throw new AnswerTooBig();
      }
      text += decoder.decode(value, { stream: true });
    }
  } finally {
    signal.removeEventListener("abort", stop);
  }
  return text + decoder.decode();
}

export async function fetchLiveRecords(source: LiveSource, area: LiveArea, signal?: AbortSignal): Promise<LiveAnswer> {
  const url = liveRequestUrl(source, area);
  // One deadline for the whole answer: a source that sends its headers and then dawdles is stopped too.
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), LIVE_TIMEOUT_MS);
  const late = (cause: unknown) => new LiveSourceError("failed", "It didn't answer in time.", { cause });
  let body: unknown;
  try {
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
      if (isAbort(cause)) throw late(cause);
      throw new LiveSourceError("refused", "It didn't answer this browser.", { cause });
    }
    if (!response.ok) throw new LiveSourceError("failed", `It answered with an error (${response.status}).`);
    const length = Number(response.headers.get("Content-Length") ?? 0);
    if (length > MAX_ANSWER_BYTES) throw new LiveSourceError("failed", "Its answer was too big to show.");
    let text: string;
    try {
      text = await readCapped(response, MAX_ANSWER_BYTES, timeout.signal);
    } catch (cause) {
      if (signal?.aborted) throw cause;
      if (cause instanceof AnswerTooBig)
        throw new LiveSourceError("failed", "Its answer was too big to show.", { cause });
      if (timeout.signal.aborted) throw late(cause);
      throw new LiveSourceError("failed", "Its answer couldn't be read.", { cause });
    }
    try {
      body = JSON.parse(text);
    } catch (cause) {
      throw new LiveSourceError("failed", "Its answer couldn't be read.", { cause });
    }
  } finally {
    clearTimeout(timer);
  }
  try {
    return parseLiveAnswer(body, source);
  } catch (cause) {
    if (cause instanceof LiveResponseError)
      throw new LiveSourceError("failed", "Its answer couldn't be read.", { cause });
    throw cause;
  }
}
