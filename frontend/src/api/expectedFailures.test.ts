import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchLiveSources as fetchCreditSources } from "../features/about/api.js";
import { fetchMe } from "../features/account/api.js";
import { fetchFindingsInBox, fetchFindingsPage } from "../features/findings/api.js";
import { NO_FILTERS } from "../features/findings/filters.js";
import { fetchLiveSources } from "../features/records/api.js";
import { json } from "../test/http.js";
import { forgetFailures, keptFailures } from "./failures.js";
import { fetchGeoPoint } from "./geo.js";

/**
 * The answers a page expects as a matter of course aren't kept for a
 * problem report, or every signed-out visit would fill the ten slots: the
 * 401 that says nobody is signed in, and the 404 of an endpoint the
 * interface was built ahead of.
 */

const BOX = [-1.86, 51.42, -1.84, 51.43] as const;

function answerAll(status: number) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => json({ error: { code: status === 401 ? "unauthorised" : "not_found", message: "No." } }, status)),
  );
}

beforeEach(() => forgetFailures());
afterEach(() => {
  vi.unstubAllGlobals();
  forgetFailures();
});

describe("an expected answer", () => {
  it("isn't kept when nobody is signed in", async () => {
    answerAll(401);
    await expect(fetchMe()).resolves.toBeNull();
    expect(keptFailures()).toEqual([]);
  });

  it.each([
    ["the findings in a box", () => fetchFindingsInBox([...BOX])],
    ["a page of findings", () => fetchFindingsPage([...BOX], NO_FILTERS, null)],
    ["the live sources", () => fetchLiveSources()],
    ["the live sources for the credits", () => fetchCreditSources()],
    ["what is at a point", () => fetchGeoPoint(-1.85, 51.43)],
  ])("isn't kept when the server has no endpoint for %s", async (_name, probe) => {
    answerAll(404);
    await expect(probe()).rejects.toMatchObject({ status: 404 });
    expect(keptFailures()).toEqual([]);
  });

  it("is kept when it isn't what the caller expected", async () => {
    answerAll(404);
    await expect(fetchMe()).rejects.toMatchObject({ status: 404 });
    expect(keptFailures()).toHaveLength(1);
  });
});
