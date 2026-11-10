import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router";
import type { Meta } from "../../api/meta.js";
import { useDraftAutoSave } from "../drafts/useDraftAutoSave.js";
import { SIGNIN_ERROR_PARAM, withoutSigninError } from "./next.js";
import { useAccountUi } from "./requireAccount.js";
import { currentMapHash } from "./returnPath.js";
import { SignInSheet } from "./SignInSheet.js";
import { useSession, useSessionSync } from "./session.js";
import { WelcomeSheet } from "./WelcomeSheet.js";

/**
 * Everything about accounts that isn't a page, mounted once by the shell:
 * the session's upkeep, the sign-in and welcome sheets, the message for a
 * failed provider sign-in, and saving drafts once someone is ready.
 */
export function AccountLayer({ meta }: { meta: Meta }) {
  useSessionSync(() => useAccountUi.getState().openSignIn());
  const session = useSession();
  const sheet = useAccountUi((state) => state.sheet);
  const waiting = useAccountUi((state) => state.waiting.length);
  const welcomeDismissed = useAccountUi((state) => state.welcomeDismissed);
  const location = useLocation();
  const navigate = useNavigate();

  // A provider sign-in that failed comes back with ?signin_error=<code>. Say
  // what happened in the sign-in sheet, and take the code out of the address.
  const signinError = new URLSearchParams(location.search).get(SIGNIN_ERROR_PARAM);
  useEffect(() => {
    if (signinError === null) return;
    useAccountUi.getState().openSignIn(signinError);
    navigate(
      { pathname: location.pathname, search: withoutSigninError(location.search), hash: currentMapHash(location.hash) },
      { replace: true },
    );
  }, [signinError, location.pathname, location.search, location.hash, navigate]);

  // Someone signed in: whoever was waiting is told, or the welcome step comes next.
  const { me, ready, needsWelcome } = session;
  useEffect(() => {
    if (me === null) return;
    if (ready && (waiting > 0 || sheet !== null)) useAccountUi.getState().settle(me);
    else if (needsWelcome && (sheet === "signin" || waiting > 0)) useAccountUi.getState().openWelcome();
  }, [me, ready, needsWelcome, sheet, waiting]);

  // The welcome step is owed: offer it once, unaided. After that it waits to be asked for.
  useEffect(() => {
    if (needsWelcome && sheet === null && !welcomeDismissed) useAccountUi.getState().openWelcome();
  }, [needsWelcome, sheet, welcomeDismissed]);

  useDraftAutoSave(ready);

  return (
    <>
      <SignInSheet meta={meta} />
      <WelcomeSheet meta={meta} />
    </>
  );
}
