import type { Page, Route } from "@playwright/test";
import type { RecordOut } from "../../src/features/records/api.js";
import type { GeoResult } from "../../src/features/search/api.js";
import {
  CONTEXT_LINKS,
  GEO_RESULTS,
  GRIDREF_RESULT,
  LIVE_SOURCES,
  RECORD_SEARCH_PAGE_1,
  RECORD_SEARCH_PAGE_2,
  RECORDS_BY_ID,
  WILTSHIRE_RECORDED_ANSWER,
} from "../../src/test/fixtures/records.js";
import { apiRoute } from "./network.js";

/**
 * Stand-ins for the record index, the search box, the context catalogue and
 * the live sources, from the shared fixtures. Each answers as the backend or
 * the publisher would, and logs what it was asked.
 */

export interface RecordsLog {
  /** The `q` of each `GET /geo/search`, in order. */
  geoSearches: string[];
  /** Each `GET /records/search`, as its query. */
  recordSearches: URLSearchParams[];
  /** Each request to a live source's host, by host. */
  live: Record<string, string[]>;
}

function json(route: Route, body: unknown, status = 200, headers: Record<string, string> = {}): Promise<void> {
  return route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });
}

/** The answer to `GET /geo/search?q=`, by what was typed. */
function geoAnswer(q: string): { status: number; body: unknown } {
  const text = q.toLowerCase();
  if (text.startsWith("ave")) return { status: 200, body: { items: GEO_RESULTS } };
  if (text.startsWith("su")) return { status: 200, body: { items: [GRIDREF_RESULT] } };
  if (text === "slow") {
    return {
      status: 503,
      body: { error: { code: "search_timeout", message: "That search took too long. Add another word." } },
    };
  }
  return { status: 200, body: { items: [] as GeoResult[] } };
}

export async function serveRecordsApi(page: Page): Promise<RecordsLog> {
  const log: RecordsLog = { geoSearches: [], recordSearches: [], live: {} };

  await page.route(apiRoute("/geo/search"), async (route) => {
    const q = new URL(route.request().url()).searchParams.get("q") ?? "";
    log.geoSearches.push(q);
    const { status, body } = geoAnswer(q);
    return json(route, body, status);
  });

  await page.route(/^https?:\/\/localhost(:\d+)?\/api\/v1\/records\/(\d+)(?:\?|$)/, (route) => {
    const id = Number(/\/records\/(\d+)/.exec(route.request().url())?.[1]);
    const record: RecordOut | undefined = RECORDS_BY_ID[id];
    if (!record) return json(route, { error: { code: "record_not_found", message: "No such record." } }, 404);
    return json(route, record);
  });

  await page.route(apiRoute("/records/search"), (route) => {
    const params = new URL(route.request().url()).searchParams;
    log.recordSearches.push(params);
    if (params.get("format") === "geojson") {
      const features = [...RECORD_SEARCH_PAGE_1.items, ...RECORD_SEARCH_PAGE_2.items].map((record) => ({
        type: "Feature",
        id: record.id,
        geometry: { type: "Point", coordinates: [record.lon, record.lat] },
        properties: {
          id: record.id,
          name: record.name,
          licence: record.source.licence,
          attribution: record.source.attribution,
          reuse: record.source.reuse,
        },
      }));
      return route.fulfill({
        status: 200,
        contentType: "application/geo+json",
        body: JSON.stringify({ type: "FeatureCollection", features }),
      });
    }
    return json(route, params.get("cursor") === "page-2" ? RECORD_SEARCH_PAGE_2 : RECORD_SEARCH_PAGE_1);
  });

  await page.route(apiRoute("/context/links"), (route) => json(route, CONTEXT_LINKS));
  await page.route(apiRoute("/context/live-sources"), (route) => json(route, { items: LIVE_SOURCES }));
  return log;
}

/**
 * The live sources' own hosts. Wiltshire replays its recorded answer and
 * allows this site to read it. Aberdeenshire's request is refused. A browser tells a page about a cross-origin refusal only as a
 * failed fetch with no response, the same as a dropped connection, and an
 * answer Playwright fulfils is not checked for CORS headers, so the request
 * is failed outright: from the page that is exactly what a refusal looks
 * like. Dartmoor answers with a server error. Set `wiltshire` to answer
 * something else.
 */
export async function serveLiveHosts(
  page: Page,
  log: RecordsLog,
  wiltshire: unknown = WILTSHIRE_RECORDED_ANSWER,
): Promise<void> {
  const note = (route: Route): string => {
    const url = new URL(route.request().url());
    const list = log.live[url.host] ?? [];
    list.push(url.href);
    log.live[url.host] = list;
    return route.request().headers().origin ?? "*";
  };
  await page.route(/^https:\/\/maps\.wiltshire\.gov\.uk\//, (route) =>
    json(route, wiltshire, 200, { "Access-Control-Allow-Origin": note(route) }),
  );
  await page.route(/^https:\/\/services2\.arcgis\.com\//, (route) => {
    note(route);
    return route.abort("accessdenied");
  });
  await page.route(/^https:\/\/services-eu1\.arcgis\.com\//, (route) =>
    route.fulfill({ status: 500, headers: { "Access-Control-Allow-Origin": note(route) }, body: "Server error" }),
  );
}
