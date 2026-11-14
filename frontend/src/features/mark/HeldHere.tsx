import { useRef } from "react";
import { Button } from "../../ui/Button.js";
import { focusPanelTitle } from "./TakeOverNotice.js";

interface Choice {
  label: string;
  onClick: () => void;
}

/**
 * Said on a tool's page when the tool holds this finding's unsent change or
 * suggestion and the server no longer lets the person send it: the finding
 * was withdrawn, or they took the marking on or handed it on. What was drawn
 * is never left with no way on. It can be discarded, at the person's word,
 * and where there is one, carried on another way.
 */
export function HeldHere({ words, choices }: { words: string; choices: Choice[] }) {
  const host = useRef<HTMLDivElement>(null);
  return (
    <div className="fc-mark__notice" role="alert" ref={host}>
      <p>{words}</p>
      <div className="fc-mark__notice-actions">
        {choices.map((choice, index) => (
          <Button
            key={choice.label}
            size="sm"
            variant={index === 0 ? "primary" : "secondary"}
            onClick={() => {
              focusPanelTitle(host.current);
              choice.onClick();
            }}
          >
            {choice.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
