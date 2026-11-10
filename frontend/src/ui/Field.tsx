import { type ReactNode, useId } from "react";
import "./Field.css";

/** Props to spread onto the control so the label, hint and error are announced with it. */
export interface FieldControlProps {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
}

export interface FieldProps {
  label: string;
  /** One sentence explaining the field or a term in it. */
  hint?: string;
  error?: string;
  children: (control: FieldControlProps) => ReactNode;
}

export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");
  const control: FieldControlProps = { id };
  if (describedBy) control["aria-describedby"] = describedBy;
  if (error) control["aria-invalid"] = true;
  return (
    <div className="fc-field">
      <label className="fc-field__label" htmlFor={id}>
        {label}
      </label>
      {children(control)}
      {hint ? (
        <p className="fc-field__hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="fc-field__error" id={errorId} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
