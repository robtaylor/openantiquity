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

/**
 * True when focus is nowhere: on the page itself, as a browser leaves it
 * when the focused control is taken away, or still named as a control that
 * is no longer on the page. Focus that has since gone to a control that is
 * there has not been lost, whatever became of the one that was pressed.
 */
function focusLost(): boolean {
  const active = document.activeElement;
  return active === null || active === document.body || !active.isConnected;
}

/**
 * Once a frame has passed, and only if focus is then nowhere, focus goes to
 * the first match of `selector`. `pressed` is the control whose going may
 * have taken focus with it. If focus has moved on by the frame it is left
 * where it is: taking it back would send the person's next key to a control
 * they had left, and once deleted the wrong point.
 */
export function focusAfter(pressed: Element | null, selector: string): void {
  requestAnimationFrame(() => {
    // Still on the control that was pressed, which is still there: nothing was taken away.
    if (pressed?.isConnected && document.activeElement === pressed) return;
    if (!focusLost()) return;
    document.querySelector<HTMLElement>(selector)?.focus();
  });
}
