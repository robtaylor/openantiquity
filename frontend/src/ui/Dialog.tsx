import { X } from "lucide-react";
import { type KeyboardEvent, type ReactNode, useEffect, useId, useLayoutEffect, useRef } from "react";
import { IconButton } from "./IconButton.js";
import { closeOnEscape } from "./Panel.js";
import "./Dialog.css";

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Buttons for the foot of the dialog, with the main one last. */
  actions?: ReactNode;
  /** Extra classes, for a dialog with a layout of its own. */
  className?: string;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Tab from the last control goes to the first, and Shift+Tab from the first
 * to the last. A native modal dialog lets Tab leave for the browser's own
 * controls, which a person using the keyboard can lose themselves in.
 */
function wrapTab(event: KeyboardEvent<HTMLElement>): void {
  if (event.key !== "Tab" || event.defaultPrevented) return;
  const controls = [...event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (element) => !element.closest("[inert], [hidden]"),
  );
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (!first || !last) return;
  // Focus may be on something that isn't a control, such as the title.
  const index = controls.indexOf(document.activeElement as HTMLElement);
  if (event.shiftKey && index <= 0) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && index === controls.length - 1) {
    event.preventDefault();
    first.focus();
  }
}

/**
 * A modal dialog on the native `<dialog>` element. Opening it puts focus on
 * its title. It keeps Tab inside, closes on Escape and puts focus back where
 * it came from, whether it is closed with `open` or taken out of the page
 * while open.
 */
export function Dialog({ open, onClose, title, children, actions, className }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const titleId = useId();
  /** What had focus when it opened. */
  const opener = useRef<HTMLElement | null>(null);

  // The browser hands focus back when a dialog is closed, but not when it is
  // taken out of the page. A layout effect's clean-up runs while the dialog
  // is still there, so it can tell whether focus is about to be lost with it.
  useLayoutEffect(() => {
    if (!open) return;
    const active = document.activeElement;
    if (active instanceof HTMLElement && !ref.current?.contains(active)) opener.current = active;
    const dialog = ref.current;
    return () => {
      const now = document.activeElement;
      const lost = now === null || now === document.body || dialog?.contains(now) === true;
      if (lost && opener.current?.isConnected) opener.current.focus({ preventScroll: true });
    };
  }, [open]);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // jsdom has no showModal, so tests fall back to the open attribute.
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      // As a panel does: focus on the title, so a screen reader says what
      // opened and the next Tab lands on the first control.
      titleRef.current?.focus({ preventScroll: true });
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={className ? `fc-dialog ${className}` : "fc-dialog"}
      aria-labelledby={titleId}
      onClose={() => {
        // The browser sends "close" a moment after the dialog shuts. If it has
        // been opened again since, the event is stale and is ignored.
        if (!ref.current?.open) onClose();
      }}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        // A click on the backdrop lands on the dialog element itself.
        if (event.target === event.currentTarget) onClose();
      }}
      onKeyDown={(event) => {
        closeOnEscape(onClose)(event);
        wrapTab(event);
      }}
    >
      {open ? (
        <>
          <div className="fc-dialog__header">
            <h2 className="fc-dialog__title" id={titleId} ref={titleRef} tabIndex={-1}>
              {title}
            </h2>
            <IconButton label="Close" onClick={onClose}>
              <X size={20} aria-hidden />
            </IconButton>
          </div>
          <div className="fc-dialog__body">{children}</div>
          {actions ? <div className="fc-dialog__actions">{actions}</div> : null}
        </>
      ) : null}
    </dialog>
  );
}
