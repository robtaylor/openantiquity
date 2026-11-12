import { ChevronDown, CloudOff, RotateCw, Send, Trash2 } from "lucide-react";
import { type ReactNode, useId, useRef } from "react";
import { Button } from "../../ui/Button.js";
import { toast } from "../../ui/toastStore.js";
import { useDismiss } from "../../ui/useDismiss.js";
import { AccountRequiredError, useRequireAccount } from "../account/requireAccount.js";
import { accountIdentity, useSession } from "../account/session.js";
import { draftLabel } from "./savers.js";
import {
  claimDraftsAsOwn,
  type Draft,
  discardDraft,
  draftsArePersisted,
  restoreDraft,
  retryDraft,
  sendHeldDraft,
  useAllDrafts,
  useDrafts,
} from "./store.js";
import { useDraftsUi } from "./uiStore.js";
import "./drafts.css";

function count(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

function summary(drafts: readonly Draft[], others: number): string {
  if (others === drafts.length) return `${count(others, "draft")} left here`;
  const held = drafts.filter((draft) => draft.held).length;
  if (held > 0) return `${count(held, "second look")} to send`;
  const saving = drafts.filter((draft) => draft.state === "saving").length;
  const failed = drafts.filter((draft) => draft.state === "failed").length;
  if (saving > 0) return `Saving ${count(saving, "draft")}…`;
  if (failed === drafts.length) return `${count(failed, "draft")} couldn't be saved`;
  return `${count(drafts.length, "draft")} not saved yet`;
}

/**
 * One draft. `account` is set for the signed-in person's own drafts, so a
 * failed one can be tried again and a held second look sent. Someone else's
 * draft is shown by its kind alone: what it says, and where, stays theirs.
 */
function DraftRow({ draft, account, theirs }: { draft: Draft; account: string | null; theirs: boolean }) {
  const named = draftLabel(draft);
  const label = named.label;
  const description = theirs ? null : named.description;
  function discard(): void {
    const removed = discardDraft(draft.id);
    if (removed) toast(`${label} discarded.`, { action: { label: "Undo", onClick: () => restoreDraft(removed) } });
  }
  return (
    <li className="fc-drafts__item">
      <div className="fc-drafts__what">
        <span className="fc-drafts__label">{label}</span>
        {description ? <span className="fc-drafts__description">{description}</span> : null}
        {draft.state === "failed" && draft.failure ? (
          <span className="fc-drafts__failure">Couldn't be saved: {draft.failure.message}</span>
        ) : null}
        {draft.state === "saving" ? <span className="fc-drafts__description">Saving…</span> : null}
        {draft.held && !theirs ? (
          <span className="fc-drafts__description">
            Given before you signed in. An answer is final, so send it only if you gave it.
          </span>
        ) : null}
      </div>
      <div className="fc-drafts__buttons">
        {draft.held && !theirs && account !== null ? (
          <Button
            size="sm"
            variant="primary"
            icon={<Send size={14} aria-hidden />}
            onClick={() => sendHeldDraft(draft.id, account)}
          >
            Send
          </Button>
        ) : null}
        {draft.state === "failed" && account !== null && !theirs ? (
          <Button size="sm" icon={<RotateCw size={14} aria-hidden />} onClick={() => retryDraft(draft.id)}>
            Try again
          </Button>
        ) : null}
        <Button
          size="sm"
          variant="ghost"
          icon={<Trash2 size={14} aria-hidden />}
          aria-label={`Discard ${label.toLowerCase()}`}
          disabled={draft.state === "saving"}
          onClick={discard}
        >
          Discard
        </Button>
      </div>
    </li>
  );
}

/**
 * Drafts someone else may have left in this browser. A signed-in person says
 * whether to save them as their own, or discards them; someone signed out
 * can only discard them, or sign in and claim them.
 */
function OthersDrafts({ drafts, account }: { drafts: readonly Draft[]; account: string | null }) {
  const one = drafts.length === 1;
  function discardAll(): void {
    const removed = drafts.flatMap((draft) => discardDraft(draft.id) ?? []);
    toast(one ? "Draft discarded." : `${count(removed.length, "draft")} discarded.`, {
      action: { label: "Undo", onClick: () => removed.forEach(restoreDraft) },
    });
  }
  return (
    <div className="fc-drafts__others">
      <p className="fc-drafts__hint">
        {one ? "This draft was" : "These drafts were"} left in this browser by an earlier visit, perhaps by someone
        else.{" "}
        {account === null
          ? `Sign in to save ${one ? "it" : "them"} as yours, but only if you made ${one ? "it" : "them"}.`
          : `Save ${one ? "it" : "them"} as yours only if you made ${one ? "it" : "them"}.`}
      </p>
      <div className="fc-drafts__buttons">
        {account !== null ? (
          <Button
            size="sm"
            variant="primary"
            onClick={() =>
              claimDraftsAsOwn(
                drafts.map((draft) => draft.id),
                account,
              )
            }
          >
            Save as mine
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" icon={<Trash2 size={14} aria-hidden />} onClick={discardAll}>
          {one ? "Discard it" : "Discard them"}
        </Button>
      </div>
      <ul>
        {drafts.map((draft) => (
          <DraftRow key={draft.id} draft={draft} account={null} theirs />
        ))}
      </ul>
    </div>
  );
}

/**
 * The quiet bar that says how many drafts are waiting and offers to save
 * them. Saving while signed out opens the sign-in sheet. Drafts that aren't
 * the viewer's own (Decision 0022) are asked about before anything is
 * saved, and a second look adopted at sign-in waits to be sent. It shows
 * nothing when there are no drafts.
 */
export function DraftsBar() {
  const drafts = useAllDrafts();
  const mine = useDrafts();
  const session = useSession();
  const requireAccount = useRequireAccount();
  const open = useDraftsUi((state) => state.open);
  const setOpen = useDraftsUi((state) => state.setOpen);
  const listId = useId();
  const ref = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);

  useDismiss(ref, open, (cause) => {
    setOpen(false);
    if (cause === "escape" && ref.current?.contains(document.activeElement)) toggle.current?.focus();
  });

  if (drafts.length === 0) return null;

  const account = session.ready && session.me ? accountIdentity(session.me) : null;
  const others = drafts.filter((draft) => !mine.includes(draft));
  const failed = mine.filter((draft) => draft.state === "failed");
  const allFailed = failed.length > 0 && failed.length === drafts.length;

  async function save(): Promise<void> {
    try {
      await requireAccount();
    } catch (error) {
      if (!(error instanceof AccountRequiredError)) throw error;
    }
  }

  let action: ReactNode = null;
  if (!session.ready && mine.length > 0) {
    action = (
      <Button size="sm" variant="primary" onClick={() => void save()}>
        Save
      </Button>
    );
  } else if ((others.length > 0 || mine.some((draft) => draft.held)) && !open) {
    action = (
      <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
        Check
      </Button>
    );
  } else if (allFailed) {
    action = (
      <Button
        size="sm"
        variant="primary"
        onClick={() => {
          for (const draft of failed) retryDraft(draft.id);
        }}
      >
        Try again
      </Button>
    );
  }

  return (
    <section className="fc-drafts" aria-label="Drafts" ref={ref}>
      <div className={allFailed ? "fc-drafts__bar fc-drafts__bar--failed" : "fc-drafts__bar"}>
        <CloudOff size={16} aria-hidden className="fc-drafts__icon" />
        <span className="fc-drafts__summary" role="status">
          {summary(drafts, others.length)}
        </span>
        {action}
        <button
          type="button"
          ref={toggle}
          className="fc-drafts__toggle"
          aria-expanded={open}
          aria-controls={listId}
          aria-label={open ? "Hide drafts" : "Show drafts"}
          title={open ? "Hide drafts" : "Show drafts"}
          onClick={() => setOpen(!open)}
        >
          <ChevronDown size={16} aria-hidden />
        </button>
      </div>
      {open ? (
        <div className="fc-drafts__list" id={listId}>
          <p className="fc-drafts__hint">
            A draft is kept only in this browser until it's saved. Whoever uses this browser next can see that it's
            here, but not what it says or where.
            {draftsArePersisted() ? "" : " This browser isn't keeping them, so they'll go when you close the page."}
          </p>
          {others.length > 0 ? <OthersDrafts drafts={others} account={account} /> : null}
          {mine.length > 0 ? (
            <ul>
              {mine.map((draft) => (
                <DraftRow key={draft.id} draft={draft} account={account} theirs={false} />
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
