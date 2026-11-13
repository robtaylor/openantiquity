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
import { useAccountUi } from "../account/requireAccount.js";
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
import { DrawingSection, useMarkInView } from "./MarkForm.js";
import { MARK_PATH_LAYERS } from "./MarkLayer.js";
import { useMarkPath, useMarkStore } from "./markStore.js";
import { anchorOf, apiPath, type Path } from "./path.js";
import "./mark.css";

export const LOOKED_AT_SOURCE = "mark-looked-at";
export const LOOKED_AT_LAYER = "mark-looked-at-line";

export const CHANGED_ELSEWHERE = "The shape was changed somewhere else while you had it open. This is it as it is now.";
export const CHANGED_UNDER_YOU =
  "The shape was changed somewhere else while you had it open, so what is here can't be saved over it.";

/** The address of the tool for a saved finding. */
export function changeShapePath(publicId: string): string {
  return `/mark/finding/${encodeURIComponent(publicId)}`;
}

function editingPrefix(publicId: string): string {
  return `finding:${publicId}:`;
}

/**
 * How the tool names the path it was given: the finding and the shape
 * revision the change begins on, so it is taken up once and not over a
 * change in progress.
 */
function editingKey(finding: FindingDetail): string {
  return `${editingPrefix(finding.public_id)}${finding.location.shape.revision ?? 0}`;
}

/** The revision the change in the tool began on, or null when the tool holds no change to this finding. */
function baseRevision(editing: string | null, publicId: string): number | null {
  const prefix = editingPrefix(publicId);
  if (!editing?.startsWith(prefix)) return null;
  const revision = Number(editing.slice(prefix.length));
  // A key this panel didn't make holds no change it can save.
  return Number.isInteger(revision) ? revision : null;
}

/**
 * The saved path, or the finding's one point when it has no shape. Null
 * when its shape can't be read as a path: an old shape of several parts or
 * with holes, which can be replaced but not changed point by point.
 */
export function savedPath(finding: FindingDetail): Path | null {
  const { path, outline, lon, lat } = finding.location;
  if (path) return { closed: path.closed, points: path.points.map(({ lon, lat, kind }) => ({ lon, lat, kind })) };
  if (outline) return null;
  return { closed: false, points: [{ lon, lat, kind: "corner" }] };
}

/**
 * The body that saves `path` over the finding's shape, begun on shape
 * `revision`, or null when there is nothing to save.
 */
export function changeBody(finding: FindingDetail, path: Path, revision: number): FindingUpdate | null {
  const hadShape = finding.location.path !== null || finding.location.outline !== null;
  if (path.points.length >= 2) return { path: apiPath(path), path_revision: revision };
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
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const saved = useMemo(() => savedPath(finding), [finding]);
  const key = editingKey(finding);
  const base = baseRevision(editing, finding.public_id);
  const ready = base !== null;
  // The tool holds a change begun on an older shape than the finding's now.
  const stale = editing !== null && ready && editing !== key;
  const { lon, lat } = finding.location;

  const takeUpSaved = useCallback((): void => {
    const anchor: Path = { closed: false, points: [{ lon, lat, kind: "corner" }] };
    useMarkStore.getState().edit(key, saved ?? anchor);
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
    if (saving || stale || base === null) return;
    const mark = useMarkStore.getState();
    const body = changeBody(finding, mark.shape.present, base);
    if (body === null) {
      if (mark.shape.present.points.length === 0) {
        mark.setProblem({ field: "path", message: "Put at least one point down, or cancel to leave it as it was." });
        return;
      }
      navigate(findingPath(finding.public_id));
      return;
    }
    mark.setProblem(null);
    setNotice(null);
    setSaving(true);
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
      setSaving(false);
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
        <Button variant="ghost" onClick={() => navigate(findingPath(finding.public_id))}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

/**
 * The panel at `/mark/finding/:publicId`. Escape, or closing it, stops
 * adding points first, as marking does, then goes back to the finding.
 */
export function ChangeShapePanel({ meta }: { meta: Meta }) {
  const { publicId = "" } = useParams();
  const navigate = useNavigate();
  const query = useFinding(publicId);
  const finding = query.data;
  useDocumentTitle("Change the shape");

  function leave(): void {
    const mark = useMarkStore.getState();
    if (mark.drawing && mark.shape.present.points.length > 0) {
      mark.finish();
      return;
    }
    navigate(findingPath(publicId));
  }
  const leaveRef = useRef(leave);
  leaveRef.current = leave;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (useAccountUi.getState().sheet !== null) return;
      if (event.target instanceof Element && event.target.closest('[role="dialog"], .fc-panel')) return;
      leaveRef.current();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

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
