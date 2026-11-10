import { Ellipsis } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router";
import { useDismiss } from "../../ui/useDismiss.js";
import { isModeActive, MODES, REFERENCE, TAB_BAR_MODES } from "./navigation.js";

/** The phone tab bar: four modes and "More", which holds the rest. */
export function TabBar() {
  const { pathname } = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);
  const menuId = useId();
  const moreRef = useRef<HTMLDivElement>(null);
  const moreButton = useRef<HTMLButtonElement>(null);

  const tabs = MODES.slice(0, TAB_BAR_MODES);
  const rest = [...MODES.slice(TAB_BAR_MODES), ...REFERENCE];
  const restActive = rest.some((mode) => isModeActive(mode, pathname));

  // Going anywhere closes the menu.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the path is the trigger
  useEffect(() => {
    setMoreOpen(false);
  }, [pathname]);

  useDismiss(moreRef, moreOpen, (cause) => {
    setMoreOpen(false);
    // The menu is about to go, and focus with it if it was inside. Hand it back to the button.
    if (cause === "escape" && moreRef.current?.contains(document.activeElement)) moreButton.current?.focus();
  });

  return (
    <nav className="fc-tabbar" aria-label="Modes">
      {tabs.map((mode) => {
        const Icon = mode.icon;
        const active = isModeActive(mode, pathname);
        return (
          <NavLink
            key={mode.id}
            to={mode.to}
            className={active ? "fc-tabbar__tab fc-tabbar__tab--active" : "fc-tabbar__tab"}
            aria-current={active ? "page" : undefined}
          >
            <Icon size={22} aria-hidden />
            <span>{mode.shortLabel}</span>
          </NavLink>
        );
      })}
      <div className="fc-tabbar__more" ref={moreRef}>
        <button
          type="button"
          ref={moreButton}
          className={restActive || moreOpen ? "fc-tabbar__tab fc-tabbar__tab--active" : "fc-tabbar__tab"}
          aria-expanded={moreOpen}
          aria-controls={menuId}
          onClick={() => setMoreOpen((open) => !open)}
        >
          <Ellipsis size={22} aria-hidden />
          <span>More</span>
        </button>
        {moreOpen ? (
          <div className="fc-tabbar__menu" id={menuId}>
            {rest.map((mode) => {
              const Icon = mode.icon;
              const active = isModeActive(mode, pathname);
              return (
                <NavLink
                  key={mode.id}
                  to={mode.to}
                  className={active ? "fc-tabbar__item fc-tabbar__item--active" : "fc-tabbar__item"}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon size={20} aria-hidden />
                  {mode.label}
                </NavLink>
              );
            })}
          </div>
        ) : null}
      </div>
    </nav>
  );
}
