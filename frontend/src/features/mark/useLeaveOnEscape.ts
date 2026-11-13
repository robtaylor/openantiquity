import { useEffect, useRef } from "react";
import { useAccountUi } from "../account/requireAccount.js";
import { useMarkStore } from "./markStore.js";

/**
 * Escape, from anywhere on the page, leaves a drawing panel, unless
 * something else on screen took it: a dialog, the sign-in sheet or another
 * panel. While points are being added it stops adding them first, keeping
 * what was drawn, and only the next Escape calls `leave`.
 *
 * Returns the same step for the panel's close button.
 */
export function useLeaveOnEscape(leave: () => void, own: () => boolean = () => true): () => void {
  // `own` says whether what the tool holds is this panel's to finish. What it holds for another
  // panel, behind a question this one is asking, is left exactly as it is.
  const leaveRef = useRef(leave);
  leaveRef.current = () => finishOrLeave(leave, own());

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

  return () => leaveRef.current();
}

function finishOrLeave(leave: () => void, own: boolean): void {
  const mark = useMarkStore.getState();
  // A marking set aside isn't being drawn here, so there is nothing to stop first.
  if (own && !mark.setAside && mark.drawing && mark.shape.present.points.length > 0) {
    mark.finish();
    return;
  }
  leave();
}
