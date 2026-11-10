import type { CSSProperties } from "react";
import { tierVar } from "./tokens.js";
import "./Meter.css";
import { clamp } from "./math.js";

export interface MeterTier {
  id: string;
  label: string;
  base_score: number;
}

export interface MeterProps {
  /** Confidence, 0 to 100. */
  value: number;
  /** The ladder, lowest step first, from `/meta`. */
  tiers: MeterTier[];
  /** The step the finding is on. */
  tierId: string;
  /** A ruled-out finding scores nothing and shows an empty track. */
  ruledOut?: boolean;
  /** Show each step's score under its tick. */
  showScale?: boolean;
}

/**
 * The confidence meter. The bar fills to the score, and a tick marks the base
 * score of every step on the ladder, so you can see how far the next one is.
 * The current step is also given in words, because colour and position alone
 * never carry meaning here.
 */
export function Meter({ value, tiers, tierId, ruledOut = false, showScale = false }: MeterProps) {
  const score = clamp(Number.isFinite(value) ? value : 0, 0, 100);
  const current = tiers.find((tier) => tier.id === tierId);
  const label = ruledOut
    ? "Explained. Confidence 0 out of 100."
    : `${current?.label ?? "Unknown step"}. Confidence ${Math.round(score)} out of 100.`;
  const classes = ["fc-meter"];
  if (ruledOut) classes.push("fc-meter--ruled-out");
  return (
    <div className={classes.join(" ")} style={{ "--meter-colour": tierVar(tierId) } as CSSProperties}>
      {/* biome-ignore lint/a11y/useSemanticElements: a native meter cannot hold the tier ticks */}
      <div
        className="fc-meter__track"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={ruledOut ? 0 : Math.round(score)}
        aria-valuetext={label}
        aria-label="Confidence"
      >
        <div className="fc-meter__fill" style={{ width: `${score}%` }} />
        {tiers.map((tier) => {
          const tickClasses = ["fc-meter__tick"];
          if (!ruledOut && tier.base_score <= score) tickClasses.push("fc-meter__tick--reached");
          if (!ruledOut && tier.id === tierId) tickClasses.push("fc-meter__tick--current");
          return (
            <span
              key={tier.id}
              className={tickClasses.join(" ")}
              style={{ left: `${tier.base_score}%` }}
              title={`${tier.label}: ${tier.base_score}`}
              data-tier={tier.id}
            />
          );
        })}
      </div>
      {showScale ? (
        <div className="fc-meter__scale" aria-hidden="true">
          {tiers.map((tier) => (
            <span
              key={tier.id}
              className={tier.id === tierId && !ruledOut ? "fc-meter__step--current" : undefined}
              style={{ left: `${tier.base_score}%` }}
            >
              {tier.base_score}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
