import { type ReactNode, type RefObject, useLayoutEffect, useRef } from "react";
import { useNavigate } from "react-router";
import { Panel } from "../../ui/Panel.js";
import { Sheet } from "../../ui/Sheet.js";
import { BARE_MAP_PATH } from "./navigation.js";
import { usePanelEnvironment } from "./panelContext.js";

export interface PanelFrameProps {
  /** Identifies the panel, so a different one takes focus afresh. Usually the path. */
  panelKey: string;
  title: string;
  subtitle?: string;
  /** Defaults to going back to the bare map (`BARE_MAP_PATH`). */
  onClose?: () => void;
  /**
   * Where focus goes when the panel closes and the control that opened it is
   * gone or unknown. Defaults to the shell's choice, the map.
   */
  fallbackFocus?: () => HTMLElement | null;
  children: ReactNode;
}

/**
 * Keyboard focus around a panel. Opening one moves focus to its title, so the
 * next Tab lands on its first control and a screen reader says what opened.
 * Closing one hands focus back to whatever opened it.
 *
 * It is a layout effect on purpose. Its clean-up runs before React takes the
 * panel out of the page, which is the last moment at which the page can still
 * say whether focus was inside it.
 */
function usePanelFocus(
  host: RefObject<HTMLElement | null>,
  title: RefObject<HTMLElement | null>,
  panelKey: string,
  shouldTakeFocus: () => boolean,
  fallbackFocus: () => HTMLElement | null,
): void {
  const latest = useRef({ shouldTakeFocus, fallbackFocus });
  latest.current = { shouldTakeFocus, fallbackFocus };
  /** The control that had focus when the panel opened. Kept when one panel's content gives way to another's. */
  const opener = useRef<HTMLElement | null>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: a new panel is the trigger
  useLayoutEffect(() => {
    const active = document.activeElement;
    if (active instanceof HTMLElement && active !== document.body && !host.current?.contains(active)) {
      opener.current = active;
    }
    // The shell says no for a panel that is on screen when the page first
    // loads, and for one that is only showing again because the panel on top
    // of it closed.
    if (latest.current.shouldTakeFocus()) title.current?.focus({ preventScroll: true });

    return () => {
      // Only focus that is about to be lost with the panel is moved. Focus
      // that is already somewhere else was put there on purpose.
      if (!host.current?.contains(document.activeElement)) return;
      const target = opener.current?.isConnected ? opener.current : latest.current.fallbackFocus();
      target?.focus({ preventScroll: true });
    };
  }, [panelKey]);
}

/**
 * Whatever panel is open, in the right container for the screen: the side
 * panel on a desktop, the bottom sheet on a phone. Feature pages render this
 * for their route.
 */
export function PanelFrame({ panelKey, title, subtitle, onClose, fallbackFocus, children }: PanelFrameProps) {
  const environment = usePanelEnvironment();
  const navigate = useNavigate();
  const close = onClose ?? (() => navigate(BARE_MAP_PATH));
  const host = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  usePanelFocus(host, titleRef, panelKey, environment.shouldTakeFocus, fallbackFocus ?? environment.fallbackFocus);

  if (environment.isPhone) {
    return (
      <div className="fc-panel-host fc-panel-host--sheet" ref={host}>
        <Sheet
          title={title}
          subtitle={subtitle}
          onClose={close}
          stop={environment.stop}
          onStopChange={environment.setStop}
          availableHeight={environment.sheetHeight}
          titleRef={titleRef}
        >
          {children}
        </Sheet>
      </div>
    );
  }
  return (
    <div className="fc-panel-host fc-panel-host--side" ref={host}>
      <Panel title={title} subtitle={subtitle} onClose={close} titleRef={titleRef}>
        {children}
      </Panel>
    </div>
  );
}
