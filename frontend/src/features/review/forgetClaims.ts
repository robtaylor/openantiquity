import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { activityKeys } from "../activity/keys.js";
import { findingKeys } from "../findings/keys.js";
import { helpKeys } from "../help/keys.js";
import { mentionKeys } from "../mentions/keys.js";
import { notificationKeys } from "../notifications/keys.js";

/**
 * While `active`, nothing about any finding's claim is kept from before:
 * the findings lists, the map's findings, any finding's page, help
 * wanted's tasks, the recent mentions feed, the activity feed and the
 * notifications are dropped from the cache when the queue opens. Browsed
 * first, they would hold the title, class and step of the finding a card
 * turns out to be (Decision 0008). Each is asked for again when it is next
 * shown, and the notifications not before the queue closes
 * (`useUnreadCount`).
 */
export function useForgetClaimsWhile(active: boolean): void {
  const client = useQueryClient();
  useEffect(() => {
    if (!active) return;
    client.removeQueries({ queryKey: findingKeys.all });
    client.removeQueries({ queryKey: helpKeys.all });
    client.removeQueries({ queryKey: mentionKeys.recent });
    client.removeQueries({ queryKey: activityKeys.all });
    client.removeQueries({ queryKey: notificationKeys.all });
  }, [active, client]);
}
