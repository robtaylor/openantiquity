// @vitest-environment node
import type { Map as MapLibreMap } from "maplibre-gl";
import { describe, expect, it, vi } from "vitest";
import { type FindingCandidate, findingCandidatesAt, pickFinding, REACH_PX, reachFor } from "./findingHits.js";
import { FINDING_POINT_LAYERS, FINDING_SHAPE_LAYERS } from "./overlayLayers.js";

interface Rendered {
  layer: { id: string };
  properties: Record<string, unknown>;
  geometry?: { type: string; coordinates: unknown };
}

function fakeMap(rendered: Rendered[]) {
  const query = vi.fn((_box: unknown, options?: { layers?: string[] }) =>
    rendered.filter((feature) => !options?.layers || options.layers.includes(feature.layer.id)),
  );
  const map = {
    getLayer: () => ({}),
    queryRenderedFeatures: query,
    project: ([lon, lat]: [number, number]) => ({ x: lon * 1000, y: lat * 1000 }),
  } as unknown as MapLibreMap;
  return { map, query };
}

function marker(id: string, at: [number, number] = [0.1, 0.1]): Rendered {
  return {
    layer: { id: FINDING_POINT_LAYERS.points },
    properties: { public_id: id },
    geometry: { type: "Point", coordinates: at },
  };
}

function line(id: string, size: number): Rendered {
  return { layer: { id: FINDING_SHAPE_LAYERS.lines }, properties: { public_id: id, shape: "line", size } };
}

function area(id: string, size: number): Rendered {
  return { layer: { id: FINDING_SHAPE_LAYERS.areaEdges }, properties: { public_id: id, shape: "area", size } };
}

const TAP = { x: 100, y: 100 };

function pickAt(rendered: Rendered[], reach = REACH_PX.mouse) {
  const { map } = fakeMap(rendered);
  return pickFinding(findingCandidatesAt(map, TAP, reach));
}

function ids(candidates: readonly FindingCandidate[]): string[] {
  return candidates.map((candidate) => candidate.publicId);
}

describe("the reach of a tap", () => {
  it("is 6 px for a mouse or a pen and 16 px for a finger", () => {
    expect(reachFor("mouse")).toBe(6);
    expect(reachFor("pen")).toBe(6);
    expect(reachFor("touch")).toBe(16);
    expect(reachFor(undefined)).toBe(6);
  });

  it("is asked of the map as a box round the tap, over markers, lines and area edges but never an area's inside", () => {
    const { map, query } = fakeMap([]);
    findingCandidatesAt(map, TAP, 16);
    const [box, options] = query.mock.calls[0] ?? [];
    expect(box).toEqual([
      [84, 84],
      [116, 116],
    ]);
    expect(options?.layers).toEqual(expect.arrayContaining([FINDING_POINT_LAYERS.points, FINDING_SHAPE_LAYERS.lines]));
    expect(options?.layers).toContain(FINDING_SHAPE_LAYERS.areaEdges);
    expect(options?.layers).not.toContain(FINDING_SHAPE_LAYERS.areaFills);
  });
});

describe("picking one of overlapping findings", () => {
  it("opens nothing where nothing is in reach", () => {
    expect(pickAt([])).toEqual({ kind: "none" });
  });

  it("lets a marker beat a line, and a line beat an area's edge", () => {
    const markerFirst = pickAt([area("field", 1e6), line("road", 5000), marker("barrow")]);
    expect(markerFirst.kind === "one" && markerFirst.candidate.publicId).toBe("barrow");
    const lineFirst = pickAt([area("field", 1e6), line("road", 5000)]);
    expect(lineFirst.kind === "one" && lineFirst.candidate.publicId).toBe("road");
  });

  it("counts a line finding's own marker and line as one candidate", () => {
    const picked = pickAt([line("road", 5000), marker("road")]);
    expect(picked).toMatchObject({ kind: "one", candidate: { publicId: "road", kind: "marker" } });
  });

  it("gives the smaller of two alike only when it is under half the other", () => {
    const clear = pickAt([line("long", 10_000), line("short", 4_000)]);
    expect(clear.kind === "one" && clear.candidate.publicId).toBe("short");
    const alike = pickAt([line("a", 10_000), line("b", 6_000)]);
    expect(alike.kind).toBe("choose");
    expect(alike.kind === "choose" && ids(alike.candidates)).toEqual(["b", "a"]);
    const areas = pickAt([area("big", 4e6), area("small", 1e6)]);
    expect(areas.kind === "one" && areas.candidate.publicId).toBe("small");
  });

  it("opens the chooser for two markers in reach, and lists everything in reach in the order of specificity", () => {
    const picked = pickAt([area("field", 1e6), line("road", 5000), marker("b", [0.101, 0.1]), marker("a")]);
    expect(picked.kind).toBe("choose");
    expect(picked.kind === "choose" && ids(picked.candidates)).toEqual(["a", "b", "road", "field"]);
  });
});
