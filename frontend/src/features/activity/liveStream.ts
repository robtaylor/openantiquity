/**
 * The one connection to `GET /events/stream` for the whole app.
 *
 * An open stream holds a server instance awake, which is most of the running
 * cost, so it is open only while the page is visible and the browser is
 * online, and closed as soon as either stops. Each event is a hint to ask the
 * API again, never something to show: it carries ids and a kind and nothing
 * more (docs/ARCHITECTURE.md, "Events").
 *
 * How the stream ends, and what happens next:
 *
 * - The server's `resync`: events were lost on its side. Refetch what is on screen.
 * - `dropped` (this client fell behind) or `closed` (the server is shutting
 *   down): the stream ends. It is reopened after a few seconds, spread out a
 *   little so every browser doesn't come back at once, and what is on screen
 *   is refetched once it is open, because events were missed meanwhile.
 * - The stream simply ending, or the connection breaking: the browser
 *   reconnects by itself once, and the reopened stream refetches what is on
 *   screen. If that reconnection fails too (the server is down, or a proxy
 *   drops the connection), it is treated as a refusal below, because a browser
 *   would otherwise try again every few seconds for ever.
 * - A refusal before the stream starts (`too_many_streams`, `rate_limited`,
 *   a proxy's 502): a browser never retries those. It is reopened after a
 *   growing delay, and meanwhile the feed is asked now and then whether
 *   anything has happened.
 * - Hidden or offline: closed, and opened again with a refetch on return.
 */

import { isFiniteNumber, isRecord } from "../../api/guards.js";
import type { StreamEvent } from "./api.js";
import { isActivityKind } from "./kinds.js";

/** `EventSource.CLOSED`, which a browser sets when it won't reconnect by itself. */
const CLOSED = 2;

/** After `dropped` or `closed`, at least this long before reopening, and up to twice as long. */
export const REOPEN_AFTER_END_MS = 3_000;
/** The first wait after a refusal. Each refusal in a row doubles it, up to `RETRY_MAX_MS`. */
export const RETRY_FIRST_MS = 5_000;
export const RETRY_MAX_MS = 5 * 60_000;
/** While the stream is refused, how often the feed is asked whether anything has happened. */
export const POLL_MS = 60_000;
/** Errors in a row, with no open between them, that the browser may retry by itself before the stream gives up. */
export const SELF_RETRIES = 1;

/**
 * - "connecting": opening, or the browser is reconnecting by itself.
 * - "live": events arrive as they happen.
 * - "waiting": refused, so the feed is asked now and then until it opens.
 * - "paused": the page is hidden, or the browser offline.
 * - "unsupported": this browser has no `EventSource`.
 */
export type LiveStatus = "connecting" | "live" | "waiting" | "paused" | "offline" | "unsupported";

/** What the stream needs of `EventSource`, so a test can stand in for it. */
export interface EventSourceLike {
  readonly readyState: number;
  addEventListener(type: string, listener: (event: Event) => void): void;
  close(): void;
}

export interface LiveStreamEnvironment {
  /** Null where the browser has no `EventSource`. */
  createSource: ((url: string) => EventSourceLike) | null;
  isVisible: () => boolean;
  isOnline: () => boolean;
  /** Call `onChange` whenever visibility or connectivity changes. Returns a function that stops. */
  watch: (onChange: () => void) => () => void;
  random: () => number;
}

export interface LiveStreamHandlers {
  onEvent: (event: StreamEvent) => void;
  /** Events may have been missed: refetch what is on screen. */
  onResync: () => void;
  /** The newest id in the feed, for checking for news while the stream is refused. */
  latestId: () => Promise<number | null>;
  onStatus?: (status: LiveStatus) => void;
}

/** The browser's own environment. */
export function browserEnvironment(): LiveStreamEnvironment {
  return {
    createSource: typeof EventSource === "function" ? (url) => new EventSource(url) : null,
    isVisible: () => document.visibilityState !== "hidden",
    isOnline: () => navigator.onLine !== false,
    watch: (onChange) => {
      document.addEventListener("visibilitychange", onChange);
      window.addEventListener("online", onChange);
      window.addEventListener("offline", onChange);
      return () => {
        document.removeEventListener("visibilitychange", onChange);
        window.removeEventListener("online", onChange);
        window.removeEventListener("offline", onChange);
      };
    },
    random: Math.random,
  };
}

/** An `activity` event's data, or null when it isn't one this build can use. */
export function parseStreamEvent(data: unknown): StreamEvent | null {
  let value: unknown;
  try {
    value = typeof data === "string" ? JSON.parse(data) : null;
  } catch {
    return null;
  }
  if (!isRecord(value) || !isFiniteNumber(value.id) || !isActivityKind(value.kind)) return null;
  const text = (field: unknown): string | null | undefined =>
    field === null || field === undefined ? null : typeof field === "string" ? field : undefined;
  const finding = text(value.finding);
  const investigation = text(value.investigation);
  const actor = text(value.actor);
  if (finding === undefined || investigation === undefined || actor === undefined) return null;
  return { id: value.id, kind: value.kind, finding, investigation, actor };
}

/** The wait before the next try after `failures` refusals in a row, spread by up to a fifth either way. */
export function retryDelay(failures: number, random: () => number): number {
  const base = Math.min(RETRY_MAX_MS, RETRY_FIRST_MS * 2 ** Math.max(0, failures - 1));
  return Math.round(base * (0.8 + 0.4 * random()));
}

export class LiveStream {
  private source: EventSourceLike | null = null;
  private reopenTimer: ReturnType<typeof setTimeout> | null = null;
  private pollTimer: ReturnType<typeof setTimeout> | null = null;
  private stopWatching: (() => void) | null = null;
  /** Refusals in a row, for the growing delay. */
  private failures = 0;
  /** Errors since the stream last opened, across reopens. */
  private errorsSinceOpen = 0;
  /** Set whenever events may have gone by unheard, so the next open refetches. */
  private missed = false;
  /** The newest event id heard, by the stream or by asking the feed. */
  private lastId: number | null = null;
  private status: LiveStatus | null = null;

  constructor(
    private readonly url: string,
    private readonly handlers: LiveStreamHandlers,
    private readonly environment: LiveStreamEnvironment = browserEnvironment(),
  ) {}

  start(): void {
    if (this.stopWatching) return;
    if (!this.environment.createSource) {
      this.setStatus("unsupported");
      return;
    }
    this.stopWatching = this.environment.watch(() => this.update());
    this.update();
  }

  stop(): void {
    this.stopWatching?.();
    this.stopWatching = null;
    this.closeAll();
  }

  private setStatus(status: LiveStatus): void {
    if (status === this.status) return;
    this.status = status;
    this.handlers.onStatus?.(status);
  }

  private update(): void {
    const { isVisible, isOnline } = this.environment;
    if (!isVisible() || !isOnline()) {
      this.closeAll();
      this.missed = true;
      this.setStatus(isOnline() ? "paused" : "offline");
      return;
    }
    if (this.source === null && this.reopenTimer === null) this.open();
  }

  private open(): void {
    const create = this.environment.createSource;
    if (!create) return;
    const source = create(this.url);
    this.source = source;
    this.setStatus("connecting");
    const current = () => this.source === source;

    source.addEventListener("open", () => {
      if (!current()) return;
      this.failures = 0;
      this.errorsSinceOpen = 0;
      this.stopPolling();
      this.setStatus("live");
      if (this.missed) {
        this.missed = false;
        this.handlers.onResync();
      }
    });
    source.addEventListener("activity", (event) => {
      if (!current() || !(event instanceof MessageEvent)) return;
      const parsed = parseStreamEvent(event.data);
      if (!parsed) return;
      this.lastId = Math.max(this.lastId ?? 0, parsed.id);
      this.handlers.onEvent(parsed);
    });
    source.addEventListener("resync", () => {
      if (current()) this.handlers.onResync();
    });
    for (const ending of ["dropped", "closed"]) {
      source.addEventListener(ending, () => {
        if (!current()) return;
        this.closeSource();
        this.missed = true;
        this.reopenIn(Math.round(REOPEN_AFTER_END_MS * (1 + this.environment.random())));
        this.setStatus("connecting");
      });
    }
    source.addEventListener("error", () => {
      if (!current()) return;
      this.missed = true;
      this.errorsSinceOpen += 1;
      if (source.readyState !== CLOSED && this.errorsSinceOpen <= SELF_RETRIES) {
        // The browser is reconnecting by itself.
        this.setStatus("connecting");
        return;
      }
      // Refused before it started, so the browser won't try again, or its own
      // reconnecting keeps failing: either way, wait longer each time.
      this.closeSource();
      this.failures += 1;
      this.reopenIn(retryDelay(this.failures, this.environment.random));
      this.startPolling();
      this.setStatus("waiting");
    });
  }

  private reopenIn(delay: number): void {
    this.clearReopen();
    this.reopenTimer = setTimeout(() => {
      this.reopenTimer = null;
      this.update();
    }, delay);
  }

  private startPolling(): void {
    if (this.pollTimer !== null) return;
    const poll = (): void => {
      this.handlers
        .latestId()
        .then((id) => {
          if (id === null) return;
          if (this.lastId !== null && id > this.lastId) this.handlers.onResync();
          this.lastId = Math.max(this.lastId ?? 0, id);
        })
        .catch(() => {
          // Asking again at the next turn is all there is to do.
        });
    };
    const next = (): void => {
      this.pollTimer = setTimeout(() => {
        poll();
        next();
      }, POLL_MS);
    };
    poll();
    next();
  }

  private stopPolling(): void {
    if (this.pollTimer !== null) clearTimeout(this.pollTimer);
    this.pollTimer = null;
  }

  private clearReopen(): void {
    if (this.reopenTimer !== null) clearTimeout(this.reopenTimer);
    this.reopenTimer = null;
  }

  private closeSource(): void {
    this.source?.close();
    this.source = null;
  }

  private closeAll(): void {
    this.closeSource();
    this.clearReopen();
    this.stopPolling();
  }
}
