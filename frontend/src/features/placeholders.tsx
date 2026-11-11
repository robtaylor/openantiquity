import { Activity, BookOpen, Info, type LucideIcon, MapPinned, ScanSearch, UserRound } from "lucide-react";
import { useEffect } from "react";
import { Link, useLocation, useParams } from "react-router";
import { EmptyState } from "../ui/EmptyState.js";
import { PanelFrame } from "./shell/PanelFrame.js";

/**
 * Every route that is not the bare map, with a titled placeholder panel.
 * Each feature replaces its entry with the real page as it is built.
 */

export const APP_NAME = "Field Club";

type Params = Readonly<Record<string, string | undefined>>;

export interface PlaceholderRoute {
  path: string;
  title: string;
  /** A second line under the title, such as the id being shown. */
  subtitle?: (params: Params) => string;
  icon: LucideIcon;
  /** What this page will do, in a sentence or two. */
  body: string;
  /** A part of it that is built already, offered beside "Back to the map". */
  built?: { to: string; label: string };
}

export const PLACEHOLDER_ROUTES: PlaceholderRoute[] = [
  {
    path: "/scan",
    title: "Scan a square",
    icon: ScanSearch,
    body: "You'll be sent to a one-kilometre square that few people have looked at, to mark what you see or to say there's nothing obvious.",
  },
  {
    path: "/activity",
    title: "Activity",
    icon: Activity,
    body: "New findings, findings moving up a step, and mentions in videos and articles will appear here as they happen.",
    built: { to: "/mentions", label: "Recent mentions" },
  },
  {
    path: "/u/:handle",
    title: "Profile",
    subtitle: (params) => `@${params.handle ?? ""}`,
    icon: UserRound,
    body: "A profile will show what someone has found and what they've helped with.",
  },
  {
    path: "/about",
    title: `About ${APP_NAME}`,
    icon: Info,
    body: "A shared map for finding and checking archaeological earthworks in LIDAR data. The full story, the data sources and their licences will be set out here.",
  },
  {
    path: "/guide",
    title: "Guide",
    icon: BookOpen,
    body: "How to read LIDAR, what the different layers are good for, and how a finding climbs from spotted to on record.",
  },
];

/** Sets the window title to `title · Field Club` while the page is shown. */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · ${APP_NAME}`;
    return () => {
      document.title = APP_NAME;
    };
  }, [title]);
}

function BackToMap() {
  return (
    <Link className="fc-button fc-button--secondary fc-button--md" to="/">
      Back to the map
    </Link>
  );
}

export function PlaceholderPanel({ route }: { route: PlaceholderRoute }) {
  const params = useParams();
  const { pathname } = useLocation();
  useDocumentTitle(route.title);
  const Icon = route.icon;
  return (
    <PanelFrame panelKey={pathname} title={route.title} subtitle={route.subtitle?.(params)}>
      <EmptyState
        icon={<Icon size={22} />}
        title="This part isn't built yet"
        action={
          route.built ? (
            <>
              <Link className="fc-button fc-button--primary fc-button--md" to={route.built.to}>
                {route.built.label}
              </Link>
              <BackToMap />
            </>
          ) : (
            <BackToMap />
          )
        }
      >
        <p>{route.body}</p>
      </EmptyState>
    </PanelFrame>
  );
}

export function NotFoundPanel() {
  const { pathname } = useLocation();
  useDocumentTitle("Page not found");
  return (
    <PanelFrame panelKey={pathname} title="Page not found">
      <EmptyState icon={<MapPinned size={22} />} title="There's nothing at this address" action={<BackToMap />}>
        <p>The link may be old or mistyped. The map is still here.</p>
      </EmptyState>
    </PanelFrame>
  );
}
