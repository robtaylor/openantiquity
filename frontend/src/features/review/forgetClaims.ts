import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { findingKeys } from "../findings/keys.js";
import { helpKeys } from "../help/keys.js";
import { mentionKeys } from "../mentions/keys.js";

/**
 * While `active`, nothing about any finding's claim is kept from before:
 * the findings lists, the map's findings, any finding's page, help
 * wanted's tasks and the recent mentions feed are dropped from the cache
 * when the queue opens. Browsed first, they would hold the title and class
 * of the finding a card turns out to be (Decision 0008). Each is asked for
 * again when it is next shown.
 */
export function useForgetClaimsWhile(active: boolean): void {
  const client = useQueryClient();
  useEffect(() => {
    if (!active) return;
    client.removeQueries({ queryKey: findingKeys.all });
    client.removeQueries({ queryKey: helpKeys.all });
    client.removeQueries({ queryKey: mentionKeys.recent });
  }, [active, client]);
}
