import { useQueryClient } from "@tanstack/react-query";
import { Crop, Download, FileText, Globe, Lock, MapPinned, Trash2, Link2 as Unlisted, X } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useNavigate } from "react-router";
import { useMapStore, useViewAreaStore } from "../../map/store.js";
import { uncoveredBounds, useMapCover } from "../../map/visibleArea.js";
import { Button } from "../../ui/Button.js";
import { Dialog } from "../../ui/Dialog.js";
import { toast } from "../../ui/toastStore.js";
import { toastFailure } from "../finding/feedback.js";
import { framingFor } from "../layers/profile/line.js";
import {
  deleteInvestigation,
  exportUrl,
  INVESTIGATIONS_PATH,
  type InvestigationDetail,
  type Member,
  type Visibility,
} from "./api.js";
import { areaShape, boundsOf, polygonOf } from "./area.js";
import { type Powers, VISIBILITY, visibilityChoices } from "./describe.js";
import { investigationKeys } from "./keys.js";
import type { Notebook } from "./useInvestigation.js";

const VISIBILITY_ICON: Record<Visibility, ReactNode> = {
  private: <Lock size={15} aria-hidden />,
  unlisted: <Unlisted size={15} aria-hidden />,
  public: <Globe size={15} aria-hidden />,
};

/** What changing to each visibility means, said before it is done. */
const CHANGE_SAYS: Record<Visibility, string> = {
  public:
    "Publishing it lists it for everyone, signed in or not, with all its notes and items, and tells the activity feed. You can make it unlisted or private again later.",
  unlisted:
    "Anyone with its link will be able to read it, and moderators can find it, but it won't be listed. Then you can invite people.",
  private: "Only you will be able to find it.",
};

const CHANGE_BUTTON: Record<Visibility, string> = {
  public: "Publish it",
  unlisted: "Make it unlisted",
  private: "Make it private",
};

/** Show the whole area in the part of the map nothing covers. */
export function showArea(detail: InvestigationDetail): void {
  const shape = areaShape(detail.area);
  if (!shape) return;
  const [west, south, east, north] = boundsOf(shape);
  const framing = framingFor(
    [
      [west, south],
      [east, north],
    ],
    window.innerWidth,
    window.innerHeight,
    useMapCover.getState().cover,
  );
  if (framing) useMapStore.getState().requestCamera({ ...framing, bearing: 0, pitch: 0 });
}

function AreaSection({
  detail,
  powers,
  notebook,
}: {
  detail: InvestigationDetail;
  powers: Powers;
  notebook: Notebook;
}) {
  const hasArea = areaShape(detail.area) !== null;
  const bounds = useViewAreaStore((state) => state.bounds);

  function takeView(): void {
    if (!bounds) return;
    const size = { width: window.innerWidth, height: window.innerHeight };
    const area = polygonOf(uncoveredBounds(bounds, size, useMapCover.getState().cover));
    void notebook.update({ area }, "The area couldn't be saved.").then((saved) => {
      if (saved) toast("Its area is what the map shows now.", { kind: "success" });
    });
  }

  if (!hasArea && !powers.edit) return null;
  return (
    <section className="fc-inv-section" aria-labelledby="inv-area">
      <h3 id="inv-area">Its area</h3>
      <p className="fc-field__hint">
        {hasArea
          ? "Drawn on the map as a dashed outline. A public investigation is found by its area."
          : "The part of the map it's about. A public investigation is found by its area, so give it one before you publish."}
      </p>
      <div className="fc-inv-tools">
        {hasArea ? (
          <Button size="sm" icon={<MapPinned size={15} aria-hidden />} onClick={() => showArea(detail)}>
            Show its area
          </Button>
        ) : null}
        {powers.edit ? (
          <Button size="sm" icon={<Crop size={15} aria-hidden />} disabled={!bounds} onClick={takeView}>
            {hasArea ? "Use the map's view instead" : "Use the map's view as its area"}
          </Button>
        ) : null}
        {powers.edit && hasArea ? (
          <Button
            size="sm"
            variant="ghost"
            icon={<X size={15} aria-hidden />}
            onClick={() => void notebook.update({ area: null }, "The area couldn't be taken off.")}
          >
            Take the area off
          </Button>
        ) : null}
      </div>
    </section>
  );
}

function VisibilitySection({
  detail,
  members,
  notebook,
}: {
  detail: InvestigationDetail;
  members: readonly Member[];
  notebook: Notebook;
}) {
  const [asking, setAsking] = useState<Visibility | null>(null);
  const choices = visibilityChoices(detail, members);
  const privateBlocked = detail.visibility !== "private" && !choices.includes("private");

  async function change(visibility: Visibility): Promise<void> {
    setAsking(null);
    const saved = await notebook.update({ visibility }, "Who can see it couldn't be changed.");
    if (saved) toast(`It's ${VISIBILITY[visibility].label.toLowerCase()} now. ${VISIBILITY[visibility].says}`);
  }

  return (
    <section className="fc-inv-section" aria-labelledby="inv-visibility">
      <h3 id="inv-visibility">Who can see it</h3>
      <p className="fc-inv-visibility">
        {VISIBILITY_ICON[detail.visibility]}
        <strong>{VISIBILITY[detail.visibility].label}.</strong> {VISIBILITY[detail.visibility].says}
      </p>
      <div className="fc-inv-tools">
        {choices.map((visibility) => (
          <Button
            key={visibility}
            size="sm"
            variant={visibility === "public" ? "primary" : "secondary"}
            icon={VISIBILITY_ICON[visibility]}
            onClick={() => setAsking(visibility)}
          >
            {CHANGE_BUTTON[visibility]}
          </Button>
        ))}
      </div>
      {privateBlocked ? (
        <p className="fc-field__hint">
          It can be made private again once it has no other members and no invitations waiting.
        </p>
      ) : null}
      <Dialog
        open={asking !== null}
        onClose={() => setAsking(null)}
        title={asking === "public" ? "Publish this investigation?" : `${asking ? CHANGE_BUTTON[asking] : ""}?`}
        actions={
          <>
            <Button onClick={() => setAsking(null)}>Not now</Button>
            <Button variant="primary" onClick={() => asking && void change(asking)}>
              {asking ? CHANGE_BUTTON[asking] : ""}
            </Button>
          </>
        }
      >
        <p>{asking ? CHANGE_SAYS[asking] : null}</p>
      </Dialog>
    </section>
  );
}

function Downloads({ detail }: { detail: InvestigationDetail }) {
  return (
    <section className="fc-inv-section" aria-labelledby="inv-downloads">
      <h3 id="inv-downloads">Download</h3>
      <div className="fc-inv-tools">
        <a
          className="fc-button fc-button--secondary fc-button--sm"
          href={exportUrl(detail.public_id, "geojson")}
          download
        >
          <Download size={15} aria-hidden />
          GeoJSON
        </a>
        <a className="fc-button fc-button--secondary fc-button--sm" href={exportUrl(detail.public_id, "csv")} download>
          <Download size={15} aria-hidden />
          Spreadsheet (CSV)
        </a>
        <a
          className="fc-button fc-button--secondary fc-button--sm"
          href={exportUrl(detail.public_id, "html")}
          target="_blank"
          rel="noopener noreferrer"
        >
          <FileText size={15} aria-hidden />
          Printable report
          <span className="fc-visually-hidden"> (opens in a new tab)</span>
        </a>
      </div>
      <p className="fc-field__hint">
        The spreadsheet uses the field names Historic Environment Records use. A protected place downloads as its
        one-kilometre square unless you can see it exactly, and every record carries its licence.
      </p>
    </section>
  );
}

function DeleteSection({ detail }: { detail: InvestigationDetail }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [asking, setAsking] = useState(false);

  async function remove(): Promise<void> {
    setAsking(false);
    try {
      await deleteInvestigation(detail.public_id);
      toast(`“${detail.title}” is deleted.`);
      client.removeQueries({ queryKey: investigationKeys.detail(detail.public_id) });
      void client.invalidateQueries({ queryKey: investigationKeys.lists });
      navigate(INVESTIGATIONS_PATH);
    } catch (error) {
      toastFailure("It couldn't be deleted.", error);
    }
  }

  return (
    <section className="fc-inv-section" aria-labelledby="inv-delete">
      <h3 id="inv-delete">Delete it</h3>
      <Button size="sm" variant="danger" icon={<Trash2 size={15} aria-hidden />} onClick={() => setAsking(true)}>
        Delete this investigation
      </Button>
      <Dialog
        open={asking}
        onClose={() => setAsking(false)}
        title="Delete this investigation?"
        actions={
          <>
            <Button onClick={() => setAsking(false)}>Keep it</Button>
            <Button variant="danger" onClick={() => void remove()}>
              Delete it
            </Button>
          </>
        }
      >
        <p>
          Its notes, its items and its list of members go with it, for everyone, and it can't be undone. The findings
          and records in it stay where they are.
        </p>
      </Dialog>
    </section>
  );
}

/** The parts of the page about the investigation as a whole: its area, who can see it, downloads, deleting it. */
export function Settings({
  detail,
  members,
  powers,
  notebook,
}: {
  detail: InvestigationDetail;
  members: readonly Member[];
  powers: Powers;
  notebook: Notebook;
}) {
  return (
    <>
      <AreaSection detail={detail} powers={powers} notebook={notebook} />
      {powers.own ? <VisibilitySection detail={detail} members={members} notebook={notebook} /> : null}
      <Downloads detail={detail} />
      {powers.own ? <DeleteSection detail={detail} /> : null}
    </>
  );
}
