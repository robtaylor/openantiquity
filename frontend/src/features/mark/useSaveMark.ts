import { type QueryClient, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef } from "react";
import { type NavigateFunction, useNavigate } from "react-router";
import { ApiError, isTransient } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { toast } from "../../ui/toastStore.js";
import { AccountRequiredError, useRequireAccount } from "../account/requireAccount.js";
import { accountIdentity, useSession } from "../account/session.js";
import { type Draft, DraftBusyError, DraftTooLargeError, newId, sendHeldDraft } from "../drafts/store.js";
import { positionFields } from "../finding/positionInText.js";
import { createFinding } from "../findings/api.js";
import { findingKeys } from "../findings/keys.js";
import { findingPath, useSelectedFinding } from "../findings/selection.js";
import type { FindingDetail } from "../findings/types.js";
import { composeFinding, saveProblem } from "./compose.js";
import { createBody, type FindingDraft, findingDrafts } from "./findingDrafts.js";
import { useMarkReturn } from "./markReturn.js";
import { useMarkStore } from "./markStore.js";
import { usePendingFindings } from "./pending.js";

/**
 * Leave the form for the page of the finding it became: the page has the
 * finding at once from the cache, and the map marks it. Marking opened over
 * a mode that carries on, such as a scan, goes back to it instead, with the
 * finding's page a press away in the toast.
 */
export function openSavedFinding(
  client: QueryClient,
  navigate: NavigateFunction,
  finding: FindingDetail,
  forget = true,
): void {
  client.setQueryData(findingKeys.detail(finding.public_id), finding);
  // With `forget` false the tool holds something else, which is the person's to keep or discard.
  if (forget) useMarkStore.getState().start();
  const back = useMarkReturn.getState().to;
  if (back) {
    navigate(back.path, { replace: true });
    toast("Your finding is saved.", {
      kind: "success",
      action: { label: "Open it", onClick: () => navigate(findingPath(finding.public_id)) },
    });
    return;
  }
  const { lon, lat, obscured } = finding.location;
  useSelectedFinding.getState().select(finding.public_id, [lon, lat], obscured);
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
 * mark off again and says why in a toast, with "Try again" when the failure
 * may pass, and everything typed stays in the form.
 *
 * Otherwise, and whenever a draft is being edited, it is kept as a draft in
 * this browser and the sign-in sheet opens over the form (Decision 0002).
 * The address becomes the draft's, so a provider's round trip comes back to
 * it. Once the person is ready the drafts machinery saves it, exactly once,
 * and the panel opens the finding it became. A draft taken over at sign-in
 * waits for the person's say-so (Decision 0024): pressing Save here gives it.
 */
export function useSaveMark(meta: Meta): () => Promise<void> {
  const session = useSession();
  const requireAccount = useRequireAccount();
  const client = useQueryClient();
  const navigate = useNavigate();
  const { ready } = session;
  const account = ready && session.me ? accountIdentity(session.me) : null;
  /** The save itself, for a toast's "Try again", which sends the form as it is by then. */
  const again = useRef<() => Promise<void>>(async () => {});
  /**
   * One reference for every attempt to save this mark, so trying again after
   * a save the server made but whose answer was lost doesn't make it twice.
   */
  const clientRef = useRef<string>(newId());

  const keepAsDraft = useCallback(
    async (draft: FindingDraft, draftId: string | null): Promise<void> => {
      let kept: Draft;
      try {
        kept = findingDrafts.put(draft, draftId ?? undefined);
      } catch (error) {
        if (error instanceof DraftTooLargeError || error instanceof DraftBusyError) {
          toast(error.message, { kind: "error" });
          return;
        }
        throw error;
      }
      useMarkStore.getState().keptAs(kept.id);
      navigate(draftPath(kept.id), { replace: true });
      // Once ready, the drafts machinery sends it, so nothing is sent from here: that could
      // save it twice. A draft taken over at sign-in is held until the person says so
      // (Decision 0024). Pressing Save on its own form is them saying so, which lifts the hold.
      if (ready) {
        if (kept.held && account !== null) sendHeldDraft(kept.id, account);
        return;
      }
      try {
        await requireAccount();
      } catch (error) {
        if (!(error instanceof AccountRequiredError)) throw error;
        toast("Kept in this browser as a draft until you sign in.");
        const back = useMarkReturn.getState().to;
        if (back) navigate(back.path, { replace: true });
      }
    },
    [account, navigate, ready, requireAccount],
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
        // A title or note that says where it is: said beside each, which the toast needn't repeat for long.
        const placed = [...positionFields(error)];
        current.setPlaced(placed);
        // A refusal of what was sent would be refused again, and the form says what to change.
        // Only a failure that may pass, of the network or the server, is worth sending again as it is.
        const retry = !(error instanceof ApiError) || isTransient(error);
        toast(`Your finding couldn't be saved. ${problem.message}`, {
          kind: "error",
          // It stays until dismissed, unless the form beside it says the same.
          ...(retry || (!problem.field && placed.length === 0) ? { duration: 0 } : {}),
          ...(retry ? { action: { label: "Try again", onClick: () => void again.current() } } : {}),
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
