import { type RefObject, useEffect, useRef } from "react";

/**
 * While `open`, call `onDismiss` when a pointer goes down outside `ref`, or
 * when Escape is pressed anywhere. For pop-ups and menus that close by
 * themselves.
 */
export function useDismiss(
  ref: RefObject<HTMLElement | null>,
  open: boolean,
  onDismiss: (cause: "pointer" | "escape") => void,
): void {
  const latest = useRef(onDismiss);
  latest.current = onDismiss;

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent): void {
      if (!ref.current?.contains(event.target as Node)) latest.current("pointer");
    }
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") latest.current("escape");
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [ref, open]);
}
