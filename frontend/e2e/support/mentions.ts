import type { Page, Route } from "@playwright/test";
import type { FindingDetail } from "../../src/features/finding/types.js";
import type { Mention, MentionIn, MentionPreview, RecentMention } from "../../src/features/mentions/types.js";
import { previewFixture } from "../../src/test/fixtures/mentions.js";
import { apiRoute, FINDING_PAGE_ROUTE } from "./network.js";
import { solidPng } from "./png.js";

/**
 * A stand-in for the mention routes in fixture mode: one finding's mentions,
 * the preview, removing one, and the recent feed, which lists every mention
 * the fake holds with its finding. Video pictures come from a stubbed image
 * host, so no request leaves the test.
 */
export interface FakeMentions {
  /** The body of every write, by route: "POST preview", "POST mention", "DELETE mention". */
  sent: Record<string, unknown[]>;
  /** What the next preview finds. By default the YouTube video of `previewFixture`. */
  previewWith: (preview: Partial<MentionPreview>) => void;
  /** Refuse the next write to this route with this error code. */
  failNext: (route: string, status: number, code: string, message: string) => void;
}

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

const PICTURE = solidPng(480, 360, [96, 112, 92]);

export async function fakeMentions(
  page: Page,
  finding: FindingDetail,
  options: { mentions?: Mention[]; me?: { handle: string; display_name: string } } = {},
): Promise<FakeMentions> {
  let mentions = [...(options.mentions ?? [])];
  let nextId = 5000;
  let preview: Partial<MentionPreview> = {};
  const failures = new Map<string, { status: number; code: string; message: string }>();
  const fake: FakeMentions = {
    sent: {},
    previewWith: (next) => {
      preview = next;
    },
    failNext: (route, status, code, message) => failures.set(route, { status, code, message }),
  };

  /** Record a write, and answer with its failure if one is queued. */
  async function write(route: Route, name: string): Promise<boolean> {
    const request = route.request();
    fake.sent[name] = [...(fake.sent[name] ?? []), request.postData() ? request.postDataJSON() : null];
    const failure = failures.get(name);
    if (!failure) return true;
    failures.delete(name);
    await json(route, { error: { code: failure.code, message: failure.message } }, failure.status);
    return false;
  }

  function recent(mention: Mention): RecentMention {
    const { location } = finding;
    return {
      ...mention,
      finding: {
        public_id: finding.public_id,
        title: finding.title,
        feature_class: finding.feature_class,
        tier: finding.tier,
        state: finding.state,
        location,
        author: finding.author,
      },
    };
  }

  await page.route("https://i.ytimg.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: PICTURE }),
  );

  await page.route(FINDING_PAGE_ROUTE, async (route) => {
    const request = route.request();
    const match = FINDING_PAGE_ROUTE.exec(request.url());
    if (decodeURIComponent(match?.[1] ?? "") !== finding.public_id || match?.[2] !== "/mentions") {
      return route.fallback();
    }
    if (request.method() === "GET") return json(route, { items: mentions, next_cursor: null });
    if (request.method() !== "POST" || !(await write(route, "POST mention"))) return;
    const body = request.postDataJSON() as MentionIn;
    const found = previewFixture(preview);
    const saved: Mention = {
      id: nextId++,
      kind: body.kind ?? found.kind,
      url: body.url,
      canonical_url: found.canonical_url,
      provider: found.provider,
      title: found.title,
      author_name: found.author_name,
      thumbnail_url: found.thumbnail_url,
      published_at: found.published_at,
      start_seconds: body.start_seconds ?? null,
      note: body.note ?? null,
      auto_detected: false,
      added_by: {
        handle: options.me?.handle ?? "KeenLynchet7",
        display_name: options.me?.display_name ?? "Mary Anning",
        role: "member",
      },
      created_at: new Date().toISOString(),
      hidden: false,
    };
    mentions = [saved, ...mentions];
    return json(route, saved, 201);
  });

  await page.route(apiRoute("/mentions/preview"), async (route) => {
    if (!(await write(route, "POST preview"))) return;
    const { url } = route.request().postDataJSON() as { url: string };
    return json(route, previewFixture({ url, ...preview }));
  });

  await page.route(/^https?:\/\/localhost(?::\d+)?\/api\/v1\/mentions\/(\d+)$/, async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    if (!(await write(route, "DELETE mention"))) return;
    const id = Number(/\/mentions\/(\d+)$/.exec(route.request().url())?.[1]);
    mentions = mentions.filter((mention) => mention.id !== id);
    return route.fulfill({ status: 204 });
  });

  await page.route(apiRoute("/mentions/recent"), (route) =>
    json(route, { items: mentions.map(recent), next_cursor: null }),
  );

  return fake;
}
