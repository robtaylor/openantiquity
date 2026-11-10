// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  createTileHealth,
  FAILED_SHARE,
  RETRY_DELAY_MS,
  RETRY_MEMORY_MS,
  SETTLE_MS,
  type TileHealth,
} from "./tileErrors.js";

const TILE = { tileID: "14/8106/5452" };

function setup() {
  const reload = vi.fn();
  const onFailing = vi.fn();
  const onRecovered = vi.fn();
  const warn = vi.fn();
  const health = createTileHealth({ reload, onFailing, onRecovered, warn });
  return { health, reload, onFailing, onRecovered, warn };
}

function fail(health: TileHealth, sourceId: string, count = 1, status = 500): void {
  for (let i = 0; i < count; i++) health.onError({ sourceId, tile: TILE, error: { status } });
}

function load(health: TileHealth, sourceId: string, count = 1): void {
  for (let i = 0; i < count; i++) health.onTileLoaded(sourceId);
}

/** Let the tracker judge what has arrived. */
function settle(): void {
  vi.advanceTimersByTime(SETTLE_MS);
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("createTileHealth", () => {
  it("shrugs off one failed tile among many", () => {
    const { health, reload, onFailing } = setup();
    load(health, "overlay-findings", 5);
    fail(health, "overlay-findings");
    load(health, "overlay-findings", 7);
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS * 2);
    expect(reload).not.toHaveBeenCalled();
    expect(onFailing).not.toHaveBeenCalled();
  });

  it("counts tiles that arrived before the failure, not only after it", () => {
    const { health, reload } = setup();
    load(health, "view-composite", 12);
    vi.advanceTimersByTime(2000);
    fail(health, "view-composite");
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    expect(reload).not.toHaveBeenCalled();
  });

  it("loads a source again, once and after a pause, when at least half its tiles fail", () => {
    const { health, reload, onFailing } = setup();
    expect(FAILED_SHARE).toBe(0.5);
    fail(health, "overlay-records", 6);
    load(health, "overlay-records", 6);
    settle();
    expect(reload).not.toHaveBeenCalled();
    vi.advanceTimersByTime(RETRY_DELAY_MS - 1);
    expect(reload).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(reload).toHaveBeenCalledWith("overlay-records");
    expect(onFailing).not.toHaveBeenCalled();
  });

  it("reports a source that is still failing after its second attempt", () => {
    const { health, reload, onFailing } = setup();
    fail(health, "overlay-records", 8);
    settle();
    // More failures while the second attempt is waiting belong to the first.
    fail(health, "overlay-records", 4);
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(onFailing).not.toHaveBeenCalled();

    fail(health, "overlay-records", 8);
    settle();
    expect(onFailing).toHaveBeenCalledTimes(1);
    expect(onFailing).toHaveBeenCalledWith("overlay-records");
    // It is reported once, and never loaded again unprompted.
    fail(health, "overlay-records", 8);
    settle();
    vi.advanceTimersByTime(RETRY_MEMORY_MS);
    expect(onFailing).toHaveBeenCalledTimes(1);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("says nothing when the second attempt works", () => {
    const { health, reload, onFailing } = setup();
    fail(health, "view-composite", 4);
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    expect(reload).toHaveBeenCalledTimes(1);
    load(health, "view-composite", 9);
    settle();
    expect(onFailing).not.toHaveBeenCalled();
  });

  it("reports a source whose only tile fails twice", () => {
    // Zoomed past a source's deepest level, a single tile can cover the whole screen.
    const { health, reload, onFailing } = setup();
    fail(health, "overlay-records");
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    expect(reload).toHaveBeenCalledTimes(1);
    fail(health, "overlay-records");
    settle();
    expect(onFailing).toHaveBeenCalledWith("overlay-records");
  });

  it("treats a source that could not be set up, such as a failed TileJSON, like any other failure", () => {
    const { health, reload, onFailing, warn } = setup();
    health.onError({ sourceId: "overlay-osm", error: { status: 503 } });
    expect(warn).toHaveBeenCalledWith('[map] "overlay-osm" could not be set up (HTTP 503).');
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    expect(reload).toHaveBeenCalledWith("overlay-osm");
    health.onError({ sourceId: "overlay-osm", error: { status: 503 } });
    settle();
    expect(onFailing).toHaveBeenCalledWith("overlay-osm");
  });

  it("never loads a source again more than once a minute, however the trouble comes and goes", () => {
    const { health, reload, onFailing } = setup();
    fail(health, "view-composite", 4);
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    load(health, "view-composite", 9);
    settle();
    expect(reload).toHaveBeenCalledTimes(1);

    // Trouble again ten seconds later is reported, not retried.
    vi.advanceTimersByTime(10_000);
    fail(health, "view-composite", 4);
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(onFailing).toHaveBeenCalledTimes(1);
  });

  it("gives a source a fresh second attempt once the last one is long past", () => {
    const { health, reload, onFailing } = setup();
    fail(health, "view-composite", 4);
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    load(health, "view-composite", 9);
    settle();

    vi.advanceTimersByTime(RETRY_MEMORY_MS + 1);
    fail(health, "view-composite", 4);
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    expect(reload).toHaveBeenCalledTimes(2);
    expect(onFailing).not.toHaveBeenCalled();
  });

  it("notices when a reported source starts loading again", () => {
    const { health, onFailing, onRecovered } = setup();
    fail(health, "view-composite", 4);
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    fail(health, "view-composite", 4);
    settle();
    expect(onFailing).toHaveBeenCalledTimes(1);

    // Still failing: no recovery.
    fail(health, "view-composite", 2);
    settle();
    expect(onRecovered).not.toHaveBeenCalled();

    // The old failures age out, and new tiles arrive.
    vi.advanceTimersByTime(15_000);
    load(health, "view-composite", 6);
    settle();
    expect(onRecovered).toHaveBeenCalledWith("view-composite");
  });

  it("reports straight away when an attempt a person asked for fails", () => {
    const { health, reload, onFailing } = setup();
    fail(health, "overlay-records", 4);
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    fail(health, "overlay-records", 4);
    settle();
    expect(onFailing).toHaveBeenCalledTimes(1);

    health.retried("overlay-records");
    fail(health, "overlay-records", 4);
    settle();
    expect(onFailing).toHaveBeenCalledTimes(2);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("keeps each source's count apart", () => {
    const { health, reload } = setup();
    fail(health, "overlay-records", 3);
    load(health, "overlay-findings", 30);
    settle();
    vi.advanceTimersByTime(RETRY_DELAY_MS);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(reload).toHaveBeenCalledWith("overlay-records");
  });

  it("prints each kind of failure once", () => {
    const { health, warn } = setup();
    fail(health, "view-composite", 5, 504);
    health.onError({ sourceId: "view-composite", tile: TILE, error: { message: "Failed to fetch" } });
    health.onError({ error: { message: "Something else" } });
    health.onError({ error: { message: "Something else" } });
    health.onError({});
    expect(warn.mock.calls.map((call) => call[0])).toEqual([
      '[map] "view-composite" tiles failed to load (HTTP 504).',
      '[map] "view-composite" tiles failed to load (Failed to fetch).',
      "[map] Something else",
      "[map] unknown error",
    ]);
  });

  it("stops printing when problems keep coming", () => {
    const { health, warn } = setup();
    for (let i = 0; i < 500; i++) health.onError({ error: { message: `problem ${i}` } });
    expect(warn.mock.calls.length).toBe(200);
  });

  it("does nothing once disposed", () => {
    const { health, reload, onFailing } = setup();
    fail(health, "overlay-records", 4);
    health.dispose();
    vi.advanceTimersByTime(SETTLE_MS + RETRY_DELAY_MS + RETRY_MEMORY_MS);
    fail(health, "overlay-records", 4);
    vi.advanceTimersByTime(SETTLE_MS + RETRY_DELAY_MS);
    expect(reload).not.toHaveBeenCalled();
    expect(onFailing).not.toHaveBeenCalled();
  });
});
