import { useEffect } from "react";
import { toast } from "../../ui/toastStore.js";
import { isDue, onDraftsSaved, saveWaitingDrafts, useSaversVersion, withDraftsLock } from "./savers.js";
import { adoptFormerDrafts, adoptSignedOutDrafts, setDraftsViewer, useDrafts } from "./store.js";
import { useDraftsUi } from "./uiStore.js";

function plural(count: number, one: string, many: string): string {
  return count === 1 ? one : many.replace("{n}", String(count));
}

/**
 * Keep the drafts in step with who is signed in, and save their drafts.
 * `account` is the signed-in person's identity, or null; `ready` is true when
 * they are through the welcome step. Mounted once, by the account layer.
 *
 * New drafts are stamped with `account`. When someone signs in, the drafts
 * made signed out just before become theirs, and so do drafts kept under
 * `former`, the identity their account had before drafts were keyed to its id. While `ready`, every waiting
 * draft of theirs that has a saver is saved, and they are told what happened.
 * Anyone else's drafts wait to be asked about in the drafts bar. It runs
 * again when a draft or a saver arrives, and each run reports once however
 * many times React runs the effect.
 */
export function useDraftAutoSave(account: string | null, ready: boolean, former: string | null = null): void {
  const drafts = useDrafts();
  const saversVersion = useSaversVersion();
  // Worked out each render: a saver arriving re-renders through `useSaversVersion`.
  const due = ready && account !== null && drafts.some((draft) => isDue(draft, account));

  useEffect(() => {
    setDraftsViewer(account);
    if (account === null) return;
    void withDraftsLock(async () => {
      if (former !== null) adoptFormerDrafts(former, account);
      adoptSignedOutDrafts(account);
    });
  }, [account, former]);

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
    if (due && account !== null) void saveWaitingDrafts(account);
  }, [due, account, drafts, saversVersion]);
}
