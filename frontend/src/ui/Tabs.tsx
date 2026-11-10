import type { KeyboardEvent, ReactNode } from "react";
import { useRovingFocus } from "./useRovingFocus.js";
import "./Tabs.css";

export interface TabItem {
  id: string;
  label: string;
  /** A second, quieter line under the label. */
  detail?: string;
}

export interface TabsProps {
  /** Names the tab list for screen readers. */
  label: string;
  tabs: TabItem[];
  value: string;
  onChange: (id: string) => void;
  /** Prefix for tab and panel ids, so `TabPanel` can point back at its tab. */
  idPrefix: string;
}

export function tabId(idPrefix: string, id: string): string {
  return `${idPrefix}-tab-${id}`;
}

export function tabPanelId(idPrefix: string, id: string): string {
  return `${idPrefix}-panel-${id}`;
}

export function Tabs({ label, tabs, value, onChange, idPrefix }: TabsProps) {
  const roving = useRovingFocus();

  function select(index: number): void {
    const tab = tabs[(index + tabs.length) % tabs.length];
    if (!tab) return;
    onChange(tab.id);
    roving.focus(tab.id);
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number): void {
    if (event.key === "ArrowRight") select(index + 1);
    else if (event.key === "ArrowLeft") select(index - 1);
    else if (event.key === "Home") select(0);
    else if (event.key === "End") select(tabs.length - 1);
    else return;
    event.preventDefault();
  }

  return (
    <div className="fc-tabs" role="tablist" aria-label={label}>
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          id={tabId(idPrefix, tab.id)}
          className="fc-tab"
          aria-selected={tab.id === value}
          aria-controls={tabPanelId(idPrefix, tab.id)}
          tabIndex={tab.id === value ? 0 : -1}
          onClick={() => onChange(tab.id)}
          onKeyDown={(event) => onKeyDown(event, index)}
          ref={roving.refFor(tab.id)}
        >
          {tab.label}
          {tab.detail ? <span className="fc-tab__detail">{tab.detail}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ idPrefix, id, children }: { idPrefix: string; id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={tabPanelId(idPrefix, id)} aria-labelledby={tabId(idPrefix, id)}>
      {children}
    </div>
  );
}
