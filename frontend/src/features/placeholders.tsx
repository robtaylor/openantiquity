import { MapPinned } from "lucide-react";
import { useEffect } from "react";
import { Link, useLocation } from "react-router";
import { EmptyState } from "../ui/EmptyState.js";
import { PanelFrame } from "./shell/PanelFrame.js";

/**
 * What every page shares: the app's name, the window title, and the panel
 * for an address that leads nowhere. Each route once had a placeholder here
 * until its page was built, and every one now has its page.
 */

export const APP_NAME = "Open Antiquity";

/** Sets the window title to `title · Open Antiquity` while the page is shown. */
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
