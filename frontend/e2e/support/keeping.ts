import type { Page, Route } from "@playwright/test";
import type { components } from "../../src/api/schema.js";
import type { FindingDetail, PublicUser, ShapeSuggestion } from "../../src/features/finding/types.js";
import type { FindingSummary } from "../../src/features/findings/types.js";
import type { FakeFindingPage } from "./findingPage.js";

type EarlierShape = components["schemas"]["EarlierShapeOut"];
type Path = components["schemas"]["Path"];
type ChangeKind = components["schemas"]["ShapeChangeKind"];

/**
 * Stand-ins, in fixture mode, for the routes of keeping, suggestions and an
 * admin's removal, on the finding a `fakeFindingPage` serves. They change
 * that finding as the server would for the one viewer the test plays, and
 * refuse as it does, with its statuses, codes and messages
 * (`backend/src/fieldclub/services/suggestions.py`, `keeping.py`,
 * `shape_edits.py`, `errors.py`):
 *
 * - a suggestion: 429 `rate_limited` when `limitNext` was called, 409
 *   `shape_changed` on a stale `path_revision`, 422 `suggestion_unchanged`
 *   for the shape as it is, 409 `too_many_suggestions` at `maxPending`. Its
 *   `kind` and `length_m` are worked out from what was sent, and `behind`
 *   from the revision, as the shape changes.
 * - an accept: 409 `shape_changed` on a stale `shape_revision`, and 422
 *   `looked_at_moved` when `refuseNextAccept` was called.
 * - an offer: 404 `user_not_found` for a handle not in `people`, with one
 *   body, and 422 `already_keeper` for the keeper.
 * - a removal: 409 `not_orphaned` while `orphaned` is false, 409
 *   `shape_changed` on a stale `shape_revision`, and 422 `no_such_revision`.
 *
 * Every write is kept in `sent`, by route, such as "POST suggestions".
 * What each viewer may do afterwards is the test's to say with `fake.set`,
 * as it is the server's.
 */
export interface FakeKeeping {
  sent: Record<string, unknown[]>;
  refuseNextAccept: (message: string) => void;
  /** Answer the next suggestion 429, as the hourly limit does. */
  limitNext: () => void;
  /** Change the shape as the keeper would elsewhere, raising its revision, so what the page holds is stale. */
  changeShapeElsewhere: () => void;
}

export interface KeepingState {
  /** Who the viewer is, for the suggestions they make. */
  me: PublicUser;
  /** Whom an offer by handle names. */
  people?: Record<string, PublicUser>;
  orphaned?: Array<{ finding: FindingSummary; keeper: PublicUser; keeper_gone: "deleted" | "banned" }>;
  earlier?: EarlierShape[];
  /** Whether the marking is orphaned, for a removal. Yes unless said. */
  isOrphaned?: boolean;
  /** The pending suggestions a finding may hold. The server's is 20. */
  maxPending?: number;
}

const MESSAGES = {
  shape_changed: "The shape was changed somewhere else. Reload the finding and make your change again.",
  suggestion_unchanged: "The suggested shape is the shape the finding has now.",
  too_many_suggestions: "This finding has 20 suggestions waiting for its keeper. Try again once some are answered.",
  rate_limited: "You're doing that too often. Try again shortly.",
  suggestion_not_found: "There's no suggestion with that id on this finding.",
  user_not_found: "There's nobody by that handle.",
  already_keeper: "They keep this marking already.",
  not_orphaned: "This marking's keeper is still a member. A moderator hides it, or bans its keeper, first.",
  no_such_revision: "There's no earlier shape of this finding with that revision to put back.",
} as const;

function json(route: Route, body: unknown, status = 200, headers: Record<string, string> = {}): Promise<void> {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body), headers });
}

function refusal(route: Route, status: number, code: keyof typeof MESSAGES | "looked_at_moved", message?: string) {
  const said = message ?? MESSAGES[code as keyof typeof MESSAGES];
  return json(route, { error: { code, message: said } }, status, status === 429 ? { "Retry-After": "60" } : {});
}

const KEEPING_ROUTE =
  /^https?:\/\/localhost(?::\d+)?\/api\/v1\/findings\/([^/?#]+)\/(suggestions(?:\/(\d+)(?:\/(accept|decline))?)?|keeping\/(offer|accept))(?:\?|$)/;
const MOD_ROUTE =
  /^https?:\/\/localhost(?::\d+)?\/api\/v1\/mod\/(markings\/orphaned|findings\/([^/?#]+)\/(shapes|marking))(?:\?|$)/;

function outlineOf(path: Path): ShapeSuggestion["outline"] {
  const coordinates = path.points.map(({ lon, lat }) => [lon, lat]);
  const first = coordinates[0];
  return path.closed && first
    ? { type: "Polygon", coordinates: [[...coordinates, first]] }
    : { type: "LineString", coordinates };
}

type Point = { lon: number; lat: number };

function same(a: Point, b: Point): boolean {
  return a.lon === b.lon && a.lat === b.lat;
}

/** How `next` changes `before`, as `shapes.classify_change` says: an extension keeps the old open path whole and in order. */
function classify(before: Path | null, next: Path): ChangeKind {
  if (before === null) return "drawn";
  if (before.closed !== next.closed) return next.closed ? "closed" : "opened";
  if (!before.closed && next.points.length > before.points.length) {
    for (let start = 0; start + before.points.length <= next.points.length; start++) {
      if (before.points.every((point, index) => same(point, next.points[start + index] as Point))) return "extended";
    }
  }
  return "reshaped";
}

/** Near enough for a fixture: the length along the points, in metres. */
function lengthOf(path: Path): number {
  const points = path.closed && path.points[0] ? [...path.points, path.points[0]] : path.points;
  let metres = 0;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1] as Point;
    const b = points[i] as Point;
    const k = Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180);
    metres += Math.hypot((b.lon - a.lon) * 111_320 * k, (b.lat - a.lat) * 111_320);
  }
  return Math.round(metres);
}

function samePath(a: Path | null, b: Path): boolean {
  return (
    a !== null &&
    a.closed === b.closed &&
    a.points.length === b.points.length &&
    a.points.every((point, index) => same(point, b.points[index] as Point))
  );
}

/** The finding with these pending suggestions, each `behind` when made on an earlier revision than the shape's now. */
function withSuggestions(finding: FindingDetail, suggestions: ShapeSuggestion[]): FindingDetail {
  const revision = finding.location.shape.revision ?? 0;
  return {
    ...finding,
    location: {
      ...finding.location,
      shape: {
        ...finding.location.shape,
        suggestions: suggestions.map((entry) => ({ ...entry, behind: entry.base_revision < revision })),
      },
    },
  };
}

export async function fakeKeeping(page: Page, fake: FakeFindingPage, state: KeepingState): Promise<FakeKeeping> {
  const sent: Record<string, unknown[]> = {};
  let acceptRefusal: string | null = null;
  let limited = false;
  let nextId = 500;

  function record(route: Route, name: string): unknown {
    const body = route.request().postData() ? route.request().postDataJSON() : null;
    sent[name] = [...(sent[name] ?? []), body];
    return body;
  }

  /** The shape as stored, as a path the server would compare against. */
  function storedPath(finding: FindingDetail): Path | null {
    const path = finding.location.path;
    return path ? { closed: path.closed, curve: path.curve, points: path.points } : null;
  }

  await page.route(KEEPING_ROUTE, async (route) => {
    const match = KEEPING_ROUTE.exec(route.request().url());
    const finding = fake.current();
    if (decodeURIComponent(match?.[1] ?? "") !== finding.public_id) return route.fallback();
    const method = route.request().method();
    const [, , , sid, decision, keeping] = match ?? [];
    const pending = finding.location.shape.suggestions ?? [];
    const suggestion = pending.find((entry) => String(entry.id) === sid);
    const revision = finding.location.shape.revision ?? 0;

    if (method === "POST" && sid === undefined && keeping === undefined) {
      const body = record(route, "POST suggestions") as { path: Path; path_revision: number };
      if (limited) {
        limited = false;
        return refusal(route, 429, "rate_limited");
      }
      if (body.path_revision !== revision) return refusal(route, 409, "shape_changed");
      if (samePath(storedPath(finding), body.path)) return refusal(route, 422, "suggestion_unchanged");
      // One pending suggestion per person: a new one replaces theirs, and doesn't count against the cap.
      const others = pending.filter((entry) => entry.by.handle !== state.me.handle);
      if (others.length >= (state.maxPending ?? 20)) return refusal(route, 409, "too_many_suggestions");
      const made: ShapeSuggestion = {
        id: nextId++,
        by: state.me,
        created_at: new Date().toISOString(),
        base_revision: body.path_revision,
        behind: false,
        kind: classify(storedPath(finding), body.path),
        length_m: lengthOf(body.path),
        path: { closed: body.path.closed, curve: "catmull-rom-centripetal-1", points: body.path.points },
        outline: outlineOf(body.path),
        state: "pending",
        decided_at: null,
      };
      fake.set(withSuggestions(finding, [made, ...others]));
      return json(route, made, 201);
    }
    if (sid !== undefined && !suggestion) return refusal(route, 404, "suggestion_not_found");
    if (method === "DELETE" && suggestion && decision === undefined) {
      record(route, "DELETE suggestion");
      fake.set(
        withSuggestions(
          finding,
          pending.filter((entry) => entry !== suggestion),
        ),
      );
      return route.fulfill({ status: 204 });
    }
    if (method === "POST" && suggestion && decision === "accept") {
      const body = record(route, "POST accept") as { shape_revision: number };
      if (body.shape_revision !== revision) return refusal(route, 409, "shape_changed");
      if (acceptRefusal !== null) {
        const message = acceptRefusal;
        acceptRefusal = null;
        return refusal(route, 422, "looked_at_moved", message);
      }
      const changed: FindingDetail = {
        ...finding,
        location: {
          ...finding.location,
          path: suggestion.path,
          outline: suggestion.outline,
          shape: {
            ...finding.location.shape,
            revision: revision + 1,
            length_m: suggestion.length_m,
            changes: [
              ...finding.location.shape.changes,
              { kind: suggestion.kind, on: new Date().toISOString().slice(0, 10), suggested_by: suggestion.by },
            ],
          },
        },
      };
      const after = withSuggestions(
        changed,
        pending.filter((entry) => entry !== suggestion),
      );
      fake.set(after);
      return json(route, after);
    }
    if (method === "POST" && suggestion && decision === "decline") {
      record(route, "POST decline");
      fake.set(
        withSuggestions(
          finding,
          pending.filter((entry) => entry !== suggestion),
        ),
      );
      return json(route, { ...suggestion, state: "declined", decided_at: new Date().toISOString() });
    }
    if (method === "PUT" && keeping === "offer") {
      const body = record(route, "PUT offer") as { handle: string };
      const person = state.people?.[body.handle];
      // An unknown, deleted or banned handle answers alike.
      if (!person) return refusal(route, 404, "user_not_found");
      if (person.handle === finding.keeper.handle) return refusal(route, 422, "already_keeper");
      const offered = { ...finding, keeping: { offered_to: person, offered_at: new Date().toISOString() } };
      fake.set(offered);
      return json(route, offered);
    }
    if (method === "DELETE" && keeping === "offer") {
      record(route, "DELETE offer");
      fake.set({
        ...finding,
        keeping: null,
        actions: { ...finding.actions, take_keeping: { allowed: false, reason: "not_offered" } },
      });
      return route.fulfill({ status: 204 });
    }
    if (method === "POST" && keeping === "accept") {
      record(route, "POST take");
      const taken: FindingDetail = {
        ...finding,
        keeper: state.me,
        keeping: null,
        actions: {
          ...finding.actions,
          edit: { allowed: true, reason: null },
          hand_on: { allowed: true, reason: null },
          decide_suggestions: { allowed: true, reason: null },
          suggest: { allowed: false, reason: "own_marking" },
          take_keeping: { allowed: false, reason: "not_offered" },
        },
      };
      fake.set(taken);
      return json(route, taken);
    }
    return route.fallback();
  });

  await page.route(MOD_ROUTE, async (route) => {
    const match = MOD_ROUTE.exec(route.request().url());
    const method = route.request().method();
    if (match?.[1] === "markings/orphaned" && method === "GET") {
      return json(route, { items: state.orphaned ?? [], next_cursor: null });
    }
    const finding = fake.current();
    if (decodeURIComponent(match?.[2] ?? "") !== finding.public_id) return route.fallback();
    if (match?.[3] === "shapes" && method === "GET")
      return json(route, { items: state.earlier ?? [], next_cursor: null });
    if (match?.[3] === "marking" && method === "PUT") {
      const body = record(route, "PUT marking") as { to_revision: number | null; shape_revision: number };
      const revision = finding.location.shape.revision ?? 0;
      // In the order the route refuses.
      if (state.isOrphaned === false) return refusal(route, 409, "not_orphaned");
      if (body.shape_revision !== revision) return refusal(route, 409, "shape_changed");
      const earlier = state.earlier?.find((entry) => entry.revision - 1 === body.to_revision);
      if (body.to_revision !== null && !earlier) return refusal(route, 422, "no_such_revision");
      const restored = earlier?.path_before ?? null;
      const changed: FindingDetail = {
        ...finding,
        location: {
          ...finding.location,
          path: restored,
          outline: restored ? outlineOf(restored) : null,
          shape: {
            ...finding.location.shape,
            kind: restored ? (restored.closed ? "area" : "line") : null,
            revision: revision + 1,
            changes: [
              ...finding.location.shape.changes,
              {
                kind: restored ? classify(storedPath(finding), restored) : "removed",
                on: new Date().toISOString().slice(0, 10),
              },
            ],
          },
        },
      };
      fake.set(changed);
      return json(route, changed);
    }
    return route.fallback();
  });

  return {
    sent,
    refuseNextAccept: (message) => {
      acceptRefusal = message;
    },
    limitNext: () => {
      limited = true;
    },
    changeShapeElsewhere: () => {
      const finding = fake.current();
      const revision = (finding.location.shape.revision ?? 0) + 1;
      const moved: FindingDetail = {
        ...finding,
        location: { ...finding.location, shape: { ...finding.location.shape, revision } },
      };
      fake.set(withSuggestions(moved, finding.location.shape.suggestions ?? []));
    },
  };
}
