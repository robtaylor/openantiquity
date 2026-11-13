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
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { isMapLive } from "../../map/MapPane.js";
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
import { PanelFrame } from "../shell/PanelFrame.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { saveProblem } from "./compose.js";
import { baseRevision, changeShapePath, editingKey } from "./editingKey.js";
import { DrawingSection, useMarkInView } from "./MarkForm.js";
import { MARK_PATH_LAYERS } from "./MarkLayer.js";
import { useMarkPath, useMarkStore } from "./markStore.js";
import { anchorOf, apiPath, type Path, plainPoints, spotPath } from "./path.js";
import { useLeaveOnEscape } from "./useLeaveOnEscape.js";
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

/** The faint under-line of what was looked at, under the path's own line where the map draws it. */
function useLookedAtOnMap(map: MapLibreMap | null, geometry: GeoJSONGeometry | null | undefined): void {
  const data = useMemo(() => lookedAtFeatures(geometry), [geometry]);
  useEffect(() => {
    if (!map || !isMapLive(map)) return;
    if (data === EMPTY_COLLECTION && !map.getSource(LOOKED_AT_SOURCE)) return;
    if (!map.getSource(LOOKED_AT_SOURCE)) {
      map.addSource(LOOKED_AT_SOURCE, { type: "geojson", data: EMPTY_COLLECTION });
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
    (map.getSource(LOOKED_AT_SOURCE) as GeoJSONSource | undefined)?.setData(data);
    return () => {
      if (isMapLive(map)) (map.getSource(LOOKED_AT_SOURCE) as GeoJSONSource | undefined)?.setData(EMPTY_COLLECTION);
    };
  }, [map, data]);
}

/** Cancel, or closing the panel: the change is thrown away, so the tool opens again on the saved shape. */
function discardAndLeave(navigate: ReturnType<typeof useNavigate>, publicId: string): void {
  useMarkStore.getState().start();
  navigate(findingPath(publicId));
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

  // The saved path is taken up once per revision, so a change in progress survives the panel going and coming back.
  // A newer revision is taken up only when nothing has been changed here: otherwise the change stays, and `stale` says so.
  // It is framed on the map as it is taken up, once the panel or the sheet has settled.
  useEffect(() => {
    const mark = useMarkStore.getState();
    if (mark.editing === key) return;
    if (baseRevision(mark.editing, finding.public_id) !== null && mark.shape.past.length > 0) return;
    takeUpSaved();
  }, [key, finding.public_id, takeUpSaved]);
  const framed = useRef<string | null>(null);
  useEffect(() => {
    if (!ready || framed.current === editing) return;
    return whenStageSettled(() => {
      framed.current = editing;
      const { points } = useMarkStore.getState().shape.present;
      frameExtent(points.map(({ lon, lat }) => [lon, lat] as const));
    });
  }, [ready, editing]);

  const lookedAt = finding.location.shape.looked_at;
  useLookedAtOnMap(ready ? map : null, lookedAt);
  useMarkInView(
    useMemo(() => anchorOf(path), [path]),
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

  if (!ready) return null;
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

  const leave = useLeaveOnEscape(() => discardAndLeave(navigate, publicId));

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
