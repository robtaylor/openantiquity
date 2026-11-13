import { useRef } from "react";
import { Button } from "../../ui/Button.js";

/** Put focus on the title of the panel `from` is in. A button that goes when it is pressed would leave focus nowhere. */
export function focusPanelTitle(from: Element | null): void {
  from?.closest(".fc-panel")?.querySelector<HTMLElement>(".fc-panel__title")?.focus();
}

interface Choice {
  label: string;
  onClick: () => void;
}

/**
 * The question a drawing panel asks before it takes the tool over from
 * something unsaved: what would be lost, the way back to it, and the way on.
 * It is an alert, since it is put in after the panel's title has been read
 * and nothing goes on until it is answered.
 */
export function TakeOverNotice({ words, back, on }: { words: string; back: Choice; on: Choice }) {
  const host = useRef<HTMLDivElement>(null);
  const press = (choice: Choice) => () => {
    focusPanelTitle(host.current);
    choice.onClick();
  };
  return (
    <div className="fc-mark__notice" role="alert" ref={host}>
      <p>{words}</p>
      <div className="fc-mark__notice-actions">
        <Button size="sm" variant="primary" onClick={press(back)}>
          {back.label}
        </Button>
        <Button size="sm" onClick={press(on)}>
          {on.label}
        </Button>
      </div>
    </div>
  );
}
