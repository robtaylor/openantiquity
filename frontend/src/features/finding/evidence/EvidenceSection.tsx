import { useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useRef, useState } from "react";
import type { Meta } from "../../../api/meta.js";
import { useMapStore } from "../../../map/store.js";
import { Button } from "../../../ui/Button.js";
import { viewStateFrom } from "../../mark/describe.js";
import { NO_PHOTO, type PhotoState } from "../../photos/PhotoUpload.js";
import { addEvidence, deleteEvidence, verifyEvidence, voteEvidence } from "../api.js";
import { groupEvidence, lowerFirst, offered, type Viewer, type ViewerPosition } from "../describe.js";
import { composeEvidence, type FieldId, type FormValues, isRecordKind } from "../evidenceForms.js";
import { reasonOf, toastFailure, useSignedInFirst } from "../feedback.js";
import { findingPageKeys } from "../keys.js";
import { MAP_LINK_WORDS, refusesLink } from "../positionInText.js";
import type { Evidence, EvidenceIn, FindingDetail } from "../types.js";
import { useOptimisticFinding } from "../useFinding.js";
import { EvidenceForm } from "./EvidenceForm.js";
import { EvidenceItem } from "./EvidenceItem.js";
import { KindChooser, useOpener } from "./KindChooser.js";
import { composeRecordLink, NO_RECORD, RecordLinkForm, type RecordLinkValues } from "./RecordLinkForm.js";

/** Which form is open, and what it holds. Kept here so a failed save can open it again as it was. */
export interface OpenForm {
  kindId: string;
  values: FormValues;
  /** The photo, for a form that takes one. It is uploaded as soon as it is chosen. */
  photo: PhotoState;
  record: RecordLinkValues;
  problem: { field: FieldId | null; message: string } | null;
}

export function openForm(kindId: string, record: Partial<RecordLinkValues> = {}): OpenForm {
  return { kindId, values: {}, photo: NO_PHOTO, record: { ...NO_RECORD, ...record }, problem: null };
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
  /** Open a form for a kind, in sight, with focus on its heading. */
  onOpen: (form: OpenForm) => void;
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
  onOpen,
  onApplied,
}: EvidenceSectionProps) {
  const client = useQueryClient();
  const signedInFirst = useSignedInFirst();
  const optimistic = useOptimisticFinding(finding.public_id);
  const [pending, setPending] = useState<Evidence[]>([]);
  const [choosing, setChoosing] = useState(false);
  const opener = useOpener("fc-evidence-add");
  const mayAdd = position.mayAddEvidence;
  const groups = groupEvidence(meta, [...finding.evidence, ...pending]);
  const refresh = () => void client.invalidateQueries({ queryKey: findingPageKeys.detail(finding.public_id) });

  /** Run `act` once the person is signed in and ready; say nothing if they close the sheet. */
  async function signedIn(act: () => void | Promise<void>): Promise<void> {
    if (await signedInFirst()) await act();
  }

  async function submit(open: OpenForm): Promise<void> {
    if (open.photo.status === "uploading") {
      setForm({ ...open, problem: { field: "photo", message: "Wait for the photo to finish sending." } });
      return;
    }
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
      // A form holds an uploaded photo only when its kind takes one.
      const body = open.photo.status === "done" ? { ...composed.body, media_id: open.photo.media.id } : composed.body;
      onApplied(await addEvidence(finding.public_id, body));
    } catch (error) {
      const problem = refusesLink(error)
        ? { field: "url" as const, message: MAP_LINK_WORDS }
        : { field: null, message: reasonOf(error) };
      setForm({ ...open, problem });
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

  // A moderator hiding evidence takes it off the page at once, and puts it back if the server refuses.
  const unhide = useRef(new Map<number, () => void>());
  function hidden(item: Evidence, isHidden: boolean): void {
    if (isHidden) {
      unhide.current.set(
        item.id,
        optimistic((current) => ({
          ...current,
          evidence: current.evidence.filter((entry) => entry.id !== item.id),
        })),
      );
    } else {
      unhide.current.get(item.id)?.();
      unhide.current.delete(item.id);
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
          ? " A piece stops counting while more people dispute it than endorse it, and experienced members' votes weigh more."
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
                  mayVote={offered(item.actions.vote) && (item.actions.vote.allowed || mayAdd)}
                  whyNoVote={
                    own
                      ? "Others endorse or dispute what you add."
                      : position.isFinder
                        ? "Others endorse or dispute the evidence on your finding."
                        : null
                  }
                  mayVerify={item.actions.verify.allowed}
                  mayDelete={own}
                  onVote={(value) => vote(item, value)}
                  onVerify={() => void verify(item)}
                  onDelete={() => void remove(item)}
                  onHidden={(isHidden) => hidden(item, isHidden)}
                  onHiddenDone={() => {
                    unhide.current.delete(item.id);
                    // The finding is reassessed without it.
                    refresh();
                  }}
                />
              );
            })}
          </ul>
        </div>
      ))}

      {mayAdd ? (
        form ? (
          <div className="fc-evidence-add">
            <h4 className="fc-evidence-add__title" tabIndex={-1}>
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
                photo={form.photo}
                onPhoto={(photo) =>
                  // The form reads only the name, to know that a photo is there.
                  setForm({
                    ...form,
                    photo,
                    values: { ...form.values, photo: photo.status === "done" ? photo.name : "" },
                    problem: null,
                  })
                }
                onSubmit={() => void submit(form)}
                onCancel={() => setForm(null)}
              />
            )}
          </div>
        ) : choosing ? (
          <KindChooser
            heading="What kind of evidence?"
            kinds={meta.vocab.evidence_kinds}
            idPrefix="fc-kind-hint"
            onChoose={(kindId) => {
              setChoosing(false);
              void signedIn(() => onOpen(openForm(kindId)));
            }}
            onCancel={() => {
              setChoosing(false);
              opener.giveBack();
            }}
          />
        ) : (
          <Button id={opener.id} icon={<Plus size={16} aria-hidden />} onClick={() => setChoosing(true)}>
            Add evidence
          </Button>
        )
      ) : null}
    </section>
  );
}
