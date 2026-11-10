import { X } from "lucide-react";
import { Button } from "./Button.js";
import { IconButton } from "./IconButton.js";
import { useToastStore } from "./toastStore.js";
import "./Toast.css";

/** Renders the current toasts. Mount it once, near the root. */
export function ToastViewport() {
  const toasts = useToastStore((state) => state.toasts);
  const dismiss = useToastStore((state) => state.dismiss);
  return (
    <div className="fc-toasts" aria-live="polite" aria-relevant="additions">
      {toasts.map((item) => (
        <div
          key={item.id}
          className={`fc-toast fc-toast--${item.kind}`}
          role={item.kind === "error" ? "alert" : "status"}
        >
          <span className="fc-toast__message">{item.message}</span>
          {item.action ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                item.action?.onClick();
                dismiss(item.id);
              }}
            >
              {item.action.label}
            </Button>
          ) : null}
          <IconButton size="sm" label="Dismiss" onClick={() => dismiss(item.id)}>
            <X size={16} aria-hidden />
          </IconButton>
        </div>
      ))}
    </div>
  );
}
