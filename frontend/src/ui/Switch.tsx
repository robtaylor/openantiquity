import { useId } from "react";
import "./Switch.css";

export interface SwitchProps {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

/** An on/off control for settings that take effect at once. */
export function Switch({ label, hint, checked, onChange, disabled = false }: SwitchProps) {
  const id = useId();
  const labelId = `${id}-label`;
  const hintId = `${id}-hint`;
  return (
    // The whole row is the click target, but only the first line is the name:
    // the hint is the description, and must not be read out twice.
    <label className={disabled ? "fc-switch fc-switch--disabled" : "fc-switch"} htmlFor={id}>
      <span className="fc-switch__text">
        <span className="fc-switch__label" id={labelId}>
          {label}
        </span>
        {hint ? (
          <span className="fc-switch__hint" id={hintId}>
            {hint}
          </span>
        ) : null}
      </span>
      <input
        id={id}
        className="fc-switch__input"
        type="checkbox"
        role="switch"
        aria-labelledby={labelId}
        aria-checked={checked}
        checked={checked}
        disabled={disabled}
        aria-describedby={hint ? hintId : undefined}
        onChange={(event) => onChange(event.currentTarget.checked)}
      />
    </label>
  );
}
