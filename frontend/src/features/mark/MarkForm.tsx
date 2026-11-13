/**
 * The marking form: the guidance and the drawing tool, what it looks like,
 * the optional details, the two notices, and saving. `MarkPanel` shows it.
 */

import { Trash2, Waypoints } from "lucide-react";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useId, useMemo, useRef } from "react";
import { useNavigate } from "react-router";
import type { Meta } from "../../api/meta.js";
import { safeHref } from "../../map/attribution.js";
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
import { DrawingBar, Guidance, SelectedPointBar } from "./DrawingTool.js";
import { exactGridRefOf, suggestTitle } from "./describe.js";
import type { FindingDraft } from "./findingDrafts.js";
import { isAdding, useMarkPath, useMarkStore } from "./markStore.js";
import { FINDS_NOTICE, findsRoute, sensitivityNotice } from "./notices.js";
import { anchorOf, type LngLat } from "./path.js";
import { useSaveMark } from "./useSaveMark.js";

/** Classes whose features run along the ground, which a finding of one point is invited to draw as a line. */
export const LINEAR_CLASSES: ReadonlySet<string> = new Set(["linear", "trackway", "road"]);

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
function keepInView(map: MapLibreMap, point: LngLat, box: ReturnType<typeof uncoveredBox>): void {
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
 * rests at its peek stop while points are being added, so the map is free
 * to tap, then opens half-way for the form once drawing stops, with the map
 * moved if need be so the mark stays in sight above it.
 */
export function useMarkInView(anchor: LngLat | null, drawing: boolean): void {
  const environment = usePanelEnvironment();
  const map = useMainMap();
  const { isPhone, setStop, sheetHeight } = environment;
  const placed = anchor !== null;
  const latest = useRef(anchor);
  latest.current = anchor;
  // biome-ignore lint/correctness/useExhaustiveDependencies: placing the mark and stopping drawing are the triggers, not each move
  useEffect(() => {
    if (isPhone) setStop(placed && !drawing ? "half" : "peek");
    const point = latest.current;
    if (!placed || !map || !point || (isPhone && drawing)) return;
    keepInView(map, point, uncoveredBox({ isPhone, sheetHeight }, window.innerWidth, window.innerHeight));
  }, [placed, drawing, isPhone, map]);
}

function ClassChooser({ meta }: { meta: Meta }) {
  const featureClass = useMarkStore((state) => state.featureClass);
  const setFeatureClass = useMarkStore((state) => state.setFeatureClass);
  const problem = useMarkStore((state) => (state.problem?.field === "featureClass" ? state.problem.message : null));
  const spot = useMarkStore((state) => state.shape.present.points.length === 1);
  const drawing = useMarkStore((state) => state.drawing);
  const hint = meta.vocab.feature_classes.find((candidate) => candidate.id === featureClass)?.hint;
  const notice = sensitivityNotice(meta, featureClass);
  const headingId = useId();
  const linear = spot && featureClass !== null && LINEAR_CLASSES.has(featureClass);
  return (
    <section className="fc-mark__step" aria-labelledby={headingId}>
      <h3 className="fc-field__label" id={headingId} tabIndex={-1}>
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
      {linear ? (
        <div className="fc-mark__notice">
          <p>
            A feature like this runs along the ground. You can carry on from your point and draw it as a line, or keep
            it as a spot.
          </p>
          {drawing ? null : (
            <div className="fc-mark__row">
              <Button
                size="sm"
                icon={<Waypoints size={14} aria-hidden />}
                onClick={() => useMarkStore.getState().continueFrom("end")}
              >
                Draw it as a line
              </Button>
            </div>
          )}
        </div>
      ) : null}
      {notice ? <p className="fc-mark__notice">{notice}</p> : null}
    </section>
  );
}

/** The guidance and the drawing bars, with what the server or the limits said of the shape. */
export function DrawingSection({ map, isPhone }: { map: MapLibreMap | null; isPhone: boolean }) {
  const problem = useMarkStore((state) => (state.problem?.field === "path" ? state.problem.message : null));
  // On a phone the bars float above the sheet while points are being added (`MarkButton`).
  const adding = useMarkStore(isAdding);
  const floating = isPhone && adding;
  return (
    <div className="fc-mark__step">
      <Guidance map={map} isPhone={isPhone} />
      {floating ? null : (
        <>
          <DrawingBar map={map} isPhone={isPhone} />
          <SelectedPointBar map={map} />
        </>
      )}
      {adding ? <p className="fc-mark__hint">Findings already on the map don't take taps while you draw.</p> : null}
      {problem ? (
        <p className="fc-mark__problem" role="alert">
          {problem}
        </p>
      ) : null}
    </div>
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
          {safeHref(route.url) ? (
            <a href={safeHref(route.url)} target="_blank" rel="noreferrer noopener">
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
          Kept only in this browser until you sign in and save it. Whoever uses this browser next can see that it's
          there, but not what it says or where.
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
  const path = useMarkPath();
  const drawing = useMarkStore((state) => state.drawing);
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
  const anchor = useMemo(() => anchorOf(path), [path]);
  // The nation, for the finds notice, by the first point: a nation's border isn't moved by a few metres of line.
  const first = path.points[0];
  const nation = usePointDetail(first ? { lng: first.lon, lat: first.lat } : null).detail?.nation ?? null;
  const busy = saving || draft?.state === "saving";
  useMarkInView(anchor, drawing);

  const suggestion = anchor ? suggestTitle(meta, featureClass, anchor) : "";
  const where = anchor && path.points.length === 1 ? exactGridRefOf(anchor) : null;

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

      <DrawingSection map={map} isPhone={environment.isPhone} />

      {/* The drawing tool stays where it is as the first point goes down, so focus on its buttons isn't lost. */}
      {anchor === null ? null : (
        <>
          {where || pointProblem ? (
            <section className="fc-mark__step" aria-label="Where it is">
              {where ? (
                <div className="fc-mark__where">
                  <span className="fc-field__label">Where</span>
                  <span className="fc-mark__gridref">{where}</span>
                </div>
              ) : null}
              {pointProblem ? (
                <p className="fc-mark__problem" role="alert">
                  {pointProblem}
                </p>
              ) : null}
            </section>
          ) : null}

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
        </>
      )}
    </form>
  );
}
