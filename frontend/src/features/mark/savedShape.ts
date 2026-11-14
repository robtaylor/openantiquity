/**
 * What "Change the shape" and "Suggest a change" share: the drawing tool
 * taken up on a saved finding's shape, under a key of the panel's own kind
 * (`editingKey`), and the question each asks before it takes the tool over
 * from something unsaved (`Unsaved`). Neither the tool nor the store knows
 * which of the two it is working for. The panels differ only in how they
 * send the result and in what Close does with it.
 */

import type { QueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router";
import { frameExtent, whenStageSettled } from "../finding/mapView.js";
import type { FindingDetail } from "../finding/types.js";
import { findingQuery, refreshFindingLists } from "../finding/useFinding.js";
import { firstArrival } from "../shell/arrival.js";
import { baseRevision, changeShapePath, type EditingKind, editingKey, suggestPath } from "./editingKey.js";
import { CARRY_ON, MARK_PATH } from "./markPaths.js";
import { type MarkFields, type Unsaved, unsavedInHand, unsavedKey, useMarkStore } from "./markStore.js";
import { type Path, plainPoints, spotPath } from "./path.js";
import { draftPath } from "./useSaveMark.js";

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

/** Whether what the tool holds is this finding's shape, taken up here for `kind`. */
export function holdsThisFinding(publicId: string, kind: EditingKind): boolean {
  return baseRevision(useMarkStore.getState().editing, publicId, kind) !== null;
}

/** What would be discarded, in words, ending with what taking the tool over would do, such as "Changing this shape". */
export function inTheWayWords(doing: string): Record<Unsaved["kind"], string> {
  return {
    marking: `You have an unfinished marking. ${doing} would discard it.`,
    change: `You have a change to another finding's shape that isn't saved. ${doing} would discard it.`,
    suggestion: `You have a suggested change to a finding's shape that isn't sent. ${doing} would discard it.`,
    draft: `You have a draft with changes that aren't kept. ${doing} would discard them.`,
  };
}

/**
 * Something unsaved the tool holds that isn't this panel's own for this
 * finding, which taking this shape up would throw away without a word. A
 * draft as it was kept, and a saved shape taken up and not changed, are no
 * loss.
 */
export function inTheWayOf(publicId: string, kind: EditingKind, state: MarkFields): Unsaved | null {
  const held = unsavedInHand(state);
  const own = kind === "finding" ? "change" : "suggestion";
  return held !== null && held.kind === own && held.publicId === publicId ? null : held;
}

/** The way back to what the tool holds. */
export function wayBackTo(held: Unsaved): { to: string; state?: object } {
  switch (held.kind) {
    case "marking":
      return { to: MARK_PATH, state: CARRY_ON };
    case "change":
      return { to: changeShapePath(held.publicId) };
    case "suggestion":
      return { to: suggestPath(held.publicId) };
    case "draft":
      return { to: draftPath(held.draftId) };
  }
}

export interface SavedShapeInTool {
  /** The shape as saved, or null for an old shape the tool can't read point by point. */
  saved: Path | null;
  /** The key for the shape as it is now. */
  key: string;
  /** The revision what the tool holds began on, or null while it holds nothing of this finding's. */
  base: number | null;
  /** The tool holds this finding's shape, taken up for this panel. */
  ready: boolean;
  /** The tool holds a change begun on an older shape than the finding's now. */
  stale: boolean;
  /** Something has been changed since the shape was taken up. */
  unsaved: boolean;
  /** The panel opened on a change left unsent some other way, and says so until it is thrown away. */
  resumed: boolean;
  dropResumed: () => void;
  /** Take the saved shape up afresh, throwing away what the tool holds. */
  takeUpSaved: () => void;
  /** Something unsaved the tool holds that isn't this panel's, as text, or null. */
  heldKey: string | null;
}

/**
 * Take the finding's saved shape up in the tool for a panel of `kind`, once
 * per revision, so a change in progress survives the panel going and coming
 * back. A newer revision is taken up only when nothing has been changed
 * here: otherwise the change stays, and `stale` says so. Something unsaved
 * that isn't this panel's is asked about first (`heldKey`), and until then
 * nothing is taken up. The shape is framed on the map as it is taken up,
 * once the panel or the sheet has settled.
 */
export function useSavedShapeInTool(finding: FindingDetail, kind: EditingKind): SavedShapeInTool {
  const { pathname } = useLocation();
  const editing = useMarkStore((state) => state.editing);
  const saved = useMemo(() => savedPath(finding), [finding]);
  const key = editingKey(finding, kind);
  const base = baseRevision(editing, finding.public_id, kind);
  const ready = base !== null;
  const stale = editing !== null && ready && editing !== key;
  const { lon, lat } = finding.location;
  const unsaved = useMarkStore((state) => state.shape.past.length > 0);
  // A change left unsent by leaving some other way, such as the tab bar or Back, is picked up again.
  const [resumed, setResumed] = useState(() => {
    const mark = useMarkStore.getState();
    return baseRevision(mark.editing, finding.public_id, kind) !== null && mark.shape.past.length > 0;
  });

  // What "Mark a finding" set aside while it asked is this panel's to settle on arrival, as
  // `MarkPanel` settles it for a marking: Back and Forward can bring the person here with it
  // still set, and the tool would show its controls and take no taps.
  useEffect(() => {
    if (useMarkStore.getState().setAside) useMarkStore.setState({ setAside: false });
  }, []);

  const takeUpSaved = useCallback((): void => {
    useMarkStore.getState().edit(key, saved ?? spotPath([lon, lat]));
  }, [key, saved, lon, lat]);
  // Followed as text, so the question goes when what it is about goes, as when the person signs out.
  const heldKey = useMarkStore((state) => {
    const held = inTheWayOf(finding.public_id, kind, state);
    return held === null ? null : unsavedKey(state);
  });

  useEffect(() => {
    const mark = useMarkStore.getState();
    if (mark.editing === key) return;
    if (baseRevision(mark.editing, finding.public_id, kind) !== null && mark.shape.past.length > 0) return;
    if (heldKey === null) takeUpSaved();
  }, [key, finding.public_id, kind, takeUpSaved, heldKey]);
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

  return {
    saved,
    key,
    base,
    ready,
    stale,
    unsaved,
    resumed,
    dropResumed: () => setResumed(false),
    takeUpSaved,
    heldKey,
  };
}

/**
 * The revision what the tool holds for this panel can be sent on: the one
 * its key names, as long as that is the shape's revision now (`key`). Null
 * while it holds nothing of this finding's, or a change begun on an older
 * shape, which goes only once the person has said to send it over the newer
 * one. Read from the store, so a step taken just before counts.
 */
export function sendableRevision(publicId: string, kind: EditingKind, key: string): number | null {
  const { editing } = useMarkStore.getState();
  return editing === key ? baseRevision(editing, publicId, kind) : null;
}

/**
 * After a 409 `shape_changed`: the finding is asked for again, so the panel
 * knows the shape as it now is and says so, and the map's findings are, so
 * the map draws it. What the tool holds is left exactly as it is.
 *
 * Answers whether the finding came back. When it didn't, the panel has no
 * newer shape to show its notice against, so the caller must say in its own
 * words that the work wasn't sent: `shapeChangedUnseen`.
 */
export async function learnShapeChanged(client: QueryClient, publicId: string): Promise<boolean> {
  const learnt = await client.fetchQuery({ ...findingQuery(publicId), staleTime: 0 }).then(
    () => true,
    () => false,
  );
  refreshFindingLists(client);
  return learnt;
}

/**
 * What to say when the shape changed under a drawing and the shape as it now
 * is couldn't be loaded: the work is named, and that it is still in hand.
 */
export function shapeChangedUnseen(work: "suggestion" | "change"): string {
  const lost = work === "suggestion" ? "your suggestion wasn't sent" : "your change wasn't saved";
  const again = work === "suggestion" ? "sending" : "saving";
  return `The shape was changed while you were drawing, so ${lost}. Your drawing is still here. The shape as it is now couldn't be loaded: check your connection, then try ${again} again.`;
}
