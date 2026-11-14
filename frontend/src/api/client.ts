/**
 * The one place the frontend talks to the backend. Every request sends the
 * session cookie. Every mutation carries `X-OpenAntiquity-Client: web`, which the API
 * requires and a cross-site form cannot send. Failures become an `ApiError`
 * built from the `{"error": {"code", "message", "details"}}` envelope. A 401
 * from any path is announced to `onUnauthorised` listeners, which is how the
 * session learns that nobody is signed in any more, and a 403 to `onForbidden`
 * listeners, which is how it learns the welcome step is still owed.
 */

import { keepRequestFailure } from "./failures.js";
import { isRecord } from "./guards.js";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  /** HTTP status, or 0 when no response arrived. */
  readonly status: number;
  /** The stable code from the error envelope, such as "not_found". */
  readonly code: string;
  /** The envelope's `details`, such as the masked address of `confirmation_required`. Empty when it had none. */
  readonly details: Readonly<Record<string, unknown>>;
  /**
   * The fields a refusal names, when `details` is a list of them, as
   * `validation_error` and `position_in_text` send it: `field` is the
   * request's path to it, such as `body.title`. Empty otherwise.
   */
  readonly fields: readonly FieldProblem[];
  /** The id the server gave the request, from the envelope or `X-Request-ID`, or null when no answer came. */
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    options?: ErrorOptions & {
      details?: Record<string, unknown>;
      fields?: readonly FieldProblem[];
      requestId?: string | null;
    },
  ) {
    super(message, options);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = options?.details ?? {};
    this.fields = options?.fields ?? [];
    this.requestId = options?.requestId ?? null;
  }
}

/** One field a refusal names, and what is wrong with it, in the server's words. */
export interface FieldProblem {
  field: string;
  message: string;
}

function fieldProblems(details: unknown): FieldProblem[] | undefined {
  if (!Array.isArray(details)) return undefined;
  return details.filter(
    (item): item is FieldProblem =>
      isRecord(item) && typeof item.field === "string" && typeof item.message === "string",
  );
}

type UnauthorisedListener = (path: string) => void;
const unauthorisedListeners = new Set<UnauthorisedListener>();

/**
 * Call `listener` with the path of every request the server answers with 401.
 * Returns a function that stops listening.
 */
export function onUnauthorised(listener: UnauthorisedListener): () => void {
  unauthorisedListeners.add(listener);
  return () => {
    unauthorisedListeners.delete(listener);
  };
}

type ForbiddenListener = (error: ApiError, path: string) => void;
const forbiddenListeners = new Set<ForbiddenListener>();

/**
 * Call `listener` with the error and path of every request the server
 * answers with 403, such as `onboarding_required`. Returns a function that
 * stops listening.
 */
export function onForbidden(listener: ForbiddenListener): () => void {
  forbiddenListeners.add(listener);
  return () => {
    forbiddenListeners.delete(listener);
  };
}

export type QueryValue = string | number | boolean | null | undefined;
/** A list is sent as the same parameter once per item, such as `tier=seen&tier=probable`. */
export type QueryParam = QueryValue | readonly QueryValue[];

export interface ApiRequest {
  method?: "GET" | "HEAD" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, QueryParam>;
  /** Sent as JSON. */
  body?: unknown;
  /** Sent as it is, with its own type, in place of `body`: an image for `POST /media`. */
  file?: Blob;
  signal?: AbortSignal;
  /**
   * Statuses the caller expects and handles, such as 401 when asking who is
   * signed in. They are thrown as ever, but not kept for a problem report.
   */
  expected?: readonly number[];
}

/** What an endpoint the interface was built ahead of answers when the server lacks it (`isEndpointMissing`). */
const ENDPOINT_MISSING_STATUSES: readonly number[] = [404, 405, 501];

const SAFE_METHODS = new Set(["GET", "HEAD"]);
/** Statuses that come from a proxy in front of a backend that is down. */
const GATEWAY_STATUSES = new Set([502, 503, 504]);

export function apiUrl(path: string, query: Record<string, QueryParam> = {}): string {
  if (!path.startsWith("/")) throw new ApiError(0, "bad_request", `API path "${path}" must start with "/"`);
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    const items: readonly QueryValue[] = Array.isArray(value) ? value : [value];
    for (const item of items) {
      if (item !== null && item !== undefined) params.append(key, String(item));
    }
  }
  const search = params.toString();
  return `${API_BASE}${path}${search ? `?${search}` : ""}`;
}

/** The header the server names each request's id in. */
export const REQUEST_ID_HEADER = "X-Request-ID";

async function errorFrom(response: Response): Promise<ApiError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }
  return errorFromPayload(response.status, response.statusText, payload, response.headers.get(REQUEST_ID_HEADER));
}

function errorFromPayload(status: number, statusText: string, payload: unknown, header: string | null): ApiError {
  const envelope = isRecord(payload) && isRecord(payload.error) ? payload.error : undefined;
  const requestId = envelope && typeof envelope.request_id === "string" ? envelope.request_id : header;
  if (envelope && typeof envelope.code === "string" && typeof envelope.message === "string") {
    const details = isRecord(envelope.details) ? envelope.details : undefined;
    const fields = fieldProblems(envelope.details);
    return new ApiError(status, envelope.code, envelope.message, { details, fields, requestId });
  }
  const reason = statusText ? `${status} ${statusText}` : String(status);
  const message = GATEWAY_STATUSES.has(status)
    ? `The server isn't answering right now (${reason}). It may be restarting.`
    : `The server answered ${reason}.`;
  return new ApiError(status, `http_${status}`, message, { requestId });
}

/**
 * True when the server has no such endpoint yet (404, 405 or 501), as
 * opposed to one that is failing. Parts of the interface built ahead of
 * their endpoint use it to stay quiet until the endpoint exists.
 */
export function isEndpointMissing(error: unknown): boolean {
  return error instanceof ApiError && ENDPOINT_MISSING_STATUSES.includes(error.status);
}

/** A dropped connection or a server error may pass. A bad document or a 4xx will not. */
export function isTransient(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500);
}

/** Call the API and return the decoded JSON body, or undefined for 204. */
export async function apiFetch<T>(path: string, request: ApiRequest = {}): Promise<T> {
  const method = request.method ?? "GET";
  try {
    return await send<T>(method, path, request);
  } catch (error) {
    // Kept for a problem report, unless it was stopped on purpose or expected (`failures.ts`).
    const kept = error instanceof ApiError && !request.signal?.aborted && !request.expected?.includes(error.status);
    if (kept) keepRequestFailure(method, path, error);
    throw error;
  }
}

async function send<T>(method: NonNullable<ApiRequest["method"]>, path: string, request: ApiRequest): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (!SAFE_METHODS.has(method)) headers["X-OpenAntiquity-Client"] = "web";
  const init: RequestInit = { method, headers, credentials: "include", signal: request.signal };
  if (request.file !== undefined) {
    headers["Content-Type"] = request.file.type || "application/octet-stream";
    init.body = request.file;
  } else if (request.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(request.body);
  }

  let response: Response;
  try {
    response = await fetch(apiUrl(path, request.query), init);
  } catch (cause) {
    if (isRecord(cause) && cause.name === "AbortError") throw cause;
    throw networkError(cause);
  }

  if (response.status === 401) {
    for (const listener of [...unauthorisedListeners]) listener(path);
  }
  if (!response.ok) {
    const error = await errorFrom(response);
    if (response.status === 403) for (const listener of [...forbiddenListeners]) listener(error, path);
    throw error;
  }
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch (cause) {
    throw new ApiError(response.status, "bad_response", "The server sent a reply that wasn't JSON.", {
      cause,
      requestId: response.headers.get(REQUEST_ID_HEADER),
    });
  }
}

export interface UploadRequest {
  /** Told how much of the file has been sent, from 0 to 1, as it goes. */
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
}

function networkError(cause?: unknown): ApiError {
  return new ApiError(0, "network_error", "Couldn't reach the server. Check your connection and try again.", {
    cause,
  });
}

/**
 * POST a file as the request body, as `apiFetch` does with `file`, but
 * through `XMLHttpRequest`, because `fetch` can't say how much of an upload
 * has been sent. The answer, the errors and the 401 and 403 listeners are
 * the same as `apiFetch`'s. An abort rejects with an `AbortError`.
 */
export function apiUpload<T>(path: string, file: Blob, request: UploadRequest = {}): Promise<T> {
  const url = apiUrl(path);
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    const finish = () => request.signal?.removeEventListener("abort", abort);
    if (request.signal?.aborted) {
      reject(new DOMException("The upload was stopped.", "AbortError"));
      return;
    }
    xhr.open("POST", url);
    xhr.withCredentials = true;
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("X-OpenAntiquity-Client", "web");
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) request.onProgress?.(Math.min(1, event.loaded / event.total));
    };
    /** Reject with a failure, kept for a problem report as `apiFetch` keeps its own. */
    const fail = (error: ApiError) => {
      keepRequestFailure("POST", path, error);
      reject(error);
    };
    xhr.onerror = () => {
      finish();
      fail(networkError());
    };
    xhr.onabort = () => {
      finish();
      reject(new DOMException("The upload was stopped.", "AbortError"));
    };
    xhr.onload = () => {
      finish();
      let payload: unknown;
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
      } catch {
        payload = undefined;
      }
      if (xhr.status === 401) for (const listener of [...unauthorisedListeners]) listener(path);
      const requestId = xhr.getResponseHeader(REQUEST_ID_HEADER);
      if (xhr.status < 200 || xhr.status >= 300) {
        const error = errorFromPayload(xhr.status, xhr.statusText, payload, requestId);
        if (xhr.status === 403) for (const listener of [...forbiddenListeners]) listener(error, path);
        fail(error);
        return;
      }
      if (payload === undefined) {
        fail(new ApiError(xhr.status, "bad_response", "The server sent a reply that wasn't JSON.", { requestId }));
        return;
      }
      request.onProgress?.(1);
      resolve(payload as T);
    };
    request.signal?.addEventListener("abort", abort);
    xhr.send(file);
  });
}
