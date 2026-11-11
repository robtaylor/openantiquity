import { useEffect, useRef } from "react";
import { usePanelEnvironment } from "../../shell/panelContext.js";
import { panIntoView, whenStageSettled } from "../mapView.js";

/**
 * Keep the place a second look asks about in sight while the person answers
 * (docs/UI.md, "Behaviour"). On a phone, a sheet pulled up fully covers the
 * map, so each time `step` changes to a new non-null value the sheet comes
 * down to half-way, and once it has settled the map pans, if it must, so
 * the place is on the part nothing covers. A desktop panel never covers it
 * more than it did when the map moved there, so only the pan applies.
 *
 * `step` names where the person is, such as the card and whether its answer
 * is in, so moving between the answer and the detail brings the place back
 * once, and the person can still pull the sheet up to read.
 */
export function useAnswerInSight(point: [number, number] | null, step: string | null): void {
  const environment = usePanelEnvironment();
  const { isPhone, stop, setStop } = environment;
  const latest = useRef({ point, isPhone, stop, setStop });
  latest.current = { point, isPhone, stop, setStop };

  useEffect(() => {
    if (step === null) return;
    const now = latest.current;
    if (now.point === null) return;
    if (now.isPhone && now.stop === "full") now.setStop("half");
    const at = now.point;
    return whenStageSettled(() => panIntoView(at));
  }, [step]);
}
