import { afterEach, describe, expect, it, vi } from "vitest";
import { json } from "../test/http.js";
import { ApiError, apiFetch, apiUrl, onUnauthorised } from "./client.js";

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

  it("sends a file as it is, with its own type, and the client header", async () => {
    const mock = stubFetch(json({ id: 1 }, 201));
    const photo = new Blob(["jpeg bytes"], { type: "image/jpeg" });
    await apiFetch("/media", { method: "POST", file: photo });
    const init = mock.mock.calls[0]?.[1];
    const headers = new Headers(init?.headers);
    expect(init?.body).toBe(photo);
    expect(headers.get("Content-Type")).toBe("image/jpeg");
    expect(headers.get("X-FieldClub-Client")).toBe("web");
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

  it("sends a list as one parameter per item, and leaves out empty values", () => {
    expect(apiUrl("/findings", { tier: ["seen", "probable"], state: [], q: null, limit: 5 })).toBe(
      "/api/v1/findings?tier=seen&tier=probable&limit=5",
    );
  });
});

describe("error details and signed-out answers", () => {
  it("keeps the details object from the error envelope", async () => {
    stubFetch(
      json(
        {
          error: {
            code: "confirmation_required",
            message: "Confirm the address to sign in.",
            details: { email: "a***@example.org" },
          },
        },
        409,
      ),
    );
    const error = await apiFetch("/auth/email/verify", { method: "POST", body: { token: "t" } }).catch(
      (e: unknown) => e,
    );
    expect(error).toMatchObject({ status: 409, code: "confirmation_required", details: { email: "a***@example.org" } });
  });

  it("gives an empty details object when the envelope has none", async () => {
    stubFetch(json({ error: { code: "not_found", message: "Gone." } }, 404));
    const error = await apiFetch("/findings/x").catch((e: unknown) => e);
    expect(error).toMatchObject({ details: {}, fields: [] });
  });

  it("keeps the fields a refusal names when its details are a list of them", async () => {
    stubFetch(
      json(
        {
          error: {
            code: "position_in_text",
            message: "Take the position out.",
            details: [{ field: "body.title", message: "The title gives a position." }, { odd: true }],
          },
        },
        422,
      ),
    );
    const error = await apiFetch("/findings/x", { method: "PATCH", body: {} }).catch((e: unknown) => e);
    expect(error).toMatchObject({
      code: "position_in_text",
      details: {},
      fields: [{ field: "body.title", message: "The title gives a position." }],
    });
  });

  it("tells every listener about a 401, whichever path it came from, until they stop listening", async () => {
    const heard: string[] = [];
    const stop = onUnauthorised((path) => heard.push(path));
    stubFetch(json({ error: { code: "unauthorised", message: "Sign in first." } }, 401));
    await apiFetch("/findings", { method: "POST", body: {} }).catch(() => undefined);
    stubFetch(json({ error: { code: "forbidden", message: "No." } }, 403));
    await apiFetch("/findings/x").catch(() => undefined);
    stop();
    stubFetch(json({ error: { code: "unauthorised", message: "Sign in first." } }, 401));
    await apiFetch("/auth/me").catch(() => undefined);
    expect(heard).toEqual(["/findings"]);
  });
});
