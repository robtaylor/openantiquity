/**
 * A finding marked by someone not signed in is a draft in this browser
 * (Decision 0002). Its data is the body `POST /findings` will be sent, in
 * the API's own names, so saving it after sign-in sends exactly what was
 * marked. The saver is registered when this module loads, which the shell
 * does at start-up, so drafts left from before a provider's round trip are
 * saved as soon as the person is ready.
 *
 * The server takes no idempotency key yet, so the `draftId` the drafts
 * machinery passes is not sent. The machinery's claim on each draft is what
 * keeps a draft from being sent twice.
 */

import { create } from "zustand";
import { isFiniteNumber, isRecord } from "../../api/guards.js";
import { defineDraftKind } from "../drafts/savers.js";
import { DRAFT_KINDS } from "../drafts/store.js";
import { createFinding } from "../findings/api.js";
import type { FeatureClassId, FindingCreate, FindingDetail, GeoJSONGeometry, PeriodId } from "../findings/types.js";
import type { LngLat } from "./outline.js";

/** What a finding draft holds: the request body, with the point kept as a pair for drawing. */
export interface FindingDraft {
  point: LngLat;
  feature_class: string;
  period: string;
  title: string;
  description: string | null;
  outline: GeoJSONGeometry | null;
  view_state: NonNullable<FindingCreate["view_state"]>;
}

function isLngLat(value: unknown): value is LngLat {
  return Array.isArray(value) && value.length === 2 && value.every(isFiniteNumber);
}

function isGeometry(value: unknown): value is GeoJSONGeometry {
  return isRecord(value) && typeof value.type === "string" && Array.isArray(value.coordinates);
}

/** The draft's data, if it can be read back: storage may hold an old or damaged copy. */
export function parseFindingDraft(value: unknown): FindingDraft | null {
  if (!isRecord(value)) return null;
  const { point, feature_class: featureClass, period, title, description, outline, view_state: viewState } = value;
  if (!isLngLat(point) || typeof featureClass !== "string" || featureClass === "") return null;
  if (typeof period !== "string" || typeof title !== "string" || title === "") return null;
  if (description !== null && typeof description !== "string") return null;
  if (outline !== null && !isGeometry(outline)) return null;
  if (!isRecord(viewState)) return null;
  return {
    point: [point[0], point[1]],
    feature_class: featureClass,
    period,
    title,
    description,
    outline,
    view_state: viewState,
  };
}

/**
 * The body for `POST /findings`. Class and period ids come from `/meta`,
 * which is the server's own vocabulary, so they are the server's to judge.
 */
export function createBody(draft: FindingDraft): FindingCreate {
  const body: FindingCreate = {
    location: { type: "Point", coordinates: [draft.point[0], draft.point[1]] },
    feature_class: draft.feature_class as FeatureClassId,
    period: draft.period as PeriodId,
    title: draft.title,
    view_state: draft.view_state,
  };
  if (draft.description) body.description = draft.description;
  if (draft.outline) body.outline = draft.outline;
  return body;
}

interface SavedDrafts {
  /** The finding each draft became, by draft id, for drafts saved in this page. */
  saved: Readonly<Record<string, FindingDetail>>;
  record: (draftId: string, finding: FindingDetail) => void;
}

/**
 * Drafts saved since the page loaded. A mark panel showing a draft that has
 * just been saved opens the finding it became, and the map asks for its
 * findings again, through this.
 */
export const useSavedDrafts = create<SavedDrafts>()((set) => ({
  saved: {},
  record: (draftId, finding) => set((state) => ({ saved: { ...state.saved, [draftId]: finding } })),
}));

export const findingDrafts = defineDraftKind<FindingDraft>({
  kind: DRAFT_KINDS.finding,
  label: "Finding",
  parse: parseFindingDraft,
  save: async (data, { draftId }) => {
    useSavedDrafts.getState().record(draftId, await createFinding(createBody(data)));
  },
  describe: (data) => data.title,
});
