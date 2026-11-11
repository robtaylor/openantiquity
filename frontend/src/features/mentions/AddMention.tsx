import { Search } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { Field } from "../../ui/Field.js";
import { useFocusLater } from "../../ui/useFocusLater.js";
import { previewMention } from "./api.js";
import {
  type MentionFailure,
  mentionFailure,
  NOTE_MAX,
  parseStart,
  previewProblem,
  startWords,
  URL_MAX,
} from "./describe.js";
import { MentionLink, MentionThumbnail } from "./MentionCard.js";
import type { MentionIn, MentionPreview } from "./types.js";

/** What looking the address up gave: what was found, or why nothing could be. */
type Lookup =
  | { state: "idle" }
  | { state: "looking"; url: string }
  | { state: "found"; url: string; preview: MentionPreview }
  /** The lookup itself failed, for a reason that doesn't stop the address being saved. */
  | { state: "unknown"; url: string; reason: string };

export interface AddMentionProps {
  meta: Meta;
  /**
   * Save the mention. Resolves null once it is saved, or with why it wasn't,
   * so the form stays open with what was typed.
   */
  onSave: (body: MentionIn, preview: MentionPreview | null) => Promise<MentionFailure | null>;
  onCancel: () => void;
}

/**
 * Adding a mention: paste an address, see what it is before saving, and
 * optionally say what kind it is, where in it the finding comes up, and a
 * note. An address whose page can't be fetched can still be saved alone.
 */
export function AddMention({ meta, onSave, onCancel }: AddMentionProps) {
  const headingId = useId();
  const [address, setAddress] = useState("");
  const [lookup, setLookup] = useState<Lookup>({ state: "idle" });
  const [kind, setKind] = useState<string | null>(null);
  const [start, setStart] = useState("");
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<MentionFailure | null>(null);
  const [saving, setSaving] = useState(false);
  const details = useRef<HTMLDivElement>(null);
  const addressInput = useRef<HTMLInputElement>(null);
  const focusLater = useFocusLater();

  // Opened from its button, the form starts at the address.
  useEffect(() => addressInput.current?.focus(), []);

  const looked = lookup.state === "found" || lookup.state === "unknown";
  const preview = lookup.state === "found" ? lookup.preview : null;

  async function lookUp(event: FormEvent): Promise<void> {
    event.preventDefault();
    const url = address.trim();
    if (url === "") {
      setProblem({ field: "url", message: "Paste the address first." });
      return;
    }
    setProblem(null);
    setLookup({ state: "looking", url });
    try {
      const found = await previewMention(url);
      setLookup({ state: "found", url, preview: found });
      setKind(found.kind);
      setStart(found.start_seconds ? startWords(found.start_seconds) : "");
    } catch (error) {
      const failure = mentionFailure(error);
      if (failure.field === "url") {
        // An address the server won't take can't be saved either.
        setLookup({ state: "idle" });
        setProblem(failure);
        return;
      }
      setLookup({ state: "unknown", url, reason: failure.message });
    }
    // What was found is read next, from the render that shows it, so nothing typed after it goes astray.
    focusLater(() => details.current, { scroll: true });
  }

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!looked || saving) return;
    const seconds = parseStart(start);
    if (Number.isNaN(seconds)) {
      setProblem({ field: "start", message: "Write the time as minutes and seconds, such as 12:34." });
      return;
    }
    const body: MentionIn = { url: lookup.url };
    if (kind !== null) body.kind = kind as MentionIn["kind"];
    if (seconds !== null) body.start_seconds = seconds;
    if (note.trim()) body.note = note.trim();
    setProblem(null);
    setSaving(true);
    const failure = await onSave(body, preview);
    setSaving(false);
    if (failure) setProblem(failure);
  }

  const fieldError = (field: MentionFailure["field"]) => (problem?.field === field ? problem.message : undefined);
  const found = preview ? previewProblem(preview) : null;

  return (
    <div className="fc-mention-add">
      <h4 id={headingId}>Add a mention</h4>
      <form
        className="fc-mention-add__address"
        aria-label="Look up an address"
        onSubmit={(event) => void lookUp(event)}
      >
        <Field label="Address" hint="A link to a video, article, podcast or paper, or a DOI." error={fieldError("url")}>
          {(control) => (
            <input
              {...control}
              ref={addressInput}
              className="fc-input"
              type="text"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              maxLength={URL_MAX}
              placeholder="https://"
              value={address}
              onChange={(event) => {
                setAddress(event.target.value);
                // A different address needs looking up again, and what the last one found no longer applies.
                if (lookup.state !== "idle") {
                  setLookup({ state: "idle" });
                  setKind(null);
                  setStart("");
                }
                if (problem?.field === "url") setProblem(null);
              }}
            />
          )}
        </Field>
        <Button type="submit" icon={<Search size={15} aria-hidden />} disabled={lookup.state === "looking"}>
          {lookup.state === "looking" ? "Looking…" : "Look it up"}
        </Button>
      </form>

      <div ref={details} tabIndex={-1} aria-live="polite" className="fc-mention-add__result">
        {lookup.state === "found" ? (
          <div className="fc-mention-add__found">
            <MentionThumbnail kind={lookup.preview.kind} src={lookup.preview.thumbnail_url} />
            <div className="fc-mention__body">
              <span className="fc-visually-hidden">Found: </span>
              <MentionLink mention={lookup.preview} />
              {lookup.preview.author_name ? <p className="fc-mention__meta">{lookup.preview.author_name}</p> : null}
              {found ? <p className="fc-mention-add__problem">{found}</p> : null}
            </div>
          </div>
        ) : lookup.state === "unknown" ? (
          <p className="fc-mention-add__problem">
            Its details couldn't be looked up. {lookup.reason} You can still save it with its address alone.
          </p>
        ) : null}
      </div>

      {looked ? (
        <form className="fc-evidence-form" aria-labelledby={headingId} onSubmit={(event) => void save(event)}>
          <div className="fc-field">
            <span className="fc-field__label" id={`${headingId}-kind`}>
              What kind is it?
            </span>
            <ChipGroup
              label="What kind is it?"
              value={kind}
              onChange={setKind}
              options={meta.vocab.mention_kinds.map((entry) => ({ id: entry.id, label: entry.label }))}
            />
          </div>
          <Field
            label="Where it comes up (optional)"
            hint="For a video or podcast, the time the finding is talked about, such as 12:34."
            error={fieldError("start")}
          >
            {(control) => (
              <input
                {...control}
                className="fc-input fc-mono"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                maxLength={8}
                value={start}
                onChange={(event) => setStart(event.target.value)}
              />
            )}
          </Field>
          <Field
            label="Note (optional)"
            hint="What it says about the finding, in a sentence or two."
            error={fieldError("note")}
          >
            {(control) => (
              <textarea
                {...control}
                className="fc-input"
                rows={2}
                maxLength={NOTE_MAX}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            )}
          </Field>
          {problem && problem.field === null ? (
            <p className="fc-mention-add__error" role="alert">
              {problem.message}
            </p>
          ) : null}
          <div className="fc-mention-add__actions">
            <Button variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
            {/* Kept focusable while saving, so focus stays here until the saved mention takes it. */}
            <Button type="submit" variant="primary" aria-disabled={saving || undefined}>
              {saving ? "Saving…" : "Save the mention"}
            </Button>
          </div>
        </form>
      ) : (
        <div className="fc-mention-add__actions">
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}
