/**
 * What each role is called, and what it means in a sentence. `/meta` has no
 * words for roles, so they are written here, typed over every role in the
 * schema so a new one doesn't build until it has words. The labels are the
 * server's own (`vocab.ROLES`).
 */

import type { components } from "../../api/schema.js";

export type Role = components["schemas"]["Role"];

export const ROLE_WORDS: Record<Role, { label: string; hint: string }> = {
  member: { label: "Member", hint: "Someone who has joined Field Club." },
  trusted: {
    label: "Trusted member",
    hint: "Trusted by a moderator after earning fifty points. Their checks count for more.",
  },
  expert: { label: "Archaeologist", hint: "A recognised archaeologist or records officer." },
  moderator: { label: "Moderator", hint: "Looks after reports and protected places." },
  admin: { label: "Admin", hint: "Runs the service." },
};

export function roleWords(role: string): { label: string; hint: string } {
  return ROLE_WORDS[role as Role] ?? { label: role.replaceAll("_", " "), hint: "" };
}
