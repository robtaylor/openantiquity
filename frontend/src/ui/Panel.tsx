import { X } from "lucide-react";
import { type KeyboardEvent, type ReactNode, type Ref, useId } from "react";
import { IconButton } from "./IconButton.js";
import "./Panel.css";

export interface PanelProps {
  title: string;
  subtitle?: string;
  /** Leave out for a panel that cannot be closed. */
  onClose?: () => void;
  /** Extra controls in the header, before the close button. */
  actions?: ReactNode;
  /**
   * The title element. It can take focus from script, though not from the Tab
   * key, so whatever opens the panel can put keyboard focus at its start.
   */
  titleRef?: Ref<HTMLHeadingElement>;
  children: ReactNode;
}

export function PanelHeader({
  title,
  subtitle,
  onClose,
  actions,
  titleId,
  titleRef,
}: Pick<PanelProps, "title" | "subtitle" | "onClose" | "actions" | "titleRef"> & { titleId: string }) {
  return (
    <header className="fc-panel__header">
      <div className="fc-panel__titles">
        <h2 className="fc-panel__title" id={titleId} ref={titleRef} tabIndex={-1}>
          {title}
        </h2>
        {subtitle ? <p className="fc-panel__subtitle">{subtitle}</p> : null}
      </div>
      {actions}
      {onClose ? (
        <IconButton label="Close panel" onClick={onClose}>
          <X size={20} aria-hidden />
        </IconButton>
      ) : null}
    </header>
  );
}

/**
 * Escape closes a panel from anywhere inside it. A control inside that uses
 * Escape itself, such as an open menu, calls preventDefault and is left to it.
 */
export function closeOnEscape(onClose: (() => void) | undefined) {
  return (event: KeyboardEvent<HTMLElement>): void => {
    if (event.key !== "Escape" || event.defaultPrevented || !onClose) return;
    event.preventDefault();
    onClose();
  };
}

/** The desktop side panel: opaque, 400 px wide, scrolling on its own. */
export function Panel({ title, subtitle, onClose, actions, titleRef, children }: PanelProps) {
  const titleId = useId();
  return (
    <aside className="fc-panel fc-panel--side" aria-labelledby={titleId} onKeyDown={closeOnEscape(onClose)}>
      <PanelHeader
        title={title}
        subtitle={subtitle}
        onClose={onClose}
        actions={actions}
        titleId={titleId}
        titleRef={titleRef}
      />
      <div className="fc-panel__body">{children}</div>
    </aside>
  );
}
