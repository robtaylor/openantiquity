/**
 * A stand-in kind of draft for fixture mode only, loaded by `main.tsx` when
 * `VITE_USE_FIXTURES` is set and left out of every other build. It lets the
 * end-to-end tests prove the drafts machinery before any feature has
 * registered a real saver. It saves by posting to `/_fixture/drafts`, which
 * only the tests answer.
 */

import { apiFetch } from "../../api/client.js";
import { isRecord } from "../../api/guards.js";
import { registerDraftSaver } from "./savers.js";

export const FIXTURE_DRAFT_KIND = "fixture_probe";

interface FixtureDraft {
  note: string;
}

registerDraftSaver<FixtureDraft>({
  kind: FIXTURE_DRAFT_KIND,
  label: "Test draft",
  parse: (data) => (isRecord(data) && typeof data.note === "string" ? { note: data.note } : null),
  save: async (data, { draftId }) => {
    await apiFetch("/_fixture/drafts", { method: "POST", body: { draft_id: draftId, note: data.note } });
  },
  describe: (data) => data.note,
});
