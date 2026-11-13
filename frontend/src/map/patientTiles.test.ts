import { beforeAll, describe, expect, it, vi } from "vitest";
import { loadPatiently, MAX_TRIES, MAX_WAIT_MS, patientUrl, plainUrl, registerPatientTiles } from "./patientTiles.js";

const ORIGIN = "https://openantiquity.org";
const TILE = `${ORIGIN}/tiles/lidar/composite/15/16198/10594.png?v=abc`;

function answer(status: number, headers: Record<string, string> = {}, body = "png"): Response {
  return new Response(status === 200 ? body : JSON.stringify({ error: { code: "tiles_busy" } }), { status, headers });
}

/** A loader whose waits are noted and take no time, and whose fetch gives each answer in turn. */
function harness(answers: Array<Response | Error>) {
  const waits: number[] = [];
  const asked: string[] = [];
  const fetch = vi.fn(async (url: RequestInfo | URL) => {
    asked.push(String(url));
    const next = answers.shift();
    if (next === undefined) throw new Error("asked more often than the test allowed for");
    if (next instanceof Error) throw next;
    return next;
  });
  const wait = vi.fn(async (ms: number) => {
    waits.push(ms);
  });
  const load = (controller = new AbortController()) =>
    loadPatiently({ url: patientUrl(TILE, ORIGIN) }, controller, { fetch, wait, random: () => 0 });
  return { load, waits, asked, fetch };
}

describe("before the protocol is registered", () => {
  it("leaves every address alone, so MapLibre fetches it itself", async () => {
    vi.resetModules();
    const fresh = await import("./patientTiles.js");
    expect(fresh.patientUrl(TILE, ORIGIN)).toBe(TILE);
  });
});

const protocols = new Map<string, unknown>();
beforeAll(() => {
  registerPatientTiles((name, load) => protocols.set(name, load));
});

describe("which tiles are asked for patiently", () => {
  it("registers a protocol for each scheme a tile address can have", () => {
    expect([...protocols.keys()].sort()).toEqual(["patient+http", "patient+https"]);
  });

  it("wraps this site's own tiles and gives the address back unchanged", () => {
    const wrapped = patientUrl(TILE, ORIGIN);
    expect(wrapped).toBe(`patient+${TILE}`);
    expect(plainUrl(wrapped)).toBe(TILE);
  });

  it("keeps the template's braces", () => {
    const template = `${ORIGIN}/tiles/lidar/composite/{z}/{x}/{y}.png?v=abc`;
    expect(plainUrl(patientUrl(template, ORIGIN))).toBe(template);
  });

  it("wraps the height tiles too", () => {
    const dem = `${ORIGIN}/tiles/dem/{z}/{x}/{y}.png?v=abc`;
    expect(patientUrl(dem, ORIGIN)).toBe(`patient+${dem}`);
  });

  it("leaves other people's tiles, and tiles of ours the server never puts off, alone", () => {
    const theirs = "https://tiles.example.org/tiles/lidar/{z}/{x}/{y}.png";
    expect(patientUrl(theirs, ORIGIN)).toBe(theirs);
    const records = `${ORIGIN}/tiles/records/{z}/{x}/{y}.mvt?v=abc`;
    expect(patientUrl(records, ORIGIN)).toBe(records);
  });
});

describe("a tile the server is too busy to draw", () => {
  it("is asked for again after the wait the server named, and then drawn", async () => {
    const { load, waits, asked } = harness([answer(503, { "Retry-After": "1" }), answer(200)]);

    const loaded = await load();

    expect(new TextDecoder().decode(loaded.data)).toBe("png");
    expect(asked).toEqual([TILE, TILE]);
    expect(waits).toEqual([1000]);
  });

  it("waits a little longer each time it is put off", async () => {
    const busy = () => answer(503, { "Retry-After": "1" });
    const { load, waits } = harness([busy(), busy(), busy(), answer(200)]);

    await load();

    expect(waits).toHaveLength(3);
    expect(waits[1]).toBeGreaterThan(waits[0] ?? 0);
    expect(waits[2]).toBeGreaterThan(waits[1] ?? 0);
  });

  it("is given up as failed once it has been put off too often, with the status the server gave", async () => {
    const { load, fetch, waits } = harness(
      Array.from({ length: MAX_TRIES }, () => answer(503, { "Retry-After": "1" })),
    );

    await expect(load()).rejects.toMatchObject({ status: 503, url: TILE });
    expect(fetch).toHaveBeenCalledTimes(MAX_TRIES);
    expect(waits.reduce((sum, ms) => sum + ms, 0)).toBeLessThanOrEqual(MAX_WAIT_MS);
  });

  it("isn't waited for longer than the limit however long the server says", async () => {
    const { load, waits } = harness([
      answer(503, { "Retry-After": "600" }),
      answer(503, { "Retry-After": "600" }),
      answer(503, { "Retry-After": "600" }),
      answer(503, { "Retry-After": "600" }),
      answer(503, { "Retry-After": "600" }),
      answer(503, { "Retry-After": "600" }),
      answer(503, { "Retry-After": "600" }),
      answer(503, { "Retry-After": "600" }),
    ]);

    await expect(load()).rejects.toMatchObject({ status: 503 });
    expect(waits.reduce((sum, ms) => sum + ms, 0)).toBeLessThanOrEqual(MAX_WAIT_MS);
  });

  it("stops waiting when the map no longer wants the tile", async () => {
    const controller = new AbortController();
    const fetch = vi.fn(async () => answer(503, { "Retry-After": "1" }));
    const wait = vi.fn(async (_ms: number, signal: AbortSignal) => {
      controller.abort();
      signal.throwIfAborted();
    });

    const loading = loadPatiently({ url: patientUrl(TILE, ORIGIN) }, controller, { fetch, wait, random: () => 0 });

    await expect(loading).rejects.toMatchObject({ name: "AbortError" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe("a tile that fails for another reason", () => {
  it("fails at once when the server is unavailable and names no wait", async () => {
    const { load, fetch, waits } = harness([answer(503)]);

    await expect(load()).rejects.toMatchObject({ status: 503 });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(waits).toEqual([]);
  });

  it("fails at once on any other refusal", async () => {
    const { load, fetch } = harness([answer(404)]);

    await expect(load()).rejects.toMatchObject({ status: 404, url: TILE });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("passes on a failure to reach the server", async () => {
    const { load } = harness([new TypeError("Failed to fetch")]);

    await expect(load()).rejects.toThrow("Failed to fetch");
  });
});

describe("a tile that is drawn", () => {
  it("carries the server's word on how long it may be kept", async () => {
    const { load } = harness([answer(200, { "Cache-Control": "public, max-age=31536000, immutable" })]);

    const loaded = await load();

    expect(loaded.cacheControl).toBe("public, max-age=31536000, immutable");
  });

  it("is asked for with the signal the map can cancel it by", async () => {
    const controller = new AbortController();
    const fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.signal).toBe(controller.signal);
      return answer(200);
    });

    await loadPatiently({ url: patientUrl(TILE, ORIGIN) }, controller, { fetch });

    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
