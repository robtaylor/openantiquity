import type { Page } from "@playwright/test";
import type { FindingFeature, FindingShape } from "../../src/features/findings/types.js";
import { offset } from "../../src/test/fixtures/findings.js";
import { openMap } from "./app.js";
import { fakeFindings } from "./findings.js";
import { expect } from "./fixtures.js";

/**
 * Findings with lines and areas for fixture-mode specs, laid out in metres
 * east and north of the view's centre, at zoom 15, where a pixel is about
 * 1.5 m, and where each place falls on the page.
 */

export const CENTRE = { lon: -1.8542, lat: 51.4286 };
export const ZOOM = 15;
export const VIEW = `#m=${ZOOM}/${CENTRE.lat}/${CENTRE.lon}/0/0&v=composite`;

export type Metres = [number, number];

export function at([east, north]: Metres): [number, number] {
  const { lon, lat } = offset(east, north, CENTRE);
  return [lon, lat];
}

export function finding(
  publicId: string,
  title: string,
  anchor: Metres,
  shape: FindingShape | null,
  featureClass: string,
): FindingFeature {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: at(anchor) },
    properties: {
      public_id: publicId,
      tier: "seen",
      state: "open",
      obscured: false,
      sensitivity: "open",
      title,
      feature_class: featureClass,
      ...(shape ? { shape } : {}),
    },
  };
}

export function line(points: Metres[]): FindingShape {
  return { type: "LineString", coordinates: points.map(at) };
}

export function ring(west: number, south: number, east: number, north: number): Array<[number, number]> {
  return [at([west, south]), at([east, south]), at([east, north]), at([west, north]), at([west, south])];
}

/** Where a place falls on the page, with the map centred on `CENTRE`, north up, filling the window. */
export function onScreen(page: Page, metres: Metres): { x: number; y: number } {
  const size = page.viewportSize() ?? { width: 0, height: 0 };
  const world = 512 * 2 ** ZOOM;
  const mercator = ([lon, lat]: [number, number]) => ({
    x: ((lon + 180) / 360) * world,
    y: ((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * world,
  });
  const centre = mercator([CENTRE.lon, CENTRE.lat]);
  const point = mercator(at(metres));
  return { x: size.width / 2 + point.x - centre.x, y: size.height / 2 + point.y - centre.y };
}

export function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

/** A tap where the project has a finger, a click where it has a mouse. */
export async function press(page: Page, metres: Metres): Promise<void> {
  const { x, y } = onScreen(page, metres);
  if (isPhone(page)) await page.touchscreen.tap(x, y);
  else await page.mouse.click(x, y);
}

export async function openWithFindings(page: Page, features: FindingFeature[]): Promise<void> {
  await fakeFindings(page, features);
  await openMap(page, `/?panel=none${VIEW}`);
  await markersDrawn(page, features.length);
}

/** Each finding's anchor marker is drawn, so its shapes have arrived with it. */
export async function markersDrawn(page: Page, count: number): Promise<void> {
  await expect
    .poll(() =>
      page.evaluate(async (count) => {
        // The dev server's own copy of the module, so the same map the page draws.
        const url = "/src/map/mainMap.ts";
        const { useMainMapStore } = (await import(/* @vite-ignore */ url)) as typeof import("../../src/map/mainMap.js");
        const map = useMainMapStore.getState().map;
        if (!map) return false;
        const ids = new Set(
          map.queryRenderedFeatures({ layers: ["findings-points"] }).map((feature) => feature.properties?.public_id),
        );
        return ids.size === count;
      }, count),
    )
    .toBe(true);
}
