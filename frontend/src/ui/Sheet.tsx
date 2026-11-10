import { type CSSProperties, type KeyboardEvent, type PointerEvent, useId, useRef, useState } from "react";
import { clamp } from "./math.js";
import { closeOnEscape, PanelHeader, type PanelProps } from "./Panel.js";
import "./Panel.css";

export type SheetStop = "peek" | "half" | "full";

export const SHEET_STOPS: readonly SheetStop[] = ["peek", "half", "full"];

/** Height of the sheet that stays visible at the peek stop: handle plus title row. */
export const SHEET_PEEK_HEIGHT = 76;

export interface SheetProps extends PanelProps {
  stop: SheetStop;
  onStopChange: (stop: SheetStop) => void;
  /** Height of the area the sheet may fill, in pixels. */
  availableHeight: number;
}

/** Visible height of the sheet at each stop. */
export function sheetHeights(availableHeight: number): Record<SheetStop, number> {
  const full = Math.max(SHEET_PEEK_HEIGHT, Math.round(availableHeight));
  return {
    peek: SHEET_PEEK_HEIGHT,
    half: Math.max(SHEET_PEEK_HEIGHT, Math.round(availableHeight * 0.5)),
    full,
  };
}

/** The stop whose height is nearest to `height`. */
export function nearestStop(height: number, heights: Record<SheetStop, number>): SheetStop {
  let best: SheetStop = "peek";
  for (const stop of SHEET_STOPS) {
    if (Math.abs(heights[stop] - height) < Math.abs(heights[best] - height)) best = stop;
  }
  return best;
}

const STOP_LABEL: Record<SheetStop, string> = {
  peek: "collapsed",
  half: "half open",
  full: "fully open",
};

/**
 * The phone panel: a bottom sheet with three stops. Drag the handle or the
 * title, tap the handle to step through the stops, or use the arrow keys.
 * The sheet is exactly as tall as the part of it on screen, so its body
 * scrolls to its end at every stop.
 */
export function Sheet({
  title,
  subtitle,
  onClose,
  actions,
  titleRef,
  children,
  stop,
  onStopChange,
  availableHeight,
}: SheetProps) {
  const titleId = useId();
  const heights = sheetHeights(availableHeight);
  const [dragHeight, setDragHeight] = useState<number | null>(null);
  const drag = useRef<{ pointerId: number; startY: number; startHeight: number; moved: boolean } | null>(null);

  const visible = dragHeight ?? heights[stop];
  const style = { "--sheet-height": `${visible}px` } as CSSProperties;

  // Plain functions: `heights` is new on every render, so memoising these would save nothing.
  function onPointerDown(event: PointerEvent<HTMLElement>): void {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    // A press on a button in the header is a click, not the start of a drag.
    if ((event.target as HTMLElement).closest(".fc-icon-button")) return;
    drag.current = { pointerId: event.pointerId, startY: event.clientY, startHeight: heights[stop], moved: false };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event: PointerEvent<HTMLElement>): void {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    const delta = current.startY - event.clientY;
    if (Math.abs(delta) > 4) current.moved = true;
    if (current.moved) setDragHeight(clamp(current.startHeight + delta, SHEET_PEEK_HEIGHT, heights.full));
  }

  function endDrag(event: PointerEvent<HTMLElement>): void {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    drag.current = null;
    if (current.moved && dragHeight !== null) onStopChange(nearestStop(dragHeight, heights));
    setDragHeight(null);
  }

  function step(direction: 1 | -1): void {
    const next = SHEET_STOPS[SHEET_STOPS.indexOf(stop) + direction];
    if (next) onStopChange(next);
  }

  function onHandleClick(): void {
    // A drag ends in a click too. Only a plain tap steps the sheet.
    if (dragHeight !== null) return;
    const index = SHEET_STOPS.indexOf(stop);
    onStopChange(SHEET_STOPS[(index + 1) % SHEET_STOPS.length] as SheetStop);
  }

  function onHandleKeyDown(event: KeyboardEvent<HTMLButtonElement>): void {
    if (event.key === "ArrowUp") {
      event.preventDefault();
      step(1);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      step(-1);
    }
  }

  const dragHandlers = {
    onPointerDown,
    onPointerMove,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
  };

  return (
    <aside
      className={dragHeight === null ? "fc-panel fc-sheet" : "fc-panel fc-sheet fc-sheet--dragging"}
      style={style}
      aria-labelledby={titleId}
      data-stop={stop}
      onKeyDown={closeOnEscape(onClose)}
    >
      <button
        type="button"
        className="fc-sheet__handle"
        aria-label={`Panel is ${STOP_LABEL[stop]}. Press to resize.`}
        onClick={onHandleClick}
        onKeyDown={onHandleKeyDown}
        {...dragHandlers}
      />
      <div {...dragHandlers}>
        <PanelHeader
          title={title}
          subtitle={subtitle}
          onClose={onClose}
          actions={actions}
          titleId={titleId}
          titleRef={titleRef}
        />
      </div>
      <div className="fc-panel__body" inert={stop === "peek" && dragHeight === null}>
        {children}
      </div>
    </aside>
  );
}
