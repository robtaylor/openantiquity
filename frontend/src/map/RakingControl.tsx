import { Sun } from "lucide-react";
import { memo, useId } from "react";
import { type Meta, rakingView } from "../api/meta.js";
import { Slider } from "../ui/Slider.js";
import { compassPoint } from "./compass.js";
import { LIMITS } from "./permalink.js";
import { SunDial } from "./SunDial.js";
import { useMapStore } from "./store.js";

/** The id of the raking view on screen, in either pane, or null. */
export function useVisibleRakingView(meta: Meta): string | null {
  const mainView = useMapStore((state) => state.mainView);
  const compareView = useMapStore((state) => state.compareView);
  const raking = rakingView(meta);
  if (!raking) return null;
  return raking.id === mainView || raking.id === compareView ? raking.id : null;
}

/**
 * Sun controls for the raking light view. They float on the map, so the
 * terrain stays in sight while the light moves.
 */
export const RakingControl = memo(function RakingControl({ meta }: { meta: Meta }) {
  const visible = useVisibleRakingView(meta);
  const sun = useMapStore((state) => state.sun);
  const exaggeration = useMapStore((state) => state.hillshadeExaggeration);
  const bearing = useMapStore((state) => state.camera.bearing);
  const setSun = useMapStore((state) => state.setSun);
  const setExaggeration = useMapStore((state) => state.setHillshadeExaggeration);
  const hintId = useId();
  if (visible === null) return null;

  return (
    <section className="fc-raking" aria-label="Raking light">
      <SunDial
        azimuth={sun.azimuth}
        bearing={bearing}
        describedBy={hintId}
        onChange={(azimuth) => setSun({ azimuth })}
      />
      <div className="fc-raking__controls">
        <p className="fc-raking__title">
          <Sun size={16} aria-hidden />
          Light from the {compassPoint(sun.azimuth)}
        </p>
        <p className="fc-raking__hint" id={hintId}>
          Turn the sun until faint banks catch the light. Lower sun, longer shadows, down to 15°.
        </p>
        <Slider
          label="Sun height"
          value={sun.altitude}
          min={LIMITS.sunAltitude.min}
          max={LIMITS.sunAltitude.max}
          step={1}
          format={(value) => `${Math.round(value)}°`}
          onChange={(altitude) => setSun({ altitude })}
        />
        <Slider
          label="Relief"
          accessibleName="Relief: how much the heights are stretched"
          value={exaggeration}
          min={LIMITS.hillshadeExaggeration.min}
          max={LIMITS.hillshadeExaggeration.max}
          step={0.5}
          format={(value) => `×${value.toFixed(1)}`}
          onChange={setExaggeration}
        />
      </div>
    </section>
  );
});
