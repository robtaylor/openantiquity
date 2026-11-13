import { MapPinPlus } from "lucide-react";
import { useLocation, useNavigate } from "react-router";
import { useMainMap } from "../../map/mainMap.js";
import { Button } from "../../ui/Button.js";
import { DrawingBar, SelectedPointBar } from "./DrawingTool.js";
import { isMarkPath } from "./MarkLayer.js";
import { MARK_PATH } from "./MarkPanel.js";
import { isAdding, useMarkStore } from "./markStore.js";

/**
 * The primary action at the foot of the map: "Mark a finding", which opens
 * the marking panel over the same view with the map taking taps at once.
 *
 * While points are being added on a phone, the drawing bar takes its
 * place, or the selected-point bar while a point is selected, so they sit
 * above the sheet's peek stop and the map stays free to tap. Once drawing
 * stops the sheet rises and the bars are in it, as on a computer, where
 * they are always in the panel.
 */
export function MarkButton({ isPhone }: { isPhone: boolean }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const map = useMainMap();
  const selected = useMarkStore((state) => state.selected !== null);
  const adding = useMarkStore(isAdding);

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
  if (!isPhone || !adding) return null;
  return (
    <div className="fc-mark-float">{selected ? <SelectedPointBar map={map} /> : <DrawingBar map={map} isPhone />}</div>
  );
}
