/**
 * What the finding's page says about changes to its shape (Decision 0029):
 * how much has been added since the last second look, from the ground
 * (`location.shape.added_since_looked_m`, framed by `added_view`), and each
 * change as a timeline entry (`location.shape.changes`), naming who
 * suggested it when the keeper accepted someone's suggestion. Someone who sees
 * only the square gets `changed` entries alone: that the shape changed, and
 * when.
 */

import { MapPinned } from "lucide-react";
import type { components } from "../../api/schema.js";
import { useMapStore } from "../../map/store.js";
import { Button } from "../../ui/Button.js";
import { lengthWords } from "../mark/DrawingTool.js";
import { formatDate } from "./describe.js";
import type { FindingDetail } from "./types.js";

export type ShapeChange = components["schemas"]["ShapeChangeOut"];
type AddedView = components["schemas"]["AddedView"];

/** One change of shape, in a few words. */
export function shapeChangeWords(change: ShapeChange): string {
  switch (change.kind) {
    case "drawn":
      return "The shape was drawn";
    case "extended":
      return change.added_length_m ? `Drawn further by ${lengthWords(change.added_length_m)}` : "Drawn further";
    case "closed":
      return "Closed into a shape";
    case "opened":
      return "Opened out into a line";
    case "removed":
      return "The shape was taken away, leaving a spot";
    default:
      return "The shape was changed";
  }
}

/** Move the map to frame a part of the shape. */
export function showView(view: AddedView): void {
  useMapStore.getState().requestCamera({ lng: view.lon, lat: view.lat, zoom: view.zoom });
}

/** "4.2 km added since the last second look", with a button that opens the map on the new part. */
export function AddedSince({ finding }: { finding: FindingDetail }) {
  const { added_since_looked_m: added, added_view: view } = finding.location.shape;
  if (!added || added <= 0) return null;
  return (
    <section className="fc-finding__section" aria-labelledby="fc-added-title">
      <h3 id="fc-added-title" className="fc-visually-hidden">
        Added since the last second look
      </h3>
      <p>
        <strong>{lengthWords(added)}</strong> added since the last second look. A second look at the new part would
        help.
      </p>
      {view ? (
        <Button size="sm" icon={<MapPinned size={15} aria-hidden />} onClick={() => showView(view)}>
          Show the new part on the map
        </Button>
      ) : null}
    </section>
  );
}

/** A change of shape as an entry in the finding's timeline. */
export function ShapeChangeEntry({ change }: { change: ShapeChange }) {
  const view = change.kind === "extended" ? change.added_view : null;
  const day = formatDate(change.on);
  return (
    <li className="fc-timeline__entry">
      <span className="fc-timeline__dot" aria-hidden="true" />
      <p className="fc-timeline__when">
        <time dateTime={change.on}>{day}</time>
      </p>
      <p className="fc-timeline__what">
        <strong>{shapeChangeWords(change)}</strong>
      </p>
      {change.suggested_by ? <p className="fc-timeline__who">Suggested by {change.suggested_by.display_name}</p> : null}
      {view ? (
        <Button size="sm" variant="ghost" icon={<MapPinned size={15} aria-hidden />} onClick={() => showView(view)}>
          Show what was added
          <span className="fc-visually-hidden"> on {day}</span>
        </Button>
      ) : null}
    </li>
  );
}
