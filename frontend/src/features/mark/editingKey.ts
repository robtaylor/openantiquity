/**
 * How "Change the shape" and "Suggest a change" name the path they gave the
 * drawing tool (`MarkFields.editing`): which of the two, the finding, and
 * the shape revision the change began on. The panels (`ChangeShapePanel`,
 * `SuggestPanel`) make the keys, and the map layer (`MarkLayer`) reads them
 * to draw a path only for the finding whose tool is open. A change and a
 * suggestion never share a key, so one is never sent as the other. The
 * tools' addresses are made and read here too.
 */

import type { FindingDetail } from "../finding/types.js";

const CHANGE_SHAPE_PREFIX = "/mark/finding/";
const SUGGEST_PREFIX = "/mark/suggest/";

/** What a key is for: a change the keeper saves, or a suggestion someone else sends. */
export type EditingKind = "finding" | "suggest";

function editingPrefix(publicId: string, kind: EditingKind = "finding"): string {
  return `${kind}:${publicId}:`;
}

/** The key for a change, or with `kind` "suggest" a suggestion, begun on the finding's shape as it is now. */
export function editingKey(finding: FindingDetail, kind: EditingKind = "finding"): string {
  return keyFor(finding.public_id, finding.location.shape.revision ?? 0, kind);
}

/** The key for a change, or a suggestion, to finding `publicId` begun on shape `revision`. */
export function keyFor(publicId: string, revision: number, kind: EditingKind = "finding"): string {
  return `${editingPrefix(publicId, kind)}${revision}`;
}

/** The finding and the revision a key of `kind` names, or null for no key or one this file didn't make. */
function parseEditingKey(editing: string | null, kind: EditingKind): { publicId: string; revision: number } | null {
  const prefix = editingPrefix("", kind);
  // Read from the right, so nothing depends on what an id may hold.
  const cut = editing?.lastIndexOf(":") ?? -1;
  if (!editing?.startsWith(prefix.slice(0, -1)) || cut < prefix.length - 1) return null;
  const publicId = editing.slice(prefix.length - 1, cut);
  const revision = Number(editing.slice(cut + 1));
  return publicId !== "" && Number.isInteger(revision) ? { publicId, revision } : null;
}

/**
 * The revision the change in the tool began on, or null when the tool holds
 * no change of `kind` to this finding.
 */
export function baseRevision(editing: string | null, publicId: string, kind: EditingKind = "finding"): number | null {
  const named = parseEditingKey(editing, kind);
  // A key this panel didn't make holds no change it can save.
  return named?.publicId === publicId ? named.revision : null;
}

/** The finding a key of `kind` names, or null for no key or one this file didn't make. */
export function editedFinding(editing: string | null, kind: EditingKind = "finding"): string | null {
  return parseEditingKey(editing, kind)?.publicId ?? null;
}

/** The address of the tool for a saved finding. */
export function changeShapePath(publicId: string): string {
  return `${CHANGE_SHAPE_PREFIX}${encodeURIComponent(publicId)}`;
}

/** The address of the tool for suggesting a change to someone else's marking. */
export function suggestPath(publicId: string): string {
  return `${SUGGEST_PREFIX}${encodeURIComponent(publicId)}`;
}

function idAfter(prefix: string, pathname: string): string | null {
  if (!pathname.startsWith(prefix)) return null;
  const rest = pathname.slice(prefix.length);
  return rest === "" || rest.includes("/") ? null : decodeURIComponent(rest);
}

/** The finding whose shape is being changed at `pathname`, or null on any other page. */
export function changeShapeId(pathname: string): string | null {
  return idAfter(CHANGE_SHAPE_PREFIX, pathname);
}

/** The finding a change is being suggested to at `pathname`, or null on any other page. */
export function suggestId(pathname: string): string | null {
  return idAfter(SUGGEST_PREFIX, pathname);
}
