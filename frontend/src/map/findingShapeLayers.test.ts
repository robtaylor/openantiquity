// @vitest-environment node
import { describe, expect, it } from "vitest";
import { parseMeta } from "../api/meta.js";
import { metaFixture } from "../test/fixtures/meta.js";
import { COLOURS, STATE_COLOURS } from "../ui/tokens.js";
import { FINDING_POINT_LAYERS, FINDING_SHAPE_LAYERS, findingsLayers, type OverlayLayer } from "./overlayLayers.js";

const meta = parseMeta(metaFixture);
const layers = findingsLayers(meta, "findings");
const ids = layers.map((entry) => entry.layer.id);

function entry(id: string): OverlayLayer {
  const found = layers.find((candidate) => candidate.layer.id === id);
  if (!found) throw new Error(`No layer ${id}`);
  return found;
}

function paint(id: string): Record<string, unknown> {
  return (entry(id).layer as { paint: Record<string, unknown> }).paint;
}

function filterText(id: string): string {
  return JSON.stringify((entry(id).layer as { filter?: unknown }).filter);
}

describe("findings drawn as lines and areas", () => {
  it("draws a line in its tier colour over a dark casing, with round joins", () => {
    const line = entry(FINDING_SHAPE_LAYERS.lines).layer as { type: string; layout: Record<string, unknown> };
    expect(line.type).toBe("line");
    expect(line.layout["line-join"]).toBe("round");
    expect(JSON.stringify(paint(FINDING_SHAPE_LAYERS.lines)["line-color"])).toContain('["get","tier"]');
    expect(filterText(FINDING_SHAPE_LAYERS.lines)).toContain('"line"');
    const casing = paint(`${FINDING_SHAPE_LAYERS.lines}-casing`);
    expect(casing["line-color"]).toBe(COLOURS.bg);
    expect(ids.indexOf(`${FINDING_SHAPE_LAYERS.lines}-casing`)).toBeLessThan(ids.indexOf(FINDING_SHAPE_LAYERS.lines));
  });

  it("draws an area as its edge with the faintest fill, so the terrain inside stays readable", () => {
    expect(filterText(FINDING_SHAPE_LAYERS.areaEdges)).toContain('"area"');
    expect(JSON.stringify(paint(FINDING_SHAPE_LAYERS.areaEdges)["line-color"])).toContain('["get","tier"]');
    const fill = entry(FINDING_SHAPE_LAYERS.areaFills);
    expect(fill.layer.type).toBe("fill");
    expect(fill.opacity["fill-opacity"]).toBeLessThanOrEqual(0.05);
  });

  it("draws known findings thinner, and ruled-out ones grey and only when asked", () => {
    const width = JSON.stringify(paint(FINDING_SHAPE_LAYERS.lines)["line-width"]);
    expect(width).toContain('"known"');
    const ruledOut = entry(FINDING_SHAPE_LAYERS.ruledOut);
    expect(ruledOut.ruledOutOnly).toBe(true);
    expect(paint(FINDING_SHAPE_LAYERS.ruledOut)["line-color"]).toBe(STATE_COLOURS.ruled_out);
    expect(filterText(FINDING_SHAPE_LAYERS.lines)).toContain('"ruled_out"');
    expect(filterText(FINDING_SHAPE_LAYERS.lines)).toContain('"withdrawn"');
  });

  it("keeps every marker above the shapes, so a line's anchor marker can always be tapped", () => {
    const lastShape = Math.max(...Object.values(FINDING_SHAPE_LAYERS).map((id) => ids.indexOf(id)));
    for (const id of Object.values(FINDING_POINT_LAYERS)) expect(ids.indexOf(id)).toBeGreaterThan(lastShape);
  });

  it("draws only an obscured finding's square dashed, never an exact area", () => {
    expect(filterText("findings-obscured")).toContain('["has","square"]');
    expect(filterText("findings-obscured-casing")).toContain('["has","square"]');
    expect(filterText("findings-obscured-ruled-out")).toContain('["has","square"]');
  });
});
