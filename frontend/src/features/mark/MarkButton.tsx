import { CircleDot, MapPinPlus } from "lucide-react";
import { useLocation, useNavigate } from "react-router";
import { useMainMap } from "../../map/mainMap.js";
import { Button } from "../../ui/Button.js";
import { isMarkPath, placeAtReticle } from "./MarkLayer.js";
import { MARK_PATH } from "./MarkPanel.js";
import { useMarkStore } from "./markStore.js";

/**
 * The primary action at the foot of the map. Usually "Mark a finding",
 * which opens the marking panel over the same view. While the mark is being
 * placed it is "Place it here", which puts the mark under the cross in the
 * middle of the map: the way to place it by keyboard, and on a phone the
 * way to place it exactly. Once the mark is down the panel has the buttons.
 */
export function MarkButton() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const map = useMainMap();
  const placed = useMarkStore((state) => state.point !== null);

  if (!isMarkPath(pathname)) {
    return (
      <Button
        variant="primary"
        size="lg"
        icon={<MapPinPlus size={20} aria-hidden />}
        onClick={() => navigate(MARK_PATH)}
      >
        Mark a finding
      </Button>
    );
  }
  if (placed) return null;
  return (
    <Button variant="primary" size="lg" icon={<CircleDot size={20} aria-hidden />} onClick={() => placeAtReticle(map)}>
      Place it here
    </Button>
  );
}
