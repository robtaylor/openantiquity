import { useEffect, useRef, useState } from "react";
import { Button } from "../../ui/Button.js";

interface Props {
  /** What happened, that the work wasn't sent, and that it is still here. */
  words: string;
  /** The button that sends the drawing as it is, against the shape as it is now. */
  sendLabel: string;
  onSend: () => void;
  /** Throw the drawing away and take the shape up as it is now. Asked about first. */
  onStartAgain: () => void;
}

/**
 * Said when the saved shape changed under a change or a suggestion in
 * progress, whether found on sending (409 `shape_changed`) or when the
 * finding came back newer. The drawing stays in hand with its undo, and
 * the map shows the shape as it now is. The person sends what they drew
 * against it, or starts again from it, which asks first: nothing drawn is
 * thrown away without their word.
 */
export function ChangedUnderYou({ words, sendLabel, onSend, onStartAgain }: Props) {
  const [asking, setAsking] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  // The button pressed goes, so focus moves to the first of the ones that take its place.
  const moved = useRef(false);
  // biome-ignore lint/correctness/useExhaustiveDependencies: the buttons swapping is the trigger
  useEffect(() => {
    if (!moved.current) return;
    host.current?.querySelector<HTMLElement>("button")?.focus();
  }, [asking]);
  const toggle = (next: boolean) => () => {
    moved.current = true;
    setAsking(next);
  };

  return (
    <div className="fc-mark__notice" role="alert" ref={host}>
      <p>{words}</p>
      {asking ? (
        <>
          <p>Starting again throws away what you drew. Discard it?</p>
          <div className="fc-mark__notice-actions">
            <Button size="sm" variant="primary" onClick={toggle(false)}>
              Keep my drawing
            </Button>
            <Button size="sm" onClick={onStartAgain}>
              Discard it and start again
            </Button>
          </div>
        </>
      ) : (
        <div className="fc-mark__notice-actions">
          <Button size="sm" variant="primary" onClick={onSend}>
            {sendLabel}
          </Button>
          <Button size="sm" onClick={toggle(true)}>
            Start again from the shape as it is now
          </Button>
        </div>
      )}
    </div>
  );
}
