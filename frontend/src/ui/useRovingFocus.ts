import { useMemo, useRef } from "react";

export interface RovingFocus {
  /** A ref callback for the element that stands for `id`. */
  refFor: (id: string) => (element: HTMLElement | null) => void;
  /** Move keyboard focus to the element that stands for `id`. */
  focus: (id: string) => void;
}

/**
 * Keeps hold of each item in a group with a roving tabindex, such as tabs or
 * a radio row of chips, so the arrow keys can move focus along it.
 */
export function useRovingFocus(): RovingFocus {
  const elements = useRef(new Map<string, HTMLElement>());
  return useMemo(
    () => ({
      refFor: (id) => (element) => {
        if (element) elements.current.set(id, element);
        else elements.current.delete(id);
      },
      focus: (id) => elements.current.get(id)?.focus(),
    }),
    [],
  );
}
