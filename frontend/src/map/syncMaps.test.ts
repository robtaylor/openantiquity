// @vitest-environment node
import { describe, expect, it, vi } from "vitest";
import {
  isSettledMove,
  isSyncedMove,
  type SyncableMap,
  type SyncCamera,
  type SyncedMove,
  syncMaps,
} from "./syncMaps.js";

type EventName = "move" | "moveend";

function fakeMap(lng: number, lat: number, zoom: number) {
  const listeners: Record<EventName, Set<() => void>> = { move: new Set(), moveend: new Set() };
  const camera = { lng, lat, zoom, bearing: 0, pitch: 0, elevation: 0 };
  const state = { clamped: true, removed: false };
  /** The event data of every synced move this map was sent, oldest first. */
  const received: Array<SyncedMove | undefined> = [];

  function fire(type: EventName): void {
    for (const listener of [...listeners[type]]) listener();
  }
  function touch(): void {
    if (state.removed) throw new TypeError("Cannot read properties of undefined (reading 'getSource')");
  }

  const jumpTo = vi.fn((options: SyncCamera, eventData?: SyncedMove) => {
    touch();
    camera.lng = options.center[0];
    camera.lat = options.center[1];
    camera.zoom = options.zoom;
    camera.bearing = options.bearing;
    camera.pitch = options.pitch;
    camera.elevation = options.elevation;
    received.push(eventData);
    // MapLibre fires both from one jumpTo, whatever else is going on.
    fire("move");
    fire("moveend");
  });
  const map: SyncableMap = {
    getCenter: () => {
      touch();
      return { lng: camera.lng, lat: camera.lat };
    },
    getZoom: () => camera.zoom,
    getBearing: () => camera.bearing,
    getPitch: () => camera.pitch,
    getCenterElevation: () => camera.elevation,
    setCenterClampedToGround: (clamped) => {
      touch();
      state.clamped = clamped;
    },
    jumpTo,
    on: (type, listener) => listeners[type].add(listener),
    off: (type, listener) => listeners[type].delete(listener),
  };
  /** One frame of a gesture: change the camera and fire "move". */
  function drag(change: Partial<typeof camera>): void {
    Object.assign(camera, change);
    fire("move");
  }
  /** The end of a gesture. MapLibre may correct the camera here with no "move" of its own. */
  function release(change: Partial<typeof camera> = {}): void {
    Object.assign(camera, change);
    fire("moveend");
  }
  function userMove(change: Partial<typeof camera>): void {
    drag(change);
    release();
  }
  return { map, camera, state, jumpTo, received, drag, release, userMove, listeners };
}

describe("syncMaps", () => {
  it("snaps the second map to the first at once", () => {
    const a = fakeMap(-1.85, 51.43, 14);
    const b = fakeMap(0, 0, 2);
    syncMaps(a.map, b.map);
    expect(b.camera).toEqual(a.camera);
    expect(a.jumpTo).not.toHaveBeenCalled();
  });

  it("copies movement both ways without bouncing", () => {
    const a = fakeMap(-1.85, 51.43, 14);
    const b = fakeMap(0, 0, 2);
    syncMaps(a.map, b.map);
    b.jumpTo.mockClear();

    a.userMove({ zoom: 16, bearing: 30, pitch: 45 });
    expect(b.camera).toEqual(a.camera);
    // Once for the frame and once for the end of the gesture.
    expect(b.jumpTo).toHaveBeenCalledTimes(2);
    expect(a.jumpTo).not.toHaveBeenCalled();

    b.userMove({ lng: -3, lat: 54 });
    expect(a.camera).toEqual(b.camera);
    expect(a.jumpTo).toHaveBeenCalledTimes(2);
    expect(b.jumpTo).toHaveBeenCalledTimes(2);
  });

  it("copies the camera again when the leader comes to rest", () => {
    // Over 3D terrain MapLibre corrects the zoom and centre of the dragged map
    // when the gesture ends, and fires only "moveend" for it.
    const a = fakeMap(-1.85, 51.43, 14);
    const b = fakeMap(0, 0, 2);
    syncMaps(a.map, b.map);

    a.drag({ lng: -1.86 });
    a.release({ lng: -1.8633, zoom: 14.0072 });
    expect(b.camera.lng).toBe(-1.8633);
    expect(b.camera.zoom).toBe(14.0072);
  });

  it("marks the moves it makes, and says which one is the last", () => {
    const a = fakeMap(-1.85, 51.43, 14);
    const b = fakeMap(0, 0, 2);
    syncMaps(a.map, b.map);
    b.received.length = 0;

    a.drag({ lng: -1.86 });
    a.drag({ lng: -1.87 });
    a.release();
    expect(b.received).toEqual([
      { synced: true, settled: false },
      { synced: true, settled: false },
      { synced: true, settled: true },
    ]);
    expect(b.received.every(isSyncedMove)).toBe(true);
    expect(b.received.map(isSettledMove)).toEqual([false, false, true]);
    expect(isSyncedMove({ originalEvent: {} })).toBe(false);
    expect(isSyncedMove(undefined)).toBe(false);
  });

  it("gives the follower the leader's centre height, and has it stop working out its own until the move ends", () => {
    const a = fakeMap(-1.85, 51.43, 14);
    const b = fakeMap(0, 0, 2);
    syncMaps(a.map, b.map);

    a.drag({ lng: -1.86, elevation: 212 });
    expect(b.camera.elevation).toBe(212);
    expect(b.state.clamped).toBe(false);
    expect(a.state.clamped).toBe(true);

    a.release({ elevation: 240 });
    expect(b.camera.elevation).toBe(240);
    expect(b.state.clamped).toBe(true);

    // Either map can lead.
    b.drag({ lng: -1.9, elevation: 180 });
    expect(a.camera.elevation).toBe(180);
    expect(a.state.clamped).toBe(false);
    expect(b.state.clamped).toBe(true);
  });

  it("stops when asked, and leaves both maps following the ground", () => {
    const a = fakeMap(-1.85, 51.43, 14);
    const b = fakeMap(0, 0, 2);
    const stop = syncMaps(a.map, b.map);
    a.drag({ lng: -1.86 });
    expect(b.state.clamped).toBe(false);
    stop();
    expect(a.listeners.move.size + a.listeners.moveend.size).toBe(0);
    expect(b.listeners.move.size + b.listeners.moveend.size).toBe(0);
    expect(a.state.clamped).toBe(true);
    expect(b.state.clamped).toBe(true);
    a.userMove({ zoom: 9 });
    expect(b.camera.zoom).toBe(14);
  });

  it("never touches a map that has been removed", () => {
    const a = fakeMap(-1.85, 51.43, 14);
    const b = fakeMap(0, 0, 2);
    b.state.removed = true;
    const isLive = (map: SyncableMap): boolean => map !== b.map;
    // Syncing with a removed map does nothing, where it used to throw.
    const stop = syncMaps(a.map, b.map, { isLive });
    expect(b.jumpTo).not.toHaveBeenCalled();
    expect(() => a.userMove({ zoom: 15 })).not.toThrow();
    expect(() => stop()).not.toThrow();
  });
});
