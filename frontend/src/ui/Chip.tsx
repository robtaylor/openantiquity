import type { KeyboardEvent, ReactNode } from "react";
import { useRovingFocus } from "./useRovingFocus.js";
import "./Chip.css";

export interface ChipProps {
  selected?: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  children: ReactNode;
  onClick?: () => void;
  /** Chips in a single-choice group are radios. Others are toggle buttons. */
  role?: "radio" | "button";
  tabIndex?: number;
  onKeyDown?: (event: KeyboardEvent<HTMLButtonElement>) => void;
  buttonRef?: (element: HTMLButtonElement | null) => void;
}

export function Chip({
  selected = false,
  disabled = false,
  icon,
  children,
  onClick,
  role = "button",
  tabIndex,
  onKeyDown,
  buttonRef,
}: ChipProps) {
  const state = role === "radio" ? { role: "radio", "aria-checked": selected } : { "aria-pressed": selected };
  return (
    <button
      type="button"
      ref={buttonRef}
      className={selected ? "fc-chip fc-chip--selected" : "fc-chip"}
      disabled={disabled}
      onClick={onClick}
      onKeyDown={onKeyDown}
      tabIndex={tabIndex}
      {...state}
    >
      {icon}
      {children}
    </button>
  );
}

export interface ChipOption {
  id: string;
  label: string;
  icon?: ReactNode;
  disabled?: boolean;
}

interface ChipGroupBase {
  /** Names the group for screen readers. */
  label: string;
  options: ChipOption[];
}

export interface SingleChipGroupProps extends ChipGroupBase {
  multiple?: false;
  value: string | null;
  onChange: (value: string) => void;
}

export interface MultipleChipGroupProps extends ChipGroupBase {
  multiple: true;
  value: string[];
  onChange: (value: string[]) => void;
}

export type ChipGroupProps = SingleChipGroupProps | MultipleChipGroupProps;

/**
 * A row of chips. With `multiple` each chip toggles on its own. Without it
 * the group is a radio group: one choice, and the arrow keys move it.
 */
export function ChipGroup(props: ChipGroupProps) {
  const { label, options } = props;
  const roving = useRovingFocus();

  if (props.multiple) {
    const { value, onChange } = props;
    return (
      // biome-ignore lint/a11y/useSemanticElements: a fieldset cannot lay its legend out inline with the chips
      <div className="fc-chip-group" role="group" aria-label={label}>
        {options.map((option) => {
          const selected = value.includes(option.id);
          return (
            <Chip
              key={option.id}
              selected={selected}
              disabled={option.disabled ?? false}
              icon={option.icon}
              onClick={() => onChange(selected ? value.filter((id) => id !== option.id) : [...value, option.id])}
            >
              {option.label}
            </Chip>
          );
        })}
      </div>
    );
  }

  const { value, onChange } = props;
  const enabled = options.filter((option) => !option.disabled);
  // Roving tabindex: the chosen chip takes focus, or the first when none is chosen.
  const tabStop = enabled.find((option) => option.id === value)?.id ?? enabled[0]?.id;

  function move(from: string, step: 1 | -1): void {
    const index = enabled.findIndex((option) => option.id === from);
    const next = enabled[(index + step + enabled.length) % enabled.length];
    if (!next) return;
    onChange(next.id);
    roving.focus(next.id);
  }

  return (
    <div className="fc-chip-group" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <Chip
          key={option.id}
          role="radio"
          selected={option.id === value}
          disabled={option.disabled ?? false}
          icon={option.icon}
          tabIndex={option.id === tabStop ? 0 : -1}
          onClick={() => onChange(option.id)}
          buttonRef={roving.refFor(option.id)}
          onKeyDown={(event) => {
            if (event.key === "ArrowRight" || event.key === "ArrowDown") {
              event.preventDefault();
              move(option.id, 1);
            } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
              event.preventDefault();
              move(option.id, -1);
            }
          }}
        >
          {option.label}
        </Chip>
      ))}
    </div>
  );
}
