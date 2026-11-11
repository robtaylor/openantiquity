import { TriangleAlert } from "lucide-react";
import { useShallow } from "zustand/react/shallow";
import type { Meta } from "../../../api/meta.js";
import { useMapStore } from "../../../map/store.js";
import { Button } from "../../../ui/Button.js";
import { ChipGroup } from "../../../ui/Chip.js";
import { Field } from "../../../ui/Field.js";
import { viewStateFrom } from "../../mark/describe.js";
import { outcomeWords, stanceWords } from "../describe.js";
import {
  type FieldId,
  type FieldSpec,
  type FormValues,
  formSpec,
  needsVisitReminder,
  today,
} from "../evidenceForms.js";
import { OUTCOMES, STANCES } from "../types.js";

/**
 * The rules for a site visit, from `/meta` for the nation the finding is in
 * (DESIGN.md, "Protecting sites"), shown before a visit, survey or dig is logged.
 */
export function VisitReminder({
  meta,
  nation,
  youngContributor,
}: {
  meta: Meta;
  nation: string | null;
  youngContributor: boolean;
}) {
  const lines =
    (nation ? meta.notices.field_visit[nation] : undefined) ?? Object.values(meta.notices.field_visit)[0] ?? [];
  return (
    <div className="fc-reminder" role="note">
      <TriangleAlert size={18} aria-hidden />
      <div>
        <strong>Before you go</strong>
        <ul>
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
          {youngContributor ? <li>{meta.notices.field_visit_16_17}</li> : null}
        </ul>
      </div>
    </div>
  );
}

function TextField({
  spec,
  value,
  error,
  onChange,
}: {
  spec: FieldSpec;
  value: string;
  error: string | undefined;
  onChange: (value: string) => void;
}) {
  const long = spec.id === "note";
  return (
    <Field label={spec.label} hint={spec.hint} error={error}>
      {(control) =>
        long ? (
          <textarea
            {...control}
            className="fc-input"
            rows={3}
            maxLength={5000}
            value={value}
            onChange={(event) => onChange(event.target.value)}
          />
        ) : (
          <input
            {...control}
            className="fc-input"
            type={spec.id === "url" ? "url" : spec.id === "occurred_on" ? "date" : "text"}
            inputMode={spec.id === "url" ? "url" : undefined}
            max={spec.id === "occurred_on" ? today() : undefined}
            maxLength={spec.id === "url" ? 2000 : 240}
            required={spec.required}
            value={value}
            onChange={(event) => onChange(event.target.value)}
          />
        )
      }
    </Field>
  );
}

export interface EvidenceFormProps {
  meta: Meta;
  kindId: string;
  nation: string | null;
  youngContributor: boolean;
  values: FormValues;
  problem: { field: FieldId | null; message: string } | null;
  onChange: (values: FormValues) => void;
  onSubmit: () => void;
  onCancel: () => void;
}

/** The form for one kind of evidence, asking only for what that kind needs (`formSpec`). */
export function EvidenceForm({
  meta,
  kindId,
  nation,
  youngContributor,
  values,
  problem,
  onChange,
  onSubmit,
  onCancel,
}: EvidenceFormProps) {
  const kind = meta.vocab.evidence_kinds.find((entry) => entry.id === kindId);
  const spec = formSpec(kindId);
  // Shallow, because the view is a new object on every read.
  const mapView = useMapStore(useShallow((state) => (spec.usesView ? viewStateFrom(state) : null)));
  const set = (id: FieldId, value: string) => onChange({ ...values, [id]: value });
  const errorFor = (id: FieldId) => (problem?.field === id ? problem.message : undefined);
  const layerTitle = mapView?.layer
    ? (meta.layers.views.find((view) => view.id === mapView.layer)?.title ?? mapView.layer)
    : null;

  return (
    <form
      className="fc-evidence-form"
      aria-label={kind ? `Add ${kind.label.toLowerCase()}` : "Add evidence"}
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      {kind ? <p className="fc-finding__hint">{kind.hint}</p> : null}
      {needsVisitReminder(kindId) ? (
        <VisitReminder meta={meta} nation={nation} youngContributor={youngContributor} />
      ) : null}
      {spec.unavailable ? <p className="fc-evidence-form__unavailable">{spec.unavailable}</p> : null}
      {spec.usesView && mapView ? (
        <p className="fc-evidence-form__view">
          This records the map as it is now: {layerTitle ?? "the current layer"}, zoom {Math.round(mapView.zoom ?? 0)},
          light from {Math.round(mapView.sun_azimuth ?? 0)}°. Set it up first, then add it.
        </p>
      ) : null}
      {spec.fields.map((field) => {
        if (field.id === "stance" || field.id === "outcome") {
          const options =
            field.id === "stance"
              ? STANCES.map((id) => ({ id, label: stanceWords(id) }))
              : OUTCOMES.map((id) => ({ id, label: outcomeWords(id) }));
          const fallback = field.id === "stance" ? "supports" : null;
          return (
            <div className="fc-field" key={field.id}>
              <span className="fc-field__label" id={`fc-evidence-${field.id}`}>
                {field.label}
              </span>
              <ChipGroup
                label={field.label}
                value={values[field.id] ?? fallback}
                onChange={(value) => set(field.id, value)}
                options={options}
              />
              {errorFor(field.id) ? (
                <p className="fc-field__error" role="alert">
                  {errorFor(field.id)}
                </p>
              ) : null}
            </div>
          );
        }
        return (
          <TextField
            key={field.id}
            spec={field}
            value={values[field.id] ?? ""}
            error={errorFor(field.id)}
            onChange={(value) => set(field.id, value)}
          />
        );
      })}
      {problem && problem.field === null ? (
        <p className="fc-field__error" role="alert">
          {problem.message}
        </p>
      ) : null}
      <div className="fc-evidence-form__actions">
        <Button onClick={onCancel}>Cancel</Button>
        {spec.unavailable ? null : (
          <Button type="submit" variant="primary">
            Add it
          </Button>
        )}
      </div>
    </form>
  );
}
