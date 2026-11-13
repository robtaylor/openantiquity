/**
 * "Change the shape": the drawing tool opened on a saved finding, at
 * `/mark/finding/:publicId`, for whoever the server lets edit it
 * (`actions.edit`, Decision 0029). The tool is given the saved path and
 * hands back the changed one; this panel alone knows that it is saved with
 * `PATCH /findings/{id}`, naming the revision it started from.
 *
 * - A 409 `shape_changed` means the shape was changed elsewhere meanwhile:
 *   the finding is asked for again and shown as it now is, with a sentence
 *   saying so.
 * - The finding may also come back newer while the panel is open, when the
 *   window regains focus or another tab extends the line. With nothing
 *   changed here the newer shape is taken up. With a change in progress the
 *   change stays, with its undo, Save is off, and one button takes up the
 *   shape as it now is, so the change is never saved over a shape it didn't
 *   start from.
 * - A 422 `looked_at_moved` is said beside the path, and the change is kept
 *   so the finder can put it right.
 * - The ground earlier second looks were given on (`location.shape.looked_at`,
 *   sent only to someone who may change the finding) is drawn as a faint
 *   line under the path while the panel is open.
 */

import { useQueryClient } from "@tanstack/react-query";
import { MapPinned } from "lucide-react";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { useMainMap } from "../../map/mainMap.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { toast } from "../../ui/toastStore.js";
import { COLOURS } from "../../ui/tokens.js";
import { isShapeChanged, updateFinding } from "../finding/api.js";
import { findingPageKeys } from "../finding/keys.js";
import { frameExtent, whenStageSettled } from "../finding/mapView.js";
import type { FindingDetail, FindingUpdate } from "../finding/types.js";
import { findingQuery, refreshFindingLists, useFinding } from "../finding/useFinding.js";
import { findingPath } from "../findings/selection.js";
import type { GeoJSONGeometry } from "../findings/types.js";
import { useDocumentTitle } from "../placeholders.js";
import { EMPTY_COLLECTION, type FeatureCollection } from "../records/geojson.js";
import { firstArrival } from "../shell/arrival.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { saveProblem } from "./compose.js";
import { baseRevision, changeShapePath, editingKey } from "./editingKey.js";
import { DrawingSection, useMarkInView } from "./MarkForm.js";
import { MARK_PATH_LAYERS, useSourceData } from "./MarkLayer.js";
import { CARRY_ON, MARK_PATH } from "./markPaths.js";
import { type MarkFields, type Unsaved, unsavedInHand, unsavedKey, useMarkPath, useMarkStore } from "./markStore.js";
import { apiPath, type Path, placesOf, plainPoints, spotPath } from "./path.js";
import { TakeOverNotice } from "./TakeOverNotice.js";
import { useLeaveOnEscape } from "./useLeaveOnEscape.js";
import { draftPath } from "./useSaveMark.js";
import "./mark.css";

export const LOOKED_AT_SOURCE = "mark-looked-at";
export const LOOKED_AT_LAYER = "mark-looked-at-line";

export const CHANGED_ELSEWHERE = "The shape was changed somewhere else while you had it open. This is it as it is now.";
const REPLACE_FIRST = "Draw the new shape first, or cancel to leave it as it was.";
export const CHANGED_UNDER_YOU =
  "The shape was changed somewhere else while you had it open, so what is here can't be saved over it.";

/**
 * The saved path, or the finding's one point when it has no shape. Null
 * when its shape can't be read as a path: an old shape of several parts or
 * with holes, which can be replaced but not changed point by point.
 */
export function savedPath(finding: FindingDetail): Path | null {
  const { path, outline, lon, lat } = finding.location;
  if (path) return { closed: path.closed, points: plainPoints(path.points) };
  if (outline) return null;
  return spotPath([lon, lat]);
}

/**
 * The body that saves `path` over the finding's shape, begun on shape
 * `revision`, or null when there is nothing to save.
 */
export function changeBody(finding: FindingDetail, path: Path, revision: number): FindingUpdate | null {
  const hadShape = finding.location.path !== null || finding.location.outline !== null;
  if (path.points.length >= 2) return { path: apiPath(path), path_revision: revision };
  // An old shape the tool can't read is replaced only by a new one: what the tool holds of it is just its point.
  if (savedPath(finding) === null) return null;
  const [only] = path.points;
  if (!only) return null;
  const location = { type: "Point", coordinates: [only.lon, only.lat] } as unknown as FindingUpdate["location"];
  // Down to one point: the shape goes, and the finding is at that point.
  if (hadShape) return { path: null, path_revision: revision, location };
  return only.lon === finding.location.lon && only.lat === finding.location.lat ? null : { location };
}

function lookedAtFeatures(geometry: GeoJSONGeometry | null | undefined): FeatureCollection {
  if (!geometry) return EMPTY_COLLECTION;
  return { type: "FeatureCollection", features: [{ type: "Feature", geometry, properties: {} }] } as FeatureCollection;
}

function addLookedAtLayer(map: MapLibreMap): void {
  map.addLayer(
    {
      id: LOOKED_AT_LAYER,
      type: "line",
      source: LOOKED_AT_SOURCE,
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": COLOURS.text, "line-width": 9, "line-opacity": 0.22 },
    },
    map.getLayer(MARK_PATH_LAYERS.fill) ? MARK_PATH_LAYERS.fill : undefined,
  );
}

/** The faint under-line of what was looked at, under the path's own line where the map draws it. */
function useLookedAtOnMap(map: MapLibreMap | null, geometry: GeoJSONGeometry | null | undefined): void {
  const data = useMemo(() => lookedAtFeatures(geometry), [geometry]);
  useSourceData(map, LOOKED_AT_SOURCE, data, addLookedAtLayer, true);
}

/** Whether what the tool holds is this finding's shape, taken up here. */
function holdsThisFinding(publicId: string): boolean {
  return baseRevision(useMarkStore.getState().editing, publicId) !== null;
}

/**
 * Cancel, or closing the panel: the change is thrown away, so the tool opens
 * again on the saved shape. What the tool holds for something else, which
 * this panel only asked about, is left as it is.
 */
function discardAndLeave(navigate: ReturnType<typeof useNavigate>, publicId: string): void {
  if (holdsThisFinding(publicId)) useMarkStore.getState().start();
  navigate(findingPath(publicId));
}

/** What would be discarded, in words, and the way back to it. */
const IN_THE_WAY: Record<Unsaved["kind"], string> = {
  marking: "You have an unfinished marking. Changing this shape would discard it.",
  change: "You have a change to another finding's shape that isn't saved. Changing this shape would discard it.",
  draft: "You have a draft with changes that aren't kept. Changing this shape would discard them.",
};

/**
 * Something unsaved the tool holds that isn't this finding's, which taking
 * this shape up would throw away without a word. A draft as it was kept, and
 * a saved shape taken up and not changed, are no loss.
 */
function inTheWayOf(publicId: string, state: MarkFields): Unsaved | null {
  const held = unsavedInHand(state);
  return held?.kind === "change" && held.publicId === publicId ? null : held;
}

function wayBackTo(held: Unsaved): { to: string; state?: object } {
  if (held.kind === "marking") return { to: MARK_PATH, state: CARRY_ON };
  return { to: held.kind === "change" ? changeShapePath(held.publicId) : draftPath(held.draftId) };
}

function NotYours({ finding }: { finding: FindingDetail }) {
  const navigate = useNavigate();
  return (
    <EmptyState
      icon={<MapPinned size={22} />}
      title="You can't change this shape"
      action={<Button onClick={() => navigate(findingPath(finding.public_id))}>Back to the finding</Button>}
    >
      <p>Only the person who marked a finding can change its shape.</p>
    </EmptyState>
  );
}

function ChangeShape({ meta, finding }: { meta: Meta; finding: FindingDetail }) {
  const { pathname } = useLocation();
  const environment = usePanelEnvironment();
  const map = useMainMap();
  const client = useQueryClient();
  const navigate = useNavigate();
  const path = useMarkPath();
  const drawing = useMarkStore((state) => state.drawing);
  const editing = useMarkStore((state) => state.editing);
  const saving = useMarkStore((state) => state.saving);
  const [notice, setNotice] = useState<string | null>(null);
  const saved = useMemo(() => savedPath(finding), [finding]);
  const key = editingKey(finding);
  const base = baseRevision(editing, finding.public_id);
  const ready = base !== null;
  // The tool holds a change begun on an older shape than the finding's now.
  const stale = editing !== null && ready && editing !== key;
  const { lon, lat } = finding.location;
  const unsaved = useMarkStore((state) => state.shape.past.length > 0);
  // A change left unsaved by leaving some other way than Cancel, such as the tab bar or Back, is picked up again.
  const [resumed, setResumed] = useState(() => {
    const mark = useMarkStore.getState();
    return baseRevision(mark.editing, finding.public_id) !== null && mark.shape.past.length > 0;
  });

  const takeUpSaved = useCallback((): void => {
    useMarkStore.getState().edit(key, saved ?? spotPath([lon, lat]));
  }, [key, saved, lon, lat]);
  // Something unsaved the tool already holds, which taking this shape up would throw away. Followed as
  // text, so the question goes when what it is about goes, as when the person signs out.
  const heldKey = useMarkStore((state) => {
    const held = inTheWayOf(finding.public_id, state);
    return held === null ? null : unsavedKey(state);
  });

  // The saved path is taken up once per revision, so a change in progress survives the panel going and coming back.
  // A newer revision is taken up only when nothing has been changed here: otherwise the change stays, and `stale` says so.
  // It is framed on the map as it is taken up, once the panel or the sheet has settled.
  useEffect(() => {
    const mark = useMarkStore.getState();
    if (mark.editing === key) return;
    if (baseRevision(mark.editing, finding.public_id) !== null && mark.shape.past.length > 0) return;
    // It is asked about first. Until then nothing is taken up, and the tool isn't open on either.
    if (heldKey === null) takeUpSaved();
  }, [key, finding.public_id, takeUpSaved, heldKey]);
  const framed = useRef<string | null>(null);
  useEffect(() => {
    if (!ready || framed.current === editing) return;
    return whenStageSettled(() => {
      framed.current = editing;
      // Once for each taking up of the shape, and not again when the Layers panel has been over it.
      if (!firstArrival(pathname, `frame ${editing}`)) return;
      const { points } = useMarkStore.getState().shape.present;
      frameExtent(
        points.map(({ lon, lat }) => [lon, lat] as const),
        { keepOwnView: finding.public_id },
      );
    });
  }, [ready, editing, finding.public_id, pathname]);

  const lookedAt = finding.location.shape.looked_at;
  useLookedAtOnMap(ready ? map : null, lookedAt);
  useMarkInView(
    useMemo(() => placesOf(path), [path]),
    drawing,
  );

  async function save(): Promise<void> {
    const mark = useMarkStore.getState();
    if (mark.saving || stale || base === null) return;
    const body = changeBody(finding, mark.shape.present, base);
    if (body === null) {
      if (saved === null) {
        mark.setProblem({ field: "path", message: REPLACE_FIRST });
        return;
      }
      if (mark.shape.present.points.length === 0) {
        mark.setProblem({ field: "path", message: "Put at least one point down, or cancel to leave it as it was." });
        return;
      }
      navigate(findingPath(finding.public_id));
      return;
    }
    mark.setProblem(null);
    setNotice(null);
    mark.setSaving(true);
    try {
      const updated = await updateFinding(finding.public_id, body);
      client.setQueryData(findingPageKeys.detail(updated.public_id), updated);
      refreshFindingLists(client);
      useMarkStore.getState().start();
      navigate(findingPath(updated.public_id), { replace: true });
      toast("The new shape is saved.", { kind: "success" });
    } catch (error) {
      if (isShapeChanged(error)) {
        // Nothing of the change is kept: it was made to a shape that is no longer there.
        const fresh = await client.fetchQuery({ ...findingQuery(finding.public_id), staleTime: 0 }).catch(() => null);
        if (fresh) {
          const again = savedPath(fresh);
          if (again) useMarkStore.getState().edit(editingKey(fresh), again);
        }
        setNotice(CHANGED_ELSEWHERE);
        return;
      }
      const problem = saveProblem(error);
      if (problem.field) {
        useMarkStore.getState().setProblem({ field: "path", message: problem.message });
        // On a phone the sheet may have the reason below its fold: it is brought into sight.
        requestAnimationFrame(() =>
          document.querySelector(".fc-mark .fc-mark__problem")?.scrollIntoView?.({ block: "nearest" }),
        );
      } else toast(`The shape couldn't be saved. ${problem.message}`, { kind: "error" });
    } finally {
      useMarkStore.getState().setSaving(false);
    }
  }

  if (!ready) {
    const held = heldKey === null ? null : inTheWayOf(finding.public_id, useMarkStore.getState());
    if (held === null) return null;
    const back = wayBackTo(held);
    return (
      <TakeOverNotice
        words={IN_THE_WAY[held.kind]}
        back={{ label: "Go back to it", onClick: () => navigate(back.to, { state: back.state }) }}
        on={{ label: "Discard it and change this shape", onClick: takeUpSaved }}
      />
    );
  }
  const limits = meta.shapes;
  return (
    <div className="fc-mark">
      {notice ? (
        <p className="fc-mark__notice" role="status">
          {notice}
        </p>
      ) : null}
      {stale ? (
        <div className="fc-mark__notice" role="status">
          <p>{CHANGED_UNDER_YOU}</p>
          <Button size="sm" onClick={takeUpSaved}>
            Show it as it is now
          </Button>
        </div>
      ) : null}
      {resumed && unsaved && !stale ? (
        <div className="fc-mark__notice" role="status">
          <p>Carrying on from changes you hadn't saved.</p>
          <Button
            size="sm"
            onClick={() => {
              setResumed(false);
              takeUpSaved();
            }}
          >
            Discard them
          </Button>
        </div>
      ) : null}
      {saved === null ? (
        <p className="fc-mark__notice">
          Its shape was drawn before the drawing tool and can't be changed point by point. What you draw here replaces
          it.
        </p>
      ) : null}
      <DrawingSection map={map} isPhone={environment.isPhone} />
      {lookedAt ? (
        <p className="fc-mark__hint">
          The faint line is where others gave second looks. Changes have to keep{" "}
          {Math.round(limits.looked_at_min_kept * 100)}% of it within {Math.round(limits.looked_at_max_move_m)} m of the
          shape.
        </p>
      ) : null}
      <div className="fc-mark__actions">
        <Button variant="primary" disabled={saving || stale} onClick={() => void save()}>
          {saving ? "Saving…" : "Save the shape"}
        </Button>
        <Button variant="ghost" onClick={() => discardAndLeave(navigate, finding.public_id)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

/**
 * The panel at `/mark/finding/:publicId`. Escape, or closing it, stops
 * adding points first, as marking does, then throws the change away and
 * goes back to the finding, as Cancel does. Leaving any other way keeps
 * the change, and the panel says so when it is picked up again.
 */
export function ChangeShapePanel({ meta }: { meta: Meta }) {
  const { publicId = "" } = useParams();
  const navigate = useNavigate();
  const query = useFinding(publicId);
  const finding = query.data;
  useDocumentTitle("Change the shape");

  const leave = useLeaveOnEscape(
    () => discardAndLeave(navigate, publicId),
    () => holdsThisFinding(publicId),
  );

  return (
    <PanelFrame panelKey={changeShapePath(publicId)} title="Change the shape" subtitle={finding?.title} onClose={leave}>
      {finding ? (
        finding.actions.edit.allowed ? (
          <ChangeShape meta={meta} finding={finding} />
        ) : (
          <NotYours finding={finding} />
        )
      ) : query.isError ? (
        <EmptyState
          tone="error"
          title="This finding couldn't be loaded"
          action={
            <Button variant="primary" onClick={() => void query.refetch()}>
              Try again
            </Button>
          }
        >
          <p>{query.error.message}</p>
        </EmptyState>
      ) : null}
    </PanelFrame>
  );
}
