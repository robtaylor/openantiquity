import type { Page, Route } from "@playwright/test";
import type { FindingCreate, FindingDetail, FindingFeature } from "../../src/features/findings/types.js";
import {
  createdFinding,
  findingDetail,
  findingSummary,
  findingsData,
  findingsMatching,
} from "../../src/test/fixtures/findings.js";
import { apiRoute, FINDING_PAGE_ROUTE } from "./network.js";

/**
 * A stand-in for the findings endpoints in fixture mode, answering both the
 * map (`format=geojson`) and the Explore list (pages of `limit`, with an
 * offset for a cursor) from one set of findings, with the filters applied
 * as the server applies them. `POST /findings` adds a spotted finding to
 * the set, so the map and the list then show it, unless a failure is queued.
 * Each finding's page (`GET /findings/{id}`) is served from the same set.
 */
export interface FakeFindings {
  /** Every body sent to `POST /findings`, in order, including refused ones. */
  created: FindingCreate[];
  /** Every list (not map) request, in order. */
  lists: URL[];
  /** Every map request, in order. */
  boxes: URL[];
  /** Refuse the next create with this error. */
  failNextCreate: (status: number, code: string, message: string) => void;
  /** Hold each create until the returned function is called, to see what the page does meanwhile. */
  holdCreates: () => () => void;
}

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

export async function fakeFindings(
  page: Page,
  initial: readonly FindingFeature[] = findingsData.features,
): Promise<FakeFindings> {
  const features = [...initial];
  const log: FakeFindings = {
    created: [],
    lists: [],
    boxes: [],
    failNextCreate: (status, code, message) => {
      failure = { status, code, message };
    },
    holdCreates: () => {
      let release = (): void => {};
      hold = new Promise<void>((resolve) => {
        release = resolve;
      });
      return () => release();
    },
  };
  let failure: { status: number; code: string; message: string } | null = null;
  let hold: Promise<void> | null = null;
  let made = 0;
  const details = new Map<string, FindingDetail>();
  /** When each finding made here was made, so a list by its author shows it as theirs and new. */
  const madeAt = new Map<string, string>();

  await page.route(FINDING_PAGE_ROUTE, (route) => {
    const match = FINDING_PAGE_ROUTE.exec(route.request().url());
    const publicId = decodeURIComponent(match?.[1] ?? "");
    if (route.request().method() !== "GET" || match?.[2] !== undefined) return route.fallback();
    const known = details.get(publicId) ?? features.find((feature) => feature.properties.public_id === publicId);
    if (!known) return route.fallback();
    return json(route, "assessment" in known ? known : findingDetail(findingSummary(known)));
  });

  await page.route(apiRoute("/findings"), async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() === "POST") {
      const body = request.postDataJSON() as FindingCreate;
      log.created.push(body);
      if (hold) await hold;
      if (failure) {
        const { status, code, message } = failure;
        failure = null;
        return json(route, { error: { code, message } }, status);
      }
      made += 1;
      const finding = createdFinding(body, `new-${made}`);
      details.set(finding.public_id, finding);
      madeAt.set(finding.public_id, new Date().toISOString());
      features.unshift({
        type: "Feature",
        geometry: { type: "Point", coordinates: [finding.location.lon, finding.location.lat] },
        properties: {
          public_id: finding.public_id,
          tier: finding.tier,
          state: finding.state,
          sensitivity: finding.sensitivity,
          obscured: false,
          title: finding.title,
          feature_class: finding.feature_class,
        },
      });
      return json(route, finding, 201);
    }
    if (request.method() !== "GET") return route.fallback();
    const found = findingsMatching(features, url);
    if (url.searchParams.get("format") === "geojson") {
      log.boxes.push(url);
      return json(route, { type: "FeatureCollection", features: found, next_cursor: null });
    }
    log.lists.push(url);
    const limit = Number(url.searchParams.get("limit") ?? 50);
    const offset = Number(url.searchParams.get("cursor") ?? 0);
    // `author=` lists the findings made here, as the one asking made them, and any seeded under that handle.
    const author = url.searchParams.get("author");
    const listed = author
      ? found.filter(
          (feature) => madeAt.has(feature.properties.public_id) || findingSummary(feature).author.handle === author,
        )
      : found;
    const items = listed.slice(offset, offset + limit).map((feature) => {
      const when = madeAt.get(feature.properties.public_id);
      const summary = findingSummary(feature);
      return when && author
        ? { ...summary, author: { ...summary.author, handle: author }, created_at: when, updated_at: when }
        : summary;
    });
    const next = offset + limit < listed.length ? String(offset + limit) : null;
    return json(route, { items, next_cursor: next });
  });
  return log;
}
