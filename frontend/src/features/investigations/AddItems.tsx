import { BookPlus, Eye, NotebookPen } from "lucide-react";
import { useState } from "react";
import type { Meta } from "../../api/meta.js";
import { useMapCover } from "../../map/visibleArea.js";
import { Button } from "../../ui/Button.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import type { Me } from "../account/api.js";
import { type Item, type ItemIn, LIMITS } from "./api.js";
import { MARKDOWN_HINT } from "./describe.js";
import { currentView } from "./savedView.js";
import type { Notebook } from "./useInvestigation.js";

/** What an item looks like before the server has answered. */
export function previewOf(me: Me, body: ItemIn): Omit<Item, "id" | "position"> {
  return {
    kind: body.kind,
    title: body.title ?? null,
    note: body.note ?? null,
    view: "view" in body ? body.view : null,
    reference: "reference" in body ? body.reference : null,
    profile: "profile" in body ? body.profile : null,
    added_by: { handle: me.handle, display_name: me.display_name, role: me.role },
    created_at: new Date().toISOString(),
  };
}

type Adding = "note" | "reference" | null;

/** What is wrong with a reference's web address, or null when it is empty or fine. */
export function addressProblem(address: string): string | null {
  return address && !/^https?:\/\/\S+$/i.test(address) ? "A web address starts with https:// or http://." : null;
}

/** A reference's web address and citation, in the add and edit dialogs alike. */
export function ReferenceFields({
  url,
  citation,
  onUrl,
  onCitation,
}: {
  url: string;
  citation: string;
  onUrl: (value: string) => void;
  onCitation: (value: string) => void;
}) {
  return (
    <>
      <Field label="Web address (optional)">
        {(control) => (
          <input
            {...control}
            className="fc-input"
            type="url"
            inputMode="url"
            placeholder="https://"
            value={url}
            onChange={(event) => onUrl(event.target.value)}
          />
        )}
      </Field>
      <Field label="Citation (optional)" hint="Authors, year, publisher and pages, however you write them.">
        {(control) => (
          <input
            {...control}
            className="fc-input"
            value={citation}
            maxLength={LIMITS.citation}
            onChange={(event) => onCitation(event.target.value)}
          />
        )}
      </Field>
    </>
  );
}

function NoteDialog({ onClose, onAdd }: { onClose: () => void; onAdd: (body: ItemIn) => void }) {
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <Dialog
      open
      onClose={onClose}
      title="Add a note"
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            onClick={() => {
              if (!note.trim()) {
                setProblem("Write the note first.");
                return;
              }
              onAdd({ kind: "note", note: note.trim(), title: title.trim() || null });
              onClose();
            }}
          >
            Add the note
          </Button>
        </>
      }
    >
      <div className="fc-dialog-form">
        <Field label="Title (optional)">
          {(control) => (
            <input
              {...control}
              className="fc-input"
              value={title}
              maxLength={LIMITS.itemTitle}
              onChange={(event) => setTitle(event.target.value)}
            />
          )}
        </Field>
        <Field label="Note" hint={MARKDOWN_HINT} error={problem ?? undefined}>
          {(control) => (
            <textarea
              {...control}
              className="fc-input"
              rows={8}
              maxLength={LIMITS.itemNote}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          )}
        </Field>
      </div>
    </Dialog>
  );
}

function ReferenceDialog({ onClose, onAdd }: { onClose: () => void; onAdd: (body: ItemIn) => void }) {
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [citation, setCitation] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  function add(): void {
    if (!title.trim()) {
      setProblem("A reference needs a title.");
      return;
    }
    const address = url.trim();
    const wrong = addressProblem(address);
    if (wrong) {
      setProblem(wrong);
      return;
    }
    onAdd({
      kind: "reference",
      title: title.trim(),
      reference: { url: address || null, citation: citation.trim() || null },
    });
    onClose();
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title="Add a reference"
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={add}>
            Add the reference
          </Button>
        </>
      }
    >
      <div className="fc-dialog-form">
        <p className="fc-field__hint">A book, a paper, a web page or an archive source that bears on the work.</p>
        <Field label="Title">
          {(control) => (
            <input
              {...control}
              className="fc-input"
              value={title}
              maxLength={LIMITS.itemTitle}
              onChange={(event) => setTitle(event.target.value)}
            />
          )}
        </Field>
        <ReferenceFields url={url} citation={citation} onUrl={setUrl} onCitation={setCitation} />
        {problem ? (
          <p className="fc-field__error" role="alert">
            {problem}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}

/**
 * Adding to the notebook from its own page: a note, a reference, or the
 * map as it is now. Findings, records and height profiles are added from
 * their own pages, which this says.
 */
export function AddItems({ meta, me, notebook }: { meta: Meta; me: Me; notebook: Notebook }) {
  const [adding, setAdding] = useState<Adding>(null);
  const add = (body: ItemIn) => void notebook.add(body, previewOf(me, body));
  return (
    <div className="fc-inv-add">
      <div className="fc-inv-add__buttons">
        <Button size="sm" icon={<NotebookPen size={15} aria-hidden />} onClick={() => setAdding("note")}>
          Add a note
        </Button>
        <Button size="sm" icon={<BookPlus size={15} aria-hidden />} onClick={() => setAdding("reference")}>
          Add a reference
        </Button>
        <Button
          size="sm"
          icon={<Eye size={15} aria-hidden />}
          onClick={() => add({ kind: "view", view: currentView(meta, useMapCover.getState().cover) })}
        >
          Add the map's view
        </Button>
      </div>
      <p className="fc-field__hint">
        To add a finding, a heritage record or a height profile, open it and choose "Add to an investigation".
      </p>
      {adding === "note" ? <NoteDialog onClose={() => setAdding(null)} onAdd={add} /> : null}
      {adding === "reference" ? <ReferenceDialog onClose={() => setAdding(null)} onAdd={add} /> : null}
    </div>
  );
}
