import { ChevronDown, CloudOff, RotateCw, Trash2 } from "lucide-react";
import { type ReactNode, useId, useRef } from "react";
import { Button } from "../../ui/Button.js";
import { toast } from "../../ui/toastStore.js";
import { useDismiss } from "../../ui/useDismiss.js";
import { AccountRequiredError, useRequireAccount } from "../account/requireAccount.js";
import { useSession } from "../account/session.js";
import { draftLabel } from "./savers.js";
import { type Draft, discardDraft, draftsArePersisted, restoreDraft, retryDraft, useDrafts } from "./store.js";
import { useDraftsUi } from "./uiStore.js";
import "./drafts.css";

function count(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

function summary(drafts: readonly Draft[]): string {
  const saving = drafts.filter((draft) => draft.state === "saving").length;
  const failed = drafts.filter((draft) => draft.state === "failed").length;
  if (saving > 0) return `Saving ${count(saving, "draft")}…`;
  if (failed === drafts.length) return `${count(failed, "draft")} couldn't be saved`;
  return `${count(drafts.length, "draft")} not saved yet`;
}

function DraftRow({ draft, canRetry }: { draft: Draft; canRetry: boolean }) {
  const { label, description } = draftLabel(draft);
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
      </div>
      <div className="fc-drafts__buttons">
        {draft.state === "failed" && canRetry ? (
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
 * The quiet bar that says how many drafts are waiting and offers to save
 * them. Saving while signed out opens the sign-in sheet. It shows nothing
 * when there are no drafts.
 */
export function DraftsBar() {
  const drafts = useDrafts();
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

  const failed = drafts.filter((draft) => draft.state === "failed");
  const allFailed = failed.length === drafts.length;

  async function save(): Promise<void> {
    try {
      await requireAccount();
    } catch (error) {
      if (!(error instanceof AccountRequiredError)) throw error;
    }
  }

  let action: ReactNode = null;
  if (!session.ready) {
    action = (
      <Button size="sm" variant="primary" onClick={() => void save()}>
        Save
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
          {summary(drafts)}
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
            A draft is kept only in this browser, and nobody else sees it until it's saved.
            {draftsArePersisted() ? "" : " This browser isn't keeping them, so they'll go when you close the page."}
          </p>
          <ul>
            {drafts.map((draft) => (
              <DraftRow key={draft.id} draft={draft} canRetry={session.ready} />
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
