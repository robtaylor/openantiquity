import { describe, expect, it } from "vitest";
import { type KeptFailure, MAX_KEPT, MESSAGE_MAX } from "../../api/failures.js";
import shellSource from "../shell/Shell.tsx?raw";
import {
  ADDRESS_MAX,
  browserName,
  CUT_NOTE,
  emailUrl,
  githubIssueUrl,
  offersPosition,
  PAGE_PATTERNS,
  pagePattern,
  positionOf,
  type ReportFacts,
  reportText,
  reportTitle,
} from "./report.js";

const COMMIT = "0123456789abcdef0123456789abcdef01234567";

function facts(overrides: Partial<ReportFacts> = {}): ReportFacts {
  return {
    version: "0.1.0",
    commit: COMMIT,
    page: "/f/:id",
    layout: "desktop",
    browser: "Firefox 140",
    window: { width: 1280, height: 800 },
    map: { mainView: "composite", compareView: null, overlays: ["findings", "records"], threeD: false },
    signedIn: false,
    failures: [],
    ...overrides,
  };
}

const TWO_FAILURES: KeptFailure[] = [
  {
    kind: "request",
    at: "2026-11-14T10:21:03.412Z",
    method: "GET",
    path: "/findings/{public_id}/comments",
    status: 500,
    code: "internal_error",
    requestId: "0123456789abcdef",
  },
  { kind: "error", at: "2026-11-14T10:21:09.020Z", message: "Cannot read properties of undefined (reading 'tier')" },
];

describe("pagePattern", () => {
  it.each([
    ["/", "/"],
    ["/f/7K3QXM", "/f/:id"],
    ["/i/AB12CD", "/i/:id"],
    ["/u/RidgewayRob", "/u/:handle"],
    ["/mark/finding/7K3QXM", "/mark/finding/:publicId"],
    ["/mark/suggest/7K3QXM", "/mark/suggest/:publicId"],
    ["/mod/markings/7K3QXM", "/mod/markings/:publicId"],
    ["/mod/markings", "/mod/:section?"],
    ["/mark/draft-1", "/mark/:draftId?"],
    ["/mark", "/mark/:draftId?"],
    ["/about/privacy", "/about/:notice"],
    ["/signin/email", "/signin/email"],
    ["/somewhere/else", "another page"],
  ])("names %s as %s", (path, pattern) => {
    expect(pagePattern(path)).toBe(pattern);
  });

  it("knows every page the shell routes to", () => {
    // Each route's path is a string in the shell or one of the constants it imports.
    const constants: Record<string, string> = {
      REVIEW_PATH: "/review",
      HELP_PATH: "/help",
      "`${HELP_PATH}/:kind`": "/help/:kind",
      SCAN_PATH: "/scan",
      ACTIVITY_PATH: "/activity",
      PROFILE_ROUTE: "/u/:handle",
      MOD_ROUTE: "/mod/:section?",
      REMOVE_MARKING_ROUTE: "/mod/markings/:publicId",
      EMAIL_LINK_PATH: "/signin/email",
      RECORD_SEARCH_PATH: "/records",
      ELSEWHERE_PATH: "/elsewhere",
      PROFILE_PATH: "/profile",
      RECENT_MENTIONS_PATH: "/mentions",
      INVESTIGATIONS_PATH: "/investigations",
      GUIDE_PATH: "/guide",
      ABOUT_PATH: "/about",
      NOTICE_ROUTE: "/about/:notice",
    };
    const routes = [...shellSource.matchAll(/path=(?:"([^"]+)"|\{(`[^`]*`|[A-Z_]+)\})/g)]
      .map(([, literal, expression]) => literal ?? constants[expression ?? ""] ?? `unknown: ${expression}`)
      .filter((path) => path !== "*");
    expect(routes.length).toBeGreaterThan(20);
    expect([...routes].sort()).toEqual([...PAGE_PATTERNS].sort());
  });
});

describe("browserName", () => {
  it.each([
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 15.3; rv:140.0) Gecko/20100101 Firefox/140.0", "Firefox 140"],
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
      "Chrome 142",
    ],
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
      "Edge 142",
    ],
    [
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1",
      "Safari 18",
    ],
    ["curl/8.4.0", "an unknown browser"],
  ])("reads %s", (agent, name) => {
    expect(browserName(agent)).toBe(name);
  });
});

describe("reportText", () => {
  it("says the build, the page, the layout, the browser, the map, the sign-in and what failed", () => {
    const text = reportText(facts({ failures: TWO_FAILURES }), {
      description: "I pressed Save finding and nothing happened.",
      position: null,
    });
    expect(text).toBe(
      [
        "## What happened",
        "",
        "I pressed Save finding and nothing happened.",
        "",
        "## The page",
        "",
        `- Build: 0.1.0, commit ${COMMIT}`,
        "- Page: /f/:id",
        "- Layout: desktop",
        "- Browser: Firefox 140, window 1280 × 800",
        "- Map: composite; overlays shown: findings, records; 3D off",
        "- Signed in: no",
        "- Where the map was: not included",
        "",
        "## What went wrong lately",
        "",
        "- 2026-11-14T10:21:03Z GET /findings/{public_id}/comments: 500 internal_error, request 0123456789abcdef",
        "- 2026-11-14T10:21:09Z An error: `Cannot read properties of undefined (reading 'tier')`",
      ].join("\n"),
    );
  });

  it("gives where the map was only when it is chosen, as its square and whole zoom", () => {
    const position = positionOf(-1.8542, 51.4286, 14.6);
    expect(position).toEqual({ square: "SU 10 69", zoom: 15 });
    const text = reportText(facts(), { description: "", position });
    expect(text).toContain("- Where the map was: SU 10 69 at zoom 15");
    expect(text).not.toMatch(/\d\.\d{3,}/);
    expect(text).toContain("Not filled in.");
    expect(text).toContain("Nothing failed in this page.");
  });

  it("says what isn't known before the map and the session have started", () => {
    const text = reportText(facts({ commit: null, version: null, map: null, signedIn: null }), {
      description: "",
      position: null,
    });
    expect(text).toContain("- Build: version not known, commit not known");
    expect(text).toContain("- Map: not started");
    expect(text).toContain("- Signed in: not known");
  });
});

describe("reportTitle", () => {
  it("is the start of what the person wrote, or the kind of page", () => {
    expect(reportTitle(facts(), { description: "  The map went white\nafter I zoomed", position: null })).toBe(
      "The map went white",
    );
    expect(reportTitle(facts(), { description: "x".repeat(100), position: null })).toHaveLength(70);
    expect(reportTitle(facts(), { description: "", position: null })).toBe("A problem on /f/:id");
  });

  it("never cuts a character in two, so an address can be made from it", () => {
    const title = reportTitle(facts(), { description: "😀".repeat(36), position: null });
    expect(title).toBe("😀".repeat(36));
    const long = reportTitle(facts(), { description: "😀".repeat(80), position: null });
    expect(Array.from(long)).toHaveLength(70);
    expect(() => githubIssueUrl(long, "body")).not.toThrow();
    expect(() => encodeURIComponent(long)).not.toThrow();
  });
});

describe("githubIssueUrl", () => {
  it("fills in the title and body of a new issue", () => {
    const { url, cut } = githubIssueUrl("The map went white", "Body & more");
    expect(cut).toBe(false);
    const address = new URL(url);
    expect(`${address.origin}${address.pathname}`).toBe("https://github.com/robtaylor/openantiquity/issues/new");
    expect(address.searchParams.get("title")).toBe("The map went white");
    expect(address.searchParams.get("body")).toBe("Body & more");
  });

  it("stays under GitHub's limit whole with the most failures the browser keeps", () => {
    const longest: KeptFailure[] = Array.from({ length: MAX_KEPT }, (_, index) =>
      index % 2
        ? { kind: "error", at: "2026-11-14T10:21:09.020Z", message: "é".repeat(MESSAGE_MAX) }
        : {
            kind: "request",
            at: "2026-11-14T10:21:03.412Z",
            method: "DELETE",
            path: "/investigations/{public_id}/members/{handle}",
            status: 503,
            code: "service_unavailable",
            requestId: "0123456789abcdef",
          },
    );
    const plain: KeptFailure[] = longest.map((failure) =>
      failure.kind === "error" ? { ...failure, message: "x".repeat(MESSAGE_MAX) } : failure,
    );
    const body = reportText(facts({ failures: plain }), { description: "A short note.", position: null });
    const { url, cut } = githubIssueUrl("The map went white", body);
    expect(cut).toBe(false);
    expect(url.length).toBeLessThan(ADDRESS_MAX);
  });

  it("cuts a body too long for the address, says so, and stays under the limit", () => {
    const body = `${"Long words, and ünïcödé 🙂 too. ".repeat(400)}`;
    const { url, cut } = githubIssueUrl("Long", body);
    expect(cut).toBe(true);
    expect(url.length).toBeLessThan(ADDRESS_MAX);
    const sent = new URL(url).searchParams.get("body") ?? "";
    expect(sent.endsWith(CUT_NOTE)).toBe(true);
    expect(body.startsWith(sent.slice(0, -CUT_NOTE.length))).toBe(true);
    expect(url.length).toBeGreaterThan(ADDRESS_MAX - 20);
  });
});

describe("positionOf and offersPosition", () => {
  it("gives no square off both national grids", () => {
    expect(positionOf(2.35, 48.85, 12)).toBeNull();
    expect(positionOf(-6.26, 53.35, 12)?.square).toMatch(/^O \d\d \d\d$/);
  });

  it.each([
    "/f/:id",
    "/review",
    "/mark/:draftId?",
    "/mark/finding/:publicId",
    "/mark/suggest/:publicId",
    "/i/:id",
    "/scan",
    "/mod/:section?",
    "/mod/markings/:publicId",
    "/_ui",
    "another page",
  ])("isn't offered on %s", (page) => {
    expect(offersPosition(page)).toBe(false);
  });

  it.each(["/", "/about", "/r/:id", "/investigations", "/u/:handle"])("is offered on %s", (page) => {
    expect(offersPosition(page)).toBe(true);
  });

  it("is offered only on pages the shell knows", () => {
    for (const page of ["/", "/about", "/r/:id"]) expect(PAGE_PATTERNS).toContain(page);
  });
});

describe("emailUrl", () => {
  it("cuts a body too long for the address, as the issue's is", () => {
    const { url, cut } = emailUrl("reports@openantiquity.example", "Long", "éèêë àâôö ".repeat(400));
    expect(cut).toBe(true);
    expect(url.length).toBeLessThan(ADDRESS_MAX);
    expect(new URLSearchParams(url.split("?")[1]).get("body")?.endsWith(CUT_NOTE)).toBe(true);
  });

  it("encodes the address, so it can't add a recipient or a header", () => {
    const { url } = emailUrl("help@x.example?bcc=other%40y.example", "T", "B");
    expect(url.startsWith("mailto:help@x.example%3Fbcc%3Dother%2540y.example?subject=")).toBe(true);
  });

  it("writes the same title and text to the address", () => {
    const { url, cut } = emailUrl("reports@openantiquity.example", "The map went white", "Line one\nLine two");
    expect(cut).toBe(false);
    expect(url.startsWith("mailto:reports@openantiquity.example?")).toBe(true);
    const query = new URLSearchParams(url.split("?")[1]);
    expect(query.get("subject")).toBe("The map went white");
    expect(query.get("body")).toBe("Line one\nLine two");
  });
});
