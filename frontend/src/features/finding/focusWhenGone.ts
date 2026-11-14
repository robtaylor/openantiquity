import { useEffect, useRef } from "react";
import { focusAfter } from "../mark/focus.js";

/** The panel's title, where focus goes when nothing nearer is left. */
export const PANEL_TITLE = ".fc-panel__title";

/**
 * For a part of the page that goes once the person has acted on it, such as
 * an offer they answered: call `arm` as they act, and when `present` turns
 * false focus goes to `target`, if focus was lost with the part (`focusAfter`).
 * Something that goes for another reason, such as a refresh, moves nothing.
 */
export function useFocusWhenGone(present: boolean, target: string): () => void {
  const armed = useRef(false);
  useEffect(() => {
    if (present || !armed.current) return;
    armed.current = false;
    focusAfter(null, target);
  }, [present, target]);
  return () => {
    armed.current = true;
  };
}
