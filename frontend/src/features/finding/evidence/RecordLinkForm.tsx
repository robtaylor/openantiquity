import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import type { Meta } from "../../../api/meta.js";
import { Button } from "../../../ui/Button.js";
import { ChipGroup } from "../../../ui/Chip.js";
import { Field } from "../../../ui/Field.js";
import { Skeleton } from "../../../ui/Skeleton.js";
import { useDebounced } from "../../../ui/useDebounced.js";
import { fetchSources, fetchSuggestedRecords, searchRecords } from "../api.js";
import { distanceWords, labelOf } from "../describe.js";
import { findingPageKeys } from "../keys.js";
import { type EvidenceIn, RELATIONS, type RecordSummary, type Relation } from "../types.js";

export const RELATION_WORDS: Record<Relation, { label: string; hint: string }> = {
  same_as: { label: "The same thing", hint: "The record is this feature." },
  part_of: {
    label: "Part of it",
    hint: "This feature is one part of what the record describes, or the other way round.",
  },
  related: { label: "Related", hint: "A different site nearby that bears on this one." },
};

/** What the record form holds: which record, how it relates, or a record we only link to. */
export interface RecordLinkValues {
  /** A stored record's id, as text, or "" for none. */
  recordId: string;
  relation: Relation | null;
  q: string;
  /** For a record from a source we don't store: its source, identifier and address (Decision 0007). */
  external: boolean;
  sourceKey: string;
  reference: string;
  url: string;
}

export const NO_RECORD: RecordLinkValues = {
  recordId: "",
  relation: null,
  q: "",
  external: false,
  sourceKey: "",
  reference: "",
  url: "",
};

export type ComposedLink = { ok: true; body: EvidenceIn } | { ok: false; field: null; message: string };

/**
 * The body for linking a record. A stored record goes by its id. A record
 * from a source that may only be linked goes by its identifier and address
 * and nothing else, no title or summary (Decision 0007).
 */
export function composeRecordLink(values: RecordLinkValues): ComposedLink {
  if (!values.relation) return { ok: false, field: null, message: "Say how the record relates to this finding." };
  if (!values.external) {
    const id = Number(values.recordId);
    if (!Number.isInteger(id) || id < 1) return { ok: false, field: null, message: "Choose a record first." };
    return { ok: true, body: { kind: "record_link", stance: "supports", relation: values.relation, record_id: id } };
  }
  const reference = values.reference.trim();
  const url = values.url.trim();
  if (!reference || !url) return { ok: false, field: null, message: "Give the record's identifier and its address." };
  if (!/^https?:\/\//.test(url)) return { ok: false, field: null, message: "The address should start with https://." };
  const body: EvidenceIn = { kind: "record_link", stance: "supports", relation: values.relation, reference, url };
  if (values.sourceKey) body.source_key = values.sourceKey;
  return { ok: true, body };
}

function RecordChoice({
  meta,
  record,
  detail,
  chosen,
  onChoose,
}: {
  meta: Meta;
  record: RecordSummary;
  detail?: string;
  chosen: boolean;
  onChoose: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        className={chosen ? "fc-record-choice fc-record-choice--chosen" : "fc-record-choice"}
        aria-pressed={chosen}
        onClick={onChoose}
      >
        <span className="fc-record-choice__name">{record.name}</span>
        <span className="fc-record-choice__meta">
          {record.source.name}
          {" · "}
          {labelOf(meta.vocab.record_categories, record.category)}
          {detail ? ` · ${detail}` : null}
        </span>
      </button>
    </li>
  );
}

export interface RecordLinkFormProps {
  meta: Meta;
  publicId: string;
  values: RecordLinkValues;
  problem: string | null;
  onChange: (values: RecordLinkValues) => void;
  onSubmit: () => void;
  onCancel: () => void;
}

/**
 * Linking a heritage record. The server's suggestions for this finding come
 * first, each with its source and distance, then a search of the record
 * index, then a record from a source that is only linked. The person says
 * how the record relates: the same thing, part of it, or related.
 */
export function RecordLinkForm({ meta, publicId, values, problem, onChange, onSubmit, onCancel }: RecordLinkFormProps) {
  const suggestions = useQuery({
    queryKey: findingPageKeys.suggestions(publicId),
    queryFn: ({ signal }) => fetchSuggestedRecords(publicId, signal),
    staleTime: 60_000,
  });
  const q = useDebounced(values.q.trim(), 300);
  const search = useQuery({
    queryKey: findingPageKeys.recordSearch(q),
    queryFn: ({ signal }) => searchRecords(q, signal),
    enabled: q.length >= 2,
    staleTime: 60_000,
  });
  const sources = useQuery({
    queryKey: findingPageKeys.sources,
    queryFn: ({ signal }) => fetchSources(signal),
    enabled: values.external,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const linkOnly = (sources.data ?? []).filter((source) => source.access !== "bulk");
  const choose = (record: RecordSummary) => onChange({ ...values, recordId: String(record.id), external: false });
  const set = (change: Partial<RecordLinkValues>) => onChange({ ...values, ...change });

  return (
    <form
      className="fc-evidence-form"
      aria-label="Link a heritage record"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="fc-record-section">
        <h4>Records near it</h4>
        {suggestions.isPending ? (
          <Skeleton lines={2} />
        ) : suggestions.isError ? (
          <p className="fc-finding__hint">The suggestions couldn't be loaded. You can still search below.</p>
        ) : suggestions.data.items.length === 0 ? (
          <p className="fc-finding__hint">
            No records in the index are near it. Search below, or link one from elsewhere.
          </p>
        ) : (
          <ul className="fc-record-list" aria-label="Records near it">
            {suggestions.data.items.map((record) => (
              <RecordChoice
                key={record.id}
                meta={meta}
                record={record}
                detail={distanceWords(record.distance_m)}
                chosen={!values.external && values.recordId === String(record.id)}
                onChoose={() => choose(record)}
              />
            ))}
          </ul>
        )}
      </div>

      <div className="fc-record-section">
        <Field label="Search the record index" hint="By name, type or record number.">
          {(control) => (
            <div className="fc-record-search">
              <Search size={16} aria-hidden />
              <input
                {...control}
                className="fc-input"
                type="search"
                value={values.q}
                maxLength={100}
                onChange={(event) => set({ q: event.target.value })}
              />
            </div>
          )}
        </Field>
        {q.length >= 2 ? (
          search.isPending ? (
            <Skeleton lines={2} />
          ) : search.isError ? (
            <p className="fc-field__error">The search didn't work. {search.error.message}</p>
          ) : search.data.items.length === 0 ? (
            <p className="fc-finding__hint">Nothing in the index matches that.</p>
          ) : (
            <ul className="fc-record-list" aria-label="Search results">
              {search.data.items.map((record) => (
                <RecordChoice
                  key={record.id}
                  meta={meta}
                  record={record}
                  chosen={!values.external && values.recordId === String(record.id)}
                  onChoose={() => choose(record)}
                />
              ))}
            </ul>
          )
        ) : null}
      </div>

      <div className="fc-record-section">
        <Button
          size="sm"
          variant="ghost"
          aria-expanded={values.external}
          onClick={() => set({ external: !values.external })}
        >
          {values.external ? "Choose from the index instead" : "It's a record from somewhere else"}
        </Button>
        {values.external ? (
          <>
            <p className="fc-finding__hint">
              Some records can only be linked, not copied here, so we keep just the record's identifier and address.
            </p>
            {linkOnly.length > 0 ? (
              <Field label="Where it's from (optional)">
                {(control) => (
                  <select
                    {...control}
                    className="fc-input"
                    value={values.sourceKey}
                    onChange={(event) => set({ sourceKey: event.target.value })}
                  >
                    <option value="">Not listed</option>
                    {linkOnly.map((source) => (
                      <option key={source.key} value={source.key}>
                        {source.name}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
            ) : null}
            <Field label="Record identifier" hint="As the record gives it, such as MWI12345.">
              {(control) => (
                <input
                  {...control}
                  className="fc-input"
                  value={values.reference}
                  maxLength={200}
                  onChange={(event) => set({ reference: event.target.value })}
                />
              )}
            </Field>
            <Field label="Record address" hint="The link to the record's own page.">
              {(control) => (
                <input
                  {...control}
                  className="fc-input"
                  type="url"
                  inputMode="url"
                  value={values.url}
                  maxLength={2000}
                  onChange={(event) => set({ url: event.target.value })}
                />
              )}
            </Field>
          </>
        ) : null}
      </div>

      <div className="fc-field">
        <span className="fc-field__label">How does it relate?</span>
        <ChipGroup
          label="How does it relate?"
          value={values.relation}
          onChange={(relation) => set({ relation: relation as Relation })}
          options={RELATIONS.map((id) => ({ id, label: RELATION_WORDS[id].label }))}
        />
        {values.relation ? <p className="fc-field__hint">{RELATION_WORDS[values.relation].hint}</p> : null}
      </div>
      {problem ? (
        <p className="fc-field__error" role="alert">
          {problem}
        </p>
      ) : null}
      <div className="fc-evidence-form__actions">
        <Button onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="primary">
          Link it
        </Button>
      </div>
    </form>
  );
}
