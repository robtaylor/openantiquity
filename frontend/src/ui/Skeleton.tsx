import type { CSSProperties } from "react";
import "./Skeleton.css";

export interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  /** Draw this many text-like lines, the last one shorter. */
  lines?: number;
}

/** A placeholder shape shown while content loads. Hidden from screen readers. */
export function Skeleton({ width = "100%", height, lines }: SkeletonProps) {
  if (lines !== undefined && lines > 1) {
    return (
      <span className="fc-skeleton-lines" aria-hidden="true">
        {Array.from({ length: lines }, (_, index) => (
          <span
            // biome-ignore lint/suspicious/noArrayIndexKey: the lines are identical and never reorder
            key={index}
            className="fc-skeleton"
            style={{ width: index === lines - 1 ? "60%" : width, height } as CSSProperties}
          />
        ))}
      </span>
    );
  }
  return <span className="fc-skeleton" style={{ width, height } as CSSProperties} aria-hidden="true" />;
}
