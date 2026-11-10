import { Minus, Navigation2, Plus } from "lucide-react";
import { IconButton } from "../ui/IconButton.js";
import { LIMITS } from "./permalink.js";
import { useMapStore } from "./store.js";

/**
 * Zoom buttons and a compass, for the column of floating buttons on the map.
 *
 * A touch screen has no one-finger way to zoom out, and a two-finger twist
 * turns the map with nothing else on screen to say so. The compass appears
 * whenever the map is turned, points to north, and turns the map back
 * north-up when pressed. It leaves the tilt alone, so pressing it in 3D
 * keeps the 3D view. The 3D button is the way back to a flat map.
 */
export function CameraControls() {
  const zoom = useMapStore((state) => state.camera.zoom);
  const bearing = useMapStore((state) => state.camera.bearing);
  const zoomBy = useMapStore((state) => state.zoomBy);
  const resetNorth = useMapStore((state) => state.resetNorth);
  const turned = bearing !== 0;

  return (
    <>
      <IconButton floating label="Zoom in" disabled={zoom >= LIMITS.zoom.max} onClick={() => zoomBy(1)}>
        <Plus size={20} aria-hidden />
      </IconButton>
      <IconButton floating label="Zoom out" disabled={zoom <= LIMITS.zoom.min} onClick={() => zoomBy(-1)}>
        <Minus size={20} aria-hidden />
      </IconButton>
      {turned ? (
        <IconButton
          floating
          label="Reset to north-up"
          title="Turn the map north-up"
          className="fc-compass"
          onClick={resetNorth}
        >
          {/* The arrow points to north on screen. */}
          <Navigation2
            size={18}
            aria-hidden
            data-testid="compass-needle"
            style={{ transform: `rotate(${-bearing}deg)` }}
          />
        </IconButton>
      ) : null}
    </>
  );
}
