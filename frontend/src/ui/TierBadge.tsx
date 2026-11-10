import type { CSSProperties } from "react";
import { stateVar, tierVar } from "./tokens.js";
import "./TierBadge.css";

export interface TierBadgeProps {
  /** The step on the ladder, from `/meta`. */
  tier: { id: string; label: string };
  /** The finding's state, when it is anything other than open. */
  state?: { id: string; label: string };
  size?: "sm" | "md";
}

/**
 * The step a finding is on, as a coloured mark and its name. The mark matches
 * the map marker: a filled dot, a ring for a known site, a small grey ring for
 * one that has been explained.
 */
export function TierBadge({ tier, state, size = "md" }: TierBadgeProps) {
  const ruledOut = state?.id === "ruled_out" || state?.id === "withdrawn";
  const known = state?.id === "known";
  const colour = ruledOut ? (stateVar("ruled_out") as string) : tierVar(tier.id);
  const markClasses = ["fc-tier-badge__mark"];
  if (ruledOut) markClasses.push("fc-tier-badge__mark--ruled-out");
  else if (known) markClasses.push("fc-tier-badge__mark--ring");
  const showState = state !== undefined && state.id !== "open";
  return (
    <span
      className={size === "sm" ? "fc-tier-badge fc-tier-badge--sm" : "fc-tier-badge"}
      style={{ "--badge-colour": colour } as CSSProperties}
      data-tier={tier.id}
      data-state={state?.id}
    >
      <span className={markClasses.join(" ")} aria-hidden="true" />
      {ruledOut ? state?.label : tier.label}
      {showState && !ruledOut ? <span className="fc-tier-badge__state">· {state.label}</span> : null}
    </span>
  );
}
