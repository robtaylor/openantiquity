import { Download, Link2, Pencil, ShieldPlus, Undo2 } from "lucide-react";
import { useState } from "react";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import { toast } from "../../ui/toastStore.js";
import { findingPath } from "../findings/selection.js";
import { SENSITIVITIES, type Sensitivity } from "../findings/types.js";
import { changeSensitivity, exportUrl, updateFinding, withdrawFinding } from "./api.js";
import { type ViewerPosition, whoSees } from "./describe.js";
import { reasonOf, toastFailure } from "./feedback.js";
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

const LEVEL_NAMES: Record<Sensitivity, string> = { open: "Open", protected: "Protected", restricted: "Restricted" };

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
  const [saving, setSaving] = useState(false);

  async function save(): Promise<void> {
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
      setProblem(reasonOf(error));
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
          <Button variant="primary" disabled={saving} onClick={() => void save()}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </>
      }
    >
      <div className="fc-dialog-form">
        <Field label="Title">
          {(control) => (
            <input
              {...control}
              className="fc-input"
              value={title}
              maxLength={120}
              onChange={(event) => setTitle(event.target.value)}
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
        <Field label="Note (optional)">
          {(control) => (
            <textarea
              {...control}
              className="fc-input"
              rows={3}
              maxLength={5000}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
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

export interface ToolsProps {
  meta: Meta;
  finding: FindingDetail;
  position: ViewerPosition;
  onApplied: (finding: FindingDetail) => void;
}

/**
 * The finder's own controls (edit, withdraw, raise the level) and everyone's
 * (copy a link, download as GeoJSON or as a spreadsheet).
 */
export function Tools({ meta, finding, position, onApplied }: ToolsProps) {
  const [dialog, setDialog] = useState<"edit" | "raise" | "withdraw" | null>(null);
  const canRaise = position.mayRaise && finding.sensitivity !== "restricted";
  const close = () => setDialog(null);

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
      {position.isFinder || canRaise ? (
        <section className="fc-finding__section" aria-labelledby="fc-yours-title">
          <h3 id="fc-yours-title">{position.isFinder ? "Your finding" : "Protecting it"}</h3>
          <p className="fc-finding__hint">{whoSees(finding.sensitivity)}</p>
          <div className="fc-finding__tools">
            {position.isFinder && position.takesWork ? (
              <Button size="sm" icon={<Pencil size={15} aria-hidden />} onClick={() => setDialog("edit")}>
                Edit
              </Button>
            ) : null}
            {canRaise ? (
              <Button size="sm" icon={<ShieldPlus size={15} aria-hidden />} onClick={() => setDialog("raise")}>
                Protect it more
              </Button>
            ) : null}
            {position.isFinder && position.takesWork ? (
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
