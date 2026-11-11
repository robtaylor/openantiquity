import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { ApiError, isTransient } from "../../api/client.js";
import { clamp } from "../../ui/math.js";
import { toast } from "../../ui/toastStore.js";
import { useSession } from "../account/session.js";
import { DraftBusyError, DraftTooLargeError, listDrafts } from "../drafts/store.js";
import { reasonOf } from "../finding/feedback.js";
import { squareWords } from "../findings/square.js";
import { MAX_FINDINGS, MAX_SECONDS, putSurvey, type Square, type SurveyIn } from "./api.js";
import { scanKeys } from "./keys.js";
import { type DoneSquare, useScanStore } from "./scanStore.js";
import { type SquareDraftData, squareDrafts } from "./squareDrafts.js";
import { askForSquare } from "./useNextSquare.js";

export type Ending = "nothing" | "marked" | "skipped";

/** The body for `PUT /squares/{ref}`: the result, the findings marked, and the whole seconds spent. */
export function surveyBody(result: Ending, marked: number, startedAt: number | null, now = Date.now()): SurveyIn {
  const body: SurveyIn = {
    result,
    findings_count: result === "marked" ? clamp(marked, 1, MAX_FINDINGS) : 0,
  };
  if (startedAt !== null) body.seconds = clamp(Math.round((now - startedAt) / 1000), 0, MAX_SECONDS);
  return body;
}

/** The draft already kept for this square, which a new result replaces. */
function draftFor(square: string): string | undefined {
  return listDrafts().find((draft) => squareDrafts.read(draft)?.square === square)?.id;
}

/**
 * End the current square with one of the three presses.
 *
 * "Skip" passes the square and asks for the next at once. Signed in, the
 * server hears of it, so it ranks the square for others; signed out, it is
 * only left out of this visit, as a skip says nothing about the square.
 *
 * "Nothing obvious" and "I marked something" count at once. Signed in and
 * through the welcome step, the result goes to `PUT /squares/{ref}`; a
 * refusal takes it back and says why in a toast. Otherwise it is a draft in
 * this browser, replacing any earlier draft for the square, saved after
 * sign-in by the drafts machinery.
 */
export function useFinishSquare(): (square: Square, ending: Ending, marked: number) => void {
  const { ready } = useSession();
  const client = useQueryClient();

  const send = useCallback(
    async function send(done: DoneSquare, body: SurveyIn): Promise<void> {
      useScanStore.getState().finish(done);
      try {
        await putSurvey(done.square, body);
        void client.invalidateQueries({ queryKey: scanKeys.allCoverage });
      } catch (error) {
        useScanStore.getState().undo(done.square);
        const retry = !(error instanceof ApiError) || isTransient(error);
        toast(`${squareWords(done.square)} couldn't be recorded. ${reasonOf(error)}`, {
          kind: "error",
          duration: 0,
          ...(retry ? { action: { label: "Try again", onClick: () => void send(done, body) } } : {}),
        });
      }
    },
    [client],
  );

  return useCallback(
    (square: Square, ending: Ending, marked: number) => {
      const { startedAt } = useScanStore.getState();
      const body = surveyBody(ending, marked, startedAt);
      if (ending === "skipped") {
        useScanStore.getState().pass();
        askForSquare();
        if (ready) {
          // A skip only ranks the square for others. One that doesn't arrive costs nobody anything.
          putSurvey(square.square, body).catch((error: unknown) =>
            console.warn(`[scan] A skip couldn't be recorded: ${reasonOf(error)}`),
          );
        }
        return;
      }
      const done: DoneSquare = { square: square.square, grid_ref: square.grid_ref, result: ending };
      if (ready) {
        void send(done, body);
        return;
      }
      const data: SquareDraftData = { square: square.square, survey: { ...body, result: ending } };
      try {
        squareDrafts.put(data, draftFor(square.square));
      } catch (error) {
        if (error instanceof DraftTooLargeError || error instanceof DraftBusyError) {
          toast(error.message, { kind: "error" });
          return;
        }
        throw error;
      }
      useScanStore.getState().finish(done);
    },
    [ready, send],
  );
}
