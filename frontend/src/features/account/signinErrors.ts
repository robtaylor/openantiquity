/**
 * What to say when a provider sign-in comes back with `?signin_error=<code>`.
 *
 * The codes are the backend's (`fieldclub.auth.failures` and the errors the
 * sign-in flow raises). An unknown code gets the general message: the
 * parameter itself is never shown, because anyone can put anything in it.
 */

export interface SigninErrorMessage {
  title: string;
  body: string;
  /** Whether trying again could help. When it can't, the sheet doesn't suggest it. */
  canRetry: boolean;
}

const GENERAL: SigninErrorMessage = {
  title: "Signing in didn't work",
  body: "Something went wrong on the way back from signing in. Please try again.",
  canRetry: true,
};

const UNAVAILABLE: SigninErrorMessage = {
  title: "That way of signing in isn't available",
  body: "It isn't working at the moment. Please choose another way to sign in.",
  canRetry: true,
};

export const SIGNIN_ERROR_MESSAGES: Readonly<Record<string, SigninErrorMessage>> = {
  cancelled: {
    title: "Signing in was cancelled",
    body: "Nothing has changed. You can sign in whenever you're ready.",
    canRetry: true,
  },
  state_mismatch: {
    title: "That sign-in timed out",
    body: "It took too long, or it was started in another window. Please try again.",
    canRetry: true,
  },
  provider_error: {
    title: "Signing in didn't finish",
    body: "The sign-in service didn't confirm who you are. Please try again, or choose another way to sign in.",
    canRetry: true,
  },
  invalid_token: {
    title: "We couldn't check who you are",
    body: "The answer from the sign-in service didn't pass our checks. Please try again.",
    canRetry: true,
  },
  signin_failed: GENERAL,
  banned: {
    title: "This account can't sign in",
    body: "It has been suspended by the moderators. You can still look at everything on the map.",
    canRetry: false,
  },
  account_deleted: {
    title: "This account was deleted",
    body: "It can't be used to sign in any more. You can still look at everything on the map.",
    canRetry: false,
  },
  email_unavailable: {
    title: "That address can't be used here",
    body: "Please sign in with another address, or choose another way to sign in.",
    canRetry: true,
  },
  provider_unavailable: UNAVAILABLE,
  config_error: UNAVAILABLE,
};

export function signinErrorMessage(code: string): SigninErrorMessage {
  return Object.hasOwn(SIGNIN_ERROR_MESSAGES, code) ? (SIGNIN_ERROR_MESSAGES[code] ?? GENERAL) : GENERAL;
}
