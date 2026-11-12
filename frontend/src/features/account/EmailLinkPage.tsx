import { useQueryClient } from "@tanstack/react-query";
import { LinkIcon, MailX, ShieldQuestion, Unplug } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "../../api/client.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Field } from "../../ui/Field.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { forgetSignInStarted } from "../drafts/store.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { captureEmailLinkToken, emailLinkToken, exchangeEmailLink, forgetEmailLinkToken } from "./emailLink.js";
import { safeNext } from "./next.js";
import { useAccountUi } from "./requireAccount.js";
import { signedIn } from "./session.js";

type Phase =
  /** `email` is the address the person typed, or null before they were asked for it. */
  | { name: "checking"; email: string | null; attempt: number }
  /** `mismatch` when the address typed wasn't the link's. */
  | { name: "confirm"; mismatch: boolean }
  | { name: "declined" }
  | { name: "invalid" }
  | { name: "missing" }
  | { name: "failed"; message: string; email: string | null };

/** Opens the sign-in sheet, keeping the `next` the link was for. */
function AskAgain({ next }: { next: string }) {
  return (
    <Button variant="primary" onClick={() => useAccountUi.getState().openSignIn(null, next)}>
      Ask for a new link
    </Button>
  );
}

/**
 * A link opened in a browser that didn't ask for it: the person types the
 * address they asked for it with, and nothing fills it in for them. The
 * server signs in only when it is the address the link was sent to, so a
 * link someone else sent can't sign them in to that person's account.
 */
function TypeYourAddress({
  mismatch,
  next,
  onSubmit,
  onDecline,
}: {
  mismatch: boolean;
  next: string;
  onSubmit: (email: string) => void;
  onDecline: () => void;
}) {
  const [email, setEmail] = useState("");
  const [empty, setEmpty] = useState(false);
  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const typed = email.trim();
    setEmpty(typed === "");
    if (typed !== "") onSubmit(typed);
  }
  const error = empty
    ? "Type the address you asked for the link with."
    : mismatch
      ? "That isn't the address this link was sent to. A link someone else sent you would sign you in to their account, so ask for your own instead."
      : undefined;
  return (
    <EmptyState icon={<ShieldQuestion size={22} />} title="Which email address is this link for?">
      <p>This link was asked for in another browser or on another device.</p>
      <p>
        Type the address you asked for it with. If someone sent you this link, don't go on: it would sign you in to
        their account.
      </p>
      <form className="fc-account-form" onSubmit={submit} noValidate>
        <Field label="Your email address" error={error}>
          {(control) => (
            <input
              {...control}
              className="fc-input"
              type="email"
              autoComplete="off"
              inputMode="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          )}
        </Field>
        <div className="fc-account-actions">
          <Button type="button" onClick={onDecline}>
            It isn't mine
          </Button>
          {mismatch ? <AskAgain next={next} /> : null}
          <Button type="submit" variant="primary">
            Sign me in
          </Button>
        </div>
      </form>
    </EmptyState>
  );
}

/**
 * `/signin/email#token=…`: where an emailed link lands. The token is taken
 * out of the address as the page loads (`emailLink.ts`) and exchanged for a
 * session. A link opened in a browser that didn't ask for it needs the
 * person to type their own address first (`TypeYourAddress`).
 *
 * Drafts made signed out are taken over only when this browser asked for
 * the link and this tab started the sign-in (Decision 0022). After a link
 * from elsewhere, the sign-in this tab may have started is forgotten, so
 * nothing left in the browser is saved to an account that may not be the
 * person's own.
 */
export function EmailLinkPage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  useDocumentTitle("Signing in");

  const [token] = useState(() => {
    captureEmailLinkToken();
    return emailLinkToken();
  });
  const [phase, setPhase] = useState<Phase>(() =>
    token ? { name: "checking", email: null, attempt: 0 } : { name: "missing" },
  );

  const checking = phase.name === "checking" ? phase : null;
  useEffect(() => {
    if (!checking || !token) return;
    let cancelled = false;
    exchangeEmailLink(token, checking.email).then(
      ({ asked_here: askedHere, ...me }) => {
        if (cancelled) return;
        forgetEmailLinkToken();
        if (!askedHere) forgetSignInStarted();
        signedIn(client, me);
        navigate(next, { replace: true });
      },
      (error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && error.code === "confirmation_required" && checking.email === null) {
          // The masked address the server gives is never shown: a stranger's can look just like yours.
          setPhase({ name: "confirm", mismatch: false });
        } else if (error instanceof ApiError && error.code === "email_mismatch") {
          setPhase({ name: "confirm", mismatch: true });
        } else if (error instanceof ApiError && error.code === "link_invalid") {
          forgetEmailLinkToken();
          setPhase({ name: "invalid" });
        } else {
          setPhase({
            name: "failed",
            message: error instanceof Error ? error.message : "Something went wrong.",
            email: checking.email,
          });
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [checking, token, client, navigate, next]);

  let body: ReactNode;
  switch (phase.name) {
    case "checking":
      body = (
        <div role="status">
          <p>Checking your link…</p>
          <Skeleton lines={2} />
        </div>
      );
      break;
    case "confirm":
      body = (
        <TypeYourAddress
          key={phase.mismatch ? "again" : "first"}
          mismatch={phase.mismatch}
          next={next}
          onSubmit={(email) => setPhase({ name: "checking", email, attempt: Date.now() })}
          onDecline={() => {
            forgetEmailLinkToken();
            setPhase({ name: "declined" });
          }}
        />
      );
      break;
    case "declined":
      body = (
        <EmptyState
          icon={<LinkIcon size={22} />}
          title="You haven't been signed in"
          action={
            <Link className="fc-button fc-button--secondary fc-button--md" to="/">
              Back to the map
            </Link>
          }
        >
          <p>Nothing has changed. If you didn't ask for that link, you can ignore the email.</p>
        </EmptyState>
      );
      break;
    case "invalid":
      body = (
        <EmptyState icon={<MailX size={22} />} title="This link can't be used" action={<AskAgain next={next} />}>
          <p>
            It has expired, it has been used already, or a newer link replaced it. Each link works once, for fifteen
            minutes.
          </p>
        </EmptyState>
      );
      break;
    case "missing":
      body = (
        <EmptyState icon={<MailX size={22} />} title="This link is incomplete" action={<AskAgain next={next} />}>
          <p>Part of it seems to be missing. Try opening it from the email again, or ask for a new one.</p>
        </EmptyState>
      );
      break;
    case "failed":
      body = (
        <EmptyState
          tone="error"
          icon={<Unplug size={22} />}
          title="We couldn't check your link"
          action={
            <Button
              variant="primary"
              onClick={() => setPhase({ name: "checking", email: phase.email, attempt: Date.now() })}
            >
              Try again
            </Button>
          }
        >
          <p>{phase.message}</p>
        </EmptyState>
      );
      break;
  }

  return (
    <PanelFrame panelKey={pathname} title="Signing in">
      {body}
    </PanelFrame>
  );
}
