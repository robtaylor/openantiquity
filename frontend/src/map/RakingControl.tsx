import { SlidersHorizontal, Sun } from "lucide-react";
import { memo, useId, useState } from "react";
import { type Meta, rakingView } from "../api/meta.js";
import { IconButton } from "../ui/IconButton.js";
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
 * terrain stays in sight while the light moves. Where the map is small, on a
 * phone, the control is `collapsible`: it starts as the dial alone, and a
 * button beside it opens the sliders.
 */
export const RakingControl = memo(function RakingControl({
  meta,
  collapsible = false,
}: {
  meta: Meta;
  collapsible?: boolean;
}) {
  const visible = useVisibleRakingView(meta);
  const sun = useMapStore((state) => state.sun);
  const exaggeration = useMapStore((state) => state.hillshadeExaggeration);
  const bearing = useMapStore((state) => state.camera.bearing);
  const setSun = useMapStore((state) => state.setSun);
  const setExaggeration = useMapStore((state) => state.setHillshadeExaggeration);
  const hintId = useId();
  const controlsId = useId();
  const [opened, setOpened] = useState(false);
  if (visible === null) return null;
  const open = !collapsible || opened;

  return (
    <section className={open ? "fc-raking" : "fc-raking fc-raking--collapsed"} aria-label="Raking light">
      <SunDial
        azimuth={sun.azimuth}
        bearing={bearing}
        size={open ? undefined : 64}
        describedBy={hintId}
        onChange={(azimuth) => setSun({ azimuth })}
      />
      {collapsible ? (
        <IconButton
          className="fc-raking__toggle"
          size="sm"
          label={open ? "Hide the sun height and relief" : "Show the sun height and relief"}
          aria-expanded={open}
          aria-controls={controlsId}
          onClick={() => setOpened((now) => !now)}
        >
          <SlidersHorizontal size={16} aria-hidden />
        </IconButton>
      ) : null}
      {/* Hidden, not taken away, so the dial's description is still there to read. */}
      <div className="fc-raking__controls" id={controlsId} hidden={!open}>
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
