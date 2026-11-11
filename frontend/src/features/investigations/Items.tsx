import { ChevronDown, ChevronUp, GripVertical, Pencil, Trash2 } from "lucide-react";
import { type KeyboardEvent, type PointerEvent, useEffect, useId, useRef, useState } from "react";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import { IconButton } from "../../ui/IconButton.js";
import { addressProblem, ReferenceFields } from "./AddItems.js";
import { type Item, type ItemUpdate, LIMITS } from "./api.js";
import { dateText, KIND_LABEL, MARKDOWN_HINT } from "./describe.js";
import { ItemBody, ItemNote } from "./ItemBody.js";
import { dropIndex } from "./order.js";
import { isPending, type Notebook } from "./useInvestigation.js";

/** A note's first line without its Markdown, cut short, to name it by. */
function plainLine(note: string): string {
  const line = note.trim().split("\n")[0] ?? "";
  return line
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^#+\s*|^\s*[-*+]\s+|[*_`\\]/g, "")
    .trim()
    .slice(0, 60);
}

/** What an item is called in words: its own title, or what it holds. */
export function itemName(item: Item): string {
  if (item.title) return item.title;
  if (item.finding) return item.finding.title;
  if (item.record) return item.record.name;
  if (item.kind === "note" && item.note) return plainLine(item.note) || KIND_LABEL.note;
  return KIND_LABEL[item.kind];
}

function EditItemDialog({
  item,
  onClose,
  onSave,
}: {
  item: Item;
  onClose: () => void;
  onSave: (changes: ItemUpdate) => void;
}) {
  const [title, setTitle] = useState(item.title ?? "");
  const [note, setNote] = useState(item.note ?? "");
  const [url, setUrl] = useState(item.reference?.url ?? "");
  const [citation, setCitation] = useState(item.reference?.citation ?? "");
  const [problem, setProblem] = useState<string | null>(null);

  function save(): void {
    if (item.kind === "note" && !note.trim()) {
      setProblem("A note needs its text.");
      return;
    }
    if (item.kind === "reference" && !title.trim()) {
      setProblem("A reference needs a title.");
      return;
    }
    const wrong = item.kind === "reference" ? addressProblem(url.trim()) : null;
    if (wrong) {
      setProblem(wrong);
      return;
    }
    const changes: ItemUpdate = {};
    if (title.trim() !== (item.title ?? "")) changes.title = title.trim() || null;
    if (note.trim() !== (item.note ?? "")) changes.note = note.trim() || null;
    if (item.kind === "reference") {
      const reference = { url: url.trim() || null, citation: citation.trim() || null };
      if (
        reference.url !== (item.reference?.url ?? null) ||
        reference.citation !== (item.reference?.citation ?? null)
      ) {
        changes.reference = reference;
      }
    }
    if (Object.keys(changes).length > 0) onSave(changes);
    onClose();
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Edit this ${KIND_LABEL[item.kind].toLowerCase()}`}
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={save}>
            Save changes
          </Button>
        </>
      }
    >
      <div className="fc-dialog-form">
        <Field label={item.kind === "reference" ? "Title" : "Title (optional)"}>
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
        {item.kind === "reference" ? (
          <ReferenceFields url={url} citation={citation} onUrl={setUrl} onCitation={setCitation} />
        ) : null}
        <Field label={item.kind === "note" ? "Note" : "Note (optional)"} hint={MARKDOWN_HINT}>
          {(control) => (
            <textarea
              {...control}
              className="fc-input"
              rows={item.kind === "note" ? 8 : 4}
              maxLength={LIMITS.itemNote}
              value={note}
              onChange={(event) => setNote(event.target.value)}
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

interface Drag {
  id: number;
  from: number;
  /** Where it would go if let go now, counted in the order once it has left its own place. */
  to: number | null;
  /** The card it is over, and which half, to draw where it would land. */
  over: { index: number; side: "before" | "after" } | null;
}

interface ItemsProps {
  meta: Meta;
  items: Item[];
  editable: boolean;
  notebook: Notebook;
}

/**
 * The notebook's items in the owner's order. Editors move them by dragging
 * the handle, by the arrow keys on it, or by the up and down buttons. Each
 * move shows at once, is saved straight away, and is said aloud.
 */
export function Items({ meta, items, editable, notebook }: ItemsProps) {
  const list = useRef<HTMLOListElement>(null);
  const [editing, setEditing] = useState<Item | null>(null);
  const [said, setSaid] = useState("");
  const [drag, setDrag] = useState<Drag | null>(null);
  const focusAfterMove = useRef<number | null>(null);
  const hintId = useId();

  // A moved card's handle keeps focus, wherever the card has gone.
  useEffect(() => {
    const id = focusAfterMove.current;
    if (id === null) return;
    focusAfterMove.current = null;
    list.current?.querySelector<HTMLElement>(`[data-item="${id}"] .fc-inv-item__handle`)?.focus();
  });

  function move(item: Item, to: number, keepFocus: boolean): void {
    if (!notebook.move(item, to)) return;
    if (keepFocus) focusAfterMove.current = item.id;
    setSaid(`Moved “${itemName(item)}” to place ${to + 1} of ${items.length}.`);
  }

  function onHandleKey(event: KeyboardEvent<HTMLButtonElement>, item: Item, index: number): void {
    const to =
      event.key === "ArrowUp"
        ? index - 1
        : event.key === "ArrowDown"
          ? index + 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? items.length - 1
              : null;
    if (to === null) return;
    event.preventDefault();
    move(item, to, true);
  }

  function overAt(clientY: number): Drag["over"] {
    const cards = [...(list.current?.querySelectorAll<HTMLElement>(":scope > li") ?? [])];
    for (const [index, card] of cards.entries()) {
      const box = card.getBoundingClientRect();
      if (clientY < box.bottom || index === cards.length - 1) {
        return { index, side: clientY < box.top + box.height / 2 ? "before" : "after" };
      }
    }
    return null;
  }

  function onPointerDown(event: PointerEvent<HTMLButtonElement>, item: Item, index: number): void {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({ id: item.id, from: index, to: null, over: null });
  }

  function onPointerMove(event: PointerEvent<HTMLButtonElement>): void {
    if (!drag) return;
    const over = overAt(event.clientY);
    const to = over ? dropIndex(drag.from, over.index, over.side) : null;
    setDrag({ ...drag, over, to: to === drag.from ? null : to });
  }

  function onPointerUp(item: Item): void {
    if (drag && drag.to !== null) move(item, drag.to, false);
    setDrag(null);
  }

  return (
    <>
      <p className="fc-visually-hidden" aria-live="polite">
        {said}
      </p>
      {editable ? (
        <p className="fc-visually-hidden" id={hintId}>
          Drag to move it, or use the up and down arrow keys.
        </p>
      ) : null}
      <ol className="fc-inv-items" ref={list} data-dragging={drag ? "true" : undefined}>
        {items.map((item, index) => {
          const pending = isPending(item);
          const name = itemName(item);
          const dropMark = drag?.over?.index === index && drag.to !== null ? `fc-inv-item--drop-${drag.over.side}` : "";
          return (
            <li
              key={item.id}
              className={`fc-inv-item ${dropMark} ${drag?.id === item.id ? "fc-inv-item--lifted" : ""}`}
              data-item={item.id}
              data-kind={item.kind}
              aria-busy={pending || undefined}
            >
              <div className="fc-inv-item__head">
                {editable ? (
                  <button
                    type="button"
                    className="fc-inv-item__handle"
                    aria-label={`Move “${name}”, place ${index + 1} of ${items.length}`}
                    aria-describedby={hintId}
                    disabled={pending}
                    onKeyDown={(event) => onHandleKey(event, item, index)}
                    onPointerDown={(event) => onPointerDown(event, item, index)}
                    onPointerMove={onPointerMove}
                    onPointerUp={() => onPointerUp(item)}
                    onPointerCancel={() => setDrag(null)}
                  >
                    <GripVertical size={16} aria-hidden />
                  </button>
                ) : null}
                <span className="fc-inv-item__kind">{KIND_LABEL[item.kind]}</span>
                {pending ? (
                  <span className="fc-inv-item__saving" role="status">
                    Saving…
                  </span>
                ) : null}
                {editable ? (
                  <span className="fc-inv-item__tools">
                    <IconButton
                      size="sm"
                      label={`Move “${name}” up`}
                      disabled={pending || index === 0}
                      onClick={() => move(item, index - 1, false)}
                    >
                      <ChevronUp size={16} aria-hidden />
                    </IconButton>
                    <IconButton
                      size="sm"
                      label={`Move “${name}” down`}
                      disabled={pending || index === items.length - 1}
                      onClick={() => move(item, index + 1, false)}
                    >
                      <ChevronDown size={16} aria-hidden />
                    </IconButton>
                    <IconButton size="sm" label={`Edit “${name}”`} disabled={pending} onClick={() => setEditing(item)}>
                      <Pencil size={15} aria-hidden />
                    </IconButton>
                    <IconButton
                      size="sm"
                      label={`Take “${name}” out`}
                      disabled={pending}
                      onClick={() => {
                        void notebook.remove(item);
                        setSaid(`Took “${name}” out.`);
                      }}
                    >
                      <Trash2 size={15} aria-hidden />
                    </IconButton>
                  </span>
                ) : null}
              </div>
              {item.title && item.kind !== "finding" ? <h4 className="fc-inv-item__title">{item.title}</h4> : null}
              {item.title && item.kind === "finding" ? <p className="fc-inv-item__label">{item.title}</p> : null}
              <ItemBody meta={meta} item={item} />
              <ItemNote item={item} />
              <p className="fc-inv-item__by">
                Added by {item.added_by.display_name}
                {pending ? null : ` on ${dateText(item.created_at)}`}
              </p>
            </li>
          );
        })}
      </ol>
      {editing ? (
        <EditItemDialog
          item={editing}
          onClose={() => setEditing(null)}
          onSave={(changes) => void notebook.edit(editing, changes)}
        />
      ) : null}
    </>
  );
}
