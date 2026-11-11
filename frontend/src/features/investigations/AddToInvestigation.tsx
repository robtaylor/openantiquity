import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { NotebookPen } from "lucide-react";
import { useId, useState } from "react";
import { useNavigate } from "react-router";
import { isTransient } from "../../api/client.js";
import { Button, type ButtonProps } from "../../ui/Button.js";
import { Dialog } from "../../ui/Dialog.js";
import { Field } from "../../ui/Field.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { toast } from "../../ui/toastStore.js";
import { useSession } from "../account/session.js";
import { reasonOf, useSignedInFirst } from "../finding/feedback.js";
import {
  addItem,
  createInvestigation,
  fetchInvestigation,
  fetchInvestigations,
  type InvestigationSummary,
  type ItemIn,
  investigationPath,
  LIMITS,
  MAX_PAGE,
} from "./api.js";
import { VISIBILITY } from "./describe.js";
import { investigationKeys } from "./keys.js";
import "./investigations.css";

const NEW = "new";

/**
 * The investigations this person may add to: every one they own, and those
 * they belong to as an editor. The list doesn't say a member's role, so the
 * page of each one they don't own is asked for it.
 */
function useEditable(enabled: boolean) {
  const session = useSession();
  const mine = useQuery({
    queryKey: investigationKeys.mine,
    queryFn: async ({ signal }) => (await fetchInvestigations("mine", null, null, signal, MAX_PAGE)).items,
    enabled,
    retry: (failures, error) => failures < 1 && isTransient(error),
  });
  const items = mine.data ?? [];
  const handle = session.me?.handle;
  const others = items.filter((item) => item.owner.handle !== handle);
  const roles = useQueries({
    queries: others.map((item) => ({
      queryKey: investigationKeys.detail(item.public_id),
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchInvestigation(item.public_id, signal),
      enabled,
    })),
  });
  const editable = new Set(roles.flatMap((role) => (role.data?.my_role === "editor" ? [role.data.public_id] : [])));
  const list: InvestigationSummary[] = items.filter(
    (item) => item.owner.handle === handle || editable.has(item.public_id),
  );
  const loading = mine.isPending || roles.some((role) => role.isPending);
  return { list, loading, error: mine.error, retry: () => void mine.refetch() };
}

function Chooser({ body, what, onClose }: { body: ItemIn; what: string; onClose: () => void }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const editable = useEditable(true);
  const [chosen, setChosen] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  /** One started here whose item couldn't be added: trying again adds to it rather than start another. */
  const [started, setStarted] = useState<Pick<InvestigationSummary, "public_id" | "title" | "visibility"> | null>(null);
  const name = useId();
  // Until the lists come back with it, the one started here is listed too.
  const options =
    started && !editable.list.some((item) => item.public_id === started.public_id)
      ? [...editable.list, started]
      : editable.list;
  const choice = chosen ?? options[0]?.public_id ?? NEW;

  async function add(): Promise<void> {
    if (choice === NEW && !title.trim()) {
      setProblem("Give the new investigation a title.");
      return;
    }
    setSaving(true);
    setProblem(null);
    try {
      let target: { public_id: string; title: string } | null =
        options.find((item) => item.public_id === choice) ?? null;
      if (choice === NEW) {
        const created = await createInvestigation(title.trim());
        client.setQueryData(investigationKeys.detail(created.public_id), created);
        // It is chosen from now on, and listed once the lists come back, so a second press doesn't start a second one.
        setStarted(created);
        setChosen(created.public_id);
        void client.invalidateQueries({ queryKey: investigationKeys.lists });
        target = created;
      }
      if (!target) throw new Error("That investigation isn't in your list any more.");
      const withNote: ItemIn = note.trim() ? { ...body, note: note.trim() } : body;
      await addItem(target.public_id, withNote);
      void client.invalidateQueries({ queryKey: investigationKeys.detail(target.public_id) });
      void client.invalidateQueries({ queryKey: investigationKeys.lists });
      const publicId = target.public_id;
      toast(`Added to “${target.title}”.`, {
        kind: "success",
        action: { label: "Open it", onClick: () => navigate(investigationPath(publicId)) },
      });
      onClose();
    } catch (error) {
      setProblem(reasonOf(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title="Add to an investigation"
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" disabled={saving || editable.loading} onClick={() => void add()}>
            {saving ? "Adding…" : choice === NEW ? "Start it and add" : "Add it"}
          </Button>
        </>
      }
    >
      <div className="fc-dialog-form fc-inv-chooser">
        <p className="fc-field__hint">
          {what} goes at the end of the investigation you choose. An investigation is a notebook tied to the map.
        </p>
        {editable.loading ? (
          <div role="status">
            <span className="fc-visually-hidden">Loading your investigations</span>
            <Skeleton lines={2} />
          </div>
        ) : (
          <fieldset className="fc-inv-chooser__list">
            <legend className="fc-field__label">Which one</legend>
            {editable.error ? (
              <p className="fc-field__error" role="alert">
                Your investigations couldn't be loaded. {editable.error.message}{" "}
                <Button size="sm" variant="ghost" onClick={editable.retry}>
                  Try again
                </Button>
              </p>
            ) : null}
            {options.map((item) => (
              <label key={item.public_id} className="fc-inv-chooser__option">
                <input
                  type="radio"
                  name={name}
                  value={item.public_id}
                  checked={choice === item.public_id}
                  onChange={() => setChosen(item.public_id)}
                />
                <span>
                  <span className="fc-inv-chooser__title">{item.title}</span>
                  <span className="fc-inv-chooser__meta">{VISIBILITY[item.visibility].label}</span>
                </span>
              </label>
            ))}
            <label className="fc-inv-chooser__option">
              <input type="radio" name={name} value={NEW} checked={choice === NEW} onChange={() => setChosen(NEW)} />
              <span className="fc-inv-chooser__title">A new investigation</span>
            </label>
          </fieldset>
        )}
        {choice === NEW && !editable.loading ? (
          <Field label="Its title" hint="It starts private, so only you can see it.">
            {(control) => (
              <input
                {...control}
                className="fc-input"
                value={title}
                maxLength={LIMITS.title}
                onChange={(event) => setTitle(event.target.value)}
              />
            )}
          </Field>
        ) : null}
        <Field label="A note to go with it (optional)">
          {(control) => (
            <textarea
              {...control}
              className="fc-input"
              rows={2}
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

export interface AddToInvestigationProps {
  /** What is added, without the note the person may write. Built when the button is pressed. */
  item: () => ItemIn;
  /** What it is, for the dialog: "This finding", "This view". */
  what: string;
  size?: ButtonProps["size"];
  variant?: ButtonProps["variant"];
  disabled?: boolean;
}

/**
 * "Add to an investigation": offers the person's investigations they may
 * add to, and a new one. Signed out, it asks them to sign in first, since
 * an investigation belongs to an account.
 */
export function AddToInvestigation({
  item,
  what,
  size = "sm",
  variant = "secondary",
  disabled,
}: AddToInvestigationProps) {
  const signedInFirst = useSignedInFirst();
  const [body, setBody] = useState<ItemIn | null>(null);
  return (
    <>
      <Button
        size={size}
        variant={variant}
        disabled={disabled}
        icon={<NotebookPen size={15} aria-hidden />}
        onClick={() => {
          // The view or line is taken as it is when the button is pressed.
          const next = item();
          void signedInFirst().then((ready) => {
            if (ready) setBody(next);
          });
        }}
      >
        Add to an investigation
      </Button>
      {body ? <Chooser body={body} what={what} onClose={() => setBody(null)} /> : null}
    </>
  );
}
