/** Where the marking tool lives, for the files that can't import each other to ask. */

export const MARK_PATH = "/mark";

/**
 * What goes with the way to the marking tool when the person has already
 * said to go back to the marking in hand, so the tool doesn't ask again
 * whether to go to one that is out of view.
 */
export const CARRY_ON = { carryOn: true } as const;

export function wasToldToCarryOn(state: unknown): boolean {
  return typeof state === "object" && state !== null && (state as { carryOn?: unknown }).carryOn === true;
}

/** True on any page of the marking panel. */
export function isMarkPath(pathname: string): boolean {
  return pathname === MARK_PATH || pathname.startsWith(`${MARK_PATH}/`);
}
