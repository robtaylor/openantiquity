import type { ReactNode } from "react";
import { ReportProblemButton } from "../features/problem/ReportProblem.js";
import "./EmptyState.css";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  /** Says what to do next, or for an error, what happened. */
  children?: ReactNode;
  /** A button: the next step, or "Try again" for an error. An error also offers "Report a problem" after it. */
  action?: ReactNode;
  tone?: "neutral" | "error";
}

export function EmptyState({ icon, title, children, action, tone = "neutral" }: EmptyStateProps) {
  return (
    <div
      className={tone === "error" ? "fc-empty fc-empty--error" : "fc-empty"}
      role={tone === "error" ? "alert" : undefined}
    >
      {icon ? (
        <span className="fc-empty__icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <h3 className="fc-empty__title">{title}</h3>
      {children ? <div className="fc-empty__body">{children}</div> : null}
      {action || tone === "error" ? (
        <div className="fc-empty__action">
          {action}
          {tone === "error" ? <ReportProblemButton /> : null}
        </div>
      ) : null}
    </div>
  );
}
