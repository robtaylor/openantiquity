import { vi } from "vitest";

/**
 * A stand-in for `maplibre-gl`'s Map, for component tests. jsdom has no
 * WebGL, so the real one cannot start. This one records what the app asks of
 * it and lets a test fire map events by hand.
 *
 * It copies two habits of the real map that have caused bugs. After
 * `remove()` the listeners stay registered, and anything that needs the style
 * throws. And `jumpTo` passes its event data on to every event it fires.
 */

type Listener = (event: Record<string, unknown>) => void;

interface FakeStyle {
  layers: Array<{ id: string; type?: string; layout?: Record<string, unknown>; paint?: Record<string, unknown> }>;
  sources: Record<string, unknown>;
  terrain?: { source: string; exaggeration?: number };
}

interface FakeCamera {
  lng: number;
  lat: number;
  zoom: number;
  bearing: number;
  pitch: number;
}

interface CameraTarget {
  center?: [number, number];
  zoom?: number;
  bearing?: number;
  pitch?: number;
  elevation?: number;
}

export interface FakeSource {
  setData: ReturnType<typeof vi.fn>;
  setUrl: ReturnType<typeof vi.fn>;
  setTiles: ReturnType<typeof vi.fn>;
}

/** A query's point or box as [left, top, right, bottom]. A point is a box of no size. */
function boxOf(geometry: unknown): [number, number, number, number] {
  const point = (value: unknown): [number, number] =>
    Array.isArray(value)
      ? [Number(value[0]), Number(value[1])]
      : [Number((value as { x: number }).x), Number((value as { y: number }).y)];
  if (Array.isArray(geometry) && (Array.isArray(geometry[0]) || typeof geometry[0] === "object")) {
    const [a, b] = [point(geometry[0]), point(geometry[1])];
    return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
  }
  const [x, y] = point(geometry);
  return [x, y, x, y];
}

export class FakeMap {
  /** Every map made since the last `FakeMap.reset()`, oldest first. */
  static instances: FakeMap[] = [];
  /**
   * The real map reports its style a moment after it is made. Set this to
   * false to hold that back, then fire "styledata" by hand when the test is
   * ready for it.
   */
  static autoStyle = true;
  /** Set to make the next map fail as it is made, as MapLibre does when there is no WebGL. Cleared once used. */
  static failNext: Error | null = null;
  /**
   * False makes `easeTo` take time, as it does in the real map: it gets half
   * way and waits for `finishEase()`. A camera call made in the meantime cuts
   * it short there, firing its "moveend", as the real map's `stop()` does.
   */
  static instantEase = true;

  static reset(): void {
    FakeMap.instances = [];
    FakeMap.autoStyle = true;
    FakeMap.failNext = null;
    FakeMap.instantEase = true;
  }

  readonly options: Record<string, unknown>;
  readonly style: FakeStyle;
  removed = false;
  /** False after `setCenterClampedToGround(false)`. */
  centreClamped = true;
  private readonly listeners = new Map<string, Set<Listener>>();
  private readonly canvas = document.createElement("canvas");
  private readonly images = new Set<string>();
  private readonly sourceHandles = new Map<string, FakeSource>();
  private camera: FakeCamera;
  private easing: { target: CameraTarget; eventData: Record<string, unknown> } | null = null;
  private elevation = 0;
  private terrain: { source: string; exaggeration?: number } | null;

  setLayoutProperty = vi.fn((layer: string, name: string, value: unknown) => {
    const found = this.requireStyle().layers.find((candidate) => candidate.id === layer);
    if (found) found.layout = { ...found.layout, [name]: value };
  });
  setPaintProperty = vi.fn((layer: string, name: string, value: unknown) => {
    const found = this.requireStyle().layers.find((candidate) => candidate.id === layer);
    if (found) found.paint = { ...found.paint, [name]: value };
  });
  setTerrain = vi.fn((terrain: { source: string; exaggeration?: number } | null) => {
    this.requireStyle();
    this.terrain = terrain;
  });
  easeTo = vi.fn((target: CameraTarget, eventData: Record<string, unknown> = {}) => {
    this.stop();
    if (FakeMap.instantEase) {
      this.moveTo(target, eventData);
      return;
    }
    // Half way there, and waiting.
    this.setCamera({
      zoom: (this.camera.zoom + (target.zoom ?? this.camera.zoom)) / 2,
      bearing: (this.camera.bearing + (target.bearing ?? this.camera.bearing)) / 2,
      pitch: (this.camera.pitch + (target.pitch ?? this.camera.pitch)) / 2,
    });
    this.easing = { target, eventData };
    this.fire("move", eventData);
  });
  jumpTo = vi.fn((target: CameraTarget, eventData?: Record<string, unknown>) => {
    this.stop();
    this.moveTo(target, eventData);
  });
  refreshTiles = vi.fn((_sourceId: string) => {
    this.requireStyle();
  });
  addImage = vi.fn((id: string) => {
    this.images.add(id);
  });
  setCenterClampedToGround = vi.fn((clamped: boolean) => {
    this.centreClamped = clamped;
  });
  addSource = vi.fn((id: string, source: unknown) => {
    const style = this.requireStyle();
    if (id in style.sources) throw new Error(`There is already a source with ID "${id}"`);
    style.sources[id] = source;
  });
  /** Adds a layer on top, or just under the layer `before`, as the real map does. */
  addLayer = vi.fn((layer: FakeStyle["layers"][number], before?: string) => {
    const style = this.requireStyle();
    if (style.layers.some((candidate) => candidate.id === layer.id)) throw new Error(`Layer "${layer.id}" exists`);
    const index = before === undefined ? -1 : style.layers.findIndex((candidate) => candidate.id === before);
    if (index < 0) style.layers.push(structuredClone(layer));
    else style.layers.splice(index, 0, structuredClone(layer));
  });
  getStyle(): FakeStyle {
    return this.requireStyle();
  }
  /** Double-click zoom, which a drawing tool turns off while it has the clicks. */
  readonly doubleClickZoom = {
    enabled: true,
    enable: vi.fn(() => {
      this.doubleClickZoom.enabled = true;
    }),
    disable: vi.fn(() => {
      this.doubleClickZoom.enabled = false;
    }),
    isEnabled: () => this.doubleClickZoom.enabled,
  };
  /** Shift-drag box zoom, which the marking tool turns off so Shift-click is a point. */
  readonly boxZoom = {
    enabled: true,
    enable: vi.fn(() => {
      this.boxZoom.enabled = true;
    }),
    disable: vi.fn(() => {
      this.boxZoom.enabled = false;
    }),
    isEnabled: () => this.boxZoom.enabled,
  };
  /** Called by MapLibre when the style asks for an image the map does not have. */
  missingImageResolver: ((id: string) => void | Promise<void>) | null = null;
  setMissingStyleImageResolver = vi.fn((resolver: ((id: string) => void | Promise<void>) | null) => {
    this.missingImageResolver = resolver;
    return this;
  });

  constructor(options: Record<string, unknown>) {
    const failure = FakeMap.failNext;
    if (failure) {
      FakeMap.failNext = null;
      throw failure;
    }
    this.options = options;
    this.style = structuredClone(options.style) as FakeStyle;
    const [lng, lat] = options.center as [number, number];
    this.camera = {
      lng,
      lat,
      zoom: this.limitZoom(options.zoom as number),
      bearing: (options.bearing as number) ?? 0,
      pitch: (options.pitch as number) ?? 0,
    };
    this.terrain = this.style.terrain ?? null;
    (options.container as HTMLElement).appendChild(this.canvas);
    FakeMap.instances.push(this);
    if (FakeMap.autoStyle) {
      queueMicrotask(() => {
        if (!this.removed) this.fire("styledata", { dataType: "style" });
      });
    }
  }

  /** The real map keeps the zoom inside the limits it was made with. */
  private limitZoom(zoom: number): number {
    const max = typeof this.options.maxZoom === "number" ? this.options.maxZoom : 22;
    const min = typeof this.options.minZoom === "number" ? this.options.minZoom : 0;
    return Math.min(max, Math.max(min, zoom));
  }

  /** Mirrors MapLibre, where a removed map has no style and says so with a TypeError. */
  private requireStyle(): FakeStyle {
    if (this.removed) throw new TypeError("Cannot read properties of undefined (reading 'getSource')");
    return this.style;
  }

  on(type: string, listener: Listener): this {
    let set = this.listeners.get(type);
    if (!set) {
      set = new Set();
      this.listeners.set(type, set);
    }
    set.add(listener);
    return this;
  }

  once(type: string, listener: Listener): this {
    const wrapped: Listener = (event) => {
      this.off(type, wrapped);
      listener(event);
    };
    return this.on(type, wrapped);
  }

  off(type: string, listener: Listener): this {
    this.listeners.get(type)?.delete(listener);
    return this;
  }

  /** Fire a map event, as MapLibre would: one that says where it happened also carries its point on the canvas. */
  fire(type: string, event: Record<string, unknown> = {}): void {
    const lngLat = event.lngLat as { lng: number; lat: number } | undefined;
    const point = event.point ?? (lngLat ? this.project(lngLat) : undefined);
    const sent = { type, target: this, ...event, ...(point === undefined ? {} : { point }) };
    for (const listener of [...(this.listeners.get(type) ?? [])]) listener(sent);
  }

  /** How many listeners are waiting for an event. */
  listenerCount(type: string): number {
    return this.listeners.get(type)?.size ?? 0;
  }

  private setCamera(change: Partial<FakeCamera>): void {
    const next = { ...this.camera, ...change };
    this.camera = { ...next, zoom: this.limitZoom(next.zoom) };
  }

  private moveTo(target: CameraTarget, eventData: Record<string, unknown> = {}): void {
    this.setCamera({
      lng: target.center?.[0] ?? this.camera.lng,
      lat: target.center?.[1] ?? this.camera.lat,
      zoom: target.zoom ?? this.camera.zoom,
      bearing: target.bearing ?? this.camera.bearing,
      pitch: target.pitch ?? this.camera.pitch,
    });
    if (target.elevation !== undefined) this.elevation = target.elevation;
    this.fire("move", eventData);
    this.fire("moveend", eventData);
  }

  /** Cut short an ease that is under way, where it has got to. MapLibre does this at the start of every camera call. */
  private stop(): void {
    const easing = this.easing;
    if (!easing) return;
    this.easing = null;
    this.fire("moveend", easing.eventData);
  }

  /** Let an ease that is under way reach its target. */
  finishEase(): void {
    const easing = this.easing;
    if (!easing) return;
    this.easing = null;
    this.moveTo(easing.target, easing.eventData);
  }

  /** Move the camera as a person dragging the map would: one frame, then the end of the gesture. */
  userMove(change: Partial<FakeCamera>): void {
    this.userDrag([change]);
  }

  /** A gesture of several frames: "move" for each, then one "moveend". */
  userDrag(frames: Array<Partial<FakeCamera>>): void {
    this.stop();
    for (const frame of frames) {
      this.camera = { ...this.camera, ...frame };
      this.fire("move", { originalEvent: {} });
    }
    this.fire("moveend", { originalEvent: {} });
  }

  /** Pretend the ground under the centre of the map is this high. */
  setElevationForTest(elevation: number): void {
    this.elevation = elevation;
  }

  layer(id: string): FakeStyle["layers"][number] {
    const found = this.style.layers.find((candidate) => candidate.id === id);
    if (!found) throw new Error(`The fake map has no layer "${id}"`);
    return found;
  }

  /** Take a layer out of the style, to stand in for a style that has gone wrong. */
  dropLayer(id: string): void {
    this.style.layers = this.style.layers.filter((candidate) => candidate.id !== id);
  }

  isVisible(layerId: string): boolean {
    return this.layer(layerId).layout?.visibility !== "none";
  }

  getLayer(id: string): unknown {
    return this.requireStyle().layers.find((candidate) => candidate.id === id);
  }

  getSource(id: string): FakeSource | undefined {
    if (!(id in this.requireStyle().sources)) return undefined;
    let handle = this.sourceHandles.get(id);
    if (!handle) {
      handle = { setData: vi.fn(), setUrl: vi.fn(), setTiles: vi.fn() };
      this.sourceHandles.set(id, handle);
    }
    return handle;
  }

  /** What `querySourceFeatures` answers with, whatever it is asked. A test sets it. */
  sourceFeatures: unknown[] = [];
  querySourceFeatures(): unknown[] {
    this.requireStyle();
    return this.sourceFeatures;
  }

  /** Filters set on layers, by layer id. */
  readonly filters = new Map<string, unknown>();
  setFilter = vi.fn((layer: string, filter: unknown) => {
    this.requireStyle();
    this.filters.set(layer, filter);
  });

  /**
   * What the map has drawn, for `queryRenderedFeatures` to answer from. It
   * filters by the layers asked for. A feature with `at`, the screen point
   * nearest the query, is found only by a query whose point or box reaches
   * it; one without is found wherever the query is. A test sets it.
   */
  rendered: Array<{
    id?: string | number;
    properties: Record<string, unknown>;
    layer: { id: string };
    geometry?: { type: string; coordinates: unknown };
    at?: { x: number; y: number };
  }> = [];
  queryRenderedFeatures = vi.fn((first?: unknown, second?: unknown) => {
    this.requireStyle();
    // Called as (options) for the whole screen, (point, options) for one spot, or ([corner, corner], options) for a box.
    const isGeometry = Array.isArray(first) || (typeof first === "object" && first !== null && "x" in first);
    const options = (isGeometry ? second : first) as { layers?: string[] } | undefined;
    const reaches = (at: { x: number; y: number } | undefined): boolean => {
      if (!at || !isGeometry) return true;
      const box = boxOf(first);
      return at.x >= box[0] && at.x <= box[2] && at.y >= box[1] && at.y <= box[3];
    };
    // As MapLibre does, a layer that is switched off has drawn nothing to find.
    const drawn = (id: string): boolean => {
      const layer = this.requireStyle().layers.find((candidate) => candidate.id === id) as
        | { layout?: { visibility?: string } }
        | undefined;
      return layer?.layout?.visibility !== "none";
    };
    return this.rendered.filter(
      (feature) =>
        (!options?.layers || options.layers.includes(feature.layer.id)) &&
        drawn(feature.layer.id) &&
        reaches(feature.at),
    );
  });

  getTerrain(): { source: string; exaggeration?: number } | null {
    return this.terrain;
  }

  hasImage(id: string): boolean {
    return this.images.has(id);
  }

  /** Forget every image, as a map does when its style is set again. */
  dropImages(): void {
    this.images.clear();
  }

  getCanvas(): HTMLCanvasElement {
    return this.canvas;
  }

  getCenter(): { lng: number; lat: number } {
    return { lng: this.camera.lng, lat: this.camera.lat };
  }

  getZoom(): number {
    return this.camera.zoom;
  }

  getBearing(): number {
    return this.camera.bearing;
  }

  getPitch(): number {
    return this.camera.pitch;
  }

  getCenterElevation(): number {
    return this.elevation;
  }

  /** A box round the centre, as wide as a 1024 by 768 px window at this zoom. Near enough for tests. */
  getBounds(): { getWest(): number; getSouth(): number; getEast(): number; getNorth(): number } {
    const halfWidth = (1024 / 2) * (360 / (512 * 2 ** this.camera.zoom));
    const halfHeight = halfWidth * 0.75 * Math.cos((this.camera.lat * Math.PI) / 180);
    const { lng, lat } = this.camera;
    return {
      getWest: () => lng - halfWidth,
      getSouth: () => lat - halfHeight,
      getEast: () => lng + halfWidth,
      getNorth: () => lat + halfHeight,
    };
  }

  /** Degrees of longitude per pixel at the current zoom, as `getBounds` assumes. */
  private degreesPerPixel(): number {
    return 360 / (512 * 2 ** this.camera.zoom);
  }

  /**
   * Where a place is on the 1024 by 768 px canvas `getBounds` assumes, flat
   * and north-up. Near enough for tests that place, drag and click.
   */
  project(lngLat: [number, number] | { lng: number; lat: number }): { x: number; y: number } {
    const [lng, lat] = Array.isArray(lngLat) ? lngLat : [lngLat.lng, lngLat.lat];
    const step = this.degreesPerPixel();
    const cos = Math.cos((this.camera.lat * Math.PI) / 180);
    return { x: 512 + (lng - this.camera.lng) / step, y: 384 - (lat - this.camera.lat) / (step * cos) };
  }

  /** The place at a point on the canvas: the inverse of `project`. */
  unproject(point: [number, number] | { x: number; y: number }): { lng: number; lat: number } {
    const [x, y] = Array.isArray(point) ? point : [point.x, point.y];
    const step = this.degreesPerPixel();
    const cos = Math.cos((this.camera.lat * Math.PI) / 180);
    return { lng: this.camera.lng + (x - 512) * step, lat: this.camera.lat - (y - 384) * step * cos };
  }

  /** Pan by a number of pixels, as `map.panBy` does, with no easing. */
  panBy = vi.fn((offset: [number, number]) => {
    const target = this.unproject([512 + offset[0], 384 + offset[1]]);
    this.moveTo({ center: [target.lng, target.lat] });
  });

  getContainer(): HTMLElement {
    return this.options.container as HTMLElement;
  }

  /** Click the map at a point on the canvas, as MapLibre reports a click that was not a drag, with any keys held. */
  click(x: number, y: number, keys: { shiftKey?: boolean; altKey?: boolean; pointerType?: string } = {}): void {
    const lngLat = this.unproject([x, y]);
    this.fire("click", { point: { x, y }, lngLat, originalEvent: { ...keys } });
  }

  /** What the app last put into a GeoJSON source, or undefined if it never has. */
  sourceData(id: string): unknown {
    const calls = this.sourceHandles.get(id)?.setData.mock.calls;
    return calls?.at(-1)?.[0];
  }

  remove(): void {
    this.removed = true;
    this.canvas.remove();
  }
}
