import { createContext, useContext } from "react";
import type { SheetStop } from "../../ui/Sheet.js";

/** What the shell tells every panel about where it is shown. */
export interface PanelEnvironment {
  isPhone: boolean;
  sheetHeight: number;
  /** Where the phone sheet rests. The shell owns it, so floating controls can stay clear of the sheet. */
  stop: SheetStop;
  setStop: (stop: SheetStop) => void;
  /** Asked as a panel appears: whether it should take keyboard focus. See `PanelFrame`. */
  shouldTakeFocus: () => boolean;
  /** Where focus goes when a panel closes and whatever opened it cannot have it back. */
  fallbackFocus: () => HTMLElement | null;
}

const PanelEnvironmentContext = createContext<PanelEnvironment | null>(null);

export const PanelEnvironmentProvider = PanelEnvironmentContext.Provider;

export function usePanelEnvironment(): PanelEnvironment {
  const environment = useContext(PanelEnvironmentContext);
  if (!environment) throw new Error("A panel was rendered outside the shell");
  return environment;
}
