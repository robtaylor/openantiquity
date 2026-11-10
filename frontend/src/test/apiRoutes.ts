import type { Mock } from "vitest";
import { fixtureResponse, json, requestPath } from "./shellHarness.js";

/** One request as a route handler sees it. */
export interface ApiCall {
  method: string;
  /** The API path without `/api/v1` and without the query, such as "/auth/me". */
  path: string;
  url: URL;
  /** The JSON body, if one was sent. */
  body: unknown;
  headers: Headers;
}

export type ApiHandler = (call: ApiCall) => Response | Promise<Response>;

const PREFIX = "/api/v1";

function callFrom(input: unknown, init?: RequestInit): ApiCall {
  const url = new URL(String(input), "http://localhost");
  let body: unknown;
  if (typeof init?.body === "string") body = JSON.parse(init.body);
  return {
    method: init?.method ?? "GET",
    path: requestPath(input).slice(PREFIX.length),
    url,
    body,
    headers: new Headers(init?.headers),
  };
}

export interface ApiRoutes {
  /** Every API call made since the routes were set up, in order. */
  calls: ApiCall[];
  /** The calls to one route, such as "POST /auth/email/verify". */
  callsTo: (route: string) => ApiCall[];
  /** Answer a route, such as "GET /auth/me", with `handler` from now on. */
  on: (route: string, handler: ApiHandler) => void;
}

/**
 * Answer API requests by method and path, on top of the fixtures: a route
 * given to `on` wins, and anything else gets `fixtureResponse`. Pass the
 * fetch mock from `setUpShellTests()`, inside a `beforeEach` or a test.
 */
export function routeApi(fetchMock: Mock, routes: Record<string, ApiHandler> = {}): ApiRoutes {
  const handlers = new Map(Object.entries(routes));
  const calls: ApiCall[] = [];
  fetchMock.mockImplementation(async (input: unknown, init?: RequestInit) => {
    const call = callFrom(input, init);
    calls.push(call);
    const handler = handlers.get(`${call.method} ${call.path}`);
    return handler ? handler(call) : fixtureResponse(input);
  });
  return {
    calls,
    callsTo: (route) => calls.filter((call) => `${call.method} ${call.path}` === route),
    on: (route, handler) => {
      handlers.set(route, handler);
    },
  };
}

/** An error in the API's envelope. */
export function apiError(status: number, code: string, message = code, details?: Record<string, unknown>): Response {
  return json({ error: { code, message, ...(details ? { details } : {}) } }, status);
}
