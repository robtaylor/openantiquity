/**
 * The requests behind "Scan a square": the next square to look over, the
 * person's result for one, and the coverage layer. Shapes come from the
 * generated schema only.
 */

import { apiFetch } from "../../api/client.js";
import type { components } from "../../api/schema.js";
import { FINDINGS_PATH } from "../findings/api.js";
import { type FindingPage, parseFindingPage } from "../findings/types.js";

type Schemas = components["schemas"];

export type Square = Schemas["SquareOut"];
export type SurveyIn = Schemas["SurveyIn"];
export type SurveyOut = Schemas["SurveyOut"];
export type SurveyResult = Schemas["SurveyResult"];
export type CoverageCollection = Schemas["CoverageCollection"];

export const SCAN_PATH = "/scan";

/** The most squares the server takes in `exclude` (`MAX_EXCLUDE` in services/squares.py). */
export const MAX_EXCLUDE = 100;
/** The longest time a result may say was spent on a square (`MAX_SECONDS`). */
export const MAX_SECONDS = 24 * 3600;
/** The most findings a result may count (`MAX_FINDINGS`). */
export const MAX_FINDINGS = 100;
/** The largest box `GET /squares/coverage` answers for (`MAX_COVERAGE_KM2`). */
export const MAX_COVERAGE_KM2 = 2500;

export interface NextSquareRequest {
  /** Where the map is, so the square is near it. */
  near: [number, number] | null;
  /** Squares to leave out: those done in this browser that the server doesn't know about yet. */
  exclude: readonly string[];
}

/** `GET /squares/next`: a square few people have looked over, near `near`, never one in `exclude`. */
export function fetchNextSquare({ near, exclude }: NextSquareRequest, signal?: AbortSignal): Promise<Square> {
  return apiFetch<Square>("/squares/next", {
    query: {
      lon: near?.[0],
      lat: near?.[1],
      // The newest are the likeliest to be near, and the server takes no more than this.
      exclude: exclude.slice(-MAX_EXCLUDE),
    },
    signal,
  });
}

/** `PUT /squares/{ref}`: the person's result for a square. A second one replaces the first. */
export function putSurvey(square: string, body: SurveyIn): Promise<SurveyOut> {
  return apiFetch<SurveyOut>(`/squares/${encodeURIComponent(square)}`, { method: "PUT", body });
}

/** `GET /squares/coverage`: how many people have scanned each square in the box. */
export function fetchScanCoverage(bbox: readonly number[], signal?: AbortSignal): Promise<CoverageCollection> {
  return apiFetch<CoverageCollection>("/squares/coverage", { query: { bbox: bbox.join(",") }, signal });
}

/** `GET /findings?bbox=&author=`: the person's own findings in a box, newest first, up to `MAX_FINDINGS`. */
export async function fetchOwnFindingsIn(
  bbox: readonly number[],
  handle: string,
  signal?: AbortSignal,
): Promise<FindingPage> {
  const body = await apiFetch<unknown>(FINDINGS_PATH, {
    query: { bbox: bbox.join(","), author: handle, limit: MAX_FINDINGS },
    signal,
  });
  return parseFindingPage(body);
}
