import type { Page, Request } from "@playwright/test";
import type { Me } from "../../src/features/account/api.js";
import { meFixture } from "../../src/test/fixtures/me.js";
import { apiRoute } from "./network.js";

export { newcomerFixture } from "../../src/test/fixtures/me.js";
export { meFixture };

/**
 * Who `GET /auth/me` says is signed in, for a fixture-mode test. Starts
 * signed out. Change it with `set`, as a sign-in or sign-out would. Every
 * request the page sends to the API is kept in `requests`, so a test can
 * check what went where.
 */
export interface FakeSession {
  set: (me: Me | null) => void;
  current: () => Me | null;
  requests: Request[];
}

export async function fakeSession(page: Page, initial: Me | null = null): Promise<FakeSession> {
  let me = initial;
  const requests: Request[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) requests.push(request);
  });
  await page.route(apiRoute("/auth/me"), (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    if (me === null) {
      return route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "unauthorised", message: "Sign in first." } }),
      });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(me) });
  });
  return {
    set: (next) => {
      me = next;
    },
    current: () => me,
    requests,
  };
}

/** Answer one API route with JSON. */
export async function answerJson(
  page: Page,
  path: string,
  body: unknown,
  { status = 200, method }: { status?: number; method?: string } = {},
): Promise<void> {
  await page.route(apiRoute(path), (route) => {
    if (method && route.request().method() !== method) return route.fallback();
    return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
}

export function meWith(overrides: Partial<Me> = {}): Me {
  return meFixture(overrides);
}
