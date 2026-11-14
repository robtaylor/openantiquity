/**
 * Handing a marking on (Decision 0038): its keeper, or an admin for a
 * marking with no keeper, offers it to a member by handle, and it passes to
 * them once they take it on. What is shown follows `actions` alone:
 * `hand_on` for offering and taking an offer back, `take_keeping` for the
 * person offered. The offer itself (`keeping`) is also sent to moderators,
 * who are shown nothing of it, since no action names them.
 *
 * Every handle the server won't take answers `user_not_found`, whether
 * nobody has it, its account is gone or it is banned, and the dialog says
 * one thing for all of them, so an offer never tells anyone that someone is
 * banned.
 */

import { useQueryClient } from "@tanstack/react-query";
import { Handshake, Undo2, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ApiError } from "../../api/client.js";
import { Button } from "../../ui/Button.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import { toast } from "../../ui/toastStore.js";
import { profilePath } from "../people/api.js";
import { offerKeeping, takeKeeping, withdrawKeepingOffer } from "./api.js";
import { formatDate } from "./describe.js";
import { reasonOf, toastFailure } from "./feedback.js";
import { PANEL_TITLE, useFocusWhenGone } from "./focusWhenGone.js";
import { findingPageKeys } from "./keys.js";
import { refreshAfterMarking } from "./refreshLists.js";
import type { FindingDetail } from "./types.js";

/** Said for every handle that can't be offered the marking, whatever the server's reason. */
export const CANT_BE_OFFERED = "It can't be offered to that handle. Check the handle and try again.";

function useRefresh(publicId: string): () => void {
  const client = useQueryClient();
  return () => void client.invalidateQueries({ queryKey: findingPageKeys.detail(publicId) });
}

/** "Hand it on", or "Offer it to someone" for an admin: whom to offer it to, by handle. */
export function OfferDialog({
  finding,
  title,
  open,
  onClose,
  onSaved,
}: {
  finding: FindingDetail;
  title: string;
  open: boolean;
  onClose: () => void;
  onSaved: (finding: FindingDetail) => void;
}) {
  const client = useQueryClient();
  const [handle, setHandle] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function offer(): Promise<void> {
    if (saving) return;
    const asked = handle.trim().replace(/^@/, "");
    if (!asked) {
      setProblem("Type the handle of the member to offer it to.");
      return;
    }
    setSaving(true);
    try {
      onSaved(await offerKeeping(finding.public_id, asked));
      // An admin's offer of a marking without a keeper changes the admins' list.
      refreshAfterMarking(client, { orphaned: true });
      toast("It's offered. It passes to them once they take it on.", { kind: "success" });
      onClose();
    } catch (error) {
      setProblem(error instanceof ApiError && error.code === "user_not_found" ? CANT_BE_OFFERED : reasonOf(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" aria-disabled={saving || undefined} onClick={() => void offer()}>
            {saving ? "Offering…" : "Offer it"}
          </Button>
        </>
      }
    >
      <div className="fc-dialog-form">
        <p>
          Whoever keeps a marking can change its shape and its words, and decides on the changes others suggest. Whoever
          found it is still named as its finder.
        </p>
        <Field
          label="Their handle"
          hint="As it shows on their page. They're asked first, and it passes to them once they take it on."
          error={problem ?? undefined}
        >
          {(control) => (
            <input
              {...control}
              className="fc-input"
              value={handle}
              maxLength={40}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => {
                setHandle(event.target.value);
                setProblem(null);
              }}
            />
          )}
        </Field>
      </div>
    </Dialog>
  );
}

/** The offer standing, for whoever may take it back: its keeper, or an admin. */
export function OfferStanding({ finding }: { finding: FindingDetail }) {
  const refresh = useRefresh(finding.public_id);
  const [busy, setBusy] = useState(false);
  const offer = finding.keeping;
  const shown = offer !== null && finding.actions.hand_on.allowed;
  // Taken back, focus goes to the control for offering it again.
  const arm = useFocusWhenGone(shown, "[data-hand-on]");
  if (!offer || !shown) return null;

  async function takeBack(): Promise<void> {
    if (busy) return;
    setBusy(true);
    arm();
    try {
      await withdrawKeepingOffer(finding.public_id);
      refresh();
      toast("The offer is taken back.");
    } catch (error) {
      toastFailure("The offer couldn't be taken back.", error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fc-keeping-offer">
      <p>
        Offered to <Link to={profilePath(offer.offered_to.handle)}>{offer.offered_to.display_name}</Link> on{" "}
        {formatDate(offer.offered_at)}. It passes to them once they take it on.
      </p>
      <Button
        size="sm"
        variant="ghost"
        icon={<Undo2 size={15} aria-hidden />}
        aria-disabled={busy || undefined}
        onClick={() => void takeBack()}
      >
        Take back the offer
      </Button>
    </div>
  );
}

/** The offer, to the person it is made to: "Take it on" or "No thanks". */
export function OfferToYou({
  finding,
  onApplied,
}: {
  finding: FindingDetail;
  onApplied: (finding: FindingDetail) => void;
}) {
  const client = useQueryClient();
  const refresh = useRefresh(finding.public_id);
  const [busy, setBusy] = useState(false);
  // Answered, the question goes from the top of the page, and focus goes to the page's title.
  const arm = useFocusWhenGone(finding.actions.take_keeping.allowed, PANEL_TITLE);
  if (!finding.actions.take_keeping.allowed) return null;

  async function run(step: () => Promise<void>, failed: string): Promise<void> {
    if (busy) return;
    setBusy(true);
    arm();
    try {
      await step();
    } catch (error) {
      toastFailure(failed, error);
    } finally {
      setBusy(false);
    }
  }

  const take = () =>
    run(async () => {
      onApplied(await takeKeeping(finding.public_id));
      refreshAfterMarking(client, { orphaned: true });
      toast("You keep it now. You can change its shape and its words.", { kind: "success" });
    }, "It couldn't be taken on.");
  const decline = () =>
    run(async () => {
      await withdrawKeepingOffer(finding.public_id);
      refresh();
      toast("You turned the offer down.");
    }, "The offer couldn't be turned down.");

  return (
    <section className="fc-finding__section fc-keeping-ask" aria-labelledby="fc-keeping-ask-title">
      <h3 id="fc-keeping-ask-title">Keep this marking?</h3>
      <p>
        You've been asked to keep this marking. Whoever keeps it can change its shape and its words, and decides on the
        changes others suggest. Whoever found it is still named as its finder.
      </p>
      <div className="fc-finding__tools">
        <Button
          size="sm"
          variant="primary"
          icon={<Handshake size={15} aria-hidden />}
          aria-disabled={busy || undefined}
          onClick={() => void take()}
        >
          Take it on
        </Button>
        <Button
          size="sm"
          icon={<X size={15} aria-hidden />}
          aria-disabled={busy || undefined}
          onClick={() => void decline()}
        >
          No thanks
        </Button>
      </div>
    </section>
  );
}
