/**
 * `useRequireAccount()` is the one way a feature gates a save.
 *
 *     const requireAccount = useRequireAccount();
 *     try {
 *       await requireAccount();
 *       // signed in and through the welcome step: save
 *     } catch (error) {
 *       if (error instanceof AccountRequiredError) return; // they closed the sheet
 *       throw error;
 *     }
 *
 * It resolves at once, with the person, for someone signed in and through the
 * welcome step. Otherwise it opens the sign-in sheet (or the welcome sheet)
 * over whatever they were doing, and resolves when they are ready or rejects
 * with `AccountRequiredError` if they close it.
 *
 * Signing in with a provider is a full-page round trip, so the page that
 * asked is gone by the time the person is back and the promise never
 * settles. Work that must survive that is a draft (`features/drafts`), which
 * is saved after sign-in without being asked for again.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { create } from "zustand";
import { accountKeys, type Me } from "./api.js";
import { meQuery } from "./session.js";

export class AccountRequiredError extends Error {
  constructor() {
    super("Signing in was closed before it finished.");
    this.name = "AccountRequiredError";
  }
}

export type AccountSheet = "signin" | "welcome";

interface Waiter {
  resolve: (me: Me) => void;
  reject: (error: Error) => void;
}

interface AccountUiState {
  /** Which sheet is open, if either. */
  sheet: AccountSheet | null;
  /** The `signin_error` code the sign-in sheet explains, if it was opened for one. */
  signinError: string | null;
  /** Set once the person has closed a welcome sheet that opened by itself, so it doesn't keep coming back. */
  welcomeDismissed: boolean;
  waiting: Waiter[];
  openSignIn: (signinError?: string | null) => void;
  openWelcome: () => void;
  /** The person closed the sheet: everyone waiting is told no. */
  close: () => void;
  /** The person is ready: everyone waiting is told yes, and the sheet closes. */
  settle: (me: Me) => void;
}

export const useAccountUi = create<AccountUiState>()((set, get) => ({
  sheet: null,
  signinError: null,
  welcomeDismissed: false,
  waiting: [],
  openSignIn: (signinError = null) => set({ sheet: "signin", signinError }),
  openWelcome: () => set({ sheet: "welcome", signinError: null }),
  close: () => {
    const { waiting, sheet } = get();
    set({
      sheet: null,
      signinError: null,
      waiting: [],
      welcomeDismissed: get().welcomeDismissed || sheet === "welcome",
    });
    for (const waiter of waiting) waiter.reject(new AccountRequiredError());
  },
  settle: (me) => {
    const { waiting } = get();
    set({ sheet: null, signinError: null, waiting: [] });
    for (const waiter of waiting) waiter.resolve(me);
  },
}));

export function useRequireAccount(): () => Promise<Me> {
  const client = useQueryClient();
  return useCallback(async () => {
    let me = client.getQueryData<Me | null>(accountKeys.me);
    if (me === undefined) me = await client.fetchQuery(meQuery).catch(() => null);
    if (me && !me.needs_welcome) return me;
    const signedIn = me !== null;
    return new Promise<Me>((resolve, reject) => {
      const ui = useAccountUi.getState();
      useAccountUi.setState({ waiting: [...ui.waiting, { resolve, reject }] });
      if (signedIn) ui.openWelcome();
      else if (ui.sheet !== "signin") ui.openSignIn();
    });
  }, [client]);
}
