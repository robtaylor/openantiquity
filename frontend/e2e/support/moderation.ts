import type { Page, Route } from "@playwright/test";
import type { Action, Eligible, Report } from "../../src/features/moderation/api.js";
import type { Profile } from "../../src/features/people/api.js";
import type { QueuedMedia } from "../../src/features/photos/api.js";

/**
 * Stand-ins, in fixture mode, for people's pages, reports and everything
 * under `/mod`: the report queue, hiding and showing again, the photo queue,
 * the members who could be trusted, roles, bans and the log. Every write is
 * kept in `sent`, by route, such as "POST /reports" or "POST /mod/comments/501/hide".
 */
export interface FakeModeration {
  sent: Record<string, unknown[]>;
}

export interface ModerationState {
  reports?: Report[];
  photos?: QueuedMedia[];
  eligible?: Eligible[];
  actions?: Action[];
  /** People's pages by handle, with their lists. */
  people?: Record<string, { profile: Profile; findings?: unknown[]; helped?: unknown[]; points?: unknown[] }>;
}

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

const page = (items: unknown[]) => ({ items, next_cursor: null });

export async function fakeModeration(browserPage: Page, state: ModerationState = {}): Promise<FakeModeration> {
  const sent: Record<string, unknown[]> = {};
  let reports = [...(state.reports ?? [])];
  let photos = [...(state.photos ?? [])];
  let eligible = [...(state.eligible ?? [])];
  const actions = [...(state.actions ?? [])];

  function record(route: Route, name: string): void {
    const body = route.request().postData() ? route.request().postDataJSON() : null;
    sent[name] = [...(sent[name] ?? []), body];
  }

  await browserPage.route(
    /^https?:\/\/localhost(?::\d+)?\/api\/v1\/(mod|reports|users)(\/[^?#]*)?(?:\?|$)/,
    (route) => {
      const url = new URL(route.request().url());
      const method = route.request().method();
      const path = url.pathname.replace(/^\/api\/v1/, "");
      const name = `${method} ${path}`;

      if (name === "POST /reports") {
        record(route, name);
        const body = route.request().postDataJSON() as { target_kind: string; target_id: string; reason: string };
        return json(route, { id: 900, ...body, created_at: new Date().toISOString() }, 201);
      }
      if (name === "GET /mod/reports") {
        const reason = url.searchParams.get("reason");
        return json(route, page(reports.filter((report) => reason === null || report.reason === reason)));
      }
      let match = /^\/mod\/reports\/(\d+)\/resolve$/.exec(path);
      if (match && method === "POST") {
        record(route, name);
        const report = reports.find((entry) => String(entry.id) === match?.[1]);
        reports = reports.filter((entry) => entry.target.id !== report?.target.id);
        return json(route, { report, resolved: 1 });
      }
      match = /^\/mod\/([a-z]+)\/([^/]+)\/(hide|unhide)$/.exec(path);
      if (match && method === "POST") {
        record(route, name);
        const hidden = match[3] === "hide";
        return json(route, {
          target_kind: match[1],
          target_id: decodeURIComponent(match[2] ?? ""),
          hidden,
          hidden_at: hidden ? new Date().toISOString() : null,
        });
      }
      if (name === "GET /mod/media") return json(route, page(photos));
      match = /^\/mod\/media\/(\d+)\/(approve|reject)$/.exec(path);
      if (match && method === "POST") {
        record(route, name);
        const photo = photos.find((entry) => String(entry.id) === match?.[1]);
        photos = photos.filter((entry) => entry !== photo);
        return json(route, { ...photo, approved: match[2] === "approve", rejected: match[2] === "reject" });
      }
      if (name === "GET /mod/users/eligible") return json(route, page(eligible));
      match = /^\/mod\/users\/([^/]+)\/role$/.exec(path);
      if (match && method === "PUT") {
        record(route, name);
        const handle = decodeURIComponent(match[1] ?? "");
        const member = eligible.find((entry) => entry.user.handle === handle);
        eligible = eligible.filter((entry) => entry !== member);
        const role = (route.request().postDataJSON() as { role: string }).role;
        return json(route, { ...member?.user, role });
      }
      match = /^\/mod\/users\/([^/]+)\/(ban|unban)$/.exec(path);
      if (match && method === "POST") {
        record(route, name);
        return json(route, { user: {}, sessions_ended: 1, findings_reassessed: 0 });
      }
      if (name === "GET /mod/actions") {
        const kind = url.searchParams.get("target_kind");
        const ref = url.searchParams.get("target_id");
        return json(
          route,
          page(actions.filter((entry) => kind === null || (entry.target.kind === kind && entry.target.ref === ref))),
        );
      }

      match = /^\/users\/([^/]+)(\/[a-z]+)?$/.exec(path);
      if (match && method === "GET") {
        const person = state.people?.[decodeURIComponent(match[1] ?? "")];
        if (!person) return json(route, { error: { code: "user_not_found", message: "Nobody by that handle." } }, 404);
        switch (match[2]) {
          case undefined:
            return json(route, person.profile);
          case "/findings":
            return json(route, page(person.findings ?? []));
          case "/contributions":
            return json(route, page(url.searchParams.get("kind") === "second_look" ? [] : (person.helped ?? [])));
          case "/points":
            return json(route, page(person.points ?? []));
        }
      }
      return route.fallback();
    },
  );
  return { sent };
}
