/**
 * Terrain tiles that wait their turn.
 *
 * The server draws a few terrain tiles at a time and lets a few more wait.
 * Past that it answers a tile at once with 503 and a `Retry-After`, so that
 * work for a map that has moved on isn't queued. A screen jumping to ground
 * nobody has looked at asks for more tiles than that at once. MapLibre takes
 * a 503 as a failed tile and never asks again, so those tiles stayed blank
 * and the layer was reported as not loading.
 *
 * This site's own terrain tiles are therefore fetched through a protocol of
 * their own, which asks again after the wait the server named, a little
 * longer each time, until the tile is drawn, the map cancels it, or the
 * limits here run out. Then, and for any other failure, the tile fails as it
 * would have.
 *
 * The protocol is registered once, where the app starts (`tileProtocol.ts`).
 * Until it is, addresses are left as they are and MapLibre fetches them
 * itself, so a map made without it still draws.
 */

/** Put before a tile address's own scheme, so `patient+https` is the protocol MapLibre looks up. */
const PREFIX = "patient+";
/** The schemes a tile address can have, each registered as `patient+<scheme>`. */
const SCHEMES = ["https", "http"] as const;

/** How often a tile is asked for before it is given up as failed. */
export const MAX_TRIES = 8;
/** The longest a tile is waited for in all, however long the server says. */
export const MAX_WAIT_MS = 30_000;
/** The shortest wait between two tries. */
const MIN_WAIT_MS = 1000;
/** How much longer each wait is than the one before it, as a share of the server's wait. */
const BACK_OFF = 0.5;
/** The most that is added to a wait at random, so a screenful of tiles doesn't come back all at once. */
const JITTER_MS = 400;

/** The tiles the server draws on its tile workers, which are the ones it may put off (`api/tiles.py`). */
const DRAWN_PATHS = ["/tiles/lidar/", "/tiles/dem/"] as const;

let registered = false;

/** The address MapLibre is given for one of this site's own terrain tiles. Any other address is returned as it is. */
export function patientUrl(url: string, origin: string): string {
  if (!registered) return url;
  const base = origin.replace(/\/$/, "");
  if (!DRAWN_PATHS.some((path) => url.startsWith(`${base}${path}`))) return url;
  if (!SCHEMES.some((scheme) => url.startsWith(`${scheme}://`))) return url;
  return `${PREFIX}${url}`;
}

/** The address a patient tile is really fetched from. */
export function plainUrl(url: string): string {
  return url.startsWith(PREFIX) ? url.slice(PREFIX.length) : url;
}

export interface PatientOptions {
  fetch?: typeof fetch;
  /** Wait `ms`, or reject as the signal does if it is aborted first. */
  wait?: (ms: number, signal: AbortSignal) => Promise<void>;
  /** A number from 0 up to 1, for the jitter. */
  random?: () => number;
}

export interface LoadedTile {
  data: ArrayBuffer;
  cacheControl?: string | null;
  expires?: string | null;
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort(): void {
      clearTimeout(timer);
      reject(signal.reason);
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

/** The server's `Retry-After` in milliseconds, or null when it named no wait this can read. */
function retryAfterMs(response: Response): number | null {
  const seconds = Number(response.headers.get("Retry-After"));
  return Number.isFinite(seconds) && seconds >= 0 && response.headers.has("Retry-After") ? seconds * 1000 : null;
}

/** A tile the server refused, with the fields MapLibre's own request error has and its listeners read. */
export class TileRefusedError extends Error {
  constructor(
    readonly status: number,
    readonly statusText: string,
    readonly url: string,
  ) {
    super(`Tile refused (${status}): ${url}`);
    this.name = "TileRefusedError";
  }
}

function failure(response: Response, url: string): TileRefusedError {
  return new TileRefusedError(response.status, response.statusText, url);
}

/** Fetch one tile, asking again while the server says it is busy. The shape MapLibre's `addProtocol` wants. */
export async function loadPatiently(
  request: { url: string },
  controller: AbortController,
  options: PatientOptions = {},
): Promise<LoadedTile> {
  const ask = options.fetch ?? fetch;
  const wait = options.wait ?? sleep;
  const random = options.random ?? Math.random;
  const url = plainUrl(request.url);
  const { signal } = controller;
  let waited = 0;
  for (let attempt = 1; ; attempt++) {
    const response = await ask(url, { signal });
    if (response.ok) {
      return {
        data: await response.arrayBuffer(),
        cacheControl: response.headers.get("Cache-Control"),
        expires: response.headers.get("Expires"),
      };
    }
    const named = response.status === 503 ? retryAfterMs(response) : null;
    if (named === null || attempt >= MAX_TRIES) throw failure(response, url);
    const longer = Math.max(named, MIN_WAIT_MS) * (1 + BACK_OFF * (attempt - 1));
    const pause = Math.min(longer + random() * JITTER_MS, MAX_WAIT_MS - waited);
    if (pause <= 0) throw failure(response, url);
    // The body isn't read, so it is let go before the wait.
    await response.body?.cancel();
    await wait(pause, signal);
    waited += pause;
  }
}

/** Have MapLibre fetch patient tile addresses through `loadPatiently`, and from now on hand such addresses out. */
export function registerPatientTiles(
  addProtocol: (
    name: string,
    load: (request: { url: string }, controller: AbortController) => Promise<LoadedTile>,
  ) => void,
): void {
  for (const scheme of SCHEMES)
    addProtocol(`${PREFIX}${scheme}`, (request, controller) => loadPatiently(request, controller));
  registered = true;
}
