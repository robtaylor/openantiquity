import type { Page, Route } from "@playwright/test";
import type { FindingDetail, ObservationIn, Reveal } from "../../src/features/finding/types.js";
import type { TaskGroup } from "../../src/features/help/api.js";
import type { ReviewCard } from "../../src/features/review/types.js";
import { observationFixture, pageFixture, revealFixture } from "../../src/test/fixtures/findingPage.js";
import { apiRoute, FINDING_PAGE_ROUTE } from "./network.js";

/**
 * A stand-in for the second-look queue and help wanted, in fixture mode.
 * The queue serves blind cards, leaving out the ones answered, as the server
 * does. An answer to a card reveals the finding behind it, given by
 * `findings` or a plain one, moved up to Seen by others.
 */
export interface FakeQueue {
  /** Each `GET /review/next`, as asked. */
  asked: URL[];
  /** The bodies of the answers sent, by finding. */
  answers: Record<string, ObservationIn[]>;
}

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

export function cardFor(finding: FindingDetail): ReviewCard {
  return {
    public_id: finding.public_id,
    place: { lon: finding.location.lon, lat: finding.location.lat, grid_ref: finding.location.grid_ref },
    view_state: finding.view_state,
  };
}

export async function fakeQueue(page: Page, findings: FindingDetail[]): Promise<FakeQueue> {
  const fake: FakeQueue = { asked: [], answers: {} };
  await page.route(apiRoute("/review/next"), (route) => {
    fake.asked.push(new URL(route.request().url()));
    const waiting = findings.filter((finding) => !(finding.public_id in fake.answers));
    return json(route, { items: waiting.map(cardFor), next_cursor: null });
  });
  await page.route(FINDING_PAGE_ROUTE, (route) => {
    const request = route.request();
    const match = FINDING_PAGE_ROUTE.exec(request.url());
    const publicId = decodeURIComponent(match?.[1] ?? "");
    const finding = findings.find((each) => each.public_id === publicId);
    if (!finding || request.method() !== "PUT" || match?.[2] !== "/observation") return route.fallback();
    const body = request.postDataJSON() as ObservationIn;
    fake.answers[publicId] = [...(fake.answers[publicId] ?? []), body];
    const answer = observationFixture({ visible: body.visible, feature_class: body.feature_class ?? null });
    const reveal: Reveal = revealFixture(answer, finding, { moved_up: true, tier_after: "seen" });
    const assessment = { ...reveal.finding.assessment, tier: "seen" as const, score: 30 };
    return json(route, { ...reveal, finding: { ...reveal.finding, tier: "seen", confidence: 30, assessment } });
  });
  return fake;
}

/** A finding for the queue, at a place of its own. */
export function queuedFinding(publicId: string, title: string, lonShift = 0, gridRef?: string): FindingDetail {
  const base = pageFixture();
  return pageFixture({
    public_id: publicId,
    title,
    location: { ...base.location, lon: base.location.lon + lonShift, grid_ref: gridRef ?? base.location.grid_ref },
  });
}

/** Answer `GET /review/tasks` from these groups, as the server would: all of them, or one by its code. */
export async function fakeTasks(page: Page, groups: TaskGroup[]): Promise<void> {
  await page.route(apiRoute("/review/tasks"), (route) => {
    const code = new URL(route.request().url()).searchParams.get("code");
    return json(route, { groups: code ? groups.filter((group) => group.code === code) : groups });
  });
}
