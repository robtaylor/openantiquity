/**
 * The drawing guide: a card on the map, in the search box's place, while
 * the drawing tool is open. It lists the gestures that apply now
 * (`guideRows`), each as an icon, the gesture and what it does, so the eye
 * runs down the gestures. Its header has a button that swaps it for the
 * search box and one that folds it down to the header, a choice the
 * browser keeps for next time. As it grows or folds, the map moves so that
 * no point placed is under it.
 */

import {
  ArrowBigUp,
  ArrowLeftRight,
  Brackets,
  Check,
  ChevronDown,
  ChevronUp,
  CircleDot,
  Crosshair,
  Diamond,
  GitCommitHorizontal,
  type LucideIcon,
  MousePointerClick,
  Move,
  Pointer,
  Route,
  Search,
  Spline,
  SquareDashed,
  Trash2,
  Waypoints,
  X,
} from "lucide-react";
import { type RefObject, useEffect, useId, useRef, useState } from "react";
import { isMapLive } from "../../map/MapPane.js";
import { useMainMap } from "../../map/mainMap.js";
import { useMapStore } from "../../map/store.js";
import { IconButton } from "../../ui/IconButton.js";
import { useIsPhone } from "../shell/useIsPhone.js";
import { useDevice } from "./DrawingTool.js";
import { GUIDE_FOLDED_KEY, type GuideIcon, type GuideRow, guideRows, stageOf } from "./guideRows.js";
import { clearPointsOfGuide } from "./keepClear.js";
import { useMarkPath, useMarkStore } from "./markStore.js";
import { canClose, hasRoomForPoint, segmentMiddles } from "./path.js";
import "./mark.css";

const ICONS: Record<GuideIcon, LucideIcon> = {
  click: MousePointerClick,
  tap: Pointer,
  again: Route,
  close: SquareDashed,
  move: Move,
  dot: GitCommitHorizontal,
  curved: Spline,
  straight: Diamond,
  switch: ArrowLeftRight,
  select: CircleDot,
  end: Waypoints,
  "keys-move": Move,
  "keys-further": ArrowBigUp,
  "keys-step": Brackets,
  "keys-delete": Trash2,
  "keys-stop": Check,
  "keys-leave": X,
  cross: Crosshair,
};

/** Whether the guide was left folded. A browser that refuses storage starts it unfolded. */
function readFolded(): boolean {
  try {
    return window.localStorage.getItem(GUIDE_FOLDED_KEY) === "folded";
  } catch {
    return false;
  }
}

function keepFolded(folded: boolean): void {
  try {
    window.localStorage.setItem(GUIDE_FOLDED_KEY, folded ? "folded" : "open");
  } catch {
    // A browser that refuses storage folds the guide all the same, for this visit.
  }
}

/**
 * Whenever the guide appears or changes size, as its rows change or it
 * folds, the map moves down by as little as keeps every point placed out
 * from under it, unless that would put one under the phone's bar.
 */
function useGuideKeepsPointsClear(card: RefObject<HTMLElement | null>): void {
  const map = useMainMap();
  useEffect(() => {
    const element = card.current;
    if (!map || !element || !isMapLive(map) || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (!isMapLive(map)) return;
      const bar = document.querySelector(".fc-mark-float")?.getBoundingClientRect() ?? null;
      clearPointsOfGuide(map, element.getBoundingClientRect(), bar);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [map, card]);
}

/** The rows for the marking as it stands and the device in hand. */
function useGuideRows(): GuideRow[] {
  const map = useMainMap();
  const isPhone = useIsPhone();
  const device = useDevice(map, isPhone);
  const path = useMarkPath();
  const drawing = useMarkStore((state) => state.drawing);
  const end = useMarkStore((state) => state.end);
  const nextKind = useMarkStore((state) => state.nextKind);
  const limits = useMapStore((state) => state.meta?.shapes);
  const dots = segmentMiddles(path).length > 0 && limits !== undefined && hasRoomForPoint(path, limits);
  return guideRows({ stage: stageOf(path), drawing, device, nextKind, end, canClose: canClose(path), dots });
}

function Row({ row }: { row: GuideRow }) {
  const Icon = ICONS[row.icon];
  return (
    <li className="fc-draw-guide__row" data-row={row.id}>
      <Icon className="fc-draw-guide__icon" size={16} aria-hidden />
      <span className="fc-draw-guide__gesture">
        {row.gesture.map((part, index) =>
          typeof part === "string" ? (
            // biome-ignore lint/suspicious/noArrayIndexKey: a gesture's parts are fixed in order
            <span key={index}>{part}</span>
          ) : (
            // biome-ignore lint/suspicious/noArrayIndexKey: a gesture's parts are fixed in order
            <kbd key={index}>{part.key}</kbd>
          ),
        )}
      </span>
      <span className="fc-visually-hidden">: </span>
      <span className="fc-draw-guide__effect">{row.effect}</span>
    </li>
  );
}

/**
 * The card itself. `onSearch` swaps it for the search box, and
 * `focusSearch` puts focus on its search button as it appears, for when it
 * comes back from a search left with Escape.
 */
export function DrawingGuide({ onSearch, focusSearch = false }: { onSearch: () => void; focusSearch?: boolean }) {
  const rows = useGuideRows();
  const [folded, setFolded] = useState(readFolded);
  const headingId = useId();
  const listId = useId();
  const searchButton = useRef<HTMLButtonElement>(null);
  const card = useRef<HTMLElement>(null);
  useGuideKeepsPointsClear(card);

  // biome-ignore lint/correctness/useExhaustiveDependencies: focus goes back once, as the card appears
  useEffect(() => {
    if (focusSearch) searchButton.current?.focus();
  }, []);

  function toggle(): void {
    const next = !folded;
    setFolded(next);
    keepFolded(next);
  }

  return (
    <section className="fc-draw-guide" aria-labelledby={headingId} data-folded={folded} ref={card}>
      <div className="fc-draw-guide__header">
        <h2 className="fc-draw-guide__title" id={headingId}>
          How to draw
        </h2>
        <IconButton size="sm" label="Search for a place" onClick={onSearch} ref={searchButton}>
          <Search size={16} aria-hidden />
        </IconButton>
        <IconButton
          size="sm"
          label={folded ? "Show the gestures" : "Hide the gestures"}
          aria-expanded={!folded}
          aria-controls={listId}
          onClick={toggle}
        >
          {folded ? <ChevronDown size={16} aria-hidden /> : <ChevronUp size={16} aria-hidden />}
        </IconButton>
      </div>
      <ul className="fc-draw-guide__list" id={listId} hidden={folded}>
        {rows.map((row) => (
          <Row key={row.id} row={row} />
        ))}
      </ul>
    </section>
  );
}
