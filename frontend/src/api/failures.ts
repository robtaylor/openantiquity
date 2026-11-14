/**
 * The last few things that went wrong in this page, for a problem report.
 *
 * They are kept in memory only, for the life of the page, and nothing here
 * sends them anywhere: the report form shows them, and they leave only if
 * the person sends the report. What is kept is chosen so that it can't say
 * where anyone was looking or who they are. A failed request keeps its
 * method, its path as a pattern with every id and number written as a
 * parameter, its status, its error code and the request id the server gave
 * it. It never keeps a body, a query string, a header or a message. An
 * uncaught error keeps its message, with every word that holds a figure
 * taken out and cut short. Neither keeps a stack trace.
 */

import type { ApiError } from "./client.js";
import { API_PATHS } from "./paths.js";

/** The most kept at once. The oldest goes first. */
export const MAX_KEPT = 10;
/** The longest an error's message is kept. */
export const MESSAGE_MAX = 200;

export interface RequestFailure {
  kind: "request";
  /** When, as an ISO 8601 time in UTC. */
  at: string;
  method: string;
  /** The API path below `/api/v1` as a pattern, such as "/findings/{public_id}". */
  path: string;
  /** The HTTP status, or 0 when no answer came. */
  status: number;
  code: string;
  /** The server's `X-Request-ID` for it, or null when no answer came. */
  requestId: string | null;
}

export interface ErrorFailure {
  kind: "error";
  at: string;
  message: string;
}

export type KeptFailure = RequestFailure | ErrorFailure;

const kept: KeptFailure[] = [];

function keep(failure: KeptFailure): void {
  kept.push(failure);
  while (kept.length > MAX_KEPT) kept.shift();
}

/** What has been kept, oldest first. A copy. */
export function keptFailures(): readonly KeptFailure[] {
  return kept.map((failure) => ({ ...failure }));
}

/** Forget everything kept. For tests. */
export function forgetFailures(): void {
  kept.length = 0;
}

interface Template {
  segments: readonly string[];
  /** How many of its segments are words rather than parameters, so the most specific wins. */
  words: number;
}

const PARAMETER = /^\{[^}]+\}$/;

const TEMPLATES: readonly Template[] = API_PATHS.map((path) => {
  const segments = path.split("/").slice(1);
  return { segments, words: segments.filter((segment) => !PARAMETER.test(segment)).length };
});

/** Every word the API's paths are made of, such as "findings" and "observation". */
const WORDS = new Set(TEMPLATES.flatMap((template) => template.segments.filter((part) => !PARAMETER.test(part))));

/**
 * An API path as a pattern: the backend's own template when one fits, such
 * as "/findings/{public_id}/comments", and otherwise each segment that isn't
 * one of the API's words written as "{…}". The query and anything after "#"
 * are dropped.
 */
export function pathPattern(path: string): string {
  const bare = path.split(/[?#]/, 1)[0] ?? "";
  const segments = bare.split("/").slice(1);
  let best: Template | undefined;
  for (const template of TEMPLATES) {
    if (template.segments.length !== segments.length) continue;
    const fits = template.segments.every((part, index) => PARAMETER.test(part) || part === segments[index]);
    if (fits && (best === undefined || template.words > best.words)) best = template;
  }
  const parts = best?.segments ?? segments.map((segment) => (WORDS.has(segment) ? segment : "{…}"));
  return `/${parts.join("/")}`;
}

/** Keep a request that failed. Called by the API client for every failure but one stopped on purpose. */
export function keepRequestFailure(method: string, path: string, error: ApiError): void {
  keep({
    kind: "request",
    at: new Date().toISOString(),
    method,
    path: pathPattern(path),
    status: error.status,
    code: error.code,
    requestId: error.requestId,
  });
}

/**
 * A message with every word that holds a figure written as "#", cut to
 * `MESSAGE_MAX`. An address, a tile's numbers, coordinates, a grid reference
 * and an id all hold figures, and any of them could say where someone was.
 */
function scrubbed(message: string): string {
  return message.replace(/\S*\d\S*/g, "#").slice(0, MESSAGE_MAX);
}

/** Keep an error nothing caught, by its message alone. */
export function keepError(message: string): void {
  keep({ kind: "error", at: new Date().toISOString(), message: scrubbed(message) });
}

function messageOf(reason: unknown): string {
  if (reason instanceof Error) return reason.message || reason.name;
  if (typeof reason === "string") return reason;
  return "An unknown error";
}

/**
 * Keep every uncaught error and unhandled rejection in `target`. A rejection
 * with an `ApiError` is a failed request, which the client has kept already.
 * Returns a function that stops watching.
 */
export function watchUncaughtErrors(target: Window): () => void {
  const onError = (event: ErrorEvent): void => keepError(event.message || messageOf(event.error));
  const onRejection = (event: PromiseRejectionEvent): void => {
    // By name, because the client imports this module and not the other way round.
    if (event.reason instanceof Error && event.reason.name === "ApiError") return;
    keepError(messageOf(event.reason));
  };
  target.addEventListener("error", onError);
  target.addEventListener("unhandledrejection", onRejection);
  return () => {
    target.removeEventListener("error", onError);
    target.removeEventListener("unhandledrejection", onRejection);
  };
}
