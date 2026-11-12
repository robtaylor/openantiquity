import type { Page } from "@playwright/test";
import type { Me } from "../../src/features/account/api.js";
import {
  ADA,
  FakeInvestigations,
  type FakeInvestigationsOptions,
  GUS,
  MARY,
} from "../../src/test/fixtures/investigations.js";

export { ADA, GUS, MARY };

/** A signed-in person as an investigation names them. */
export function publicUser(me: Me) {
  return { handle: me.handle, display_name: me.display_name, role: me.role };
}

const ROUTE = /^https?:\/\/localhost(?::\d+)?\/api\/v1(\/investigations(?:\/[^?#]*)?)(?:\?|$)/;

/**
 * Answer every investigation route from the shared in-memory stand-in, so a
 * flow can start one, add to it, reorder it and publish it, and see each
 * change come back as the backend would send it.
 */
export async function serveInvestigations(
  page: Page,
  options: Omit<FakeInvestigationsOptions, "people"> & { people?: FakeInvestigationsOptions["people"] },
): Promise<FakeInvestigations> {
  const fake = new FakeInvestigations({ people: [ADA, MARY, GUS], ...options });
  await page.route(ROUTE, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = ROUTE.exec(request.url())?.[1] ?? "";
    if (path.endsWith("/export")) {
      return route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><title>Report</title>" });
    }
    const body = request.postData() ? JSON.parse(request.postData() ?? "null") : undefined;
    const answer = fake.handle(request.method(), path, url.searchParams, body);
    if (!answer) return route.fallback();
    if (answer.status === 204) return route.fulfill({ status: 204 });
    return route.fulfill({ status: answer.status, contentType: "application/json", body: JSON.stringify(answer.body) });
  });
  return fake;
}
