import type { ReactNode } from "react";

/**
 * Plan-view pictograms for the feature classes: each one is the shape the
 * feature makes seen from above, the way it shows in LIDAR and on a site
 * plan. They are keyed by the class ids that `/meta` serves. A class the
 * frontend has no drawing for yet gets the "not sure" glyph, so a new class on
 * the backend never breaks a list.
 *
 * All glyphs are drawn on a 24 px grid with a 1.6 px stroke in the current
 * text colour. Solid areas (mounds, islands) use a light fill.
 */

const SOFT = { fill: "currentColor", fillOpacity: 0.28 } as const;
const SOLID = { fill: "currentColor", stroke: "none" } as const;

/** Short strokes pointing along a slope, as on a hachured plan. */
function hachures(cx: number, cy: number, inner: number, outer: number, count: number, startDegrees = 0): string {
  const parts: string[] = [];
  for (let i = 0; i < count; i++) {
    const angle = ((startDegrees + (360 / count) * i) * Math.PI) / 180;
    const x1 = (cx + inner * Math.cos(angle)).toFixed(2);
    const y1 = (cy + inner * Math.sin(angle)).toFixed(2);
    const x2 = (cx + outer * Math.cos(angle)).toFixed(2);
    const y2 = (cy + outer * Math.sin(angle)).toFixed(2);
    parts.push(`M${x1} ${y1}L${x2} ${y2}`);
  }
  return parts.join("");
}

const GLYPHS: Record<string, ReactNode> = {
  // A bank or ditch round a patch of ground, with an entrance gap.
  enclosure: <path d="M19 9.5V8a3 3 0 0 0-3-3H8a3 3 0 0 0-3 3v8a3 3 0 0 0 3 3h8a3 3 0 0 0 3-3v-1.5" />,

  // Two lines of rampart with the entrance on one side.
  hillfort: (
    <>
      <path d="M20.46 9.43A9 7.5 0 1 0 20.46 14.57" />
      <path d="M16.86 10.03A5.5 4.2 0 1 0 16.86 13.97" />
    </>
  ),

  // A round mound inside its ring ditch.
  round_barrow: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <circle cx="12" cy="12" r="4" {...SOLID} />
    </>
  ),

  // A long mound, wider at one end, with a ditch down each side.
  long_barrow: (
    <>
      <path
        d="M4.6 10.3 18.6 8.7a1.7 1.7 0 0 1 1.9 1.7v3.2a1.7 1.7 0 0 1-1.9 1.7L4.6 13.7a1.7 1.7 0 0 1 0-3.4Z"
        {...SOFT}
      />
      <path d="M5 6.7 19.5 5M5 17.3 19.5 19" />
    </>
  ),

  // The thick ring of a round-house wall, with its doorway.
  hut_circle: <path d="M14.32 16.98A5.5 5.5 0 1 1 16.98 14.32" strokeWidth="2.6" />,

  // House platforms either side of a lane.
  settlement: (
    <>
      <path d="M3 12.6c5-1.5 13-1.5 18 0" />
      <rect x="4.6" y="5.4" width="4.4" height="3.6" rx="0.6" {...SOFT} />
      <rect x="11.6" y="4.6" width="5.4" height="3.8" rx="0.6" {...SOFT} />
      <rect x="6.2" y="15.6" width="5.4" height="3.6" rx="0.6" {...SOFT} />
      <rect x="14.6" y="15.2" width="4.4" height="3.8" rx="0.6" {...SOFT} />
    </>
  ),

  // A building's walls in plan: two rooms, one still roofed, and a corner fallen.
  building: (
    <>
      <path d="M13.2 5.5H5.5v13h13v-7.7" />
      <rect x="5.5" y="5.5" width="5.9" height="13" {...SOFT} />
      <path d="M16.3 6.6h.01M18.4 8.1h.01M17.2 4.6h.01" />
    </>
  ),

  // A block of small fields laid out together.
  field_system: <path d="M3.5 5.5h17v13h-17zM9.5 5.5v13M15 5.5V13M3.5 11h6M9.5 13h11" />,

  // The reversed-S ridges of medieval ploughing.
  ridge_and_furrow: (
    <path d="M5 4c-1.5 2.7 1.5 5.3 0 8s1.5 5.3 0 8M8.5 4c-1.5 2.7 1.5 5.3 0 8s1.5 5.3 0 8M12 4c-1.5 2.7 1.5 5.3 0 8s1.5 5.3 0 8M15.5 4c-1.5 2.7 1.5 5.3 0 8s1.5 5.3 0 8M19 4c-1.5 2.7 1.5 5.3 0 8s1.5 5.3 0 8" />
  ),

  // A bank with its ditch alongside, running across country.
  linear: (
    <>
      <path d="M3 14.5 21 6" strokeWidth="2.2" />
      <path d="M4.5 18.5 22 10.2" strokeDasharray="2.4 2.4" />
    </>
  ),

  // The two edges of a winding sunken lane.
  trackway: <path d="M3 8.6c5 0 6 5 9 5s4-3 9-3M3 13.2c5 0 6 5 9 5s4-3 9-3" />,

  // A straight, raised road.
  road: (
    <>
      <path d="M2.5 14.2 20.5 4.4 21.5 8 3.5 17.8Z" {...SOFT} stroke="none" />
      <path d="M2.5 14.2 20.5 4.4M3.5 17.8 21.5 8" />
      <path d="M5 20.8 22 11.6" strokeDasharray="0.1 3.2" />
    </>
  ),

  // A wide ditch round a square island.
  moat: (
    <>
      <rect x="3.5" y="3.5" width="17" height="17" rx="2.6" />
      <rect x="8" y="8" width="8" height="8" rx="1" {...SOFT} />
    </>
  ),

  // A steep mound with a bailey attached.
  motte: (
    <>
      <circle cx="8.6" cy="9" r="2.6" {...SOLID} />
      <path d={hachures(8.6, 9, 4, 5.8, 10, 18)} />
      <path d="M13.8 12.4c4-1 7 .9 7 3.9 0 2.6-2.7 3.9-5.7 3.5-3-.4-5-2.1-5.6-4.6" />
    </>
  ),

  // A levelled stance with the scarp falling away below it.
  platform: (
    <>
      <rect x="4.5" y="6" width="15" height="8" rx="1" {...SOFT} />
      <path d="M6.5 16.5v2.4M10 16.5v3.6M14 16.5v3.6M17.5 16.5v2.4" />
    </>
  ),

  // A pond held back by a dam.
  pond: (
    <>
      <path d="M4.5 12c0-3.6 3.4-6 7.6-6 4.4 0 7.4 2.2 7.4 5.6 0 3.8-3.6 6.4-7.9 6.4-4.1 0-7.1-2.5-7.1-6Z" />
      <path d="M8.6 10.6c1.1-.9 2.2-.9 3.3 0s2.2.9 3.3 0M9.6 13.8c1-.8 2-.8 3 0s2 .8 3 0" strokeWidth="1.3" />
    </>
  ),

  // A hollow, with hachures running down into it.
  pit: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <path d={hachures(12, 12, 4.4, 8.2, 10)} strokeWidth="1.3" />
      <circle cx="12" cy="12" r="1.1" {...SOLID} />
    </>
  ),

  // A shaft or kiln with a tramway leading off.
  industrial: (
    <>
      <circle cx="7.6" cy="16.4" r="3.6" />
      <circle cx="7.6" cy="16.4" r="1.1" {...SOLID} />
      <path d="M10.4 13.6 20.5 3.5M12.6 9.6l1.8 1.8M15.4 6.8l1.8 1.8M18.2 4l1.8 1.8" />
    </>
  ),

  // The crenellated line of a fire trench.
  military: <path d="M2.5 14.5h3.6v-5h4.2v5h3.4v-5h4.2v5h3.6" />,

  // A henge: a ring with opposed entrances, and stones set inside it.
  ritual: (
    <>
      <path d="M4.01 9.09A8.5 8.5 0 0 1 19.99 9.09M19.99 14.91A8.5 8.5 0 0 1 4.01 14.91" />
      <g {...SOLID}>
        <circle cx="16.6" cy="12" r="0.95" />
        <circle cx="14.3" cy="15.98" r="0.95" />
        <circle cx="9.7" cy="15.98" r="0.95" />
        <circle cx="7.4" cy="12" r="0.95" />
        <circle cx="9.7" cy="8.02" r="0.95" />
        <circle cx="14.3" cy="8.02" r="0.95" />
      </g>
    </>
  ),

  // A formal garden: quartered beds round a central feature.
  garden: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="1.5" />
      <path d="M12 4v5M12 15v5M4 12h5M15 12h5" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),

  // Something is there, but what?
  unknown: (
    <>
      <circle cx="12" cy="12" r="8.6" strokeDasharray="2.7 2.7" />
      <path d="M9.6 9.7a2.5 2.5 0 1 1 3.7 2.2c-.9.5-1.3 1-1.3 2M12 16.8h.01" />
    </>
  ),
};

/** The class ids that have their own drawing. */
export const FEATURE_ICON_IDS: readonly string[] = Object.keys(GLYPHS);

export function hasFeatureIcon(classId: string): boolean {
  return classId in GLYPHS;
}

export interface FeatureIconProps {
  /** A feature class id from `/meta`, such as "round_barrow". */
  classId: string;
  size?: number;
  /** Give the icon a name when it stands alone. Leave out when a label sits beside it. */
  title?: string;
}

export function FeatureIcon({ classId, size = 24, title }: FeatureIconProps) {
  const glyph = GLYPHS[classId] ?? GLYPHS.unknown;
  return (
    <svg
      className="fc-feature-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      data-feature-class={classId}
    >
      {glyph}
    </svg>
  );
}
