/**
 * A finding marked by someone not signed in is a draft in this browser
 * (Decision 0002). Its data is the body `POST /findings` will be sent, in
 * the API's own names, so saving it after sign-in sends exactly what was
 * marked. The saver is registered when this module loads, which the shell
 * does at start-up, so drafts left from before a provider's round trip are
 * saved as soon as the person is ready.
 *
 * The draft's id goes as the finding's `client_ref`, so a draft sent again
 * after a tab died mid-save is stored once: the server answers a reference it
 * has seen from the same person with the finding it already made.
 */

import { create } from "zustand";
import { isFiniteNumber, isRecord } from "../../api/guards.js";
import { onPersonChanged } from "../account/session.js";
import { defineDraftKind } from "../drafts/savers.js";
import { DRAFT_KINDS } from "../drafts/store.js";
import { createFinding } from "../findings/api.js";
import type { FeatureClassId, FindingCreate, FindingDetail, PeriodId } from "../findings/types.js";
import { apiPath, type LngLat, type PathPoint } from "./path.js";

/** A draft's line or shape: two points or more, in the API's form. */
export interface DraftPath {
  closed: boolean;
  points: PathPoint[];
}

/**
 * What a finding draft holds: the request body, in the API's names. `point`
 * is the spot, or for a line or shape near where the server will anchor
 * it, kept so the draft can be drawn on the map. `path` is null for a spot.
 */
export interface FindingDraft {
  point: LngLat;
  path: DraftPath | null;
  feature_class: string;
  period: string;
  title: string;
  description: string | null;
  view_state: NonNullable<FindingCreate["view_state"]>;
}

function isLngLat(value: unknown): value is LngLat {
  return Array.isArray(value) && value.length === 2 && value.every(isFiniteNumber);
}

function isPathPoint(value: unknown): value is PathPoint {
  return (
    isRecord(value) &&
    isFiniteNumber(value.lon) &&
    isFiniteNumber(value.lat) &&
    (value.kind === "corner" || value.kind === "smooth")
  );
}

/** A stored path, if it can be read: two points or more, three when closed. */
function readPath(value: unknown): DraftPath | null {
  if (!isRecord(value) || typeof value.closed !== "boolean" || !Array.isArray(value.points)) return null;
  const { closed, points } = value;
  if (!points.every(isPathPoint) || points.length < (closed ? 3 : 2)) return null;
  return { closed, points: points.map(({ lon, lat, kind }) => ({ lon, lat, kind })) };
}

/** The draft's data, if it can be read back: storage may hold an old or damaged copy. */
export function parseFindingDraft(value: unknown): FindingDraft | null {
  if (!isRecord(value)) return null;
  const { point, feature_class: featureClass, period, title, description, view_state: viewState } = value;
  if (!isLngLat(point) || typeof featureClass !== "string" || featureClass === "") return null;
  if (typeof period !== "string" || typeof title !== "string" || title === "") return null;
  if (description !== null && typeof description !== "string") return null;
  if (!isRecord(viewState)) return null;
  return {
    point: [point[0], point[1]],
    path: readPath(value.path),
    feature_class: featureClass,
    period,
    title,
    description,
    view_state: viewState,
  };
}

/**
 * The body for `POST /findings`. Class and period ids come from `/meta`,
 * which is the server's own vocabulary, so they are the server's to judge.
 * `clientRef` is the same for every attempt to save one finding.
 *
 * A spot is sent as its `location` alone. A line or shape is sent as its
 * `path` alone, and the server chooses where to anchor it (Decision 0028).
 */
export function createBody(draft: FindingDraft, clientRef: string): FindingCreate {
  const body: FindingCreate = {
    client_ref: clientRef,
    ...(draft.path
      ? { path: apiPath(draft.path) }
      : { location: { type: "Point", coordinates: [draft.point[0], draft.point[1]] } }),
    feature_class: draft.feature_class as FeatureClassId,
    period: draft.period as PeriodId,
    title: draft.title,
    view_state: draft.view_state,
  };
  if (draft.description) body.description = draft.description;
  return body;
}

interface SavedDrafts {
  /** The finding each draft became, by draft id, for drafts saved in this page and not yet opened. */
  saved: Readonly<Record<string, FindingDetail>>;
  /** How many drafts have been saved in this page, so the map knows when to ask again. */
  count: number;
  record: (draftId: string, finding: FindingDetail) => void;
  /** Forget one, once its finding has been opened. */
  forget: (draftId: string) => void;
  clear: () => void;
}

/**
 * Drafts saved since the page loaded. A mark panel showing a draft that has
 * just been saved opens the finding it became, and the map asks for its
 * findings again, through this. The finding is as its finder sees it, exact
 * place and all, so it is forgotten once opened and when the person changes.
 */
export const useSavedDrafts = create<SavedDrafts>()((set) => ({
  saved: {},
  count: 0,
  record: (draftId, finding) =>
    set((state) => ({ saved: { ...state.saved, [draftId]: finding }, count: state.count + 1 })),
  forget: (draftId) =>
    set((state) => {
      if (!(draftId in state.saved)) return state;
      const { [draftId]: _opened, ...rest } = state.saved;
      return { saved: rest };
    }),
  clear: () => set({ saved: {} }),
}));

onPersonChanged(() => useSavedDrafts.getState().clear());

export const findingDrafts = defineDraftKind<FindingDraft>({
  kind: DRAFT_KINDS.finding,
  label: "Finding",
  parse: parseFindingDraft,
  save: async (data, { draftId }) => {
    useSavedDrafts.getState().record(draftId, await createFinding(createBody(data, draftId)));
  },
  describe: (data) => data.title,
});
