import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { StreamEvent } from "./api.js";
import {
  type EventSourceLike,
  type LiveStatus,
  LiveStream,
  type LiveStreamEnvironment,
  POLL_MS,
  parseStreamEvent,
  REOPEN_AFTER_END_MS,
  RETRY_FIRST_MS,
  RETRY_MAX_MS,
  retryDelay,
} from "./liveStream.js";

class FakeSource implements EventSourceLike {
  readyState = 0;
  closed = false;
  private listeners = new Map<string, Array<(event: Event) => void>>();
  constructor(readonly url: string) {}
  addEventListener(type: string, listener: (event: Event) => void): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  close(): void {
    this.closed = true;
    this.readyState = 2;
  }
  fire(type: string, data?: string): void {
    const event = data === undefined ? new Event(type) : new MessageEvent(type, { data });
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
  open(): void {
    this.readyState = 1;
    this.fire("open");
  }
  /** The browser gave up: a refusal before the stream started. */
  refuse(): void {
    this.readyState = 2;
    this.fire("error");
  }
  /** The connection broke, and the browser will reconnect by itself. */
  lose(): void {
    this.readyState = 0;
    this.fire("error");
  }
}

function setUp() {
  const sources: FakeSource[] = [];
  let visible = true;
  let online = true;
  let onChange = () => {};
  const environment: LiveStreamEnvironment = {
    createSource: (url) => {
      const source = new FakeSource(url);
      sources.push(source);
      return source;
    },
    isVisible: () => visible,
    isOnline: () => online,
    watch: (listener) => {
      onChange = listener;
      return () => {
        onChange = () => {};
      };
    },
    random: () => 0.5,
  };
  const events: StreamEvent[] = [];
  const statuses: LiveStatus[] = [];
  const onResync = vi.fn();
  const latestId = vi.fn(async (): Promise<number | null> => null);
  const stream = new LiveStream(
    "/api/v1/events/stream",
    { onEvent: (event) => events.push(event), onResync, latestId, onStatus: (status) => statuses.push(status) },
    environment,
  );
  return {
    stream,
    sources,
    events,
    statuses,
    onResync,
    latestId,
    latest: () => {
      const source = sources.at(-1);
      if (!source) throw new Error("No stream was opened");
      return source;
    },
    open: () => sources.filter((source) => !source.closed),
    setVisible: (value: boolean) => {
      visible = value;
      onChange();
    },
    setOnline: (value: boolean) => {
      online = value;
      onChange();
    },
  };
}

const EVENT = JSON.stringify({ id: 7, kind: "tier_changed", finding: "f-1", investigation: null, actor: null });

describe("the live stream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("opens one stream, passes on each event as a hint, and refetches when the server says resync", () => {
    const live = setUp();
    live.stream.start();
    live.stream.start();
    expect(live.sources).toHaveLength(1);
    expect(live.latest().url).toBe("/api/v1/events/stream");
    live.latest().open();
    expect(live.statuses.at(-1)).toBe("live");
    // The first open after loading the page refetches nothing: what is on screen is fresh.
    expect(live.onResync).not.toHaveBeenCalled();

    live.latest().fire("activity", EVENT);
    live.latest().fire("activity", "not json");
    live.latest().fire("activity", JSON.stringify({ id: 8, kind: "something_new" }));
    expect(live.events).toEqual([{ id: 7, kind: "tier_changed", finding: "f-1", investigation: null, actor: null }]);

    live.latest().fire("resync");
    expect(live.onResync).toHaveBeenCalledTimes(1);
  });

  it("closes while the page is hidden, and reopens with a refetch when it is seen again", () => {
    const live = setUp();
    live.stream.start();
    live.latest().open();
    live.setVisible(false);
    expect(live.open()).toHaveLength(0);
    expect(live.statuses.at(-1)).toBe("paused");
    vi.advanceTimersByTime(10 * 60_000);
    expect(live.sources).toHaveLength(1);
    expect(live.latestId).not.toHaveBeenCalled();

    live.setVisible(true);
    expect(live.open()).toHaveLength(1);
    live.latest().open();
    expect(live.onResync).toHaveBeenCalledTimes(1);
  });

  it("closes while offline and reopens when the browser is back online", () => {
    const live = setUp();
    live.stream.start();
    live.latest().open();
    live.setOnline(false);
    expect(live.open()).toHaveLength(0);
    expect(live.statuses.at(-1)).toBe("offline");
    live.setOnline(true);
    live.latest().open();
    expect(live.sources).toHaveLength(2);
    expect(live.onResync).toHaveBeenCalledTimes(1);
  });

  it("after dropped or closed, reopens a few seconds later, spread out, and refetches what was missed", () => {
    const live = setUp();
    live.stream.start();
    live.latest().open();
    live.latest().fire("dropped");
    expect(live.open()).toHaveLength(0);
    vi.advanceTimersByTime(REOPEN_AFTER_END_MS);
    expect(live.sources).toHaveLength(1);
    vi.advanceTimersByTime(REOPEN_AFTER_END_MS);
    expect(live.sources).toHaveLength(2);
    live.latest().open();
    expect(live.onResync).toHaveBeenCalledTimes(1);

    live.latest().fire("closed");
    vi.advanceTimersByTime(2 * REOPEN_AFTER_END_MS);
    expect(live.sources).toHaveLength(3);
  });

  it("lets the browser reconnect a broken connection itself, and refetches once it is back", () => {
    const live = setUp();
    live.stream.start();
    live.latest().open();
    live.latest().lose();
    expect(live.statuses.at(-1)).toBe("connecting");
    vi.advanceTimersByTime(60_000);
    expect(live.sources).toHaveLength(1);
    live.latest().open();
    expect(live.onResync).toHaveBeenCalledTimes(1);
  });

  it("after a refusal, reopens with a growing delay and asks the feed now and then meanwhile", async () => {
    const live = setUp();
    live.latestId.mockResolvedValueOnce(10).mockResolvedValueOnce(10).mockResolvedValueOnce(12);
    live.stream.start();
    live.latest().refuse();
    expect(live.statuses.at(-1)).toBe("waiting");
    // The feed is asked at once, for where things stand.
    await vi.advanceTimersByTimeAsync(0);
    expect(live.latestId).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(RETRY_FIRST_MS);
    expect(live.sources).toHaveLength(2);
    live.latest().refuse();
    await vi.advanceTimersByTimeAsync(RETRY_FIRST_MS);
    expect(live.sources).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(RETRY_FIRST_MS);
    expect(live.sources).toHaveLength(3);
    live.latest().refuse();

    // Nothing new at the first look; something new at the next.
    await vi.advanceTimersByTimeAsync(POLL_MS - 3 * RETRY_FIRST_MS);
    expect(live.latestId).toHaveBeenCalledTimes(2);
    expect(live.onResync).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(live.latestId).toHaveBeenCalledTimes(3);
    expect(live.onResync).toHaveBeenCalledTimes(1);

    // Once it opens, the asking stops, and what was missed is refetched.
    await vi.advanceTimersByTimeAsync(4 * RETRY_FIRST_MS);
    live.latest().open();
    expect(live.onResync).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(5 * POLL_MS);
    expect(live.latestId).toHaveBeenCalledTimes(3);
  });

  it("stops everything when stopped", () => {
    const live = setUp();
    live.stream.start();
    live.latest().refuse();
    live.stream.stop();
    vi.advanceTimersByTime(2 * RETRY_MAX_MS);
    expect(live.open()).toHaveLength(0);
    expect(live.sources).toHaveLength(1);
  });

  it("does nothing where the browser has no EventSource", () => {
    const statuses: LiveStatus[] = [];
    const stream = new LiveStream(
      "/x",
      { onEvent: () => {}, onResync: () => {}, latestId: async () => null, onStatus: (s) => statuses.push(s) },
      { createSource: null, isVisible: () => true, isOnline: () => true, watch: () => () => {}, random: Math.random },
    );
    stream.start();
    expect(statuses).toEqual(["unsupported"]);
  });
});

describe("stream helpers", () => {
  it("grows the wait after each refusal, up to five minutes", () => {
    expect(retryDelay(1, () => 0.5)).toBe(RETRY_FIRST_MS);
    expect(retryDelay(2, () => 0.5)).toBe(2 * RETRY_FIRST_MS);
    expect(retryDelay(30, () => 0.5)).toBe(RETRY_MAX_MS);
    expect(retryDelay(1, () => 0)).toBe(0.8 * RETRY_FIRST_MS);
  });

  it("reads only well-formed events", () => {
    expect(parseStreamEvent(EVENT)).toMatchObject({ id: 7, finding: "f-1" });
    expect(parseStreamEvent(JSON.stringify({ id: "7", kind: "tier_changed" }))).toBeNull();
    expect(parseStreamEvent(JSON.stringify({ id: 7, kind: "tier_changed", finding: 3 }))).toBeNull();
    expect(parseStreamEvent(JSON.stringify({ id: 7, kind: "comment_added" }))).toEqual({
      id: 7,
      kind: "comment_added",
      finding: null,
      investigation: null,
      actor: null,
    });
  });
});
