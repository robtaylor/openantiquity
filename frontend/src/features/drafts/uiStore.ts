import { create } from "zustand";

/** Whether the drafts bar's list is open, so a toast can open it too. */
export const useDraftsUi = create<{ open: boolean; setOpen: (open: boolean) => void }>()((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
}));
