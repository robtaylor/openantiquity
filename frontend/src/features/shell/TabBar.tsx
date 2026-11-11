import { Ellipsis } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router";
import { useDismiss } from "../../ui/useDismiss.js";
import { AccountModeIcon } from "../account/AccountModeIcon.js";
import { NotificationCount } from "../notifications/NotificationCount.js";
import { unreadWords, useUnreadCount } from "../notifications/useNotifications.js";
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
  // Account is under "More", so the button carries its count too.
  const unread = useUnreadCount();
  const unreadInMore = rest.some((mode) => mode.id === "account") ? unread : null;

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
          aria-label={unreadInMore ? `More, ${unreadWords(unreadInMore)}` : undefined}
          aria-expanded={moreOpen}
          aria-controls={menuId}
          onClick={() => setMoreOpen((open) => !open)}
        >
          <NotificationCount count={unreadInMore}>
            <Ellipsis size={22} aria-hidden />
          </NotificationCount>
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
                  aria-label={mode.id === "account" && unread ? `${mode.label}, ${unreadWords(unread)}` : undefined}
                >
                  {mode.id === "account" ? <AccountModeIcon icon={Icon} size={20} /> : <Icon size={20} aria-hidden />}
                  {mode.label}
                  {mode.id === "account" ? <NotificationCount count={unread} inline /> : null}
                </NavLink>
              );
            })}
          </div>
        ) : null}
      </div>
    </nav>
  );
}
