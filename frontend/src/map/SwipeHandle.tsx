import { ChevronsLeftRight } from "lucide-react";
import { type CSSProperties, type KeyboardEvent, type PointerEvent, useRef } from "react";

export interface SwipeHandleProps {
  /** Distance of the divide from the left edge of the map, in pixels. */
  x: number;
  /** The same position as a fraction of the usable width. */
  position: number;
  /** The nearest the divide may come to each side, as fractions. Home and End go to these. */
  min: number;
  max: number;
  /** The span the labels may use, in pixels from the left edge of the map: clear of the rail, the panel and the buttons. */
  labelLeft: number;
  labelRight: number;
  leftLabel: string;
  rightLabel: string;
  /** Called while dragging, with the pointer's clientX. */
  onMove: (clientX: number) => void;
  /** Called from the keyboard, with a new fraction. */
  onPosition: (position: number) => void;
}

/** Space between the divide and each label. */
export const LABEL_GAP = 10;
/** A label with less room than this is left out: a few clipped letters say nothing. */
export const MIN_LABEL_WIDTH = 56;

export interface LabelPlacement {
  /** Null when there is no room for the label. Otherwise its inline style, relative to the divide. */
  left: CSSProperties | null;
  right: CSSProperties | null;
}

/**
 * Where the two layer names go. Each sits beside the divide on its own side,
 * shrinks as that side narrows, and goes when there is no room left, so a
 * label never runs under the rail, the panel or the floating buttons.
 */
export function placeLabels(x: number, labelLeft: number, labelRight: number): LabelPlacement {
  // The left label ends beside the divide, or at the end of the usable span if the divide is past it.
  const leftEnd = Math.min(x - LABEL_GAP, labelRight);
  const leftRoom = leftEnd - labelLeft;
  const rightStart = Math.max(x + LABEL_GAP, labelLeft);
  const rightRoom = labelRight - rightStart;
  return {
    left: leftRoom >= MIN_LABEL_WIDTH ? { right: x - leftEnd, maxWidth: leftRoom } : null,
    right: rightRoom >= MIN_LABEL_WIDTH ? { left: rightStart - x, maxWidth: rightRoom } : null,
  };
}

/**
 * The divide between the main view (left) and the comparison view (right).
 * Drag it, or focus it and use the arrow keys. Shift moves in bigger steps.
 */
export function SwipeHandle({
  x,
  position,
  min,
  max,
  labelLeft,
  labelRight,
  leftLabel,
  rightLabel,
  onMove,
  onPosition,
}: SwipeHandleProps) {
  const dragging = useRef(false);

  function onPointerDown(event: PointerEvent<HTMLDivElement>): void {
    dragging.current = true;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>): void {
    if (dragging.current) onMove(event.clientX);
  }

  function endDrag(): void {
    dragging.current = false;
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const step = event.shiftKey ? 0.1 : 0.02;
    let next: number;
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") next = position - step;
    else if (event.key === "ArrowRight" || event.key === "ArrowUp") next = position + step;
    else if (event.key === "Home") next = min;
    else if (event.key === "End") next = max;
    else return;
    event.preventDefault();
    onPosition(next);
  }

  const percent = Math.round(position * 100);
  const labels = placeLabels(x, labelLeft, labelRight);
  return (
    <div className="fc-swipe" style={{ transform: `translateX(${x}px)` }}>
      <div className="fc-swipe__labels" aria-hidden="true">
        {labels.left ? (
          <span className="fc-swipe__label fc-swipe__label--left" style={labels.left}>
            {leftLabel}
          </span>
        ) : null}
        {labels.right ? (
          <span className="fc-swipe__label fc-swipe__label--right" style={labels.right}>
            {rightLabel}
          </span>
        ) : null}
      </div>
      <div
        className="fc-swipe__bar"
        role="slider"
        tabIndex={0}
        aria-label="Comparison divide"
        aria-orientation="horizontal"
        aria-valuemin={Math.round(min * 100)}
        aria-valuemax={Math.round(max * 100)}
        aria-valuenow={percent}
        aria-valuetext={`${leftLabel} on the left ${percent}%, ${rightLabel} on the right`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onKeyDown={onKeyDown}
      >
        <span className="fc-swipe__line" />
        <span className="fc-swipe__grip">
          <ChevronsLeftRight size={18} aria-hidden />
        </span>
      </div>
    </div>
  );
}
