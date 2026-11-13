/**
 * Where focus goes when the control that had it is taken away: a handle
 * deleted from the keyboard, or a bar that goes as the phone's floating bar
 * and the sheet swap. Focus waits a frame for what replaces the control to
 * appear, and is left alone when it is still somewhere.
 */

/** The name of the button that puts a point down at the cross, on the drawing bar and on the phone's. */
export const ADD_AT_CROSS = "Add a point at the cross";

/** "Add a point at the cross", wherever it is shown and can be pressed. Each such button carries `data-add-at-cross`. */
export const ADD_AT_CROSS_SELECTOR = "[data-add-at-cross]:not(:disabled)";

/** A selector for the first control of `container` that can be pressed. */
export function firstControlOf(container: string): string {
  return `${container} button:not(:disabled)`;
}

/** A selector for the handle of point `index`. */
export function handleSelector(index: number): string {
  return `.fc-path-handle[data-index="${index}"]`;
}

/** True when focus has gone to the page, as it does when the focused control is taken away. */
function focusLost(pressed: Element | null): boolean {
  const active = document.activeElement;
  return active === null || active === document.body || (pressed !== null && !pressed.isConnected);
}

/** Once a frame has passed, and only if focus went with `pressed`, focus goes to the first match of `selector`. */
export function focusAfter(pressed: Element | null, selector: string): void {
  requestAnimationFrame(() => {
    if (!focusLost(pressed)) return;
    document.querySelector<HTMLElement>(selector)?.focus();
  });
}
