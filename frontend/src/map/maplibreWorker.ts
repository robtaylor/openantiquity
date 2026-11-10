import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

/**
 * Tells MapLibre where its worker script is. From MapLibre 6 the library is
 * ES modules only, and inside a bundler it cannot find its worker from its
 * own address, so every map fails with "Worker failed to load" unless this
 * runs first. Vite's `?worker&url` bundles the worker and gives its address.
 * See MapLibre's v5 to v6 migration guide.
 *
 * Imported once, for its side effect, by `main.tsx`. Component tests replace
 * `maplibre-gl` with a fake and never import this.
 */
setWorkerUrl(workerUrl);
