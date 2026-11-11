import { type QueryClient, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef } from "react";
import { type NavigateFunction, useNavigate } from "react-router";
import type { Meta } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { toast } from "../../ui/toastStore.js";
import { AccountRequiredError, useRequireAccount } from "../account/requireAccount.js";
import { useSession } from "../account/session.js";
import { DraftBusyError, DraftTooLargeError, newId } from "../drafts/store.js";
import { createFinding } from "../findings/api.js";
import { findingKeys } from "../findings/keys.js";
import { findingPath, useSelectedFinding } from "../findings/selection.js";
import type { FindingDetail } from "../findings/types.js";
import { composeFinding, saveProblem } from "./compose.js";
import { createBody, type FindingDraft, findingDrafts } from "./findingDrafts.js";
import { useMarkStore } from "./markStore.js";
import { usePendingFindings } from "./pending.js";

/**
 * Leave the form for the page of the finding it became: the page has the
 * finding at once from the cache, and the map marks it.
 */
export function openSavedFinding(client: QueryClient, navigate: NavigateFunction, finding: FindingDetail): void {
  client.setQueryData(findingKeys.detail(finding.public_id), finding);
  const { lon, lat, obscured } = finding.location;
  useSelectedFinding.getState().select(finding.public_id, [lon, lat], obscured);
  useMarkStore.getState().start();
  navigate(findingPath(finding.public_id), { replace: true });
}

/** The address of the panel for a draft, which a sign-in comes back to. */
export function draftPath(draftId: string): string {
  return `/mark/${encodeURIComponent(draftId)}`;
}

/**
 * Save the finding being marked.
 *
 * Signed in and through the welcome step: the mark joins the map at once,
 * `POST /findings` goes, and the finding's page opens. A refusal takes the
 * mark off again and says why in a toast with "Try again", and everything
 * typed stays in the form.
 *
 * Otherwise, and whenever a draft is being edited, it is kept as a draft in
 * this browser and the sign-in sheet opens over the form (Decision 0002).
 * The address becomes the draft's, so a provider's round trip comes back to
 * it. Once the person is ready the drafts machinery saves it, exactly once,
 * and the panel opens the finding it became.
 */
export function useSaveMark(meta: Meta): () => Promise<void> {
  const session = useSession();
  const requireAccount = useRequireAccount();
  const client = useQueryClient();
  const navigate = useNavigate();
  const { ready } = session;
  /** The save itself, for a toast's "Try again", which sends the form as it is by then. */
  const again = useRef<() => Promise<void>>(async () => {});
  /**
   * One reference for every attempt to save this mark, so trying again after
   * a save the server made but whose answer was lost doesn't make it twice.
   */
  const clientRef = useRef<string>(newId());

  const keepAsDraft = useCallback(
    async (draft: FindingDraft, draftId: string | null): Promise<void> => {
      let id: string;
      try {
        id = findingDrafts.put(draft, draftId ?? undefined).id;
      } catch (error) {
        if (error instanceof DraftTooLargeError || error instanceof DraftBusyError) {
          toast(error.message, { kind: "error" });
          return;
        }
        throw error;
      }
      useMarkStore.setState({ draftId: id });
      navigate(draftPath(id), { replace: true });
      // Once ready, the drafts machinery sends it. Sending it here too could save it twice.
      if (ready) return;
      try {
        await requireAccount();
      } catch (error) {
        if (!(error instanceof AccountRequiredError)) throw error;
        toast("It's kept in this browser as a draft. Sign in when you're ready, and it will be saved.");
      }
    },
    [navigate, ready, requireAccount],
  );

  const saveNow = useCallback(
    async (draft: FindingDraft): Promise<void> => {
      const mark = useMarkStore.getState();
      const pending = usePendingFindings.getState();
      mark.setSaving(true);
      const pendingId = pending.add({ point: draft.point, title: draft.title, featureClass: draft.feature_class });
      try {
        const finding = await createFinding(createBody(draft, clientRef.current));
        clientRef.current = newId();
        openSavedFinding(client, navigate, finding);
        // The mark stays until the map and the list have the real finding.
        void client.invalidateQueries({ queryKey: findingKeys.all }).finally(() => pending.remove(pendingId));
      } catch (error) {
        pending.remove(pendingId);
        const problem = saveProblem(error);
        const current = useMarkStore.getState();
        current.setSaving(false);
        if (problem.field) current.setProblem({ field: problem.field, message: problem.message });
        toast(`Your finding couldn't be saved. ${problem.message}`, {
          kind: "error",
          duration: 0,
          action: { label: "Try again", onClick: () => void again.current() },
        });
      }
    },
    [client, navigate],
  );

  const save = useCallback(async () => {
    const fields = useMarkStore.getState();
    if (fields.saving) return;
    const composed = composeFinding(fields, meta, useMapStore.getState());
    if (!composed.ok) {
      fields.setProblem({ field: composed.field, message: composed.message });
      return;
    }
    fields.setProblem(null);
    if (fields.draftId !== null || !ready) await keepAsDraft(composed.draft, fields.draftId);
    else await saveNow(composed.draft);
  }, [meta, ready, keepAsDraft, saveNow]);
  again.current = save;
  return save;
}
