import type { Page } from "@playwright/test";
import { BORDER_COVERAGE } from "../../src/test/fixtures/coverage.js";
import { apiRoute } from "./network.js";

/**
 * Stand-in answers for the terrain tools: a height profile shaped like a
 * henge's ditch and bank, and coverage recorded at the Welsh border.
 */

export interface ProfileLog {
  /** The bodies of every `POST /terrain/profile`. */
  requests: Array<{ line: { coordinates: Array<[number, number]> }; samples: number }>;
}

/** Ground along a line: level, down into a ditch two-fifths of the way, up over a bank, then level. */
export function sectionHeight(fraction: number): number {
  const ditch = -6 * Math.exp(-(((fraction - 0.4) / 0.05) ** 2));
  const bank = 6 * Math.exp(-(((fraction - 0.55) / 0.06) ** 2));
  return Math.round((160 + ditch + bank + fraction * 3) * 100) / 100;
}

/** Answer `POST /terrain/profile` with `sectionHeight` along the straight line from the first point to the last. */
export async function serveProfile(page: Page, lengthM = 280): Promise<ProfileLog> {
  const log: ProfileLog = { requests: [] };
  await page.route(apiRoute("/terrain/profile"), (route) => {
    const body = route.request().postDataJSON() as ProfileLog["requests"][number];
    log.requests.push(body);
    const points = body.line.coordinates;
    const [first, last] = [points[0], points.at(-1)] as [[number, number], [number, number]];
    const count = Math.min(body.samples, 200);
    const samples = Array.from({ length: count }, (_, i) => {
      const t = i / (count - 1);
      return {
        distance_m: Math.round(t * lengthM * 100) / 100,
        elevation: sectionHeight(t),
        lon: first[0] + (last[0] - first[0]) * t,
        lat: first[1] + (last[1] - first[1]) * t,
      };
    });
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ length_m: lengthM, resolution_m: 1, samples }),
    });
  });
  return log;
}

/** Answer `GET /terrain/coverage` with the recording from the Welsh border, whatever box is asked about. */
export async function serveBorderCoverage(page: Page): Promise<void> {
  await page.route(apiRoute("/terrain/coverage"), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(BORDER_COVERAGE) }),
  );
}
