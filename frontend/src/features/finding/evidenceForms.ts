/**
 * One form per kind of evidence, each asking only for what that kind needs.
 *
 * The kinds themselves, their labels and hints come from `/meta`. What each
 * kind's form asks for mirrors what `POST /findings/{id}/evidence` takes for
 * it (`check_evidence_fields` in the backend), because `/meta` doesn't say
 * yet. The server stays the judge: a refusal's message is shown next to the
 * form. A kind this build doesn't know gets a plain form with a title, an
 * address and a note.
 */

import type { ViewState } from "../findings/types.js";
import type { EvidenceIn, EvidenceKindId, Outcome, Stance } from "./types.js";

export type FieldId = "title" | "url" | "reference" | "organisation" | "occurred_on" | "outcome" | "note" | "stance";

export interface FieldSpec {
  id: FieldId;
  label: string;
  hint?: string;
  required?: boolean;
}

export interface FormSpec {
  fields: FieldSpec[];
  /** A LIDAR view records the map as it is now, instead of anything typed. */
  usesView?: boolean;
  /** At least one of these must be filled, with this message when none is. */
  oneOf?: { fields: FieldId[]; message: string };
  /** The form can't be used yet, and this says why. */
  unavailable?: string;
}

const NOTE: FieldSpec = { id: "note", label: "Note (optional)", hint: "What it shows, in a sentence or two." };
const STANCE: FieldSpec = { id: "stance", label: "Does it support the finding?" };

const CITED: Omit<FormSpec, "fields"> = {
  oneOf: { fields: ["title", "url", "reference"], message: "Say which it is: a title, an address or a reference." },
};

/** What a site visit, a survey and a dig each ask for: when, who, and what it found. */
function dated(what: string, reference: boolean): FormSpec {
  const fields: FieldSpec[] = [
    { id: "occurred_on", label: "When", required: true },
    { id: "organisation", label: "Who did it (optional)", hint: "A person, a society or a company." },
    { id: "outcome", label: `What the ${what} found`, required: true },
    { id: "note", label: "What was seen (optional)" },
    { id: "url", label: "Address of the report (optional)" },
  ];
  if (reference) fields.push({ id: "reference", label: "Report reference (optional)" });
  return { fields };
}

const OFFICIAL: FormSpec = {
  fields: [
    {
      id: "reference",
      label: "Record number",
      required: true,
      hint: "As the record gives it, such as MWI12345 or list entry 1008391.",
    },
    { id: "title", label: "Name of the record (optional)" },
    { id: "url", label: "Address of the record (optional)" },
    NOTE,
  ],
};

const SPECS: Partial<Record<EvidenceKindId, FormSpec>> = {
  lidar_view: {
    usesView: true,
    fields: [{ id: "title", label: "What this view shows (optional)" }, NOTE, STANCE],
  },
  aerial: {
    fields: [
      {
        id: "title",
        label: "Source",
        hint: "Who took it and when, such as Historic England, 1976, or Google Earth, June 2018.",
      },
      { id: "url", label: "Address", required: true, hint: "A link to the photo, or to the viewer that shows it." },
      NOTE,
      STANCE,
    ],
  },
  historic_map: {
    ...CITED,
    fields: [
      { id: "title", label: "Which map", hint: "Such as OS 6-inch, Wiltshire sheet XXVIII, 1888." },
      { id: "url", label: "Address (optional)", hint: "A link to the map at this place." },
      { id: "reference", label: "Sheet or reference (optional)" },
      NOTE,
      STANCE,
    ],
  },
  document: {
    ...CITED,
    fields: [
      { id: "title", label: "Title", hint: "The book, article or report, with its author and year." },
      { id: "url", label: "Address (optional)" },
      { id: "reference", label: "Page or reference (optional)" },
      NOTE,
      STANCE,
    ],
  },
  publication: {
    ...CITED,
    fields: [
      { id: "title", label: "Title", hint: "The publication that records it, with its author and year." },
      { id: "url", label: "Address (optional)" },
      { id: "reference", label: "Page or reference (optional)" },
      NOTE,
    ],
  },
  photo: {
    fields: [],
    unavailable: "Photos can't be added yet, because uploading isn't open. A site visit can be logged now.",
  },
  field_visit: dated("visit", false),
  geophysics: dated("survey", true),
  excavation: dated("dig", true),
  her_record: OFFICIAL,
  designation: OFFICIAL,
};

const GENERIC: FormSpec = {
  ...CITED,
  fields: [{ id: "title", label: "Title" }, { id: "url", label: "Address (optional)" }, NOTE, STANCE],
};

export function formSpec(kindId: string): FormSpec {
  return SPECS[kindId as EvidenceKindId] ?? GENERIC;
}

/** Heritage records have a form of their own, with suggestions and a search. */
export function isRecordKind(kindId: string): boolean {
  return kindId === "record_link";
}

/** Before a site visit is logged, the reminder of the rules (DESIGN.md, "Protecting sites"). */
export function needsVisitReminder(kindId: string): boolean {
  return kindId === "field_visit" || kindId === "excavation" || kindId === "geophysics";
}

export type FormValues = Partial<Record<FieldId, string>>;

export type Composed = { ok: true; body: EvidenceIn } | { ok: false; field: FieldId | null; message: string };

/** A site visit's stance follows what it found. */
const OUTCOME_STANCE: Record<Outcome, Stance> = {
  supports: "supports",
  inconclusive: "neutral",
  contradicts: "contradicts",
};

/** Today in the browser's own calendar, as `YYYY-MM-DD`. */
export function today(now: Date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function isWebAddress(text: string): boolean {
  try {
    const url = new URL(text);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

/**
 * The request body for this kind's form, or the first thing missing. Empty
 * fields are left out. `view` is the map as it is now, for a LIDAR view.
 */
export function composeEvidence(
  kindId: string,
  values: FormValues,
  view: ViewState | null,
  now: Date = new Date(),
): Composed {
  const spec = formSpec(kindId);
  if (spec.unavailable) return { ok: false, field: null, message: spec.unavailable };
  const text = (id: FieldId): string | null => {
    const value = values[id]?.trim();
    return value ? value : null;
  };
  for (const field of spec.fields) {
    if (field.required && text(field.id) === null) {
      return { ok: false, field: field.id, message: `${field.label.replace(/ \(optional\)$/, "")} is needed.` };
    }
  }
  const { oneOf } = spec;
  if (oneOf?.fields.every((id) => text(id) === null)) {
    return { ok: false, field: oneOf.fields[0] ?? null, message: oneOf.message };
  }
  const url = text("url");
  if (url !== null && !isWebAddress(url)) {
    return { ok: false, field: "url", message: "The address should start with https://." };
  }
  const date = text("occurred_on");
  if (date !== null && date > today(now))
    return { ok: false, field: "occurred_on", message: "The date can't be in the future." };

  const body: EvidenceIn = { kind: kindId as EvidenceKindId, stance: "supports" };
  const asked = new Set(spec.fields.map((field) => field.id));
  const set = (id: FieldId, apply: (value: string) => void): void => {
    const value = text(id);
    if (asked.has(id) && value !== null) apply(value);
  };
  set("title", (value) => {
    body.title = value;
  });
  set("url", (value) => {
    body.url = value;
  });
  set("reference", (value) => {
    body.reference = value;
  });
  set("organisation", (value) => {
    body.organisation = value;
  });
  set("note", (value) => {
    body.note = value;
  });
  set("occurred_on", (value) => {
    body.occurred_on = value;
  });
  set("outcome", (value) => {
    body.outcome = value as Outcome;
    body.stance = OUTCOME_STANCE[value as Outcome] ?? "supports";
  });
  set("stance", (value) => {
    body.stance = value as Stance;
  });
  if (spec.usesView) {
    if (!view) return { ok: false, field: null, message: "The map isn't ready yet." };
    body.view = view;
  }
  return { ok: true, body };
}
