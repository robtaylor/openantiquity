/**
 * Colour tokens for places CSS custom properties cannot reach, chiefly the
 * MapLibre style. `tokens.css` is the source of truth. `tokens.test.ts` fails
 * if the two drift apart.
 */
export const COLOURS = {
  bg: "#14161a",
  surface: "#1d2026",
  raised: "#262a31",
  border: "#343942",
  text: "#eceae4",
  textMuted: "#a3a39b",
  accent: "#e0a43a",
  accentStrong: "#f2b94f",
  onAccent: "#1a1405",
  good: "#7fb069",
  warn: "#e07a3a",
  bad: "#d9544d",
  info: "#6ba6c9",
} as const;

/** Marker and badge colour for each step of the confidence ladder, by tier id. */
export const TIER_COLOURS: Readonly<Record<string, string>> = {
  spotted: "#9aa3ad",
  seen: "#6ba6c9",
  corroborated: "#9a8fe0",
  probable: "#e0a43a",
  ground_checked: "#7fb069",
  confirmed: "#f5d76e",
};

/** Colour for the finding states that have their own look, by state id. */
export const STATE_COLOURS: Readonly<Record<string, string>> = {
  known: "#b9b2a3",
  disputed: "#e07a3a",
  ruled_out: "#6b6f76",
};

/** Used for a tier or state the tokens do not know yet. */
export const FALLBACK_TIER_COLOUR = TIER_COLOURS.spotted as string;

export function tierColour(tierId: string): string {
  return TIER_COLOURS[tierId] ?? FALLBACK_TIER_COLOUR;
}

/** The CSS custom property that holds a tier's colour. */
export function tierVar(tierId: string): string {
  return tierId in TIER_COLOURS ? `var(--tier-${tierId.replaceAll("_", "-")})` : "var(--tier-spotted)";
}

/** The CSS custom property that holds a state's colour, or null when it has none. */
export function stateVar(stateId: string): string | null {
  return stateId in STATE_COLOURS ? `var(--state-${stateId.replaceAll("_", "-")})` : null;
}

/** The phone layout applies below this width. */
export const PHONE_MAX_WIDTH = 720;
export const PHONE_QUERY = `(max-width: ${PHONE_MAX_WIDTH - 0.02}px)`;

/**
 * A window this short, such as a phone held sideways, cannot fit the whole
 * mode rail, so the rail tightens up and scrolls.
 */
export const SHORT_MAX_HEIGHT = 480;
export const SHORT_QUERY = `(max-height: ${SHORT_MAX_HEIGHT}px)`;

/**
 * Sizes the shell needs in script as well as in CSS, in pixels. They mirror
 * `--rail-width`, `--panel-width`, `--tabbar-height` and `--status-height`.
 */
export const LAYOUT = {
  railWidth: 56,
  panelWidth: 400,
  tabBarHeight: 56,
  statusHeight: 28,
} as const;
