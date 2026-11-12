import { MailCheck } from "lucide-react";
import { type FormEvent, useState } from "react";
import { ApiError } from "../../api/client.js";
import { Button } from "../../ui/Button.js";
import { Field } from "../../ui/Field.js";
import { noteSignInStarted } from "../drafts/store.js";
import { startEmailLink } from "./api.js";
import { Notice } from "./Notice.js";

/** Enough of a check to catch a slip. The server has the last word. */
const LOOKS_LIKE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Step = { name: "form"; error: string | null } | { name: "sending" } | { name: "sent"; email: string };

function sendingError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "validation_error") return "That doesn't look like an email address. Please check it.";
    if (error.code === "rate_limited")
      return "You've asked for several links recently. Please wait a while, then try again.";
    return `The link couldn't be sent. ${error.message}`;
  }
  return "The link couldn't be sent. Please try again.";
}

/**
 * "Email me a link". After a send it always shows the same "check your
 * inbox" message, whatever the server knows about the address.
 */
export function EmailLinkForm({ next }: { next: string }) {
  const [email, setEmail] = useState("");
  const [step, setStep] = useState<Step>({ name: "form", error: null });

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const address = email.trim();
    if (!LOOKS_LIKE_EMAIL.test(address)) {
      setStep({ name: "form", error: "Enter your email address, such as name@example.org." });
      return;
    }
    setStep({ name: "sending" });
    noteSignInStarted("email");
    try {
      await startEmailLink(address, next);
      setStep({ name: "sent", email: address });
    } catch (error) {
      setStep({ name: "form", error: sendingError(error) });
    }
  }

  if (step.name === "sent") {
    return (
      <div className="fc-account-stack">
        <Notice tone="info" title="Check your inbox">
          <p>
            If <strong>{step.email}</strong> can receive email, a sign-in link is on its way. It works once, for fifteen
            minutes.
          </p>
          <p>
            Open it in this browser and you'll be signed straight in. Anything you marked before is saved as yours if
            the link opens in this tab; in another tab, you'll be asked first.
          </p>
        </Notice>
        <div className="fc-account-actions">
          <Button variant="ghost" onClick={() => setStep({ name: "form", error: null })}>
            Use a different address
          </Button>
        </div>
      </div>
    );
  }

  const error = step.name === "form" ? step.error : null;
  return (
    <form className="fc-account-form" onSubmit={(event) => void onSubmit(event)} noValidate>
      <Field
        label="Email address"
        hint="We'll send a link that signs you in. There's no password."
        error={error ?? undefined}
      >
        {(control) => (
          <input
            {...control}
            className="fc-input"
            type="email"
            autoComplete="email"
            inputMode="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        )}
      </Field>
      <Button
        type="submit"
        variant="primary"
        icon={<MailCheck size={18} aria-hidden />}
        disabled={step.name === "sending"}
      >
        {step.name === "sending" ? "Sending…" : "Email me a link"}
      </Button>
    </form>
  );
}
