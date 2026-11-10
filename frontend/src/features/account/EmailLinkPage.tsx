import { useQueryClient } from "@tanstack/react-query";
import { LinkIcon, MailX, ShieldQuestion, Unplug } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "../../api/client.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { captureEmailLinkToken, emailLinkToken, exchangeEmailLink, forgetEmailLinkToken } from "./emailLink.js";
import { safeNext } from "./next.js";
import { useAccountUi } from "./requireAccount.js";
import { signedIn } from "./session.js";

type Phase =
  | { name: "checking"; confirm: boolean; attempt: number }
  | { name: "confirm"; masked: string }
  | { name: "declined" }
  | { name: "invalid" }
  | { name: "missing" }
  | { name: "failed"; message: string; confirm: boolean };

function askForAnother(): void {
  useAccountUi.getState().openSignIn();
}

function AskAgain() {
  return (
    <Button variant="primary" onClick={askForAnother}>
      Ask for a new link
    </Button>
  );
}

/**
 * `/signin/email#token=…`: where an emailed link lands. The token is taken
 * out of the address as the page loads (`emailLink.ts`) and exchanged for a
 * session. A link opened in a browser that didn't ask for it needs the
 * person to say "yes, that's me" first, and only their click sends `confirm`.
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
    token ? { name: "checking", confirm: false, attempt: 0 } : { name: "missing" },
  );

  const checking = phase.name === "checking" ? phase : null;
  useEffect(() => {
    if (!checking || !token) return;
    let cancelled = false;
    exchangeEmailLink(token, checking.confirm).then(
      (me) => {
        if (cancelled) return;
        forgetEmailLinkToken();
        signedIn(client, me);
        navigate(next, { replace: true });
      },
      (error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && error.code === "confirmation_required" && !checking.confirm) {
          const masked = typeof error.details.email === "string" ? error.details.email : "this address";
          setPhase({ name: "confirm", masked });
        } else if (error instanceof ApiError && error.code === "link_invalid") {
          forgetEmailLinkToken();
          setPhase({ name: "invalid" });
        } else {
          setPhase({
            name: "failed",
            message: error instanceof Error ? error.message : "Something went wrong.",
            confirm: checking.confirm,
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
        <EmptyState
          icon={<ShieldQuestion size={22} />}
          title={`Sign in as ${phase.masked}?`}
          action={
            <div className="fc-account-actions">
              <Button
                onClick={() => {
                  forgetEmailLinkToken();
                  setPhase({ name: "declined" });
                }}
              >
                No, that's not me
              </Button>
              <Button variant="primary" onClick={() => setPhase({ name: "checking", confirm: true, attempt: 0 })}>
                Yes, sign me in
              </Button>
            </div>
          }
        >
          <p>This link was asked for in another browser or on another device.</p>
          <p>
            Only say yes if you asked for it yourself. If someone sent it to you, it may sign you in to their account.
          </p>
        </EmptyState>
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
        <EmptyState icon={<MailX size={22} />} title="This link can't be used" action={<AskAgain />}>
          <p>
            It has expired, it has been used already, or a newer link replaced it. Each link works once, for fifteen
            minutes.
          </p>
        </EmptyState>
      );
      break;
    case "missing":
      body = (
        <EmptyState icon={<MailX size={22} />} title="This link is incomplete" action={<AskAgain />}>
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
              onClick={() => setPhase({ name: "checking", confirm: phase.confirm, attempt: Date.now() })}
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
