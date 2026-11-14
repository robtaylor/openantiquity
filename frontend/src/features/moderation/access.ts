/**
 * Who may do what in moderation, so that nothing the server would refuse is
 * offered. These mirror the server's checks in `services/moderation.py`
 * until the API says them itself, and are listed with the other known
 * duplications in docs/ARCHITECTURE.md ("Moderation in the browser").
 */

import type { Role } from "./api.js";

const ROLES: readonly Role[] = ["member", "trusted", "expert", "moderator", "admin"];

function asRole(role: string | null): Role | null {
  return ROLES.find((entry) => entry === role) ?? null;
}

/** Moderators and admins see `/mod` and moderate content. */
export function isModerator(role: string | null): boolean {
  const known = asRole(role);
  return known === "moderator" || known === "admin";
}

/** Admins alone see the markings without a keeper and remove them (Decision 0040). */
export function isAdmin(role: string | null): boolean {
  return asRole(role) === "admin";
}

/** Trusted members, archaeologists, moderators and admins approve photos (Decision 0009). */
export function mayApprovePhotos(role: string | null): boolean {
  const known = asRole(role);
  return known !== null && known !== "member";
}

/** Fifty points make a member eligible for trusted (docs/ARCHITECTURE.md, "Reputation"). */
export const TRUSTED_AT = 50;

/**
 * The roles `actor` may give someone who is `current` now, with `points`
 * known to the actor. Nobody changes their own role, which the caller checks
 * by handle. Admins are made outside the API, only an admin makes or
 * unmakes a moderator, and a member becomes trusted from fifty points.
 */
export function roleChoices(actor: string | null, current: string, points: number): Role[] {
  const by = asRole(actor);
  const now = asRole(current);
  if (!isModerator(by) || now === null || now === "admin") return [];
  return ROLES.filter((role) => {
    if (role === now || role === "admin") return false;
    if ((role === "moderator" || now === "moderator") && by !== "admin") return false;
    if (now === "member" && role === "trusted" && points < TRUSTED_AT) return false;
    return true;
  });
}

/** A moderator bans anyone below moderator. Only an admin bans a moderator, and nobody bans an admin here. */
export function mayBan(actor: string | null, target: string): boolean {
  const by = asRole(actor);
  const them = asRole(target);
  if (!isModerator(by) || them === "admin") return false;
  return them !== "moderator" || by === "admin";
}
