/** Where the marking tool lives, for the files that can't import each other to ask. */

export const MARK_PATH = "/mark";

/** True on any page of the marking panel. */
export function isMarkPath(pathname: string): boolean {
  return pathname === MARK_PATH || pathname.startsWith(`${MARK_PATH}/`);
}
