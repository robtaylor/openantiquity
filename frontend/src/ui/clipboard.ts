import { toast } from "./toastStore.js";

/**
 * Copy text and say so in a toast: `done` when it worked, or what to do
 * instead when the browser refused, as it does on a page that isn't secure
 * or without permission.
 */
export async function copyWithToast(text: string, done: string): Promise<boolean> {
  try {
    if (!navigator.clipboard) throw new Error("No clipboard");
    await navigator.clipboard.writeText(text);
    toast(done, { kind: "success" });
    return true;
  } catch {
    toast(`This browser wouldn't copy it. Here it is to copy by hand: ${text}`, { kind: "error" });
    return false;
  }
}
