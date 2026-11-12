import { useQueryClient } from "@tanstack/react-query";
import { Dices } from "lucide-react";
import { type FormEvent, useState } from "react";
import { ApiError } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { safeLinkHref } from "../../map/attribution.js";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import { toast } from "../../ui/toastStore.js";
import { type AgeBand, accountKeys, completeWelcome, deleteMe, fetchHandleSuggestion, type Me } from "./api.js";
import { HANDLE_HELD_BACK, HANDLE_MAX_LENGTH, HANDLE_PATTERN, HANDLE_RULE, HANDLE_RULE_MESSAGE } from "./handles.js";
import { Notice } from "./Notice.js";
import { useAccountUi } from "./requireAccount.js";
import { signedIn, signedOut, useSession } from "./session.js";
import "./account.css";

const UNDER_16 = "under_16";

/** Where the contributor terms are when `/meta` doesn't say: the terms' own page. */
const TERMS_FALLBACK_URL = "/about/terms";
type BandChoice = AgeBand | typeof UNDER_16;

/** The bands, from the generated `AgeBand` type, and the answer that can't join. */
const BANDS: { id: BandChoice; label: string }[] = [
  { id: UNDER_16, label: "Under 16" },
  { id: "16_17", label: "16 or 17" },
  { id: "18_plus", label: "18 or over" },
];

interface Errors {
  handle?: string;
  band?: string;
  terms?: string;
  form?: string;
}

function errorsFrom(error: unknown): Errors {
  if (!(error instanceof ApiError)) return { form: "That didn't work. Please try again." };
  switch (error.code) {
    case "handle_taken":
      return { handle: "Someone already has that name. Try another, or press “Suggest another”." };
    case "invalid_handle":
      return { handle: `That name can't be used. ${HANDLE_RULE_MESSAGE}` };
    case "handle_held_back":
      return { handle: HANDLE_HELD_BACK };
    case "below_minimum_age":
      return { band: error.message };
    case "terms_not_accepted":
      return { terms: "Tick the box to accept the contributor terms." };
    default:
      return { form: error.message };
  }
}

function UnderSixteen() {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  async function leave(): Promise<void> {
    setBusy(true);
    try {
      await deleteMe();
      signedOut(client);
      useAccountUi.getState().close();
      toast("Your sign-in has been removed. You're welcome to keep exploring the map.");
    } catch (error) {
      setBusy(false);
      toast(error instanceof ApiError ? error.message : "That didn't work. Please try again.", { kind: "error" });
    }
  }
  return (
    <div className="fc-account-stack">
      <Notice tone="info" title="Open Antiquity is for people aged 16 and over">
        <p>
          So you can't join yet, sorry. You can still explore the map, look at every finding and try marking things,
          which stays in this browser.
        </p>
        <p>We haven't stored your age or anything you've done. The sign-in you just used can be removed now.</p>
      </Notice>
      <div className="fc-account-actions">
        <Button variant="primary" onClick={() => void leave()} disabled={busy}>
          Remove my sign-in
        </Button>
      </div>
    </div>
  );
}

function WelcomeForm({ me, meta }: { me: Me; meta: Meta }) {
  const client = useQueryClient();
  const [handle, setHandle] = useState(me.handle);
  const [band, setBand] = useState<BandChoice | null>(null);
  const [terms, setTerms] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const [drawing, setDrawing] = useState(false);

  async function suggestAnother(): Promise<void> {
    setDrawing(true);
    try {
      setHandle(await fetchHandleSuggestion());
      setErrors((current) => ({ ...current, handle: undefined }));
    } catch {
      setErrors((current) => ({ ...current, handle: "Couldn't fetch a suggestion just now. You can type your own." }));
    } finally {
      setDrawing(false);
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const chosen = handle.trim();
    const found: Errors = {};
    if (!HANDLE_PATTERN.test(chosen)) found.handle = HANDLE_RULE_MESSAGE;
    if (band === null) found.band = "Choose your age band.";
    if (!terms) found.terms = "Tick the box to accept the contributor terms.";
    setErrors(found);
    if (Object.keys(found).length > 0 || band === null || band === UNDER_16) return;
    setBusy(true);
    try {
      const welcomed = await completeWelcome({
        age_band: band,
        accept_terms: true,
        ...(chosen === me.handle ? {} : { handle: chosen }),
      });
      signedIn(client, welcomed);
    } catch (error) {
      if (error instanceof ApiError && error.code === "already_welcomed") {
        await client.invalidateQueries({ queryKey: accountKeys.me });
        return;
      }
      setErrors(errorsFrom(error));
      setBusy(false);
    }
  }

  return (
    <form className="fc-account-form" onSubmit={(event) => void onSubmit(event)} noValidate>
      <p className="fc-account-why">Three quick things before you save anything.</p>
      {errors.form ? (
        <Notice tone="error" title="That didn't work">
          <p>{errors.form}</p>
        </Notice>
      ) : null}

      <Field
        label="Your name on the map"
        hint={`This is your handle. It's shown with what you add, and in the link to your profile. ${HANDLE_RULE}`}
        error={errors.handle}
      >
        {(control) => (
          <div className="fc-account-form__row">
            <input
              {...control}
              className="fc-input"
              value={handle}
              autoComplete="username"
              spellCheck={false}
              maxLength={HANDLE_MAX_LENGTH}
              onChange={(event) => setHandle(event.target.value)}
            />
            <Button icon={<Dices size={16} aria-hidden />} onClick={() => void suggestAnother()} disabled={drawing}>
              Suggest another
            </Button>
          </div>
        )}
      </Field>

      <div className="fc-field">
        <span className="fc-field__label" aria-hidden="true">
          How old are you?
        </span>
        <ChipGroup
          label="How old are you?"
          options={BANDS}
          value={band}
          onChange={(id) => {
            setBand(id as BandChoice);
            setErrors((current) => ({ ...current, band: undefined }));
          }}
        />
        <p className="fc-field__hint">
          {band === "16_17"
            ? "Other people will see only your handle, never a name or picture from your sign-in."
            : "We keep only the band, to apply the right safety rules. Contributors must be 16 or over."}
        </p>
        {errors.band ? (
          <p className="fc-field__error" role="alert">
            {errors.band}
          </p>
        ) : null}
      </div>

      {band === UNDER_16 ? (
        <UnderSixteen />
      ) : (
        <>
          <div className="fc-field">
            <label className="fc-account-check">
              <input
                type="checkbox"
                checked={terms}
                aria-invalid={errors.terms ? true : undefined}
                aria-describedby="welcome-terms-hint"
                onChange={(event) => {
                  setTerms(event.target.checked);
                  setErrors((current) => ({ ...current, terms: undefined }));
                }}
              />
              I accept the contributor terms
            </label>
            <p className="fc-field__hint" id="welcome-terms-hint">
              What you add is public and published under {meta.app.contribution_licence}, so anyone may reuse it with
              credit. If you leave, it stays on the map, credited to “Former member”.{" "}
              <a
                href={safeLinkHref(meta.auth.terms?.url) ?? TERMS_FALLBACK_URL}
                target="_blank"
                rel="noopener noreferrer"
              >
                Read the contributor terms
                <span className="fc-visually-hidden"> (opens in a new tab)</span>
              </a>
            </p>
            {errors.terms ? (
              <p className="fc-field__error" role="alert">
                {errors.terms}
              </p>
            ) : null}
          </div>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "Joining…" : "Join Open Antiquity"}
          </Button>
        </>
      )}
    </form>
  );
}

/** The welcome sheet, for someone signed in who still owes the welcome step. */
export function WelcomeSheet({ meta }: { meta: Meta }) {
  const session = useSession();
  const open = useAccountUi((state) => state.sheet === "welcome") && session.needsWelcome;
  return (
    <Dialog
      open={open}
      className="fc-account-sheet"
      title="Welcome to Open Antiquity"
      onClose={() => {
        if (useAccountUi.getState().sheet === "welcome") useAccountUi.getState().close();
      }}
    >
      {open && session.me ? <WelcomeForm me={session.me} meta={meta} /> : null}
    </Dialog>
  );
}
