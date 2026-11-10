import { afterEach, describe, expect, it, vi } from "vitest";
import { json } from "../test/http.js";
import { ApiError, apiFetch, apiUrl } from "./client.js";

function stubFetch(outcome: Response | { throws: unknown }) {
  const mock = vi.fn(async (_url: string, _init?: RequestInit) => {
    if (outcome instanceof Response) return outcome;
    throw outcome.throws;
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("sends credentials and returns the JSON body", async () => {
    const mock = stubFetch(json({ ok: true }, 200));
    await expect(apiFetch<{ ok: boolean }>("/meta")).resolves.toEqual({ ok: true });
    const [url, init] = mock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/meta");
    expect(init?.credentials).toBe("include");
    expect(init?.method).toBe("GET");
  });

  it("leaves the client header off reads", async () => {
    const mock = stubFetch(json({}, 200));
    await apiFetch("/findings", { query: { bbox: "1,2,3,4", limit: 20, cursor: undefined, q: null } });
    const [url, init] = mock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/findings?bbox=1%2C2%2C3%2C4&limit=20");
    expect(new Headers(init?.headers).has("X-FieldClub-Client")).toBe(false);
  });

  it.each(["POST", "PUT", "PATCH", "DELETE"] as const)("sends X-FieldClub-Client on %s", async (method) => {
    const mock = stubFetch(json({}, 200));
    await apiFetch("/findings/abc/observation", { method, body: { visible: "yes" } });
    const init = mock.mock.calls[0]?.[1];
    const headers = new Headers(init?.headers);
    expect(headers.get("X-FieldClub-Client")).toBe("web");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init?.body).toBe('{"visible":"yes"}');
    expect(init?.credentials).toBe("include");
  });

  it("throws a typed error from the error envelope", async () => {
    stubFetch(json({ error: { code: "not_found", message: "No finding with that id." } }, 404));
    const error = await apiFetch("/findings/nope").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: "not_found", message: "No finding with that id." });
  });

  it("copes with an error that has no envelope", async () => {
    stubFetch(new Response("<html>Bad gateway</html>", { status: 502, statusText: "Bad Gateway" }));
    const error = await apiFetch("/meta").catch((e: unknown) => e);
    expect(error).toMatchObject({
      status: 502,
      code: "http_502",
      message: "The server isn't answering right now (502 Bad Gateway). It may be restarting.",
    });
  });

  it("reports other statuses plainly", async () => {
    stubFetch(new Response("teapot", { status: 418, statusText: "I'm a teapot" }));
    const error = await apiFetch("/meta").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 418, code: "http_418", message: "The server answered 418 I'm a teapot." });
  });

  it("turns a network failure into an ApiError", async () => {
    stubFetch({ throws: new TypeError("Failed to fetch") });
    const error = await apiFetch("/meta").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, code: "network_error" });
  });

  it("lets an abort through untouched", async () => {
    const abort = new DOMException("Aborted", "AbortError");
    stubFetch({ throws: abort });
    const error = await apiFetch("/meta").catch((e: unknown) => e);
    expect(error).toBe(abort);
  });

  it("returns undefined for 204", async () => {
    stubFetch(new Response(null, { status: 204 }));
    await expect(apiFetch("/findings/abc/follow", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("reports a success that isn't JSON", async () => {
    stubFetch(new Response("<html></html>", { status: 200 }));
    const error = await apiFetch("/meta").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 200, code: "bad_response" });
  });
});

describe("apiUrl", () => {
  it("requires a leading slash", () => {
    expect(() => apiUrl("meta")).toThrow(ApiError);
    expect(apiUrl("/meta")).toBe("/api/v1/meta");
  });
});
