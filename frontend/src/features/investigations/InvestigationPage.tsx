import { EyeOff, NotebookText, Pencil, Unplug } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { useViewAreaStore } from "../../map/store.js";
import { Button } from "../../ui/Button.js";
import { Dialog } from "../../ui/Dialog.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Field } from "../../ui/Field.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { useSession } from "../account/session.js";
import { whenStageSettled } from "../finding/mapView.js";
import { useDocumentTitle } from "../placeholders.js";
import { ReportButton } from "../reports/ReportButton.js";
import { firstArrival } from "../shell/arrival.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { AddItems } from "./AddItems.js";
import {
  INVESTIGATIONS_PATH,
  type InvestigationDetail,
  type InvestigationUpdate,
  investigationPath,
  LIMITS,
} from "./api.js";
import { areaShape, boundsOf, useInvestigationArea } from "./area.js";
import { dateText, GENERALISED_NOTICE, itemCountText, MARKDOWN_HINT, powersOf, VISIBILITY } from "./describe.js";
import { Items } from "./Items.js";
import { Markdown } from "./Markdown.js";
import { InvitationBanner, People } from "./People.js";
import { Settings, showArea } from "./Settings.js";
import { isNotFound, type Notebook, useInvestigation, useItems, useMembers, useNotebook } from "./useInvestigation.js";
import { useLiveInvestigations } from "./useLiveInvestigations.js";
import "./investigations.css";

function EditDialog({
  detail,
  onClose,
  notebook,
}: {
  detail: InvestigationDetail;
  onClose: () => void;
  notebook: Notebook;
}) {
  const [title, setTitle] = useState(detail.title);
  const [summary, setSummary] = useState(detail.summary ?? "");
  const [notes, setNotes] = useState(detail.notes ?? "");
  const [problem, setProblem] = useState<string | null>(null);

  function save(): void {
    if (!title.trim()) {
      setProblem("It needs a title.");
      return;
    }
    const changes: InvestigationUpdate = {};
    if (title.trim() !== detail.title) changes.title = title.trim();
    if (summary.trim() !== (detail.summary ?? "")) changes.summary = summary.trim() || null;
    if (notes.trim() !== (detail.notes ?? "")) changes.notes = notes.trim() || null;
    if (Object.keys(changes).length > 0) void notebook.update(changes, "Your changes couldn't be saved.");
    onClose();
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title="Edit the investigation"
      actions={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={save}>
            Save changes
          </Button>
        </>
      }
    >
      <div className="fc-dialog-form">
        <Field label="Title" error={problem ?? undefined}>
          {(control) => (
            <input
              {...control}
              className="fc-input"
              value={title}
              maxLength={LIMITS.title}
              onChange={(event) => setTitle(event.target.value)}
            />
          )}
        </Field>
        <Field label="Summary (optional)" hint="A sentence or two on what it's about, shown in the list.">
          {(control) => (
            <textarea
              {...control}
              className="fc-input"
              rows={2}
              maxLength={LIMITS.summary}
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
            />
          )}
        </Field>
        <Field label="Notes (optional)" hint={MARKDOWN_HINT}>
          {(control) => (
            <textarea
              {...control}
              className="fc-input fc-inv-notes-input"
              rows={10}
              maxLength={LIMITS.notes}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          )}
        </Field>
      </div>
    </Dialog>
  );
}

/** About as many characters as the phone's sheet header shows on one line. A longer title is shown in full below it. */
const LONG_TITLE = 28;

function NotebookBody({ meta, detail }: { meta: Meta; detail: InvestigationDetail }) {
  const { pathname } = useLocation();
  const session = useSession();
  const powers = powersOf(detail);
  const publicId = detail.public_id;
  const items = useItems(publicId);
  const members = useMembers(publicId);
  const notebook = useNotebook(publicId);
  const [editing, setEditing] = useState(false);
  const myHandle = session.me?.handle ?? null;

  // The open investigation's area is drawn on the map, and taken off when the page closes.
  const area = detail.area;
  useEffect(() => {
    useInvestigationArea.getState().setShape(areaShape(area));
    return () => useInvestigationArea.getState().setShape(null);
  }, [area]);

  // Opening the page shows the area, once, unless some of it is in view already, so a link that carries a view keeps it.
  const framed = useRef<string | null>(null);
  useEffect(() => {
    if (framed.current === publicId) return;
    // A refresh before the panel has settled starts the wait again, so the area is framed once, after it.
    return whenStageSettled(() => {
      framed.current = publicId;
      // Once for a visit to the page, and not again when the Layers panel has been over it.
      if (!firstArrival(pathname, "show the area")) return;
      const shape = areaShape(detail.area);
      if (!shape) return;
      const [west, south, east, north] = boundsOf(shape);
      const view = useViewAreaStore.getState().bounds;
      if (view && west < view[2] && east > view[0] && south < view[3] && north > view[1]) return;
      showArea(detail);
    });
  }, [publicId, detail, pathname]);

  let itemsBody: ReactNode;
  if (items.isError) {
    itemsBody = (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="What's in it couldn't be loaded"
        action={
          <Button variant="primary" onClick={() => void items.refetch()}>
            Try again
          </Button>
        }
      >
        <p>{items.error.message}</p>
      </EmptyState>
    );
  } else if (!items.data) {
    itemsBody = (
      <div role="status">
        <span className="fc-visually-hidden">Loading what's in it</span>
        <Skeleton lines={3} />
      </div>
    );
  } else if (items.data.length === 0) {
    itemsBody = (
      <EmptyState icon={<NotebookText size={22} />} title="Nothing in it yet">
        <p>
          {powers.edit
            ? "Add a note or the map's view below, or open a finding, a record or a height profile and add it from there."
            : "Its owner hasn't added anything yet."}
        </p>
      </EmptyState>
    );
  } else {
    itemsBody = <Items meta={meta} items={items.data} editable={powers.edit} notebook={notebook} />;
  }

  return (
    <div className="fc-inv-page">
      <div className="fc-inv-head">
        {detail.title.length > LONG_TITLE ? (
          <p className="fc-inv-head__title" aria-hidden="true">
            {detail.title}
          </p>
        ) : null}
        <p className="fc-inv-head__meta">
          <span className="fc-inv-badge">{VISIBILITY[detail.visibility].label}</span>
          <span>
            By {detail.owner.display_name} · started {dateText(detail.created_at)}
          </span>
        </p>
        {detail.hidden ? (
          <p className="fc-inv-banner fc-inv-banner--warn" role="note">
            <EyeOff size={15} aria-hidden /> A moderator has hidden this investigation. Only its members and moderators
            can see it.
          </p>
        ) : null}
        <InvitationBanner detail={detail} />
        {detail.summary ? <p className="fc-inv-head__summary">{detail.summary}</p> : null}
        {items.data?.some((item) => item.finding?.location.obscured) ? (
          <p className="fc-inv-banner" role="note">
            <EyeOff size={15} aria-hidden /> {GENERALISED_NOTICE}
          </p>
        ) : null}
        {powers.edit ? (
          <Button size="sm" icon={<Pencil size={15} aria-hidden />} onClick={() => setEditing(true)}>
            Edit the title, summary and notes
          </Button>
        ) : null}
        <ReportButton target={{ kind: "investigation", id: detail.public_id }} ownerHandle={detail.owner.handle} />
      </div>

      {detail.notes ? (
        <section className="fc-inv-section" aria-labelledby="inv-notes">
          <h3 id="inv-notes">Notes</h3>
          <Markdown source={detail.notes} />
        </section>
      ) : null}

      <section className="fc-inv-section" aria-labelledby="inv-items">
        {/* It takes focus when the last item is taken out. */}
        <h3 id="inv-items" tabIndex={-1}>
          In this notebook
        </h3>
        {itemsBody}
        {powers.edit && session.me ? <AddItems meta={meta} me={session.me} notebook={notebook} /> : null}
      </section>

      {members.data ? <People detail={detail} members={members.data} powers={powers} myHandle={myHandle} /> : null}
      <Settings detail={detail} members={members.data} powers={powers} notebook={notebook} />
      {editing ? <EditDialog detail={detail} notebook={notebook} onClose={() => setEditing(false)} /> : null}
    </div>
  );
}

function BackToList() {
  return (
    <Link className="fc-button fc-button--secondary fc-button--md" to={INVESTIGATIONS_PATH}>
      See the investigations
    </Link>
  );
}

/**
 * `/i/:id`, an investigation's notebook: its title, summary and notes, its
 * area drawn on the map, its items in the owner's order, who works on it,
 * who can see it, and its downloads.
 */
export function InvestigationPage({ meta }: { meta: Meta }) {
  const { id = "" } = useParams();
  const query = useInvestigation(id);
  const panelKey = investigationPath(id);
  const detail = query.data;
  useDocumentTitle(detail?.title ?? "Investigation");
  useLiveInvestigations();

  let body: ReactNode;
  if (detail) {
    body = <NotebookBody meta={meta} detail={detail} />;
  } else if (query.isError && isNotFound(query.error)) {
    body = (
      <EmptyState
        icon={<NotebookText size={22} />}
        title="There's no investigation at this address"
        action={<BackToList />}
      >
        <p>The link may be mistyped, or it may be private, or its owner may have deleted it.</p>
      </EmptyState>
    );
  } else if (query.isError) {
    body = (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="This investigation couldn't be loaded"
        action={
          <Button variant="primary" onClick={() => void query.refetch()}>
            Try again
          </Button>
        }
      >
        <p>{query.error.message}</p>
      </EmptyState>
    );
  } else {
    body = (
      <div className="fc-inv-page" role="status">
        <span className="fc-visually-hidden">Loading the investigation</span>
        <Skeleton height={20} width="40%" />
        <Skeleton lines={3} />
        <Skeleton lines={4} />
      </div>
    );
  }

  return (
    <PanelFrame
      panelKey={panelKey}
      title={detail?.title ?? "Investigation"}
      subtitle={detail ? `Investigation · ${itemCountText(detail.item_count)}` : undefined}
    >
      {body}
    </PanelFrame>
  );
}
