import { Download, Link2, Pencil, ShieldMinus, ShieldPlus, Undo2 } from "lucide-react";
import { useRef, useState } from "react";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import { toast } from "../../ui/toastStore.js";
import { useFocusLater } from "../../ui/useFocusLater.js";
import { findingPath } from "../findings/selection.js";
import { SENSITIVITIES, type Sensitivity } from "../findings/types.js";
import { AddToInvestigation } from "../investigations/AddToInvestigation.js";
import { changeSensitivity, exportUrl, lowerSensitivity, updateFinding, withdrawFinding } from "./api.js";
import { type ViewerPosition, whoSees } from "./describe.js";
import { reasonOf, toastFailure } from "./feedback.js";
import { type PositionField, positionFields, positionWords } from "./positionInText.js";
import type { FindingDetail, FindingUpdate } from "./types.js";

/** The page's own address, to share. */
export function findingUrl(publicId: string): string {
  return new URL(findingPath(publicId), window.location.origin).href;
}

/** Copy the page's link, and say so. */
export async function copyLink(publicId: string): Promise<void> {
  const url = findingUrl(publicId);
  try {
    await navigator.clipboard.writeText(url);
    toast("The link is copied. Send it to someone who might know the place.", { kind: "success" });
  } catch {
    toast(`Copy this link: ${url}`, { duration: 0 });
  }
}

/** What each level is called. */
export const LEVEL_NAMES: Record<Sensitivity, string> = {
  open: "Open",
  protected: "Protected",
  restricted: "Restricted",
};

function EditDialog({
  meta,
  finding,
  open,
  onClose,
  onSaved,
}: {
  meta: Meta;
  finding: FindingDetail;
  open: boolean;
  onClose: () => void;
  onSaved: (finding: FindingDetail) => void;
}) {
  const [title, setTitle] = useState(finding.title);
  const [description, setDescription] = useState(finding.description ?? "");
  const [featureClass, setFeatureClass] = useState<string>(finding.feature_class);
  const [period, setPeriod] = useState<string>(finding.period);
  const [problem, setProblem] = useState<string | null>(null);
  /** The fields the server refused for saying where it is more closely than its square. */
  const [placed, setPlaced] = useState<ReadonlySet<PositionField>>(new Set());
  const [saving, setSaving] = useState(false);
  const fields = useRef<HTMLDivElement>(null);
  const focusLater = useFocusLater();

  async function save(): Promise<void> {
    // The button stays focusable while saving, so focus isn't lost from the dialog: a second press does nothing.
    if (saving) return;
    if (!title.trim()) {
      setProblem("A finding needs a title.");
      return;
    }
    const changes: FindingUpdate = {};
    if (title.trim() !== finding.title) changes.title = title.trim();
    if (description.trim() !== (finding.description ?? "")) changes.description = description.trim();
    if (featureClass !== finding.feature_class) changes.feature_class = featureClass as FindingUpdate["feature_class"];
    if (period !== finding.period) changes.period = period as FindingUpdate["period"];
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    setSaving(true);
    try {
      onSaved(await updateFinding(finding.public_id, changes));
      toast("Your changes are saved.", { kind: "success" });
      onClose();
    } catch (error) {
      const named = positionFields(error);
      setPlaced(named);
      // Said beside the field it is about, which takes focus. Anything else is said under the form.
      setProblem(named.size > 0 ? null : reasonOf(error));
      // The first field refused takes focus once it says why, inside the dialog.
      if (named.size > 0) {
        focusLater(() => fields.current?.querySelector<HTMLElement>('[aria-invalid="true"]') ?? null, { scroll: true });
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Edit your finding"
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" aria-disabled={saving || undefined} onClick={() => void save()}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </>
      }
    >
      <div className="fc-dialog-form" ref={fields}>
        <Field label="Title" error={placed.has("title") ? positionWords("title") : undefined}>
          {(control) => (
            <input
              {...control}
              className="fc-input"
              value={title}
              maxLength={120}
              onChange={(event) => {
                setTitle(event.target.value);
                setPlaced((fields) => without(fields, "title"));
              }}
            />
          )}
        </Field>
        <Field label="What it looks like">
          {(control) => (
            <select
              {...control}
              className="fc-input"
              value={featureClass}
              onChange={(event) => setFeatureClass(event.target.value)}
            >
              {meta.vocab.feature_classes.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Period">
          {(control) => (
            <select
              {...control}
              className="fc-input"
              value={period}
              onChange={(event) => setPeriod(event.target.value)}
            >
              {meta.vocab.periods.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Note (optional)" error={placed.has("description") ? positionWords("description") : undefined}>
          {(control) => (
            <textarea
              {...control}
              className="fc-input"
              rows={3}
              maxLength={5000}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
                setPlaced((fields) => without(fields, "description"));
              }}
            />
          )}
        </Field>
        {problem ? (
          <p className="fc-field__error" role="alert">
            {problem}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}

function RaiseDialog({
  finding,
  open,
  onClose,
  onSaved,
}: {
  finding: FindingDetail;
  open: boolean;
  onClose: () => void;
  onSaved: (finding: FindingDetail) => void;
}) {
  const above = SENSITIVITIES.slice(SENSITIVITIES.indexOf(finding.sensitivity) + 1);
  const [level, setLevel] = useState<Sensitivity | null>(above[0] ?? null);
  const [saving, setSaving] = useState(false);

  async function save(): Promise<void> {
    if (!level) return;
    setSaving(true);
    try {
      onSaved(await changeSensitivity(finding.public_id, level));
      toast(`It's now ${LEVEL_NAMES[level].toLowerCase()}. ${whoSees(level)}`, { kind: "success" });
      onClose();
    } catch (error) {
      toastFailure("Its level couldn't be raised.", error);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Protect this finding"
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={saving || !level} onClick={() => void save()}>
            {saving ? "Saving…" : "Raise it"}
          </Button>
        </>
      }
    >
      <div className="fc-dialog-form">
        <p>
          It's {LEVEL_NAMES[finding.sensitivity].toLowerCase()} now. {whoSees(finding.sensitivity)}
        </p>
        <ChipGroup
          label="New level"
          value={level}
          onChange={(value) => setLevel(value as Sensitivity)}
          options={above.map((id) => ({ id, label: LEVEL_NAMES[id] }))}
        />
        {level ? <p>{whoSees(level)}</p> : null}
        <p className="fc-finding__hint">Only a moderator can lower it again.</p>
      </div>
    </Dialog>
  );
}

/**
 * A moderator lowers a finding's level through the moderation route, with a
 * reason for the moderation log (docs/ARCHITECTURE.md, "Location sensitivity").
 */
function LowerDialog({
  finding,
  open,
  onClose,
  onSaved,
}: {
  finding: FindingDetail;
  open: boolean;
  onClose: () => void;
  onSaved: (finding: FindingDetail) => void;
}) {
  const below = SENSITIVITIES.slice(0, SENSITIVITIES.indexOf(finding.sensitivity)).reverse();
  const [level, setLevel] = useState<Sensitivity | null>(below[0] ?? null);
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save(): Promise<void> {
    if (!level) return;
    if (!reason.trim()) {
      setProblem("Say why, for the moderation log.");
      return;
    }
    setSaving(true);
    try {
      onSaved(await lowerSensitivity(finding.public_id, level, reason.trim()));
      toast(`It's now ${LEVEL_NAMES[level].toLowerCase()}. ${whoSees(level)}`, { kind: "success" });
      onClose();
    } catch (error) {
      setProblem(reasonOf(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Lower its protection"
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={saving || !level} onClick={() => void save()}>
            {saving ? "Saving…" : "Lower it"}
          </Button>
        </>
      }
    >
      <div className="fc-dialog-form">
        <p>
          It's {LEVEL_NAMES[finding.sensitivity].toLowerCase()} now. {whoSees(finding.sensitivity)}
        </p>
        <ChipGroup
          label="New level"
          value={level}
          onChange={(value) => setLevel(value as Sensitivity)}
          options={below.map((id) => ({ id, label: LEVEL_NAMES[id] }))}
        />
        {level ? <p>{whoSees(level)}</p> : null}
        <Field label="Why" hint="Kept in the moderation log, which only moderators read." error={problem ?? undefined}>
          {(control) => (
            <textarea
              {...control}
              className="fc-input"
              rows={2}
              maxLength={500}
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
                setProblem(null);
              }}
            />
          )}
        </Field>
      </div>
    </Dialog>
  );
}

function without<T>(set: ReadonlySet<T>, item: T): ReadonlySet<T> {
  if (!set.has(item)) return set;
  const next = new Set(set);
  next.delete(item);
  return next;
}

export interface ToolsProps {
  meta: Meta;
  finding: FindingDetail;
  position: ViewerPosition;
  onApplied: (finding: FindingDetail) => void;
}

/**
 * The controls for whoever the server lets use them: edit and withdraw for
 * the finder, raising the level for the finder, trusted members and
 * moderators, lowering it for moderators; and everyone's: copy a link,
 * download as GeoJSON or as a spreadsheet.
 */
export function Tools({ meta, finding, position, onApplied }: ToolsProps) {
  const [dialog, setDialog] = useState<"edit" | "raise" | "lower" | "withdraw" | null>(null);
  const close = () => setDialog(null);
  const own = position.isFinder || position.mayEdit || position.mayWithdraw;

  async function withdraw(): Promise<void> {
    close();
    try {
      onApplied(await withdrawFinding(finding.public_id));
      toast("It's withdrawn. It stays on the map, marked withdrawn, so nobody marks it again.");
    } catch (error) {
      toastFailure("It couldn't be withdrawn.", error);
    }
  }

  return (
    <>
      {own || position.mayRaise || position.mayLower ? (
        <section className="fc-finding__section" aria-labelledby="fc-yours-title">
          <h3 id="fc-yours-title">{own ? "Your finding" : "Protecting it"}</h3>
          <p className="fc-finding__hint">{whoSees(finding.sensitivity)}</p>
          <div className="fc-finding__tools">
            {position.mayEdit ? (
              <Button size="sm" icon={<Pencil size={15} aria-hidden />} onClick={() => setDialog("edit")}>
                Edit
              </Button>
            ) : null}
            {position.mayRaise ? (
              <Button size="sm" icon={<ShieldPlus size={15} aria-hidden />} onClick={() => setDialog("raise")}>
                Protect it more
              </Button>
            ) : null}
            {position.mayLower ? (
              <Button size="sm" icon={<ShieldMinus size={15} aria-hidden />} onClick={() => setDialog("lower")}>
                Lower its protection
              </Button>
            ) : null}
            {position.mayWithdraw ? (
              <Button
                size="sm"
                variant="ghost"
                icon={<Undo2 size={15} aria-hidden />}
                onClick={() => setDialog("withdraw")}
              >
                Withdraw
              </Button>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="fc-finding__section" aria-labelledby="fc-share-title">
        <h3 id="fc-share-title">Share and download</h3>
        <div className="fc-finding__tools">
          <Button size="sm" icon={<Link2 size={15} aria-hidden />} onClick={() => void copyLink(finding.public_id)}>
            Copy link
          </Button>
          {finding.state === "withdrawn" ? null : (
            <AddToInvestigation item={() => ({ kind: "finding", finding: finding.public_id })} what="This finding" />
          )}
          <a
            className="fc-button fc-button--secondary fc-button--sm"
            href={exportUrl(finding.public_id, "geojson")}
            download
          >
            <Download size={15} aria-hidden />
            GeoJSON
          </a>
          <a
            className="fc-button fc-button--secondary fc-button--sm"
            href={exportUrl(finding.public_id, "csv")}
            download
          >
            <Download size={15} aria-hidden />
            Spreadsheet (CSV)
          </a>
        </div>
        <p className="fc-finding__hint">
          The spreadsheet uses the field names Historic Environment Records use. A protected place downloads as its
          square unless you can see it exactly.
        </p>
      </section>

      {dialog === "edit" ? <EditDialog meta={meta} finding={finding} open onClose={close} onSaved={onApplied} /> : null}
      {dialog === "raise" ? <RaiseDialog finding={finding} open onClose={close} onSaved={onApplied} /> : null}
      {dialog === "lower" ? <LowerDialog finding={finding} open onClose={close} onSaved={onApplied} /> : null}
      <Dialog
        open={dialog === "withdraw"}
        onClose={close}
        title="Withdraw this finding?"
        actions={
          <>
            <Button onClick={close}>Keep it</Button>
            <Button variant="danger" onClick={() => void withdraw()}>
              Withdraw it
            </Button>
          </>
        }
      >
        <p>
          It stays on the map, marked withdrawn, so nobody marks the same thing again. Nobody can add to it after that,
          and you can't undo it.
        </p>
      </Dialog>
    </>
  );
}
