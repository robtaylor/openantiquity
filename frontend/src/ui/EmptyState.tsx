import { type ReactNode, useContext } from "react";
import { ErrorReportContext } from "./errorReport.js";
import "./EmptyState.css";

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  /** Says what to do next, or for an error, what happened. */
  children?: ReactNode;
  /** A button: the next step, or "Try again" for an error. An error also offers what `ErrorReportContext` gives after it. */
  action?: ReactNode;
  tone?: "neutral" | "error";
}

export function EmptyState({ icon, title, children, action, tone = "neutral" }: EmptyStateProps) {
  const Report = useContext(ErrorReportContext);
  const report = tone === "error" && Report ? <Report /> : null;
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
      {action || report ? (
        <div className="fc-empty__action">
          {action}
          {report}
        </div>
      ) : null}
    </div>
  );
}
