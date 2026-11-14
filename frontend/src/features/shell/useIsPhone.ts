import { useEffect, useState } from "react";
import { PHONE_QUERY, SHORT_QUERY } from "../../ui/tokens.js";

function matches(query: string): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(query).matches
    : false;
}

/** Whether a media query matches, kept current as the window changes. */
function useMediaQuery(query: string): boolean {
  const [matched, setMatched] = useState(() => matches(query));
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const onChange = (): void => setMatched(list.matches);
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);
  return matched;
}

/** Whether the window is under 720 px now, for code that reads it once rather than following it. */
export function isPhoneNow(): boolean {
  return matches(PHONE_QUERY);
}

/** True under 720 px, where the shell switches to the phone layout. */
export function useIsPhone(): boolean {
  return useMediaQuery(PHONE_QUERY);
}

/** True in a window too short for the whole mode rail, such as a phone held sideways. */
export function useIsShort(): boolean {
  return useMediaQuery(SHORT_QUERY);
}

/** The height of the window, kept current as it resizes. */
export function useWindowHeight(): number {
  const [height, setHeight] = useState(() => (typeof window === "undefined" ? 0 : window.innerHeight));
  useEffect(() => {
    const onResize = (): void => setHeight(window.innerHeight);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return height;
}
