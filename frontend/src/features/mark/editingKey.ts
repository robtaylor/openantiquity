/**
 * How "Change the shape" names the path it gave the drawing tool
 * (`MarkFields.editing`): the finding and the shape revision the change
 * began on. The panel (`ChangeShapePanel`) makes the key, and the map layer
 * (`MarkLayer`) reads it to draw a path only for the finding whose tool is
 * open. The tool's address is made and read here too.
 */

import type { FindingDetail } from "../finding/types.js";

const CHANGE_SHAPE_PREFIX = "/mark/finding/";

function editingPrefix(publicId: string): string {
  return `finding:${publicId}:`;
}

/** The key for a change begun on the finding's shape as it is now. */
export function editingKey(finding: FindingDetail): string {
  return `${editingPrefix(finding.public_id)}${finding.location.shape.revision ?? 0}`;
}

/** The finding and the revision a key names, or null for no key or one this file didn't make. */
function parseEditingKey(editing: string | null): { publicId: string; revision: number } | null {
  const prefix = editingPrefix("");
  // Read from the right, so nothing depends on what an id may hold.
  const cut = editing?.lastIndexOf(":") ?? -1;
  if (!editing?.startsWith(prefix.slice(0, -1)) || cut < prefix.length - 1) return null;
  const publicId = editing.slice(prefix.length - 1, cut);
  const revision = Number(editing.slice(cut + 1));
  return publicId !== "" && Number.isInteger(revision) ? { publicId, revision } : null;
}

/** The revision the change in the tool began on, or null when the tool holds no change to this finding. */
export function baseRevision(editing: string | null, publicId: string): number | null {
  const named = parseEditingKey(editing);
  // A key this panel didn't make holds no change it can save.
  return named?.publicId === publicId ? named.revision : null;
}

/** The finding a key names, or null for no key or one this file didn't make. */
export function editedFinding(editing: string | null): string | null {
  return parseEditingKey(editing)?.publicId ?? null;
}

/** The address of the tool for a saved finding. */
export function changeShapePath(publicId: string): string {
  return `${CHANGE_SHAPE_PREFIX}${encodeURIComponent(publicId)}`;
}

/** The finding whose shape is being changed at `pathname`, or null on any other page. */
export function changeShapeId(pathname: string): string | null {
  if (!pathname.startsWith(CHANGE_SHAPE_PREFIX)) return null;
  const rest = pathname.slice(CHANGE_SHAPE_PREFIX.length);
  return rest === "" || rest.includes("/") ? null : decodeURIComponent(rest);
}
