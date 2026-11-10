/**
 * Watches how each map source is loading and decides when a failure is worth
 * telling someone about.
 *
 * One bad tile is not a broken layer. Upstream services drop the odd request,
 * and a hole in one corner should not switch a whole overlay off. So tiles
 * are counted as they arrive and as they fail, and a source is in trouble
 * only when at least half of what answered in the last few seconds had
 * failed. A source in trouble is loaded again once, unprompted. If it is in
 * trouble again within a minute, it is reported, and it is up to the caller
 * to say so on screen and offer another attempt.
 *
 * Without a listener MapLibre prints every failed tile to the console, which
 * floods it when the backend is down. Here each kind of failure is printed
 * once.
 */

export interface MapErrorLike {
  error?: { message?: string; status?: number; url?: string } | null;
  sourceId?: unknown;
  /** Set when one tile failed. Absent when the source itself did, for example its TileJSON. */
  tile?: unknown;
}

export interface TileHealthOptions {
  /** Load this source again. Called once, unprompted, the first time a source is in trouble. */
  reload: (sourceId: string) => void;
  /** Called when a source is still in trouble after its second attempt. */
  onFailing: (sourceId: string) => void;
  /** Called when a source that was reported starts loading again. */
  onRecovered: (sourceId: string) => void;
  /** Where the one-line reports go. */
  warn: (message: string) => void;
}

export interface TileHealth {
  /** Pass every MapLibre "error" event here. */
  onError: (event: MapErrorLike) => void;
  /** Call when a tile of this source has arrived. */
  onTileLoaded: (sourceId: string) => void;
  /**
   * Call when someone asks for another attempt. The failure is forgotten, and
   * if the source fails again it is reported without a further silent retry.
   */
  retried: (sourceId: string) => void;
  /** Stop every timer. Nothing is reported afterwards. */
  dispose: () => void;
}

/** How long after a failure a source is judged, so the tiles asked for with it have time to answer. */
export const SETTLE_MS = 1500;
/** A source is judged on the tiles that answered within this long. */
export const WINDOW_MS = 10_000;
/** A source is in trouble when this share of the tiles that answered had failed. */
export const FAILED_SHARE = 0.5;
/** How long a source in trouble is left alone before its one unprompted second attempt. */
export const RETRY_DELAY_MS = 3000;
/**
 * A source gets one unprompted second attempt in this long. Trouble that
 * comes back sooner is reported, so a failing upstream is never asked again
 * and again.
 */
export const RETRY_MEMORY_MS = 60_000;
/** Longest a list of already-printed problems may grow. */
const MAX_REPORTED = 200;

interface SourceState {
  /** When each recent tile failed or arrived, oldest first. */
  failed: number[];
  loaded: number[];
  /** True from the moment the source is reported until it recovers or is tried again. */
  reported: boolean;
  /** When the last second attempt was made, by the tracker or by a person. */
  retriedAt: number | null;
  settleTimer?: ReturnType<typeof setTimeout>;
  retryTimer?: ReturnType<typeof setTimeout>;
}

function recent(times: number[], since: number): number {
  while (times.length > 0 && (times[0] as number) < since) times.shift();
  return times.length;
}

export function createTileHealth(options: TileHealthOptions): TileHealth {
  const printed = new Set<string>();
  const sources = new Map<string, SourceState>();
  let disposed = false;

  function printOnce(key: string, message: string): void {
    if (printed.has(key) || printed.size >= MAX_REPORTED) return;
    printed.add(key);
    options.warn(message);
  }

  function stateOf(sourceId: string): SourceState {
    let state = sources.get(sourceId);
    if (!state) {
      state = { failed: [], loaded: [], reported: false, retriedAt: null };
      sources.set(sourceId, state);
    }
    return state;
  }

  function forget(state: SourceState): void {
    if (state.settleTimer !== undefined) clearTimeout(state.settleTimer);
    if (state.retryTimer !== undefined) clearTimeout(state.retryTimer);
    state.settleTimer = undefined;
    state.retryTimer = undefined;
    state.failed = [];
    state.loaded = [];
  }

  function judge(sourceId: string, state: SourceState): void {
    state.settleTimer = undefined;
    if (disposed) return;
    const now = Date.now();
    const failed = recent(state.failed, now - WINDOW_MS);
    const answered = failed + recent(state.loaded, now - WINDOW_MS);
    const inTrouble = failed > 0 && failed / answered >= FAILED_SHARE;

    if (state.reported) {
      if (!inTrouble && answered > 0) {
        state.reported = false;
        options.onRecovered(sourceId);
      }
      return;
    }
    if (!inTrouble) return;
    if (state.retriedAt !== null && now - state.retriedAt <= RETRY_MEMORY_MS) {
      state.reported = true;
      printOnce(`failing:${sourceId}`, `[map] "${sourceId}" is still not loading after a second attempt.`);
      options.onFailing(sourceId);
      return;
    }
    state.retryTimer = setTimeout(() => {
      if (disposed) return;
      // Only what answers the second attempt is judged next.
      forget(state);
      state.retriedAt = Date.now();
      options.reload(sourceId);
    }, RETRY_DELAY_MS);
  }

  function count(sourceId: string, outcome: "failed" | "loaded"): void {
    if (disposed) return;
    const state = stateOf(sourceId);
    // Whatever arrives while the second attempt is waiting belongs to the first.
    if (state.retryTimer !== undefined) return;
    const now = Date.now();
    state[outcome].push(now);
    recent(state[outcome], now - WINDOW_MS);
    // A failure calls for a judgement. So does anything from a reported source, which may have recovered.
    if ((outcome === "failed" || state.reported) && state.settleTimer === undefined) {
      state.settleTimer = setTimeout(() => judge(sourceId, state), SETTLE_MS);
    }
  }

  return {
    onError: (event) => {
      const sourceId = typeof event.sourceId === "string" ? event.sourceId : undefined;
      const status = event.error?.status;
      const detail = status ? `HTTP ${status}` : (event.error?.message ?? "unknown error");
      if (sourceId === undefined) {
        printOnce(`other:${detail}`, `[map] ${detail}`);
        return;
      }
      const what = event.tile === undefined || event.tile === null ? "could not be set up" : "tiles failed to load";
      printOnce(`source:${sourceId}:${detail}`, `[map] "${sourceId}" ${what} (${detail}).`);
      count(sourceId, "failed");
    },

    onTileLoaded: (sourceId) => count(sourceId, "loaded"),

    retried: (sourceId) => {
      const state = stateOf(sourceId);
      forget(state);
      state.reported = false;
      state.retriedAt = Date.now();
      printed.delete(`failing:${sourceId}`);
    },

    dispose: () => {
      disposed = true;
      for (const state of sources.values()) forget(state);
    },
  };
}
