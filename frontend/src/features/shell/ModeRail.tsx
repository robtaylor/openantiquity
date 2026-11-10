import { NavLink, useLocation } from "react-router";
import { AccountModeIcon } from "../account/AccountModeIcon.js";
import { isModeActive, MODES, type Mode, REFERENCE } from "./navigation.js";

function RailLink({ mode, pathname, compact }: { mode: Mode; pathname: string; compact: boolean }) {
  const Icon = mode.icon;
  const active = isModeActive(mode, pathname);
  return (
    <NavLink
      to={mode.to}
      className={active ? "fc-rail__link fc-rail__link--active" : "fc-rail__link"}
      aria-label={mode.label}
      aria-current={active ? "page" : undefined}
      // The compact rail scrolls, which clips the pop-out label, so the browser's tooltip stands in.
      title={compact ? mode.label : undefined}
    >
      {mode.id === "account" ? <AccountModeIcon icon={Icon} size={22} /> : <Icon size={22} aria-hidden />}
      <span className="fc-rail__tip" aria-hidden="true">
        {mode.label}
      </span>
    </NavLink>
  );
}

/** Two bumps: a mound and its neighbour in profile. */
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <path
        d="M2.5 20.5c2.2 0 3.3-7.5 7.2-7.5 3.2 0 3.8 4.6 5.6 4.6 1.6 0 2-2.6 4.2-2.6 2.6 0 3.2 5.5 6 5.5"
        stroke="var(--accent)"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M4 24h20" stroke="var(--text-muted)" strokeWidth="1.6" strokeLinecap="round" strokeDasharray="1 3.4" />
    </svg>
  );
}

/**
 * The desktop mode rail: a 56 px column down the left edge. In a window too
 * short to hold it, `compact` tightens it up and lets it scroll.
 */
export function ModeRail({ compact = false }: { compact?: boolean }) {
  const { pathname } = useLocation();
  const account = MODES.filter((mode) => mode.id === "account");
  const main = MODES.filter((mode) => mode.id !== "account");
  return (
    <nav className={compact ? "fc-rail fc-rail--compact" : "fc-rail"} aria-label="Modes">
      <NavLink to="/" className="fc-rail__brand" aria-label="Field Club: back to the map">
        <BrandMark />
      </NavLink>
      <div className="fc-rail__group">
        {main.map((mode) => (
          <RailLink key={mode.id} mode={mode} pathname={pathname} compact={compact} />
        ))}
      </div>
      <div className="fc-rail__group fc-rail__group--end">
        {REFERENCE.map((mode) => (
          <RailLink key={mode.id} mode={mode} pathname={pathname} compact={compact} />
        ))}
        {account.map((mode) => (
          <RailLink key={mode.id} mode={mode} pathname={pathname} compact={compact} />
        ))}
      </div>
    </nav>
  );
}
