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
export function useLeaveOnEscape(leave: () => void): () => void {
  const leaveRef = useRef(leave);
  leaveRef.current = leave;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (useAccountUi.getState().sheet !== null) return;
      if (event.target instanceof Element && event.target.closest('[role="dialog"], .fc-panel')) return;
      finishOrLeave(leaveRef.current);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return () => finishOrLeave(leaveRef.current);
}

function finishOrLeave(leave: () => void): void {
  const mark = useMarkStore.getState();
  if (mark.drawing && mark.shape.present.points.length > 0) {
    mark.finish();
    return;
  }
  leave();
}
