/**
 * Whether the person has asked for less motion. CSS turns transitions off
 * itself (`base.css`), but a script that asks for smooth scrolling overrides
 * that, so scripts ask here first.
 */
export function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** The scroll behaviour to ask for: smooth, unless the person has asked for less motion. */
export function scrollBehaviour(): ScrollBehavior {
  return prefersReducedMotion() ? "auto" : "smooth";
}
