import { CircleHelp, Eye, EyeOff } from "lucide-react";
import { ANSWERS, type Visible } from "../types.js";
import { ANSWER_WORDS } from "./answer.js";

const ICONS: Record<Visible, typeof Eye> = { yes: Eye, unsure: CircleHelp, no: EyeOff };

export interface AnswerButtonsProps {
  /** The answer chosen so far, if any. */
  value: Visible | null;
  onChoose: (visible: Visible) => void;
  disabled?: boolean;
}

/**
 * The three answers to a second look, as single buttons (docs/UI.md). A
 * chosen one stays pressed, and the others can still be pressed instead
 * until the answer is sent.
 */
export function AnswerButtons({ value, onChoose, disabled = false }: AnswerButtonsProps) {
  return (
    // biome-ignore lint/a11y/useSemanticElements: a fieldset can't lay the buttons out in a row with its legend above
    <div className="fc-answers" role="group" aria-label="Can you see it?">
      {ANSWERS.map((visible) => {
        const Icon = ICONS[visible];
        const pressed = value === visible;
        return (
          <button
            key={visible}
            type="button"
            className={pressed ? "fc-answers__button fc-answers__button--chosen" : "fc-answers__button"}
            aria-pressed={pressed}
            disabled={disabled}
            onClick={() => onChoose(visible)}
          >
            <Icon size={20} aria-hidden />
            {ANSWER_WORDS[visible].button}
          </button>
        );
      })}
    </div>
  );
}
