import { toast } from "./toastStore.js";

/**
 * Copy text and say so in a toast: `done` when it worked, or what to do
 * instead when the browser refused, as it does on a page that isn't secure
 * or without permission.
 */
export async function copyWithToast(text: string, done: string): Promise<boolean> {
  const copied = await copyText(text);
  if (copied) toast(done, { kind: "success" });
  else toast(`This browser wouldn't copy it. Here it is to copy by hand: ${text}`, { kind: "error" });
  return copied;
}

/** Copy text, and say whether the browser let it. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (!navigator.clipboard) throw new Error("No clipboard");
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
