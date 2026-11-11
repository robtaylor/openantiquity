import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { onLiveEvent } from "../activity/LiveEvents.js";
import { investigationKeys } from "./keys.js";

/**
 * While an investigations list or page is open, a live event that one was
 * published asks the lists, and that investigation's page, for their news.
 * The event is only a hint: the queries are invalidated, and those on screen
 * ask again with this viewer's rights. Other events name no investigation.
 */
export function useLiveInvestigations(): void {
  const client = useQueryClient();
  useEffect(
    () =>
      onLiveEvent((event) => {
        if (event.kind !== "investigation_published") return;
        const keep = { cancelRefetch: false };
        void client.invalidateQueries({ queryKey: investigationKeys.lists }, keep);
        if (event.investigation !== null) {
          void client.invalidateQueries({ queryKey: investigationKeys.detail(event.investigation) }, keep);
        }
      }),
    [client],
  );
}
