/**
 * The marking form: where the mark is, what it looks like, the optional
 * details and outline, the two notices, and saving. `MarkPanel` shows it.
 */

import { CircleDot, Crosshair, PenLine, Trash2, Undo2 } from "lucide-react";
import type { Map as MapLibreMap } from "maplibre-gl";
import { type ReactNode, useEffect, useId, useRef } from "react";
import { useNavigate } from "react-router";
import type { Meta } from "../../api/meta.js";
import { isMapLive } from "../../map/MapPane.js";
import { useMainMap } from "../../map/mainMap.js";
import { screenPoint } from "../../map/useMapFrame.js";
import { usePointDetail } from "../../map/usePointDetail.js";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { Field } from "../../ui/Field.js";
import { FeatureIcon } from "../../ui/featureIcons.js";
import { scrollBehaviour } from "../../ui/motion.js";
import { sheetHeights } from "../../ui/Sheet.js";
import { toast } from "../../ui/toastStore.js";
import { LAYOUT } from "../../ui/tokens.js";
import { useSession } from "../account/session.js";
import { DraftBadge } from "../drafts/DraftBadge.js";
import type { KindDraft } from "../drafts/savers.js";
import { discardDraft, restoreDraft, retryDraft } from "../drafts/store.js";
import { namedFields, POSITION_IN_TEXT, positionWords } from "../finding/positionInText.js";
import { BARE_MAP_PATH } from "../shell/navigation.js";
import { type PanelEnvironment, usePanelEnvironment } from "../shell/panelContext.js";
import { exactGridRefOf, suggestTitle } from "./describe.js";
import type { FindingDraft } from "./findingDrafts.js";
import { placeAtReticle, reticlePlace } from "./MarkLayer.js";
import { useMarkStore } from "./markStore.js";
import { FINDS_NOTICE, findsRoute, sensitivityNotice } from "./notices.js";
import { canClose, canFinishLine } from "./outline.js";
import { useSaveMark } from "./useSaveMark.js";

/** Space kept round the mark when the map is moved to show it, in pixels. */
const VIEW_MARGIN = 48;
/** The search field's strip across the top of the map. */
const SEARCH_STRIP = 68;

/**
 * The part of the map the person can see past the panel or sheet, in pixels
 * from the map's top left. On a phone the sheet is half open while the form
 * is filled in.
 */
export function uncoveredBox(
  environment: Pick<PanelEnvironment, "isPhone" | "sheetHeight">,
  width: number,
  height: number,
) {
  if (environment.isPhone) {
    const sheet = sheetHeights(environment.sheetHeight).half;
    return {
      left: 0,
      top: SEARCH_STRIP,
      right: width,
      bottom: height - LAYOUT.tabBarHeight - sheet - LAYOUT.statusHeight,
    };
  }
  return {
    left: LAYOUT.railWidth,
    top: SEARCH_STRIP,
    right: width - LAYOUT.panelWidth,
    bottom: height - LAYOUT.statusHeight,
  };
}

/** Move the map, if it must, so the mark is well inside the part of it on show. */
function keepInView(map: MapLibreMap, point: [number, number], box: ReturnType<typeof uncoveredBox>): void {
  if (!isMapLive(map)) return;
  const { x, y } = screenPoint(map, point);
  const inside =
    x >= box.left + VIEW_MARGIN &&
    x <= box.right - VIEW_MARGIN &&
    y >= box.top + VIEW_MARGIN &&
    y <= box.bottom - VIEW_MARGIN;
  if (inside) return;
  map.panBy([x - (box.left + box.right) / 2, y - (box.top + box.bottom) / 2], { duration: 0 });
}

/**
 * Keep the panel and the mark where both can be seen. On a phone the sheet
 * rests at its peek stop until the mark is placed, so the map is free to
 * tap, then opens half-way for the form, with the map moved if need be so
 * the mark stays in sight above it.
 */
function useMarkInView(placed: boolean): void {
  const environment = usePanelEnvironment();
  const map = useMainMap();
  const { isPhone, setStop, sheetHeight } = environment;
  // biome-ignore lint/correctness/useExhaustiveDependencies: placing the mark is the trigger, not each move of it
  useEffect(() => {
    if (isPhone) setStop(placed ? "half" : "peek");
    const point = useMarkStore.getState().point;
    if (!placed || !map || !point) return;
    keepInView(map, point, uncoveredBox({ isPhone, sheetHeight }, window.innerWidth, window.innerHeight));
  }, [placed, isPhone, map]);
}

function ClassChooser({ meta }: { meta: Meta }) {
  const featureClass = useMarkStore((state) => state.featureClass);
  const setFeatureClass = useMarkStore((state) => state.setFeatureClass);
  const problem = useMarkStore((state) => (state.problem?.field === "featureClass" ? state.problem.message : null));
  const hint = meta.vocab.feature_classes.find((candidate) => candidate.id === featureClass)?.hint;
  const notice = sensitivityNotice(meta, featureClass);
  const headingId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const focusForm = useMarkStore((state) => state.focusForm);
  const { isPhone, stop } = usePanelEnvironment();
  // Placed from "Place it here", which has gone: the question comes next, once the sheet has
  // risen from peek, where its body takes no focus.
  useEffect(() => {
    if (!focusForm || (isPhone && stop === "peek")) return;
    heading.current?.focus();
    useMarkStore.getState().formFocused();
  }, [focusForm, isPhone, stop]);
  return (
    <section className="fc-mark__step" aria-labelledby={headingId}>
      <h3 className="fc-field__label" id={headingId} ref={heading} tabIndex={-1}>
        What does it look like?
      </h3>
      <ChipGroup
        label="What it looks like"
        value={featureClass}
        onChange={setFeatureClass}
        options={meta.vocab.feature_classes.map((candidate) => ({
          id: candidate.id,
          label: candidate.label,
          icon: <FeatureIcon classId={candidate.id} size={18} />,
        }))}
      />
      {hint ? <p className="fc-mark__hint">{hint}</p> : null}
      {problem ? (
        <p className="fc-mark__problem" role="alert">
          {problem}
        </p>
      ) : null}
      {notice ? <p className="fc-mark__notice">{notice}</p> : null}
    </section>
  );
}

function OutlineTool({ map, isPhone }: { map: MapLibreMap | null; isPhone: boolean }) {
  const outline = useMarkStore((state) => state.outline);
  const drawing = useMarkStore((state) => state.drawing);
  const problem = useMarkStore((state) => (state.problem?.field === "outline" ? state.problem.message : null));
  const store = useMarkStore.getState();
  const count = outline?.points.length ?? 0;
  const tap = isPhone ? "Tap" : "Click";

  let body: ReactNode;
  if (drawing && outline) {
    body = (
      <>
        <p className="fc-mark__hint" role="status">
          {count === 0
            ? `${tap} the map at each corner of the feature, in order round it.`
            : `${count} ${count === 1 ? "corner" : "corners"}. ${tap} the first corner, or press "Close the shape", to finish.`}
        </p>
        <div className="fc-mark__row">
          <Button
            size="sm"
            icon={<Crosshair size={14} aria-hidden />}
            onClick={() => {
              const place = map ? reticlePlace(map) : null;
              if (place) store.addOutlinePoint(place);
            }}
          >
            Add a corner at the cross
          </Button>
          <Button
            size="sm"
            icon={<Undo2 size={14} aria-hidden />}
            disabled={count === 0}
            onClick={store.undoOutlinePoint}
          >
            Undo corner
          </Button>
          <Button size="sm" disabled={!canClose(outline)} onClick={store.closeOutline}>
            Close the shape
          </Button>
          <Button size="sm" disabled={!canFinishLine(outline)} onClick={store.finishOutlineLine}>
            Finish as a line
          </Button>
          <Button size="sm" variant="ghost" onClick={store.removeOutline}>
            Cancel outline
          </Button>
        </div>
      </>
    );
  } else if (outline) {
    body = (
      <>
        <p className="fc-mark__hint">
          {outline.shape === "polygon" ? `A closed shape with ${count} corners.` : `A line through ${count} points.`}
        </p>
        <div className="fc-mark__row">
          <Button size="sm" icon={<PenLine size={14} aria-hidden />} onClick={store.startOutline}>
            Change the outline
          </Button>
          <Button size="sm" variant="ghost" icon={<Trash2 size={14} aria-hidden />} onClick={store.removeOutline}>
            Remove it
          </Button>
        </div>
      </>
    );
  } else {
    body = (
      <>
        <div className="fc-mark__row">
          <Button size="sm" icon={<PenLine size={14} aria-hidden />} onClick={store.startOutline}>
            Draw an outline
          </Button>
        </div>
        <p className="fc-mark__hint">The shape of the bank, ditch or mound, if you can see it.</p>
      </>
    );
  }
  return (
    <section className="fc-mark__step" aria-label="Outline">
      <h3 className="fc-field__label">
        Outline <span className="fc-mark__optional">(optional)</span>
      </h3>
      {body}
      {problem ? (
        <p className="fc-mark__problem" role="alert">
          {problem}
        </p>
      ) : null}
    </section>
  );
}

function FindsNotice({ meta, nation }: { meta: Meta; nation: string | null }) {
  const route = findsRoute(meta, nation);
  return (
    <div className="fc-mark__notice fc-mark__notice--finds">
      <p>{FINDS_NOTICE}</p>
      {route ? (
        <p>
          {route.text}{" "}
          {route.url ? (
            <a href={route.url} target="_blank" rel="noreferrer noopener">
              {route.scheme} website
            </a>
          ) : null}
        </p>
      ) : (
        <p>Report it to the finds recording scheme for the nation it was found in.</p>
      )}
    </div>
  );
}

function DraftStatus({ draft }: { draft: KindDraft<FindingDraft> }) {
  const session = useSession();
  return (
    <div className="fc-mark__step">
      <div className="fc-mark__row">
        <DraftBadge />
      </div>
      {draft.state === "saving" ? (
        <p className="fc-mark__hint" role="status">
          Saving it now…
        </p>
      ) : null}
      {draft.state === "failed" && draft.failure ? (
        <p className="fc-mark__problem" role="alert">
          It couldn't be saved: {draft.failure.message}
        </p>
      ) : null}
      {draft.state === "failed" && session.ready ? (
        <div className="fc-mark__row">
          <Button size="sm" onClick={() => retryDraft(draft.id)}>
            Try again
          </Button>
        </div>
      ) : null}
      {draft.state === "waiting" && !session.ready ? (
        <p className="fc-mark__hint">
          Kept only in this browser, and nobody else sees it until you sign in and save it.
        </p>
      ) : null}
    </div>
  );
}

export function MarkForm({ meta, draft }: { meta: Meta; draft: KindDraft<FindingDraft> | null }) {
  const environment = usePanelEnvironment();
  const map = useMainMap();
  const navigate = useNavigate();
  const save = useSaveMark(meta);
  const point = useMarkStore((state) => state.point);
  const featureClass = useMarkStore((state) => state.featureClass);
  const period = useMarkStore((state) => state.period);
  const title = useMarkStore((state) => state.title);
  const note = useMarkStore((state) => state.note);
  const saving = useMarkStore((state) => state.saving);
  const pointProblem = useMarkStore((state) => (state.problem?.field === "point" ? state.problem.message : null));
  const placed = useMarkStore((state) => state.placed);
  const failure = draft?.state === "failed" ? draft.failure : undefined;
  // A draft refused after sign-in for a position in its title or note says so beside the field, as a save here would.
  useEffect(() => {
    if (failure?.code === POSITION_IN_TEXT) useMarkStore.getState().setPlaced([...namedFields(failure.fields ?? [])]);
  }, [failure]);
  // The first field refused for a position takes focus and comes into view, so the reason beside it is seen.
  const form = useRef<HTMLFormElement>(null);
  const refused = placed.length > 0;
  useEffect(() => {
    if (!refused) return;
    const field = form.current?.querySelector<HTMLElement>('[aria-invalid="true"]');
    field?.focus({ preventScroll: true });
    field?.closest(".fc-field")?.scrollIntoView?.({ block: "start", behavior: scrollBehaviour() });
  }, [refused]);
  const store = useMarkStore.getState();
  const nation = usePointDetail(point ? { lng: point[0], lat: point[1] } : null).detail?.nation ?? null;
  const busy = saving || draft?.state === "saving";
  useMarkInView(point !== null);

  if (point === null) {
    return (
      <div className="fc-mark">
        <div className="fc-mark__step">
          <p className="fc-mark__lead">{environment.isPhone ? "Tap" : "Click"} the map where you see it.</p>
          <p className="fc-mark__hint">
            Or move the map until the cross in the middle is over it, and press “Place it here” at the foot of the map,
            or this button.
          </p>
          <div>
            <Button icon={<CircleDot size={16} aria-hidden />} onClick={() => placeAtReticle(map)}>
              Place it under the cross
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const suggestion = suggestTitle(meta, featureClass, point);
  const where = exactGridRefOf(point);

  function discard(): void {
    if (!draft) return;
    const removed = discardDraft(draft.id);
    navigate(BARE_MAP_PATH);
    if (removed) toast("Draft discarded.", { action: { label: "Undo", onClick: () => restoreDraft(removed) } });
  }

  return (
    <form
      ref={form}
      className="fc-mark"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      {draft ? <DraftStatus draft={draft} /> : null}

      <section className="fc-mark__step" aria-label="Where it is">
        <div className="fc-mark__where">
          <span className="fc-field__label">Where</span>
          {where ? <span className="fc-mark__gridref">{where}</span> : null}
        </div>
        <p className="fc-mark__hint">Drag the mark to move it, or select it and use the arrow keys.</p>
        {pointProblem ? (
          <p className="fc-mark__problem" role="alert">
            {pointProblem}
          </p>
        ) : null}
      </section>

      <ClassChooser meta={meta} />

      <Field label="Period" hint="Your best guess. Leave it as not known if you can't tell.">
        {(control) => (
          <select
            {...control}
            className="fc-input"
            value={period}
            onChange={(event) => store.setPeriod(event.target.value)}
          >
            {meta.vocab.periods.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.label}
              </option>
            ))}
          </select>
        )}
      </Field>

      <Field
        label="Title"
        hint={`Leave it blank and it's called “${suggestion}”.`}
        error={placed.includes("title") ? positionWords("title") : undefined}
      >
        {(control) => (
          <input
            {...control}
            className="fc-input"
            value={title}
            placeholder={suggestion}
            maxLength={120}
            onChange={(event) => store.setTitle(event.target.value)}
          />
        )}
      </Field>

      <Field
        label="Note (optional)"
        hint="What you can see, and on which layer it shows best."
        error={placed.includes("description") ? positionWords("description") : undefined}
      >
        {(control) => (
          <textarea
            {...control}
            className="fc-input"
            value={note}
            maxLength={5000}
            onChange={(event) => store.setNote(event.target.value)}
          />
        )}
      </Field>

      <OutlineTool map={map} isPhone={environment.isPhone} />

      <FindsNotice meta={meta} nation={nation} />

      <div className="fc-mark__actions">
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "Saving…" : "Save finding"}
        </Button>
        {draft ? (
          <Button variant="ghost" icon={<Trash2 size={16} aria-hidden />} onClick={discard} disabled={busy}>
            Discard draft
          </Button>
        ) : null}
      </div>
    </form>
  );
}
