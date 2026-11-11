import { useCallback } from "react";
import { isTransient } from "../../api/client.js";
import { toast } from "../../ui/toastStore.js";
import { AccountRequiredError, useRequireAccount } from "../account/requireAccount.js";

/** The reason a request failed, in the server's words when it gave them. */
export function reasonOf(error: unknown): string {
  return error instanceof Error && error.message ? error.message : "Something went wrong.";
}

/** Say that something didn't happen, and why, in an error toast. */
export function toastFailure(what: string, error: unknown): void {
  toast(`${what} ${reasonOf(error)}`, { kind: "error" });
}

/**
 * The same, kept until dismissed, with "Try again" only for a failure that
 * may pass: a refusal of what was sent would be refused again.
 */
export function toastFailureWithRetry(what: string, error: unknown, retry: () => void): void {
  toast(`${what} ${reasonOf(error)}`, {
    kind: "error",
    duration: 0,
    ...(isTransient(error) ? { action: { label: "Try again", onClick: retry } } : {}),
  });
}

/**
 * Before acting, make sure the person is signed in and through the welcome
 * step, asking them if not (`useRequireAccount`). Resolves true when they
 * are, and false when they close the sheet instead.
 */
export function useSignedInFirst(): () => Promise<boolean> {
  const requireAccount = useRequireAccount();
  return useCallback(async () => {
    try {
      await requireAccount();
      return true;
    } catch (error) {
      if (error instanceof AccountRequiredError) return false;
      throw error;
    }
  }, [requireAccount]);
}
