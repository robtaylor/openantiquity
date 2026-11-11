import { useEffect, useRef } from "react";
import { answerForKey } from "../finding/secondLook/AnswerButtons.js";
import type { Visible } from "../finding/types.js";

/** True when a key press belongs to something being typed in, not to the page. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  if (!(target instanceof HTMLInputElement)) return false;
  // Buttons, checkboxes and radios take no text, so a number key there is still an answer.
  return !["button", "checkbox", "radio", "reset", "submit", "range", "color", "file", "image"].includes(target.type);
}

/**
 * The keys 1, 2 and 3 give the three answers while `active`. They do
 * nothing while a text field has focus, while a dialog such as the sign-in
 * sheet is open, or with a modifier held, so typing a number into a note or
 * a search never answers a second look.
 */
export function useAnswerKeys(active: boolean, onAnswer: (visible: Visible) => void): void {
  const latest = useRef(onAnswer);
  latest.current = onAnswer;
  useEffect(() => {
    if (!active) return;
    function onKeyDown(event: KeyboardEvent): void {
      if (event.defaultPrevented || event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;
      if (isTypingTarget(event.target) || document.querySelector("dialog[open]")) return;
      const visible = answerForKey(event.key);
      if (visible === null) return;
      event.preventDefault();
      latest.current(visible);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [active]);
}
