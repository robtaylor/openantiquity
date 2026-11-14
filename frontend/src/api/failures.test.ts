import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fakeUploads } from "../test/fakeUpload.js";
import { json } from "../test/http.js";
import { ApiError, apiFetch, apiUpload } from "./client.js";
import {
  forgetFailures,
  keepError,
  keptFailures,
  MAX_KEPT,
  MESSAGE_MAX,
  pathPattern,
  watchUncaughtErrors,
} from "./failures.js";
import { API_PATHS } from "./paths.js";
import schemaText from "./schema.d.ts?raw";

const REQUEST_ID = "0123456789abcdef";

function answer(response: Response) {
  const mock = vi.fn(async (_url: string, _init?: RequestInit) => response);
  vi.stubGlobal("fetch", mock);
  return mock;
}

beforeEach(() => forgetFailures());
afterEach(() => {
  vi.unstubAllGlobals();
  forgetFailures();
});

describe("pathPattern", () => {
  it.each([
    ["/findings/7K3QXM/observation", "/findings/{public_id}/observation"],
    ["/findings/7K3QXM", "/findings/{public_id}"],
    ["/users/RidgewayRob/points", "/users/{handle}/points"],
    ["/evidence/42/vote", "/evidence/{evidence_id}/vote"],
    ["/investigations/AB12CD/items/7/move", "/investigations/{public_id}/items/{item_id}/move"],
    ["/squares/SU1367", "/squares/{ref}"],
    ["/mentions/recent", "/mentions/recent"],
    ["/findings/export", "/findings/export"],
    ["/findings?bbox=-1.85,51.42,-1.84,51.43", "/findings"],
    ["/findings/7K3QXM#where", "/findings/{public_id}"],
  ])("writes %s as %s", (path, pattern) => {
    expect(pathPattern(path)).toBe(pattern);
  });

  it("keeps only the API's own words of a path it doesn't know", () => {
    expect(pathPattern("/findings/7K3QXM/nothing/51.4286")).toBe("/findings/{…}/{…}/{…}");
    expect(pathPattern("/RidgewayRob")).toBe("/{…}");
  });

  it("knows every path the backend serves", () => {
    const fromSchema = [...schemaText.matchAll(/^ {4}"\/api\/v1(\/[^"]*)": \{$/gm)].map((match) => match[1]);
    expect(fromSchema.length).toBeGreaterThan(50);
    expect([...API_PATHS]).toEqual(fromSchema.sort());
  });
});

describe("a failed request", () => {
  it("is kept by when, method, path pattern, status, code and request id, and nothing else", async () => {
    answer(
      json(
        {
          error: {
            code: "internal_error",
            message: "Something went wrong near SU 1310 6707.",
            details: { secret: "the body's own words" },
            request_id: REQUEST_ID,
          },
        },
        500,
      ),
    );
    await expect(
      apiFetch("/findings/7K3QXM/comments", {
        method: "POST",
        query: { bbox: "-1.85,51.42,-1.84,51.43" },
        body: { body: "A comment that names Avebury" },
      }),
    ).rejects.toBeInstanceOf(ApiError);

    const kept = keptFailures();
    expect(kept).toHaveLength(1);
    const [failure] = kept;
    expect(failure).toEqual({
      kind: "request",
      at: expect.stringMatching(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/),
      method: "POST",
      path: "/findings/{public_id}/comments",
      status: 500,
      code: "internal_error",
      requestId: REQUEST_ID,
    });
    const text = JSON.stringify(kept);
    for (const leak of ["7K3QXM", "bbox", "51.42", "Avebury", "SU 1310", "the body's own words", "went wrong"]) {
      expect(text).not.toContain(leak);
    }
  });

  it("takes the request id from the header when the body has none", async () => {
    answer(new Response("Bad gateway", { status: 502, headers: { "X-Request-ID": REQUEST_ID } }));
    await expect(apiFetch("/meta")).rejects.toMatchObject({ status: 502, requestId: REQUEST_ID });
    expect(keptFailures()[0]).toMatchObject({ path: "/meta", status: 502, code: "http_502", requestId: REQUEST_ID });
  });

  it("is kept when no answer came, with status 0 and no request id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    await expect(apiFetch("/meta")).rejects.toMatchObject({ code: "network_error" });
    expect(keptFailures()[0]).toMatchObject({ status: 0, code: "network_error", requestId: null });
  });

  it("isn't kept when it was stopped on purpose", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new DOMException("The user aborted a request.", "AbortError");
      }),
    );
    await expect(apiFetch("/meta")).rejects.toMatchObject({ name: "AbortError" });
    expect(keptFailures()).toEqual([]);
  });

  it("is kept from an upload too", async () => {
    const uploads = fakeUploads();
    uploads.respond(() => ({ status: 413, body: { error: { code: "request_too_large", message: "Too big." } } }));
    await expect(apiUpload("/media", new Blob(["x"]))).rejects.toMatchObject({ status: 413 });
    expect(keptFailures()).toEqual([expect.objectContaining({ method: "POST", path: "/media", status: 413 })]);
  });

  it("isn't kept when its caller expected that answer", async () => {
    answer(json({ error: { code: "unauthorised", message: "Sign in." } }, 401));
    await expect(apiFetch("/auth/me", { expected: [401] })).rejects.toMatchObject({ status: 401 });
    expect(keptFailures()).toEqual([]);
  });

  it("isn't kept when it is stopped while its answer is read", async () => {
    const controller = new AbortController();
    const response = json({ ok: true });
    vi.spyOn(response, "json").mockImplementation(async () => {
      controller.abort();
      throw new DOMException("The user aborted a request.", "AbortError");
    });
    answer(response);
    // What the caller is thrown is as it was.
    await expect(apiFetch("/meta", { signal: controller.signal })).rejects.toMatchObject({ code: "bad_response" });
    expect(keptFailures()).toEqual([]);
  });

  it("isn't kept when it worked", async () => {
    answer(json({ ok: true }));
    await apiFetch("/meta");
    expect(keptFailures()).toEqual([]);
  });
});

describe("the kept failures", () => {
  it(`hold at most ${MAX_KEPT}, dropping the oldest first`, () => {
    for (let index = 1; index <= MAX_KEPT + 3; index += 1) keepError(`Failure ${"x".repeat(index)}`);
    const kept = keptFailures();
    expect(kept).toHaveLength(MAX_KEPT);
    expect(kept[0]).toMatchObject({ message: `Failure ${"x".repeat(4)}` });
    expect(kept.at(-1)).toMatchObject({ message: `Failure ${"x".repeat(MAX_KEPT + 3)}` });
  });

  it("are a copy, so what is read can't change what is kept", () => {
    keepError("Once");
    const kept = keptFailures() as unknown[];
    kept.length = 0;
    expect(keptFailures()).toHaveLength(1);
  });
});

describe("an uncaught error", () => {
  it("is kept by when and its message, with nothing that holds a figure, cut short", () => {
    const stop = watchUncaughtErrors(window);
    try {
      const error = new Error("Couldn't draw /tiles/lidar/composite/15/16300/10900.png at 51.4286,-1.8542");
      window.dispatchEvent(new ErrorEvent("error", { message: `Uncaught Error: ${error.message}`, error }));
      window.dispatchEvent(new ErrorEvent("error", { message: "y".repeat(MESSAGE_MAX * 2) }));
    } finally {
      stop();
    }
    const [first, second] = keptFailures();
    expect(first).toEqual({
      kind: "error",
      at: expect.any(String),
      message: "Uncaught Error: Couldn't draw # at #",
    });
    expect(second?.kind === "error" && second.message.length).toBe(MESSAGE_MAX);
    expect(JSON.stringify(keptFailures())).not.toContain("at Object.");
  });

  it("loses any address and anything shaped like a public id", () => {
    keepError("No finding KQXMBW at /f/KQXMBW or https://openantiquity.org/f/KQXMBW, for RIDGE");
    expect(keptFailures()[0]).toMatchObject({ message: "No finding # at # or # for RIDGE" });
  });

  it("keeps no line breaks, ids beside other characters, @ or quoted input", () => {
    keepError("Bad\n\n## Forged heading\n- [x] done");
    keepError("No finding x_KQXMBW-there");
    keepError("Ping @robtaylor please");
    keepError('Unexpected token in JSON at "Low mound by the oak"');
    const messages = keptFailures().map((failure) => failure.kind === "error" && failure.message);
    expect(messages).toEqual([
      "Bad ## Forged heading - [x] done",
      "No finding x_#-there",
      "Ping robtaylor please",
      "Unexpected token in JSON at #",
    ]);
  });

  it("is cut by characters, so a message of emoji keeps none in halves", () => {
    keepError("😀".repeat(MESSAGE_MAX * 2));
    const [kept] = keptFailures();
    const message = kept?.kind === "error" ? kept.message : "";
    expect(Array.from(message)).toHaveLength(MESSAGE_MAX);
    expect(() => encodeURIComponent(message)).not.toThrow();
  });

  it("is kept from an unhandled rejection, but not twice for a failed request", () => {
    const stop = watchUncaughtErrors(window);
    try {
      const rejected = (reason: unknown) => {
        const event = new Event("unhandledrejection") as Event & { reason: unknown };
        event.reason = reason;
        window.dispatchEvent(event);
      };
      rejected(new Error("The worker stopped"));
      rejected("a plain string");
      rejected(new ApiError(500, "internal_error", "Something went wrong."));
    } finally {
      stop();
    }
    expect(keptFailures().map((failure) => failure.kind === "error" && failure.message)).toEqual([
      "The worker stopped",
      "a plain string",
    ]);
  });

  it("is no longer watched once watching stops", () => {
    watchUncaughtErrors(window)();
    window.dispatchEvent(new ErrorEvent("error", { message: "Late" }));
    expect(keptFailures()).toEqual([]);
  });
});
