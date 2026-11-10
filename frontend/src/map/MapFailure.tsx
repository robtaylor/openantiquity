import { Unplug } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../ui/Button.js";
import { EmptyState } from "../ui/EmptyState.js";

export interface MapFailureProps {
  title: string;
  actionLabel: string;
  onAction: () => void;
  /** The error message, shown in small type under the explanation. */
  detail: string;
  /** The explanation, in plain words. */
  children: ReactNode;
}

/** The notice that stands in for a map that cannot be shown. */
export function MapFailure({ title, actionLabel, onAction, detail, children }: MapFailureProps) {
  return (
    <div className="fc-map__failure">
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title={title}
        action={
          <Button variant="primary" onClick={onAction}>
            {actionLabel}
          </Button>
        }
      >
        {children}
        <p className="fc-map__failure-detail fc-mono">{detail}</p>
      </EmptyState>
    </div>
  );
}
