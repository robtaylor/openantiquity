import { useEffect } from "react";
import { findView, type Meta } from "../api/meta.js";
import { toast, useToastStore } from "../ui/toastStore.js";
import { changedAny, type MapState, useMapStore } from "./store.js";
import { usesElevation } from "./style.js";
import { DEM_TROUBLE_KEY, isOverlayTroubleKey, overlayTroubleKey, viewTroubleKey } from "./trouble.js";

/** Something on the map that is not loading, in words. Trying it again is `retrySource(key)`. */
export interface TileNotice {
  message: string;
}

/** The fields of the map state that decide which notices are up. */
const NOTICE_KEYS = ["overlays", "failing", "mainView", "compareView", "terrain"] as const satisfies ReadonlyArray<
  keyof MapState
>;

type NoticeState = Pick<MapState, (typeof NOTICE_KEYS)[number]>;

/**
 * The notices the map state calls for, by key. Only what is on screen is
 * mentioned: an overlay that is switched on, a view in one of the panes, and
 * the elevation data while raking light or 3D is using it.
 */
export function noticesFor(meta: Meta, state: NoticeState): Map<string, TileNotice> {
  const notices = new Map<string, TileNotice>();

  for (const overlay of meta.layers.overlays) {
    const key = overlayTroubleKey(overlay.id);
    if (!state.overlays[overlay.id]?.visible || !state.failing[key]) continue;
    notices.set(key, { message: `The ${overlay.title} layer isn't loading, so it's switched off for now.` });
  }

  const shown = [state.mainView, state.compareView];
  for (const id of shown) {
    const view = id === null ? undefined : findView(meta, id);
    if (!view || !state.failing[viewTroubleKey(view.id)]) continue;
    notices.set(viewTroubleKey(view.id), { message: `The ${view.title} layer isn't loading.` });
  }

  if (usesElevation(meta, state.terrain.enabled, shown) && state.failing[DEM_TROUBLE_KEY]) {
    notices.set(DEM_TROUBLE_KEY, { message: "The height data isn't loading, so raking light and 3D may be blank." });
  }

  return notices;
}

/** True for a change to what is on screen, as opposed to a change in what is failing. */
function shownChanged(next: MapState, previous: MapState): boolean {
  return changedAny(next, previous, ["overlays", "mainView", "compareView", "terrain"]);
}

/**
 * Says so when part of the map is not loading, and offers another attempt.
 * Each problem gets one notice that stays until it is dismissed, retried, or
 * no longer true.
 */
export function useTileNotices(meta: Meta): void {
  useEffect(() => {
    /** Toast id for each notice already raised, including ones the person has since dismissed. */
    const raised = new Map<string, number>();

    /** `fresh` is true when what is on screen has changed, rather than what is failing. */
    function sync(state: MapState, fresh: boolean): void {
      const notices = noticesFor(meta, state);
      for (const [key, id] of raised) {
        if (notices.has(key)) continue;
        useToastStore.getState().dismiss(id);
        raised.delete(key);
      }
      for (const [key, notice] of notices) {
        if (raised.has(key)) continue;
        raised.set(
          key,
          toast(notice.message, {
            kind: "error",
            duration: 0,
            action: { label: "Try again", onClick: () => useMapStore.getState().retrySource(key) },
          }),
        );
      }
      // Trouble with a view or the elevation data that has left the screen is
      // forgotten and tried again, so it gets a fresh start when it comes back.
      // A mark for one already off screen is simply dropped. Overlays keep
      // theirs, and stay off until someone tries them again.
      for (const [key, failing] of Object.entries(state.failing)) {
        if (!failing || notices.has(key) || isOverlayTroubleKey(key)) continue;
        if (fresh) state.retrySource(key);
        else state.setSourceFailing(key, false);
      }
    }

    sync(useMapStore.getState(), true);
    const unsubscribe = useMapStore.subscribe((next, previous) => {
      if (next.meta !== null && changedAny(next, previous, NOTICE_KEYS)) sync(next, shownChanged(next, previous));
    });
    return () => {
      unsubscribe();
      for (const id of raised.values()) useToastStore.getState().dismiss(id);
    };
  }, [meta]);
}
