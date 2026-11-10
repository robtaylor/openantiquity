import { X } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef } from "react";
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
}

/**
 * A modal dialog on the native `<dialog>` element, which traps focus, closes
 * on Escape and puts focus back where it came from.
 */
export function Dialog({ open, onClose, title, children, actions }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // jsdom has no showModal, so tests fall back to the open attribute.
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="fc-dialog"
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        // A click on the backdrop lands on the dialog element itself.
        if (event.target === event.currentTarget) onClose();
      }}
      onKeyDown={closeOnEscape(onClose)}
    >
      {open ? (
        <>
          <div className="fc-dialog__header">
            <h2 className="fc-dialog__title" id={titleId}>
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
