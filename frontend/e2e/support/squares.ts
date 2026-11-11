import type { Page, Route } from "@playwright/test";
import type { Square, SurveyIn } from "../../src/features/scan/api.js";
import { coverageOf } from "../../src/test/fixtures/squares.js";
import { apiRoute } from "./network.js";

/**
 * A stand-in for "Scan a square" in fixture mode that keeps the server's
 * rules: `GET /squares/next` hands out `squares` in turn, never one the
 * person has a result for nor one named in `exclude`, and says
 * `no_square_available` when none is left; `PUT /squares/{ref}` keeps one
 * result per square, refusing a marked result with no findings; and
 * `GET /squares/coverage` counts every result but a skip, on top of
 * `scans` already given.
 */
export interface FakeSquares {
  /** Each `GET /squares/next`, as asked. */
  asked: URL[];
  /** The results sent, by square, in order. */
  results: Record<string, SurveyIn[]>;
  /** Each `GET /squares/coverage`, as asked. */
  coverage: URL[];
}

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

export async function fakeSquares(page: Page, squares: Square[]): Promise<FakeSquares> {
  const fake: FakeSquares = { asked: [], results: {}, coverage: [] };
  await page.route(apiRoute("/squares/next"), (route) => {
    const url = new URL(route.request().url());
    fake.asked.push(url);
    const left = new Set(url.searchParams.getAll("exclude"));
    const square = squares.find((each) => !left.has(each.square) && !(each.square in fake.results));
    if (!square) {
      return json(route, { error: { code: "no_square_available", message: "There's no square left." } }, 404);
    }
    return json(route, square);
  });
  await page.route(/\/api\/v1\/squares\/[A-Z]{2}\d{4}$/, (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    const ref = new URL(route.request().url()).pathname.split("/").pop() ?? "";
    const body = route.request().postDataJSON() as SurveyIn;
    if ((body.result === "marked") !== (body.findings_count ?? 0) > 0) {
      return json(route, { error: { code: "invalid_survey", message: "Mark at least one finding." } }, 422);
    }
    const first = !(ref in fake.results);
    fake.results[ref] = [...(fake.results[ref] ?? []), body];
    const square = squares.find((each) => each.square === ref);
    return json(
      route,
      { square: ref, grid_ref: square?.grid_ref ?? ref, seconds: null, ...body, created_at: new Date().toISOString() },
      first ? 201 : 200,
    );
  });
  await page.route(apiRoute("/squares/coverage"), (route) => {
    fake.coverage.push(new URL(route.request().url()));
    const entries = squares.flatMap((square) => {
      const latest = fake.results[square.square]?.at(-1);
      const scans = square.scans + (latest && latest.result !== "skipped" ? 1 : 0);
      return scans > 0 ? [{ square, scans }] : [];
    });
    return json(route, coverageOf(entries));
  });
  return fake;
}
