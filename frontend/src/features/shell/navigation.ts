import {
  Activity,
  BookOpen,
  CircleUser,
  Compass,
  Eye,
  HandHelping,
  Info,
  type LucideIcon,
  NotebookText,
  ScanSearch,
} from "lucide-react";

/**
 * `/` is Explore, which lists the findings in view. The bare map, with no
 * panel open, is `/?panel=none`, and closing a panel goes there.
 */
export const BARE_MAP_PARAM = "none";
export const BARE_MAP_PATH = `/?panel=${BARE_MAP_PARAM}`;

export interface Mode {
  id: string;
  /** Full name, for tooltips and screen readers. */
  label: string;
  /** Fits under an icon in the phone tab bar. */
  shortLabel: string;
  to: string;
  icon: LucideIcon;
  /** Path prefixes that belong to this mode, besides `to`. */
  also?: string[];
}

/** The modes, in rail order. The first four also fill the phone tab bar. */
export const MODES: Mode[] = [
  // A finding or a record opened from the map, the record search, "open elsewhere" and a height profile are all still exploring.
  {
    id: "explore",
    label: "Explore",
    shortLabel: "Explore",
    to: "/",
    icon: Compass,
    also: ["/f/", "/r/", "/records", "/elsewhere", "/profile"],
  },
  { id: "review", label: "Second look", shortLabel: "Second look", to: "/review", icon: Eye },
  { id: "scan", label: "Scan a square", shortLabel: "Scan", to: "/scan", icon: ScanSearch },
  { id: "help", label: "Help wanted", shortLabel: "Help wanted", to: "/help", icon: HandHelping },
  {
    id: "investigations",
    label: "Investigations",
    shortLabel: "Investigations",
    to: "/investigations",
    icon: NotebookText,
    also: ["/i/"],
  },
  // The recent mentions across the map are part of the activity.
  {
    id: "activity",
    label: "Activity",
    shortLabel: "Activity",
    to: "/activity",
    icon: Activity,
    also: ["/mentions"],
  },
  { id: "account", label: "Account", shortLabel: "Account", to: "/account", icon: CircleUser, also: ["/u/"] },
];

/** Reference pages, shown at the foot of the rail and under "More". */
export const REFERENCE: Mode[] = [
  { id: "guide", label: "Guide", shortLabel: "Guide", to: "/guide", icon: BookOpen },
  { id: "about", label: "About", shortLabel: "About", to: "/about", icon: Info },
];

/** How many modes the phone tab bar shows before "More". */
export const TAB_BAR_MODES = 4;

export function isModeActive(mode: Mode, pathname: string): boolean {
  if (mode.to === "/") return pathname === "/" || (mode.also ?? []).some((prefix) => pathname.startsWith(prefix));
  return (
    pathname === mode.to ||
    pathname.startsWith(`${mode.to}/`) ||
    (mode.also ?? []).some((prefix) => pathname.startsWith(prefix))
  );
}

export function activeMode(pathname: string): Mode | undefined {
  return [...MODES, ...REFERENCE].find((mode) => isModeActive(mode, pathname));
}

/**
 * The query string `search` with the `panel` parameter set to `panel`, or
 * taken out when `panel` is null. Everything else in it is kept, so a panel
 * that keeps its state there, such as a height profile's line, survives the
 * layer panel opening over it and closing again.
 */
export function searchWithPanel(search: string, panel: string | null): string {
  const params = new URLSearchParams(search);
  if (panel === null) params.delete("panel");
  else params.set("panel", panel);
  const next = params.toString();
  return next ? `?${next}` : "";
}
