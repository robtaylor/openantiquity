import { useEffect, useRef } from "react";
import { toast, useToastStore } from "../../ui/toastStore.js";
import { accountIdentity, onSignedInHere } from "../account/session.js";
import { isDue, onDraftsSaved, saveWaitingDrafts, useSaversVersion, withDraftsLock } from "./savers.js";
import {
  adoptDraftsAfterSignIn,
  adoptFormerDrafts,
  isOwnDraft,
  listAllDrafts,
  setDraftsViewer,
  useDrafts,
} from "./store.js";
import { useDraftsUi } from "./uiStore.js";

function plural(count: number, one: string, many: string): string {
  return count === 1 ? one : many.replace("{n}", String(count));
}

/** After an adoption: say that the drafts from before signing in wait for them to send them (Decision 0024). */
function tellHeld(adopted: number, account: string): void {
  if (adopted === 0) return;
  const held = listAllDrafts().filter((draft) => draft.held && isOwnDraft(draft, account)).length;
  if (held === 0) return;
  const id = toast(
    plural(
      held,
      "A draft from before you signed in is waiting. Send it only if you made it.",
      "{n} drafts from before you signed in are waiting. Send them only if you made them.",
    ),
    { duration: 0, action: { label: "Show", onClick: () => useDraftsUi.getState().setOpen(true) } },
  );
  // Once the drafts bar is open it says the same, and on a phone the toast would cover it.
  const stop = useDraftsUi.subscribe((state) => {
    if (!state.open) return;
    useToastStore.getState().dismiss(id);
    stop();
  });
}

/**
 * Keep the drafts in step with who is signed in, and save their drafts.
 * `account` is the signed-in person's identity, null for nobody, or
 * undefined while that isn't known; `ready` is true when they are through
 * the welcome step. Mounted once, by the account layer.
 *
 * New drafts are stamped with `account`, and only theirs are shown as
 * theirs. Drafts kept under `former`, the identity their account had before
 * drafts were keyed to its id, become theirs. The drafts this tab made
 * signed out become theirs only after a sign-in that started and finished
 * in this tab (Decision 0022): a provider's, which comes back as the page
 * loading signed in, or one finished here without leaving the page
 * (`onSignedInHere`), and then wait for them to say to send them, because
 * someone else may have used the tab before them (Decision 0024). While
 * `ready`, every waiting draft of theirs that has a saver and isn't held is
 * saved, and they are told what happened. Anyone else's
 * drafts wait to be asked about in the drafts bar. It runs again when a
 * draft or a saver arrives, and each run reports once however many times
 * React runs the effect.
 */
export function useDraftAutoSave(
  account: string | null | undefined,
  ready: boolean,
  former: string | null = null,
): void {
  const drafts = useDrafts();
  const saversVersion = useSaversVersion();
  // Worked out each render: a saver arriving re-renders through `useSaversVersion`.
  const due = ready && typeof account === "string" && drafts.some((draft) => isDue(draft, account));
  /** The first answer this page had about who is signed in, once there is one. */
  const firstKnown = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    setDraftsViewer(account);
    if (account === undefined) return;
    const pageLoad = firstKnown.current === undefined;
    if (pageLoad) firstKnown.current = account;
    if (account === null) return;
    void withDraftsLock(async () => {
      if (former !== null) adoptFormerDrafts(former, account);
      // A provider's sign-in comes back as a page load. Any other change of person arriving later isn't this tab's.
      if (pageLoad) tellHeld(adoptDraftsAfterSignIn(account, ["provider"]), account);
    });
  }, [account, former]);

  useEffect(
    () =>
      onSignedInHere((me) => {
        const identity = accountIdentity(me);
        void withDraftsLock(async () => tellHeld(adoptDraftsAfterSignIn(identity, ["email", "dev"]), identity));
      }),
    [],
  );

  useEffect(
    () =>
      onDraftsSaved((report) => {
        if (report.saved > 0) {
          toast(plural(report.saved, "Your draft is saved.", "Your {n} drafts are saved."), { kind: "success" });
        }
        if (report.failed > 0) {
          toast(
            plural(
              report.failed,
              "One draft couldn't be saved. It's still here, with the reason.",
              "{n} drafts couldn't be saved. They're still here, with the reasons.",
            ),
            {
              kind: "error",
              duration: 0,
              action: { label: "Show", onClick: () => useDraftsUi.getState().setOpen(true) },
            },
          );
        }
      }),
    [],
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: a new draft or saver is the trigger
  useEffect(() => {
    if (due && typeof account === "string") void saveWaitingDrafts(account);
  }, [due, account, drafts, saversVersion]);
}
