import type { QueryClient } from "@tanstack/react-query";
import { activityKeys } from "../activity/keys.js";
import { moderationKeys } from "../moderation/keys.js";

/**
 * After an act on a marking's keeping or shape, the lists it changes are
 * asked for again: the activity feed, which may gain a change of shape or a
 * new keeper, and with `orphaned` the admins' list of markings without a
 * keeper, which an admin's offer or removal changes.
 */
export function refreshAfterMarking(client: QueryClient, { orphaned = false }: { orphaned?: boolean } = {}): void {
  void client.invalidateQueries({ queryKey: activityKeys.all });
  if (orphaned) void client.invalidateQueries({ queryKey: moderationKeys.orphaned });
}
