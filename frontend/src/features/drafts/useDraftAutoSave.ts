import { useEffect } from "react";
import { toast } from "../../ui/toastStore.js";
import { onDraftsSaved, saverFor, saveWaitingDrafts, useSaversVersion } from "./savers.js";
import { useDrafts } from "./store.js";
import { useDraftsUi } from "./uiStore.js";

function plural(count: number, one: string, many: string): string {
  return count === 1 ? one : many.replace("{n}", String(count));
}

/**
 * While `ready` (signed in and through the welcome step), save every waiting
 * draft that has a saver, and say what happened. Mounted once, by the
 * account layer. It runs again when a draft or a saver arrives, and each run
 * reports once however many times React runs the effect.
 */
export function useDraftAutoSave(ready: boolean): void {
  const drafts = useDrafts();
  const saversVersion = useSaversVersion();
  const due = ready && drafts.some((draft) => draft.state === "waiting" && saverFor(draft.kind) !== undefined);

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
    if (due) void saveWaitingDrafts();
  }, [due, drafts, saversVersion]);
}
