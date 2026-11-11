import type { Page, Route } from "@playwright/test";
import type {
  Comment,
  Evidence,
  EvidenceIn,
  FindingDetail,
  Observation,
  ObservationIn,
  Reveal,
} from "../../src/features/finding/types.js";
import { observationFixture, revealFixture, suggestionsFixture } from "../../src/test/fixtures/findingPage.js";
import { FINDING_PAGE_ROUTE } from "./network.js";

/**
 * A stand-in for one finding's page and everything on it, in fixture mode:
 * the finding, its discussion, the answers, the suggested records, and the
 * writes the page makes. A test can make the next write of a kind fail, or
 * hold it to see what the page shows meanwhile.
 */
export interface FakeFindingPage {
  /** The finding as the page is served it now. Change it with `set`. */
  current: () => FindingDetail;
  set: (finding: FindingDetail) => void;
  /** The body of every write, by route, such as "PUT observation" or "POST comments". */
  sent: Record<string, unknown[]>;
  /** Every part of the page asked for, such as "observations", in order. */
  asked: string[];
  /** Refuse the next write to this route with this error. */
  failNext: (route: string, status: number, message: string) => void;
  /** Hold each write to this route until the returned function is called. */
  hold: (route: string) => () => void;
  /** What answering reveals. By default: the finding with answers visible, two others who can see it. */
  onAnswer: (reveal: (answer: ObservationIn, finding: FindingDetail) => Reveal) => void;
}

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

const EVIDENCE_ROUTE = /^https?:\/\/localhost(?::\d+)?\/api\/v1\/(evidence|comments)\/(\d+)(\/[a-z]+)?(?:\?|$)/;

export async function fakeFindingPage(
  page: Page,
  initial: FindingDetail,
  options: { comments?: Comment[]; me?: { handle: string; display_name: string } } = {},
): Promise<FakeFindingPage> {
  let finding = initial;
  let comments = [...(options.comments ?? [])];
  let nextId = 1000;
  const failures = new Map<string, { status: number; message: string }>();
  const holds = new Map<string, Promise<void>>();
  let reveal = (answer: ObservationIn, before: FindingDetail): Reveal => {
    const given: Observation = observationFixture({
      user: {
        handle: options.me?.handle ?? "KeenLynchet7",
        display_name: options.me?.display_name ?? "Mary Anning",
        role: "member",
      },
      visible: answer.visible,
      feature_class: answer.feature_class ?? null,
      explanation: answer.explanation ?? null,
      not_modern: answer.not_modern ?? null,
      not_natural: answer.not_natural ?? null,
      not_artefact: answer.not_artefact ?? null,
      note: answer.note ?? null,
    });
    return revealFixture(given, before);
  };
  const fake: FakeFindingPage = {
    current: () => finding,
    set: (next) => {
      finding = next;
    },
    sent: {},
    asked: [],
    failNext: (route, status, message) => failures.set(route, { status, message }),
    hold: (route) => {
      let release = (): void => {};
      holds.set(
        route,
        new Promise<void>((resolve) => {
          release = resolve;
        }),
      );
      return () => release();
    },
    onAnswer: (next) => {
      reveal = next;
    },
  };

  /** Record a write, wait if it is held, and answer with its failure if one is queued. */
  async function write(route: Route, name: string): Promise<boolean> {
    const body = route.request().postData() ? route.request().postDataJSON() : null;
    fake.sent[name] = [...(fake.sent[name] ?? []), body];
    const held = holds.get(name);
    if (held) await held;
    const failure = failures.get(name);
    if (!failure) return true;
    failures.delete(name);
    await json(route, { error: { code: "refused", message: failure.message } }, failure.status);
    return false;
  }

  await page.route(FINDING_PAGE_ROUTE, async (route) => {
    const request = route.request();
    const match = FINDING_PAGE_ROUTE.exec(request.url());
    if (decodeURIComponent(match?.[1] ?? "") !== finding.public_id) return route.fallback();
    const part = match?.[2]?.slice(1) ?? "";
    const method = request.method();
    if (method === "GET") fake.asked.push(part || "finding");
    if (method === "GET" && part === "") return json(route, finding);
    if (method === "GET" && part === "comments") return json(route, { items: comments, next_cursor: null });
    if (method === "GET" && part === "observations") {
      if (!finding.answers_visible)
        return json(route, { error: { code: "answer_first", message: "Answer first." } }, 403);
      return json(route, { items: finding.my_observation ? [finding.my_observation] : [], next_cursor: null });
    }
    if (method === "GET" && part === "suggested-records") return json(route, suggestionsFixture());
    if (method === "POST" && part === "comments") {
      if (!(await write(route, "POST comments"))) return;
      const body = request.postDataJSON() as { body: string; parent_id?: number };
      const comment: Comment = {
        id: nextId++,
        parent_id: body.parent_id ?? null,
        author: {
          handle: options.me?.handle ?? "KeenLynchet7",
          display_name: options.me?.display_name ?? "Mary Anning",
          role: "member",
        },
        body: body.body,
        created_at: new Date().toISOString(),
        edited_at: null,
        deleted: false,
        hidden: false,
      };
      comments = [...comments, comment];
      return json(route, comment, 201);
    }
    if ((method === "PUT" || method === "DELETE") && part === "follow") {
      if (!(await write(route, `${method} follow`))) return;
      finding = { ...finding, following: method === "PUT" };
      return json(route, { following: finding.following });
    }
    if (method === "PUT" && part === "observation") {
      if (!(await write(route, "PUT observation"))) return;
      const answered = reveal(request.postDataJSON() as ObservationIn, finding);
      finding = answered.finding;
      return json(route, answered);
    }
    if (method === "POST" && part === "evidence") {
      if (!(await write(route, "POST evidence"))) return;
      const body = request.postDataJSON() as EvidenceIn;
      const item: Evidence = {
        id: nextId++,
        kind: body.kind,
        stance: body.stance ?? "supports",
        title: body.title ?? null,
        note: body.note ?? null,
        url: body.url ?? null,
        record_id: body.record_id ?? null,
        source_key: body.source_key ?? null,
        reference: body.reference ?? null,
        relation: body.relation ?? null,
        media_id: body.media_id ?? null,
        view: body.view ?? null,
        occurred_on: body.occurred_on ?? null,
        organisation: body.organisation ?? null,
        outcome: body.outcome ?? null,
        contributor: {
          handle: options.me?.handle ?? "KeenLynchet7",
          display_name: options.me?.display_name ?? "Mary Anning",
          role: "member",
        },
        created_at: new Date().toISOString(),
        verified_by: null,
        vote_total: 0,
        standing: true,
        independent: true,
        my_vote: null,
        redacted: false,
        endorsements: 0,
        disputes: 0,
        // The contributor can't vote on or verify their own item.
        actions: {
          vote: { allowed: false, reason: "vote_not_allowed" },
          verify: { allowed: false, reason: "own_evidence" },
        },
      };
      finding = { ...finding, evidence: [...finding.evidence, item] };
      return json(route, finding, 201);
    }
    return route.fallback();
  });

  await page.route(EVIDENCE_ROUTE, async (route) => {
    const match = EVIDENCE_ROUTE.exec(route.request().url());
    const [, what, id, part] = match ?? [];
    if (what === "evidence" && part === "/vote") {
      if (!(await write(route, "PUT vote"))) return;
      const value = (route.request().postDataJSON() as { value: number }).value;
      finding = {
        ...finding,
        evidence: finding.evidence.map((item) =>
          String(item.id) === id
            ? {
                ...item,
                my_vote: value === 0 ? null : value,
                vote_total: item.vote_total - (item.my_vote ?? 0) + value,
              }
            : item,
        ),
      };
      return json(route, { evidence_id: Number(id), value });
    }
    if (what === "comments" && route.request().method() === "DELETE") {
      if (!(await write(route, "DELETE comment"))) return;
      comments = comments.map((comment) =>
        String(comment.id) === id ? { ...comment, deleted: true, body: null, author: null } : comment,
      );
      return route.fulfill({ status: 204 });
    }
    return route.fallback();
  });

  return fake;
}
