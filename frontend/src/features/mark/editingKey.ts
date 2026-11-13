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

/** The revision the change in the tool began on, or null when the tool holds no change to this finding. */
export function baseRevision(editing: string | null, publicId: string): number | null {
  const prefix = editingPrefix(publicId);
  if (!editing?.startsWith(prefix)) return null;
  const revision = Number(editing.slice(prefix.length));
  // A key this panel didn't make holds no change it can save.
  return Number.isInteger(revision) ? revision : null;
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
