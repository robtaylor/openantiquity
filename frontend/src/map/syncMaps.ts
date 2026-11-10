/** The camera a follower is sent to. */
export interface SyncCamera {
  center: [number, number];
  zoom: number;
  bearing: number;
  pitch: number;
  /** Height of the centre point in metres, so a follower over 3D terrain sits where the leader does. */
  elevation: number;
}

/**
 * Carried by every event a synced move fires on the follower. `settled` is
 * true for the copy made when the leader comes to rest.
 */
export interface SyncedMove {
  synced: true;
  settled: boolean;
}

/** The parts of a MapLibre map that camera syncing needs. */
export interface SyncableMap {
  getCenter(): { lng: number; lat: number };
  getZoom(): number;
  getBearing(): number;
  getPitch(): number;
  getCenterElevation(): number;
  setCenterClampedToGround(clamped: boolean): unknown;
  jumpTo(options: SyncCamera, eventData?: SyncedMove): unknown;
  on(type: "move" | "moveend", listener: () => void): unknown;
  off(type: "move" | "moveend", listener: () => void): unknown;
}

export interface SyncOptions<M> {
  /**
   * Says whether a map can still be used. A map that has been removed is
   * never read or moved, because MapLibre throws from a removed map.
   */
  isLive?: (map: M) => boolean;
}

/** True for an event fired by a synced move, which listeners that record the camera should ignore. */
export function isSyncedMove(event: unknown): event is SyncedMove {
  return typeof event === "object" && event !== null && (event as { synced?: unknown }).synced === true;
}

/** True for the last synced move of a gesture, when the follower has reached its resting place. */
export function isSettledMove(event: unknown): boolean {
  return isSyncedMove(event) && event.settled;
}

/**
 * Keep two maps on the same camera. Moving either one moves the other. The
 * second map is snapped to the first straight away. Returns a function that
 * stops the syncing.
 *
 * The follower is told the leader's centre height and stops working out its
 * own. Over 3D terrain MapLibre freezes that height on the map being dragged
 * and lets it catch up when the gesture ends, so two maps that each worked
 * it out would sit at different heights for the whole drag. When the leader
 * comes to rest it corrects its zoom and centre without a "move" event, so
 * the camera is copied once more on "moveend".
 */
export function syncMaps<M extends SyncableMap>(first: M, second: M, options: SyncOptions<M> = {}): () => void {
  const isLive = options.isLive ?? (() => true);
  // jumpTo fires "move" and "moveend" on the map it moves, which must not bounce back.
  let copying = false;

  function copy(from: M, to: M, settled: boolean): void {
    if (copying || !isLive(from) || !isLive(to)) return;
    copying = true;
    try {
      // The leader follows the ground. The follower takes the leader's word for it until the move is over.
      from.setCenterClampedToGround(true);
      to.setCenterClampedToGround(false);
      const centre = from.getCenter();
      to.jumpTo(
        {
          center: [centre.lng, centre.lat],
          zoom: from.getZoom(),
          bearing: from.getBearing(),
          pitch: from.getPitch(),
          elevation: from.getCenterElevation(),
        },
        { synced: true, settled },
      );
      if (settled) to.setCenterClampedToGround(true);
    } finally {
      copying = false;
    }
  }

  const moveFirst = (): void => copy(first, second, false);
  const endFirst = (): void => copy(first, second, true);
  const moveSecond = (): void => copy(second, first, false);
  const endSecond = (): void => copy(second, first, true);
  first.on("move", moveFirst);
  first.on("moveend", endFirst);
  second.on("move", moveSecond);
  second.on("moveend", endSecond);
  endFirst();

  return () => {
    first.off("move", moveFirst);
    first.off("moveend", endFirst);
    second.off("move", moveSecond);
    second.off("moveend", endSecond);
    for (const map of [first, second]) {
      if (isLive(map)) map.setCenterClampedToGround(true);
    }
  };
}
