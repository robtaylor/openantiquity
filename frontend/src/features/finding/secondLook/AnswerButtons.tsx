import { CircleHelp, Eye, EyeOff } from "lucide-react";
import { ANSWERS, type Visible } from "../types.js";
import { ANSWER_WORDS } from "./answer.js";

const ICONS: Record<Visible, typeof Eye> = { yes: Eye, unsure: CircleHelp, no: EyeOff };

/** The key that gives each answer where the answers take keys: 1, 2 and 3, in the order shown. */
export const ANSWER_KEYS = { yes: "1", unsure: "2", no: "3" } as const satisfies Record<Visible, string>;

/** The answer a key gives, or null for any other key. */
export function answerForKey(key: string): Visible | null {
  return ANSWERS.find((visible) => ANSWER_KEYS[visible] === key) ?? null;
}

export interface AnswerButtonsProps {
  /** The answer chosen so far, if any. */
  value: Visible | null;
  onChoose: (visible: Visible) => void;
  disabled?: boolean;
  /** Show each answer's key (`ANSWER_KEYS`), for a page that listens for them. */
  keyHints?: boolean;
}

/**
 * The three answers to a second look, as single buttons (docs/UI.md). A
 * chosen one stays pressed, and the others can still be pressed instead
 * until the answer is sent.
 */
export function AnswerButtons({ value, onChoose, disabled = false, keyHints = false }: AnswerButtonsProps) {
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
            aria-keyshortcuts={keyHints ? ANSWER_KEYS[visible] : undefined}
            disabled={disabled}
            onClick={() => onChoose(visible)}
          >
            <Icon size={20} aria-hidden />
            {ANSWER_WORDS[visible].button}
            {keyHints ? (
              <span className="fc-answers__key" aria-hidden="true">
                {ANSWER_KEYS[visible]}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
