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
import { useMemo } from "react";
import { useNavigate, useParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { useMainMap } from "../../map/mainMap.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { toast } from "../../ui/toastStore.js";
import { COLOURS } from "../../ui/tokens.js";
import { isShapeChanged, updateFinding } from "../finding/api.js";
import { findingPageKeys } from "../finding/keys.js";
import type { FindingDetail, FindingUpdate } from "../finding/types.js";
import { refreshFindingLists, useFinding } from "../finding/useFinding.js";
import { findingPath } from "../findings/selection.js";
import type { GeoJSONGeometry } from "../findings/types.js";
import { useDocumentTitle } from "../placeholders.js";
import { EMPTY_COLLECTION, type FeatureCollection } from "../records/geojson.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { ChangedUnderYou } from "./ChangedUnderYou.js";
import { saveProblem } from "./compose.js";
import { changeShapePath, suggestPath } from "./editingKey.js";
import { HeldHere } from "./HeldHere.js";
import { DrawingSection, useMarkInView } from "./MarkForm.js";
import { MARK_PATH_LAYERS, useSourceData } from "./MarkLayer.js";
import { unsavedInHand, useMarkPath, useMarkStore } from "./markStore.js";
import { apiPath, type Path, placesOf } from "./path.js";
import {
  holdsThisFinding,
  inTheWayOf,
  inTheWayWords,
  learnShapeChanged,
  savedPath,
  sendableRevision,
  shapeChangedUnseen,
  useSavedShapeInTool,
  wayBackTo,
} from "./savedShape.js";
import { TakeOverNotice } from "./TakeOverNotice.js";
import { useLeaveOnEscape } from "./useLeaveOnEscape.js";
import "./mark.css";

export { savedPath };

export const LOOKED_AT_SOURCE = "mark-looked-at";
export const LOOKED_AT_LAYER = "mark-looked-at-line";

const REPLACE_FIRST = "Draw the new shape first, or cancel to leave it as it was.";
export const CHANGED_UNDER_YOU =
  "The shape was changed somewhere else while you had it open. Your change hasn't been saved, and it is still here. The map shows the shape as it is now.";

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

/**
 * Cancel, or closing the panel: the change is thrown away, so the tool opens
 * again on the saved shape. What the tool holds for something else, which
 * this panel only asked about, is left as it is.
 */
function discardAndLeave(navigate: ReturnType<typeof useNavigate>, publicId: string): void {
  if (holdsThisFinding(publicId, "finding")) useMarkStore.getState().start();
  navigate(findingPath(publicId));
}

const IN_THE_WAY = inTheWayWords("Changing this shape");

/**
 * For anyone the server doesn't let change the shape. "Suggest a change" is
 * offered only where the server allows a suggestion (`actions.suggest`).
 */
function NotYours({ finding }: { finding: FindingDetail }) {
  const held = useMarkStore((state) => {
    const inHand = unsavedInHand(state);
    return inHand?.kind === "change" && inHand.publicId === finding.public_id;
  });
  return (
    <>
      {held ? (
        <HeldHere
          words="Your change to this shape wasn't saved, and it can't be saved now."
          choices={[{ label: "Discard your change", onClick: () => useMarkStore.getState().start() }]}
        />
      ) : null}
      <NotYoursBody finding={finding} />
    </>
  );
}

function NotYoursBody({ finding }: { finding: FindingDetail }) {
  const navigate = useNavigate();
  const back = <Button onClick={() => navigate(findingPath(finding.public_id))}>Back to the finding</Button>;
  const suggest = finding.actions.suggest.allowed;
  return (
    <EmptyState
      icon={<MapPinned size={22} />}
      title="You can't change this shape"
      action={
        suggest ? (
          <>
            <Button variant="primary" onClick={() => navigate(suggestPath(finding.public_id))}>
              Suggest a change
            </Button>
            {back}
          </>
        ) : (
          back
        )
      }
    >
      <p>Only the keeper of a marking can change its shape.</p>
      {suggest ? <p>You can suggest a change, which its keeper accepts or declines.</p> : null}
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
  const saving = useMarkStore((state) => state.saving);
  const { saved, key, ready, stale, unsaved, resumed, dropResumed, takeUpSaved, heldKey } = useSavedShapeInTool(
    finding,
    "finding",
  );

  const lookedAt = finding.location.shape.looked_at;
  useLookedAtOnMap(ready ? map : null, lookedAt);
  useMarkInView(
    useMemo(() => placesOf(path), [path]),
    drawing,
  );

  async function save(): Promise<void> {
    const mark = useMarkStore.getState();
    const base = sendableRevision(finding.public_id, "finding", key);
    if (mark.saving || base === null) return;
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
        // The change stays in hand with its undo. The panel says so, and the person chooses what next.
        // Without the shape as it now is the panel has nothing to say it against, so a toast does.
        if (!(await learnShapeChanged(client, finding.public_id))) {
          toast(shapeChangedUnseen("change"), { kind: "error" });
        }
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
    const held = heldKey === null ? null : inTheWayOf(finding.public_id, "finding", useMarkStore.getState());
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
      {stale ? (
        <ChangedUnderYou
          words={CHANGED_UNDER_YOU}
          sendLabel="Save it over the shape as it is now"
          onSend={() => {
            useMarkStore.getState().rename(key);
            void save();
          }}
          onStartAgain={takeUpSaved}
        />
      ) : null}
      {resumed && unsaved && !stale ? (
        <div className="fc-mark__notice" role="status">
          <p>Carrying on from changes you hadn't saved.</p>
          <Button
            size="sm"
            onClick={() => {
              dropResumed();
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
    () => holdsThisFinding(publicId, "finding"),
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
