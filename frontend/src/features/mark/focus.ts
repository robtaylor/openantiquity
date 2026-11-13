/**
 * Where focus goes when the control that had it is taken away: a handle
 * deleted from the keyboard, or a bar that goes as the phone's floating bar
 * and the sheet swap. Each waits a frame for what replaces it to appear,
 * and leaves focus alone when it is still somewhere.
 */

/** The name of the button that puts a point down at the cross, on the drawing bar and on the phone's. */
export const ADD_AT_CROSS = "Add a point at the cross";

/** True when focus has gone to the page, as it does when the focused control is taken away. */
function focusLost(pressed: Element | null): boolean {
  const active = document.activeElement;
  return active === null || active === document.body || (pressed !== null && !pressed.isConnected);
}

/** Focus goes to the first control of `selector` once it has appeared. */
export function focusFirstControlAfter(pressed: Element | null, selector: string): void {
  requestAnimationFrame(() => {
    if (!focusLost(pressed)) return;
    document.querySelector(selector)?.querySelector<HTMLElement>("button:not(:disabled)")?.focus();
  });
}

/** After the last point is deleted, focus goes to "Add a point at the cross", wherever it is shown. */
export function focusAddAtCrossAfter(pressed: Element | null): void {
  requestAnimationFrame(() => {
    if (!focusLost(pressed)) return;
    const buttons = [...document.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
    buttons
      .find((button) => (button.getAttribute("aria-label") ?? button.textContent?.trim()) === ADD_AT_CROSS)
      ?.focus();
  });
}

/** Focus goes to the handle of point `index`. */
export function focusHandleIfLost(pressed: Element, index: number): void {
  if (!focusLost(pressed)) return;
  document.querySelector<HTMLElement>(`.fc-path-handle[data-index="${index}"]`)?.focus();
}
