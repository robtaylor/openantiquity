/**
 * A short list to choose one thing from, opened beside a point on the
 * screen: a popover by the pointer on a computer, a short sheet on a phone.
 * Either way it never covers the point (docs/UI.md, "Behaviour"): the
 * popover sits in the quarter away from the screen's middle, and the sheet
 * at the top or the bottom, whichever leaves the point clear.
 *
 * Built on `Dialog`, so it takes focus, keeps Tab inside and closes on
 * Escape. The first entry takes focus on opening. The arrow keys, Home and
 * End move through the entries, Enter chooses, and hovering or focusing an
 * entry reports it, so what it stands for can be shown.
 */

import { type CSSProperties, type KeyboardEvent, type ReactNode, useEffect, useRef } from "react";
import { Button } from "./Button.js";
import { Dialog } from "./Dialog.js";
import "./Chooser.css";

export interface ChooserEntry {
  id: string;
  /** What the entry shows. */
  content: ReactNode;
  /** Its accessible name, which `content` should say too. */
  label: string;
}

export interface ChooserProps {
  open: boolean;
  title: string;
  /** The point it is opened beside, in pixels from the window's top left. */
  at: { x: number; y: number };
  /** A sheet on a phone, a popover elsewhere. */
  sheet: boolean;
  entries: readonly ChooserEntry[];
  /** A last button below the entries, such as "Show all in Explore". */
  more?: { label: string; onClick: () => void };
  onChoose: (id: string) => void;
  /** The entry hovered or focused, or null once none is. */
  onActive?: (id: string | null) => void;
  onClose: () => void;
}

/** Space kept between the point and the chooser, in pixels. */
export const CHOOSER_GAP = 16;

/** Where the chooser goes, so the point stays in sight. */
export function chooserPlace(
  at: { x: number; y: number },
  sheet: boolean,
  view: { width: number; height: number },
): { place: string; style: CSSProperties } {
  const below = at.y < view.height / 2;
  if (sheet) {
    // The sheet takes the side of the screen the point isn't on, and stops short of it.
    return below
      ? { place: "sheet-bottom", style: { maxHeight: Math.max(120, view.height - at.y - CHOOSER_GAP * 2) } }
      : { place: "sheet-top", style: { maxHeight: Math.max(120, at.y - CHOOSER_GAP * 2) } };
  }
  const right = at.x < view.width / 2;
  const style: CSSProperties = right ? { left: at.x + CHOOSER_GAP } : { right: view.width - at.x + CHOOSER_GAP };
  if (below) style.top = at.y + CHOOSER_GAP;
  else style.bottom = view.height - at.y + CHOOSER_GAP;
  return { place: `popover-${below ? "below" : "above"}-${right ? "right" : "left"}`, style };
}

export function Chooser({ open, title, at, sheet, entries, more, onChoose, onActive, onClose }: ChooserProps) {
  const list = useRef<HTMLUListElement>(null);
  const { place, style } = chooserPlace(at, sheet, { width: window.innerWidth, height: window.innerHeight });

  // After the dialog has put focus on its title, the first entry takes it, so the arrow keys work at once.
  useEffect(() => {
    if (!open) return;
    list.current?.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true });
  }, [open]);

  function onKeyDown(event: KeyboardEvent<HTMLUListElement>): void {
    const buttons = [...(list.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])];
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    let next: number | null = null;
    if (event.key === "ArrowDown") next = Math.min(buttons.length - 1, index + 1);
    else if (event.key === "ArrowUp") next = Math.max(0, index - 1);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = buttons.length - 1;
    if (next === null) return;
    event.preventDefault();
    buttons[next]?.focus();
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      className={sheet ? "fc-chooser fc-chooser--sheet" : "fc-chooser fc-chooser--popover"}
      style={style}
      place={place}
    >
      <ul className="fc-chooser__list" ref={list} onKeyDown={onKeyDown} onMouseLeave={() => onActive?.(null)}>
        {entries.map((entry) => (
          <li key={entry.id}>
            <button
              type="button"
              className="fc-chooser__entry"
              aria-label={entry.label}
              onClick={() => onChoose(entry.id)}
              onFocus={() => onActive?.(entry.id)}
              onMouseEnter={() => onActive?.(entry.id)}
            >
              {entry.content}
            </button>
          </li>
        ))}
      </ul>
      {more ? (
        <Button size="sm" variant="ghost" onClick={more.onClick}>
          {more.label}
        </Button>
      ) : null}
    </Dialog>
  );
}
