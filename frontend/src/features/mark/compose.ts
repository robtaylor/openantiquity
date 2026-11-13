import { ApiError } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { kmSquareAt } from "../../map/gridref.js";
import type { MapState } from "../../map/store.js";
import { suggestTitle, viewStateFrom } from "./describe.js";
import type { FindingDraft } from "./findingDrafts.js";
import type { MarkFields } from "./markStore.js";
import { anchorOf, apiPath, pathProblem } from "./path.js";

export type MarkProblemField = "point" | "featureClass" | "path";

export type Composed = { ok: true; draft: FindingDraft } | { ok: false; field: MarkProblemField; message: string };

/** Said when the mark is somewhere OpenAntiquity doesn't cover, by the server or before asking it. */
export const OUTSIDE_MESSAGE =
  "OpenAntiquity covers the land of Great Britain, Ireland and their islands. Move the mark onto it.";

/**
 * Turn the form into what is sent, or say what is missing. Only a point on
 * the map and the class are required. One point is a spot; two or more are
 * a line or shape. An empty title becomes the suggested one, and the view
 * comes from the map as it is now. The limits on a line or shape come from
 * `/meta`.
 */
export function composeFinding(
  fields: MarkFields,
  meta: Meta,
  map: Pick<MapState, "meta" | "mainView" | "camera" | "sun" | "terrain" | "hillshadeExaggeration">,
): Composed {
  const { featureClass } = fields;
  const path = fields.shape.present;
  const point = anchorOf(path);
  if (point === null) return { ok: false, field: "point", message: "Put the mark on the map first." };
  if (path.points.some(({ lon, lat }) => kmSquareAt(lon, lat) === null)) {
    return { ok: false, field: "point", message: OUTSIDE_MESSAGE };
  }
  if (featureClass === null) return { ok: false, field: "featureClass", message: "Choose what it looks like." };
  const shapeMessage = pathProblem(path, meta.shapes);
  if (shapeMessage) return { ok: false, field: "path", message: shapeMessage };
  const note = fields.note.trim();
  return {
    ok: true,
    draft: {
      point,
      path: path.points.length > 1 ? apiPath(path) : null,
      feature_class: featureClass,
      period: fields.period,
      title: fields.title.trim() || suggestTitle(meta, featureClass, point),
      description: note === "" ? null : note,
      view_state: viewStateFrom(map),
    },
  };
}

/** Error codes that are about where the mark is, so the message goes by the point. */
const PLACE_CODES = new Set(["outside_british_isles"]);
/** Error codes about the line or shape. The server's message says what to change. */
const SHAPE_CODES = new Set([
  "location_required",
  "outline_too_far",
  "points_too_close",
  "path_too_many_points",
  "shape_too_complex",
  "shape_too_big",
  "line_too_long",
  "shape_crosses_itself",
  "unknown_curve",
  "looked_at_moved",
]);

/** What a refused save means, in plain words, and which part of the form it is about. */
export function saveProblem(error: unknown): { field: MarkProblemField | null; message: string } {
  if (error instanceof ApiError) {
    if (PLACE_CODES.has(error.code)) return { field: "point", message: OUTSIDE_MESSAGE };
    if (SHAPE_CODES.has(error.code)) return { field: "path", message: error.message };
    return { field: null, message: error.message };
  }
  return { field: null, message: "Something went wrong while saving it." };
}
