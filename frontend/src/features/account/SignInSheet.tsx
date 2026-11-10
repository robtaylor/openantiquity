import { useQueryClient } from "@tanstack/react-query";
import { Mail, Wrench } from "lucide-react";
import { type FormEvent, useMemo, useState } from "react";
import { useLocation } from "react-router";
import { ApiError } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import { devLogin } from "./api.js";
import { EmailLinkForm } from "./EmailLinkForm.js";
import { Notice } from "./Notice.js";
import { ProviderButton } from "./ProviderButton.js";
import { useAccountUi } from "./requireAccount.js";
import { returnPath } from "./returnPath.js";
import { signedIn } from "./session.js";
import { signinErrorMessage } from "./signinErrors.js";
import "./account.css";

const EMAIL_PROVIDER = "email";

/** The development sign-in, offered only when /meta says the server has it. */
function DevSignIn() {
  const client = useQueryClient();
  const [handle, setHandle] = useState("DevTester");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      signedIn(client, await devLogin(handle.trim()));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "That didn't work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="fc-account-form" onSubmit={(event) => void onSubmit(event)}>
      <Field
        label="Development sign-in"
        hint="Signs in as this handle. Only a development server offers it."
        error={error ?? undefined}
      >
        {(control) => (
          <div className="fc-account-form__row">
            <input
              {...control}
              className="fc-input"
              value={handle}
              autoComplete="off"
              onChange={(event) => setHandle(event.target.value)}
            />
            <Button type="submit" icon={<Wrench size={16} aria-hidden />} disabled={busy}>
              Sign in
            </Button>
          </div>
        )}
      </Field>
    </form>
  );
}

function SignInChoices({ meta }: { meta: Meta }) {
  const signinError = useAccountUi((state) => state.signinError);
  const [emailOpen, setEmailOpen] = useState(false);
  // Worked out as the sheet opens. The map can't move while it is open.
  const location = useLocation();
  // biome-ignore lint/correctness/useExhaustiveDependencies: fixed for as long as the sheet is open
  const next = useMemo(() => returnPath(location), []);
  const enabled = meta.auth.providers.filter((provider) => provider.enabled);
  const providers = enabled.filter((provider) => provider.id !== EMAIL_PROVIDER);
  const emailEnabled = enabled.some((provider) => provider.id === EMAIL_PROVIDER);
  const devEnabled = meta.auth.dev_login === true;
  const failure = signinError === null ? null : signinErrorMessage(signinError);

  return (
    <div className="fc-account-stack">
      {failure ? (
        <Notice tone="error" title={failure.title}>
          <p>{failure.body}</p>
        </Notice>
      ) : null}
      <p className="fc-account-why">
        Saving needs an account, so that everything on the map has a real person behind it.
      </p>

      {providers.length > 0 ? (
        <ul className="fc-account-providers">
          {providers.map((provider) => (
            <li key={provider.id}>
              <ProviderButton provider={provider} next={next} />
            </li>
          ))}
        </ul>
      ) : null}

      {emailEnabled ? (
        <>
          {providers.length > 0 ? <div className="fc-account-or">or</div> : null}
          {emailOpen || providers.length === 0 ? (
            <EmailLinkForm next={next} />
          ) : (
            <Button variant="secondary" block icon={<Mail size={18} aria-hidden />} onClick={() => setEmailOpen(true)}>
              Email me a link
            </Button>
          )}
        </>
      ) : null}

      {providers.length === 0 && !emailEnabled && !devEnabled ? (
        <Notice tone="error" title="Signing in isn't available right now">
          <p>No way of signing in is switched on. You can still look at everything, and your drafts stay here.</p>
        </Notice>
      ) : null}

      {devEnabled ? <DevSignIn /> : null}

      <p className="fc-account-small">
        Anything you've marked stays in this browser while you sign in, and is saved after.
      </p>
    </div>
  );
}

/** The sign-in sheet, over whatever the person was doing. */
export function SignInSheet({ meta }: { meta: Meta }) {
  const open = useAccountUi((state) => state.sheet === "signin");
  return (
    <Dialog
      open={open}
      className="fc-account-sheet"
      title="Sign in"
      onClose={() => {
        // The dialog also reports closing when another sheet takes over from it.
        if (useAccountUi.getState().sheet === "signin") useAccountUi.getState().close();
      }}
    >
      {open ? <SignInChoices meta={meta} /> : null}
    </Dialog>
  );
}
