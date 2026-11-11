import { useEffect } from "react";
import { useMapStore } from "./store.js";

/**
 * Hold an overlay off the map while `active` is true, whatever the person's
 * switch for it says, and let it back afterwards. The switch, and the
 * address that records it, are left as they were. Nothing happens for a
 * null id, as for an overlay the catalogue doesn't have.
 */
export function useHoldOverlayWhile(overlayId: string | null, active: boolean): void {
  useEffect(() => {
    if (!active || overlayId === null) return;
    useMapStore.getState().holdOverlay(overlayId, true);
    return () => useMapStore.getState().holdOverlay(overlayId, false);
  }, [overlayId, active]);
}
