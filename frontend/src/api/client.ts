/**
 * The one place the frontend talks to the backend. Every request sends the
 * session cookie. Every mutation carries `X-FieldClub-Client: web`, which the API
 * requires and a cross-site form cannot send. Failures become an `ApiError`
 * built from the `{"error": {"code", "message"}}` envelope.
 */

import { isRecord } from "./guards.js";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  /** HTTP status, or 0 when no response arrived. */
  readonly status: number;
  /** The stable code from the error envelope, such as "not_found". */
  readonly code: string;

  constructor(status: number, code: string, message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export type QueryValue = string | number | boolean | null | undefined;

export interface ApiRequest {
  method?: "GET" | "HEAD" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, QueryValue>;
  /** Sent as JSON. */
  body?: unknown;
  signal?: AbortSignal;
}

const SAFE_METHODS = new Set(["GET", "HEAD"]);
/** Statuses that come from a proxy in front of a backend that is down. */
const GATEWAY_STATUSES = new Set([502, 503, 504]);

export function apiUrl(path: string, query: Record<string, QueryValue> = {}): string {
  if (!path.startsWith("/")) throw new ApiError(0, "bad_request", `API path "${path}" must start with "/"`);
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined) params.set(key, String(value));
  }
  const search = params.toString();
  return `${API_BASE}${path}${search ? `?${search}` : ""}`;
}

async function errorFrom(response: Response): Promise<ApiError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }
  const envelope = isRecord(payload) && isRecord(payload.error) ? payload.error : undefined;
  if (envelope && typeof envelope.code === "string" && typeof envelope.message === "string") {
    return new ApiError(response.status, envelope.code, envelope.message);
  }
  const reason = response.statusText ? `${response.status} ${response.statusText}` : String(response.status);
  const message = GATEWAY_STATUSES.has(response.status)
    ? `The server isn't answering right now (${reason}). It may be restarting.`
    : `The server answered ${reason}.`;
  return new ApiError(response.status, `http_${response.status}`, message);
}

/**
 * True when the server has no such endpoint yet (404, 405 or 501), as
 * opposed to one that is failing. Parts of the interface built ahead of
 * their endpoint use it to stay quiet until the endpoint exists.
 */
export function isEndpointMissing(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 405 || error.status === 501);
}

/** A dropped connection or a server error may pass. A bad document or a 4xx will not. */
export function isTransient(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500);
}

/** Call the API and return the decoded JSON body, or undefined for 204. */
export async function apiFetch<T>(path: string, request: ApiRequest = {}): Promise<T> {
  const method = request.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (!SAFE_METHODS.has(method)) headers["X-FieldClub-Client"] = "web";
  const init: RequestInit = { method, headers, credentials: "include", signal: request.signal };
  if (request.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(request.body);
  }

  let response: Response;
  try {
    response = await fetch(apiUrl(path, request.query), init);
  } catch (cause) {
    if (isRecord(cause) && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "network_error", "Couldn't reach the server. Check your connection and try again.", {
      cause,
    });
  }

  if (!response.ok) throw await errorFrom(response);
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch (cause) {
    throw new ApiError(response.status, "bad_response", "The server sent a reply that wasn't JSON.", { cause });
  }
}
