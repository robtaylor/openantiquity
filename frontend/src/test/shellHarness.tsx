import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type RenderResult, render, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, type Mock, vi } from "vitest";
import { BARE_MAP_PATH } from "../features/shell/navigation.js";
import { Shell } from "../features/shell/Shell.js";
import { useMapStore, usePointerStore, useViewAreaStore } from "../map/store.js";
import { useToastStore } from "../ui/toastStore.js";
import { PHONE_QUERY } from "../ui/tokens.js";
import { FakeMap } from "./fakeMapLibre.js";
import { findingPage, findingsData, findingsMatching } from "./fixtures/findings.js";
import { metaFixture } from "./fixtures/meta.js";
import { json, requestPath } from "./http.js";

export { json, requestPath };

/**
 * What every test of the whole shell needs: the app rendered in a memory
 * router, the API answered from fixtures, and the fake map. A test file
 * that uses it must also mock `maplibre-gl` with `FakeMap` itself, because
 * `vi.mock` only works from the file under test.
 */

export function metaResponse(meta: unknown = metaFixture): Response {
  return json(meta);
}

/** The answer `GET /auth/me` gives when nobody is signed in. */
export function signedOutResponse(): Response {
  return json({ error: { code: "unauthorised", message: "Sign in first." } }, 401);
}

/**
 * The fixtures' answer to a request: `/meta` and `/findings` from their
 * fixtures (GeoJSON for the map, a page for the list, with the filters
 * applied as the server applies them), nobody signed in, an empty second-look
 * queue and no help wanted, no mentions and no activity, and 404 for anything else, as a backend that has
 * not built the endpoint yet would say.
 */
export async function fixtureResponse(input: unknown): Promise<Response> {
  switch (requestPath(input)) {
    case "/api/v1/meta":
      return metaResponse();
    case "/api/v1/findings": {
      const url = new URL(String(input), "http://localhost");
      const found = { ...findingsData, features: findingsMatching(findingsData.features, url) };
      return url.searchParams.get("format") === "geojson" ? json(found) : json(findingPage(found));
    }
    case "/api/v1/auth/me":
      return signedOutResponse();
    // Nothing waiting for a second look, and no help wanted.
    case "/api/v1/review/next":
      return json({ items: [], next_cursor: null });
    case "/api/v1/review/tasks":
      return json({ groups: [] });
    // Nobody has mentioned anything, and nothing has happened.
    case "/api/v1/mentions/recent":
    case "/api/v1/activity":
      return json({ items: [], next_cursor: null });
    default:
      if (/^\/api\/v1\/findings\/[^/]+\/mentions$/.test(requestPath(input)))
        return json({ items: [], next_cursor: null });
      return json({ detail: "Not Found" }, 404);
  }
}

export { BARE_MAP_PATH };

export function renderShell(path = BARE_MAP_PATH, extra?: ReactNode): RenderResult {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Shell />
        {extra}
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export function liveMaps(): FakeMap[] {
  return FakeMap.instances.filter((instance) => !instance.removed);
}

export async function mapReady(): Promise<FakeMap> {
  await waitFor(() => expect(document.querySelector('.fc-map[data-ready="true"]')).not.toBeNull());
  const map = liveMaps()[0];
  if (!map) throw new Error("No map was created");
  return map;
}

/** Answer the phone media query with yes, so the shell lays itself out for a phone. */
export function usePhoneLayout(): void {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: query === PHONE_QUERY,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList,
  );
}

export interface ShellHarness {
  fetchMock: () => Mock;
  /** How many requests have gone to an API path, such as "/meta". */
  requestsTo: (path: string) => number;
  /** Answer an API path, such as "/findings", with `respond` from now on. Other paths keep their answers. */
  answer: (path: string, respond: (url: URL) => Response | Promise<Response>) => void;
}

/**
 * Reset the stores, the fake map and the address bar before each test, and
 * answer the API from the fixtures. Returns the fetch mock so a test can make
 * a request fail, a count of the requests made to one path, and a way to
 * answer one path differently.
 */
export function setUpShellTests(): ShellHarness {
  let fetchMock: Mock = vi.fn();

  beforeEach(() => {
    FakeMap.reset();
    useMapStore.setState(useMapStore.getInitialState(), true);
    usePointerStore.setState({ position: null });
    useToastStore.getState().clear();
    window.history.replaceState(null, "", "/");
    useViewAreaStore.setState({ bounds: null, zoom: 0 });
    fetchMock = vi.fn(fixtureResponse);
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  return {
    fetchMock: () => fetchMock,
    requestsTo: (path) => fetchMock.mock.calls.filter(([input]) => requestPath(input) === `/api/v1${path}`).length,
    answer: (path, respond) => {
      const fallback = fetchMock.getMockImplementation();
      fetchMock.mockImplementation(async (input: unknown, init?: RequestInit) =>
        requestPath(input) === `/api/v1${path}`
          ? respond(new URL(String(input), "http://localhost"))
          : fallback?.(input, init),
      );
    },
  };
}
