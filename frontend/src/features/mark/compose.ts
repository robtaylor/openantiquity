import { ApiError } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { kmSquareAt } from "../../map/gridref.js";
import type { MapState } from "../../map/store.js";
import { suggestTitle, viewStateFrom } from "./describe.js";
import type { FindingDraft } from "./findingDrafts.js";
import type { MarkFields } from "./markStore.js";
import { outlineGeometry, outlineProblem } from "./outline.js";

export type MarkProblemField = "point" | "featureClass" | "outline";

export type Composed = { ok: true; draft: FindingDraft } | { ok: false; field: MarkProblemField; message: string };

/** Said when the mark is somewhere OpenAntiquity doesn't cover, by the server or before asking it. */
export const OUTSIDE_MESSAGE =
  "OpenAntiquity covers the land of Great Britain, Ireland and their islands. Move the mark onto it.";

/**
 * Turn the form into what is sent, or say what is missing. Only the point
 * and the class are required. An empty title becomes the suggested one, and
 * the view comes from the map as it is now.
 */
export function composeFinding(
  fields: MarkFields,
  meta: Meta,
  map: Pick<MapState, "meta" | "mainView" | "camera" | "sun" | "terrain" | "hillshadeExaggeration">,
): Composed {
  const { point, featureClass } = fields;
  if (point === null) return { ok: false, field: "point", message: "Put the mark on the map first." };
  if (kmSquareAt(point[0], point[1]) === null) return { ok: false, field: "point", message: OUTSIDE_MESSAGE };
  if (featureClass === null) return { ok: false, field: "featureClass", message: "Choose what it looks like." };
  const outlineMessage = outlineProblem(fields.outline, point);
  if (outlineMessage) return { ok: false, field: "outline", message: outlineMessage };
  const note = fields.note.trim();
  return {
    ok: true,
    draft: {
      point,
      feature_class: featureClass,
      period: fields.period,
      title: fields.title.trim() || suggestTitle(meta, featureClass, point),
      description: note === "" ? null : note,
      outline: outlineGeometry(fields.outline),
      view_state: viewStateFrom(map),
    },
  };
}

/** Error codes that are about where the mark is, so the message goes by the point. */
const PLACE_CODES = new Set(["outside_british_isles"]);
const OUTLINE_CODES = new Set(["outline_too_big", "outline_too_far"]);

/** What a refused save means, in plain words, and which part of the form it is about. */
export function saveProblem(error: unknown): { field: MarkProblemField | null; message: string } {
  if (error instanceof ApiError) {
    if (PLACE_CODES.has(error.code)) return { field: "point", message: OUTSIDE_MESSAGE };
    if (OUTLINE_CODES.has(error.code)) return { field: "outline", message: error.message };
    return { field: null, message: error.message };
  }
  return { field: null, message: "Something went wrong while saving it." };
}
