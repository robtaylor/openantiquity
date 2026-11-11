import { useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import type { Meta } from "../../../api/meta.js";
import { useMapStore } from "../../../map/store.js";
import { Button } from "../../../ui/Button.js";
import { viewStateFrom } from "../../mark/describe.js";
import { addEvidence, deleteEvidence, uploadPhoto, verifyEvidence, voteEvidence } from "../api.js";
import { groupEvidence, lowerFirst, type Viewer, type ViewerPosition } from "../describe.js";
import { composeEvidence, type FieldId, type FormValues, isRecordKind, photoProblem } from "../evidenceForms.js";
import { reasonOf, toastFailure, useSignedInFirst } from "../feedback.js";
import { findingPageKeys } from "../keys.js";
import type { Evidence, EvidenceIn, FindingDetail } from "../types.js";
import { useOptimisticFinding } from "../useFinding.js";
import { EvidenceForm } from "./EvidenceForm.js";
import { EvidenceItem } from "./EvidenceItem.js";
import { composeRecordLink, NO_RECORD, RecordLinkForm, type RecordLinkValues } from "./RecordLinkForm.js";

/** Which form is open, and what it holds. Kept here so a failed save can open it again as it was. */
export interface OpenForm {
  kindId: string;
  values: FormValues;
  /** The picture chosen for a form that takes one. */
  file: File | null;
  record: RecordLinkValues;
  problem: { field: FieldId | null; message: string } | null;
}

export function openForm(kindId: string, record: Partial<RecordLinkValues> = {}): OpenForm {
  return { kindId, values: {}, file: null, record: { ...NO_RECORD, ...record }, problem: null };
}

/** A stand-in for evidence being saved, shown at once and replaced by the server's answer. */
function pendingItem(body: EvidenceIn, viewer: Viewer, displayName: string): Evidence {
  return {
    id: -Date.now(),
    kind: body.kind,
    stance: body.stance ?? "supports",
    title: body.title ?? null,
    note: body.note ?? null,
    url: body.url ?? null,
    record_id: body.record_id ?? null,
    source_key: body.source_key ?? null,
    reference: body.reference ?? null,
    relation: body.relation ?? null,
    media_id: null,
    view: body.view ?? null,
    occurred_on: body.occurred_on ?? null,
    organisation: body.organisation ?? null,
    outcome: body.outcome ?? null,
    contributor: { handle: viewer.handle ?? "", display_name: displayName, role: viewer.role ?? "member" },
    created_at: new Date().toISOString(),
    verified_by: null,
    vote_total: 0,
    standing: true,
    independent: true,
    my_vote: null,
    redacted: false,
    endorsements: 0,
    disputes: 0,
    // Nothing can be done to a stand-in. The server's answer replaces it within a moment.
    actions: { vote: { allowed: false, reason: null }, verify: { allowed: false, reason: null } },
  };
}

export interface EvidenceSectionProps {
  meta: Meta;
  finding: FindingDetail;
  position: ViewerPosition;
  viewer: Viewer;
  displayName: string;
  youngContributor: boolean;
  form: OpenForm | null;
  setForm: (form: OpenForm | null) => void;
  onApplied: (finding: FindingDetail) => void;
}

/**
 * The evidence on a finding, grouped by kind, and the forms that add more.
 * Adding, voting, verifying and removing all show at once and are put back,
 * with a toast, if the server refuses.
 */
export function EvidenceSection({
  meta,
  finding,
  position,
  viewer,
  displayName,
  youngContributor,
  form,
  setForm,
  onApplied,
}: EvidenceSectionProps) {
  const client = useQueryClient();
  const signedInFirst = useSignedInFirst();
  const optimistic = useOptimisticFinding(finding.public_id);
  const [pending, setPending] = useState<Evidence[]>([]);
  const [choosing, setChoosing] = useState(false);
  const mayAdd = position.seesExact && position.takesWork;
  const groups = groupEvidence(meta, [...finding.evidence, ...pending]);
  const refresh = () => void client.invalidateQueries({ queryKey: findingPageKeys.detail(finding.public_id) });

  /** Run `act` once the person is signed in and ready; say nothing if they close the sheet. */
  async function signedIn(act: () => void | Promise<void>): Promise<void> {
    if (await signedInFirst()) await act();
  }

  async function submit(open: OpenForm): Promise<void> {
    const composed = isRecordKind(open.kindId)
      ? composeRecordLink(open.record)
      : composeEvidence(open.kindId, open.values, viewStateFrom(useMapStore.getState()));
    if (!composed.ok) {
      setForm({ ...open, problem: { field: composed.field, message: composed.message } });
      return;
    }
    const placeholder = pendingItem(composed.body, viewer, displayName);
    setForm(null);
    setPending((items) => [...items, placeholder]);
    try {
      // A form holds a file only when its kind takes a photo, which goes up first.
      const body = open.file ? { ...composed.body, media_id: (await uploadPhoto(open.file)).id } : composed.body;
      onApplied(await addEvidence(finding.public_id, body));
    } catch (error) {
      setForm({ ...open, problem: { field: null, message: reasonOf(error) } });
      toastFailure("Your evidence couldn't be added.", error);
    } finally {
      setPending((items) => items.filter((item) => item !== placeholder));
    }
  }

  function vote(item: Evidence, value: -1 | 0 | 1): void {
    void signedIn(async () => {
      // Only the vote itself shows at once. The total is weighted by who
      // voted, which is the server's to work out, so it waits for the refresh.
      const undo = optimistic((current) => ({
        ...current,
        evidence: current.evidence.map((entry) =>
          entry.id === item.id ? { ...entry, my_vote: value === 0 ? null : value } : entry,
        ),
      }));
      try {
        await voteEvidence(item.id, value);
        // The weighted total and the step may have moved: ask for them.
        refresh();
      } catch (error) {
        undo();
        toastFailure("Your vote couldn't be saved.", error);
      }
    });
  }

  async function verify(item: Evidence): Promise<void> {
    try {
      onApplied(await verifyEvidence(item.id));
    } catch (error) {
      toastFailure("It couldn't be verified.", error);
    }
  }

  async function remove(item: Evidence): Promise<void> {
    const undo = optimistic((current) => ({
      ...current,
      evidence: current.evidence.filter((entry) => entry.id !== item.id),
    }));
    try {
      await deleteEvidence(item.id);
      refresh();
    } catch (error) {
      undo();
      toastFailure("It couldn't be removed.", error);
    }
  }

  return (
    <section className="fc-finding__section" aria-labelledby="fc-evidence-title" id="fc-evidence">
      <h3 id="fc-evidence-title">Evidence</h3>
      <p className="fc-finding__hint">
        Old maps, aerial photos, records and visits that bear on it. Evidence counts when someone other than the finder
        adds it or endorses it.
        {groups.length > 0
          ? " Its support is endorsements minus disputes, with more weight for experienced members."
          : null}
      </p>

      {groups.length === 0 ? <p className="fc-muted">No evidence yet.</p> : null}
      {groups.map((group) => (
        <div key={group.kind.id} className="fc-evidence-group">
          <h4>
            {group.kind.label} <span className="fc-muted">({group.items.length})</span>
          </h4>
          <ul className="fc-evidence-list">
            {group.items.map((item) => {
              const own = viewer.handle !== null && item.contributor.handle === viewer.handle;
              return (
                <EvidenceItem
                  key={item.id}
                  meta={meta}
                  item={item}
                  pending={item.id < 0}
                  mayVote={mayAdd && !own && !position.isFinder}
                  whyNoVote={
                    own
                      ? "Others endorse or dispute what you add."
                      : position.isFinder
                        ? "Others endorse or dispute the evidence on your finding."
                        : null
                  }
                  mayVerify={position.mayVerify && !own && !position.isFinder}
                  mayDelete={own}
                  onVote={(value) => vote(item, value)}
                  onVerify={() => void verify(item)}
                  onDelete={() => void remove(item)}
                />
              );
            })}
          </ul>
        </div>
      ))}

      {mayAdd ? (
        form ? (
          <div className="fc-evidence-add">
            <h4>
              {isRecordKind(form.kindId)
                ? "Link a heritage record"
                : `Add ${lowerFirst(meta.vocab.evidence_kinds.find((kind) => kind.id === form.kindId)?.label ?? "evidence")}`}
            </h4>
            {isRecordKind(form.kindId) ? (
              <RecordLinkForm
                meta={meta}
                publicId={finding.public_id}
                values={form.record}
                problem={form.problem?.message ?? null}
                onChange={(record) => setForm({ ...form, record, problem: null })}
                onSubmit={() => void submit(form)}
                onCancel={() => setForm(null)}
              />
            ) : (
              <EvidenceForm
                meta={meta}
                kindId={form.kindId}
                nation={finding.nation}
                youngContributor={youngContributor}
                values={form.values}
                problem={form.problem}
                onChange={(values) => setForm({ ...form, values, problem: null })}
                onFile={(file) => {
                  // Said at once, rather than after the upload is refused.
                  const problem = file ? photoProblem(file) : null;
                  const kept = problem ? null : file;
                  setForm({
                    ...form,
                    file: kept,
                    values: { ...form.values, photo: kept?.name ?? "" },
                    problem: problem ? { field: "photo", message: problem } : null,
                  });
                }}
                onSubmit={() => void submit(form)}
                onCancel={() => setForm(null)}
              />
            )}
          </div>
        ) : choosing ? (
          <div className="fc-evidence-add">
            <h4>What kind of evidence?</h4>
            {/* Each kind is explained beside it, because a tooltip never reaches touch or the keyboard. */}
            <ul className="fc-kind-list">
              {meta.vocab.evidence_kinds.map((kind) => (
                <li key={kind.id} className="fc-kind-list__item">
                  <Button
                    size="sm"
                    aria-describedby={`fc-kind-hint-${kind.id}`}
                    onClick={() => {
                      setChoosing(false);
                      void signedIn(() => setForm(openForm(kind.id)));
                    }}
                  >
                    {kind.label}
                  </Button>
                  <span className="fc-finding__hint" id={`fc-kind-hint-${kind.id}`}>
                    {kind.hint}
                  </span>
                </li>
              ))}
            </ul>
            <Button size="sm" variant="ghost" onClick={() => setChoosing(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button icon={<Plus size={16} aria-hidden />} onClick={() => setChoosing(true)}>
            Add evidence
          </Button>
        )
      ) : null}
    </section>
  );
}
