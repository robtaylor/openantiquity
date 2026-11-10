import { create } from "zustand";

export type ToastKind = "info" | "success" | "error";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
  /** For example "Retry" after a failed save, or "Undo". */
  action?: ToastAction;
}

export interface ToastOptions {
  kind?: ToastKind;
  action?: ToastAction;
  /** Milliseconds before the toast goes. Zero keeps it until dismissed. */
  duration?: number;
}

interface ToastState {
  toasts: Toast[];
  show: (message: string, options?: ToastOptions) => number;
  dismiss: (id: number) => void;
  clear: () => void;
}

const DEFAULT_DURATION = 5000;
const MAX_TOASTS = 3;

let nextId = 1;
const timers = new Map<number, ReturnType<typeof setTimeout>>();

export const useToastStore = create<ToastState>()((set, get) => ({
  toasts: [],
  show: (message, options = {}) => {
    const id = nextId++;
    const toast: Toast = { id, kind: options.kind ?? "info", message, action: options.action };
    const toasts = [...get().toasts, toast];
    // The oldest gives way when too many pile up.
    for (const dropped of toasts.slice(0, Math.max(0, toasts.length - MAX_TOASTS))) get().dismiss(dropped.id);
    set((state) => ({ toasts: [...state.toasts, toast] }));
    const duration = options.duration ?? DEFAULT_DURATION;
    if (duration > 0) {
      timers.set(
        id,
        setTimeout(() => get().dismiss(id), duration),
      );
    }
    return id;
  },
  dismiss: (id) => {
    const timer = timers.get(id);
    if (timer !== undefined) clearTimeout(timer);
    timers.delete(id);
    set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) }));
  },
  clear: () => {
    for (const timer of timers.values()) clearTimeout(timer);
    timers.clear();
    set({ toasts: [] });
  },
}));

/** Show a toast from anywhere, including outside React. */
export function toast(message: string, options?: ToastOptions): number {
  return useToastStore.getState().show(message, options);
}
