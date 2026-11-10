import { type CSSProperties, useId } from "react";
import "./Slider.css";
import { clamp } from "./math.js";

export interface SliderProps {
  /** The words shown above the track. */
  label: string;
  /**
   * The name read to a screen reader, when the shown label needs its context
   * said too. Three sliders in a list that are all labelled "Opacity" would be
   * "OpenStreetMap opacity" and so on. It must contain the shown label.
   */
  accessibleName?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  /** Turn the number into the text shown beside the label and read aloud. */
  format?: (value: number) => string;
  disabled?: boolean;
}

export function Slider({
  label,
  accessibleName,
  value,
  min,
  max,
  step = 1,
  onChange,
  format,
  disabled = false,
}: SliderProps) {
  const id = useId();
  const text = format ? format(value) : String(value);
  const fill = max > min ? ((value - min) / (max - min)) * 100 : 0;
  return (
    <div className="fc-slider">
      <label className="fc-slider__label" htmlFor={id}>
        {label}
      </label>
      <output className="fc-slider__value" htmlFor={id}>
        {text}
      </output>
      <input
        id={id}
        className="fc-slider__input"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-label={accessibleName}
        aria-valuetext={text}
        style={{ "--slider-fill": `${clamp(fill, 0, 100)}%` } as CSSProperties}
        onChange={(event) => onChange(Number(event.currentTarget.value))}
      />
    </div>
  );
}
