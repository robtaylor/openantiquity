import { ArrowRight, Check, CircleSlash, Compass, LogIn, MapPinned, SkipForward, Timer, Unplug } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef } from "react";
import { Link } from "react-router";
import { findOverlay, type Meta } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { overlayTroubleKey } from "../../map/trouble.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { Switch } from "../../ui/Switch.js";
import { useSession } from "../account/session.js";
import { DraftBadge } from "../drafts/DraftBadge.js";
import { useKindDrafts } from "../drafts/savers.js";
import { reasonOf, useSignedInFirst } from "../finding/feedback.js";
import { useDocumentTitle } from "../placeholders.js";
import { REVIEW_PATH } from "../review/ReviewLayer.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { SCAN_PATH, type Square } from "./api.js";
import { ScanCoverageStatus } from "./ScanCoverageStatus.js";
import { showSquare } from "./ScanLayer.js";
import { type DoneSquare, useScanStore } from "./scanStore.js";
import { squareDrafts } from "./squareDrafts.js";
import { useFinishSquare } from "./useFinishSquare.js";
import { useMarkedInSquare } from "./useMarkedInSquare.js";
import { askForSquare, useNextSquare } from "./useNextSquare.js";
import { useSquareElevation } from "./useSquareElevation.js";
import { findingsWords, RESULT_WORDS, scansWords, squaresWords } from "./words.js";
import "./scan.css";

export const SCAN_TITLE = "Scan a square";

/** True when this browser holds the square's result as a draft. */
function useHasDraft(square: string): boolean {
  return useKindDrafts(squareDrafts).some((draft) => draft.data.square === square);
}

/**
 * Focus goes to `target` as each new square or result appears, so the
 * keyboard and a screen reader carry on from there and not from the top of
 * the page: when focus was in the panel, or, with `fromLost`, was lost with
 * the button just pressed. Focus put somewhere else on purpose is left
 * there, and so is the page as it loads (see `PanelFrame`).
 */
function useFocusOnChange(target: () => HTMLElement | null | undefined, trigger: string, fromLost: boolean): void {
  const { shouldTakeFocus } = usePanelEnvironment();
  // biome-ignore lint/correctness/useExhaustiveDependencies: a new trigger is the point
  useEffect(() => {
    const element = target();
    const active = document.activeElement;
    const lost = active === null || active === document.body;
    const inPanel = active !== null && element?.closest(".fc-panel")?.contains(active) === true;
    if (inPanel || (fromLost && lost && shouldTakeFocus())) element?.focus({ preventScroll: true });
  }, [trigger]);
}

/** The reward: how many squares the person has looked over in this visit. There is no leaderboard. */
function VisitCount({ done }: { done: readonly DoneSquare[] }) {
  if (done.length === 0) return null;
  return (
    <p className="fc-scan__count">
      <Check size={16} aria-hidden />
      <span>
        <strong>{squaresWords(done.length)}</strong> looked over this visit. Thank you.
      </span>
    </p>
  );
}

/** The scan coverage layer's switch, offered while scanning as well as in the layer panel. */
function CoverageSwitch({ meta }: { meta: Meta }) {
  const overlay = findOverlay(meta, "coverage");
  const id = overlay?.id ?? "";
  const visible = useMapStore((state) => state.overlays[id]?.visible === true);
  const failing = useMapStore((state) => Boolean(state.failing[overlayTroubleKey(id)]));
  if (!overlay) return null;
  return (
    <div className="fc-scan__coverage">
      <Switch
        label={overlay.title}
        hint="Shades each square by how many people have looked it over."
        checked={visible}
        onChange={(on) => useMapStore.getState().setOverlayVisible(id, on)}
      />
      {visible && failing ? (
        <p className="fc-scan-coverage" role="status">
          Scan coverage isn't loading right now.{" "}
          <Button size="sm" variant="ghost" onClick={() => useMapStore.getState().retrySource(overlayTroubleKey(id))}>
            Try again
          </Button>
        </p>
      ) : visible ? (
        <ScanCoverageStatus />
      ) : null}
    </div>
  );
}

/** A square with no elevation to look at: nothing to record, so on to another. */
function NoElevation({ square }: { square: Square }) {
  return (
    <div className="fc-scan__notice" role="status">
      <p>
        <strong>There's no one-metre elevation for {square.grid_ref}</strong>, so there's nothing here to look over. It
        isn't recorded as scanned.
      </p>
      <Button
        variant="primary"
        icon={<ArrowRight size={16} aria-hidden />}
        onClick={() => {
          useScanStore.getState().pass();
          askForSquare();
        }}
      >
        Find another square
      </Button>
    </div>
  );
}

function Looking({ meta, square, first }: { meta: Meta; square: Square; first: boolean }) {
  const startedAt = useScanStore((state) => state.startedAt);
  const marked = useMarkedInSquare(square, startedAt);
  const elevation = useSquareElevation(square);
  const finish = useFinishSquare();
  const { ready } = useSession();
  const intro = useRef<HTMLParagraphElement>(null);
  // The first square of a visit leaves a lost focus alone: it is the page loading, not a press.
  useFocusOnChange(() => intro.current, square.square, !first);
  const nothingHint = useId();
  const markedHint = useId();

  return (
    <div className="fc-scan__looking">
      <p className="fc-scan__intro" ref={intro} tabIndex={-1}>
        Look over this one-kilometre grid square in any view you like. Mark anything you see with “Mark a finding”, then
        say how it went.
      </p>
      <p className="fc-scan__place">
        <span>
          Square <span className="fc-mono">{square.grid_ref}</span>
        </span>
        <span>{scansWords(square.scans)}</span>
      </p>
      <Button size="sm" variant="ghost" icon={<Compass size={15} aria-hidden />} onClick={() => showSquare(square)}>
        Back to the whole square
      </Button>
      {elevation === "no" ? (
        <NoElevation square={square} />
      ) : (
        <>
          <p className="fc-scan__marked" role="status">
            {marked.count > 0 ? (
              <>
                You've marked {findingsWords(marked.count)} in this square.
                {marked.drafts > 0 ? (
                  <>
                    {" "}
                    <DraftBadge />
                  </>
                ) : null}
              </>
            ) : null}
          </p>
          <div className="fc-scan__actions">
            <Button
              variant="primary"
              block
              icon={<CircleSlash size={16} aria-hidden />}
              onClick={() => finish(square, "nothing", 0)}
              aria-describedby={nothingHint}
            >
              {RESULT_WORDS.nothing.button}
            </Button>
            <p className="fc-finding__hint" id={nothingHint}>
              An empty square is worth recording: it shows the ground was checked, not missed.
            </p>
            <Button
              block
              icon={<MapPinned size={16} aria-hidden />}
              disabled={marked.count === 0}
              onClick={() => finish(square, "marked", marked.count)}
              aria-describedby={markedHint}
            >
              {RESULT_WORDS.marked.button}
            </Button>
            <p className="fc-finding__hint" id={markedHint}>
              {marked.count === 0
                ? "Mark what you see in the square with “Mark a finding”, then come back to this square."
                : "Each finding you marked here counts towards it."}
            </p>
            <div className="fc-scan__skip">
              <Button
                size="sm"
                variant="ghost"
                icon={<SkipForward size={15} aria-hidden />}
                onClick={() => finish(square, "skipped", 0)}
              >
                {RESULT_WORDS.skipped.button}
              </Button>
              <span className="fc-finding__hint">Skipping says nothing about the square.</span>
            </div>
          </div>
          {ready ? null : (
            <p className="fc-finding__hint">
              You're not signed in, so what you say is kept in this browser until you are.
            </p>
          )}
        </>
      )}
      <CoverageSwitch meta={meta} />
    </div>
  );
}

function Recorded({ meta, done }: { meta: Meta; done: DoneSquare }) {
  const drafted = useHasDraft(done.square);
  const { ready } = useSession();
  const signedIn = useSignedInFirst();
  const next = useRef<HTMLDivElement>(null);
  useFocusOnChange(() => next.current?.querySelector("button"), `${done.square}:${done.result}`, true);
  return (
    <div className="fc-scan__recorded">
      <p className="fc-scan__thanks" role="status">
        <span>
          <strong>{done.grid_ref}</strong> is recorded: {RESULT_WORDS[done.result].recorded}.
        </span>
        {drafted ? <DraftBadge /> : null}
      </p>
      {drafted && !ready ? (
        <div className="fc-scan__save">
          <p className="fc-finding__hint">It's kept in this browser until you sign in.</p>
          <Button size="sm" icon={<LogIn size={15} aria-hidden />} onClick={() => void signedIn()}>
            Sign in to save it
          </Button>
        </div>
      ) : null}
      <div className="fc-scan__next" ref={next}>
        <Button variant="primary" block icon={<ArrowRight size={16} aria-hidden />} onClick={askForSquare}>
          Next square
        </Button>
      </div>
      <CoverageSwitch meta={meta} />
    </div>
  );
}

function SquareView({ meta, square, first }: { meta: Meta; square: Square; first: boolean }) {
  const finished = useScanStore((state) => (state.finished?.square === square.square ? state.finished : null));
  return finished ? <Recorded meta={meta} done={finished} /> : <Looking meta={meta} square={square} first={first} />;
}

/**
 * Scan a square, at `/scan`: a one-kilometre square few people have looked
 * at, near where the map is, framed on the map with the ground outside it
 * shaded. The person looks it over in whatever views they like, marks what
 * they see with the marking flow every mode uses, and ends with one press:
 * nothing obvious, I marked something, or skip. Then the next square, with
 * one more. Signed out, the result is a draft (Decision 0002).
 */
export function ScanPanel({ meta }: { meta: Meta }) {
  useDocumentTitle(SCAN_TITLE);
  const status = useNextSquare();
  const done = useScanStore((state) => state.done);
  // The square up when the panel opened, which arrives with the page or the panel and not after a press.
  const firstShown = useRef<string | null>(useScanStore.getState().current?.square ?? null);
  if (firstShown.current === null && status.kind === "square") firstShown.current = status.square.square;
  let body: ReactNode;
  switch (status.kind) {
    case "loading":
      body = (
        <div role="status" className="fc-scan__loading">
          <span className="fc-visually-hidden">Finding a square for you</span>
          <Skeleton lines={3} />
          <Skeleton height={44} />
        </div>
      );
      break;
    case "none":
      body = (
        <EmptyState
          icon={<Compass size={22} />}
          title="No square left near here"
          action={
            <div className="fc-scan__empty-actions">
              <Button variant="primary" onClick={askForSquare}>
                Look again from here
              </Button>
              <Link className="fc-button fc-button--secondary fc-button--md" to={REVIEW_PATH}>
                Give a second look
              </Link>
            </div>
          }
        >
          <p>
            Every square within 50 km has been looked over by you or by plenty of others. Move the map somewhere else
            and look again, or check someone's finding instead.
          </p>
        </EmptyState>
      );
      break;
    case "busy":
      body = (
        <EmptyState
          tone="error"
          icon={<Timer size={22} />}
          title="The server is busy"
          action={
            <Button variant="primary" onClick={status.retry}>
              Try again
            </Button>
          }
        >
          <p>A lot of people are asking at once. Wait a minute, then try again. Nothing you've done is lost.</p>
        </EmptyState>
      );
      break;
    case "error":
      body = (
        <EmptyState
          tone="error"
          icon={<Unplug size={22} />}
          title="The next square couldn't be fetched"
          action={
            <Button variant="primary" onClick={status.retry}>
              Try again
            </Button>
          }
        >
          <p>{reasonOf(status.error)}</p>
        </EmptyState>
      );
      break;
    case "square":
      body = <SquareView meta={meta} square={status.square} first={firstShown.current === status.square.square} />;
      break;
  }
  return (
    <PanelFrame
      panelKey={SCAN_PATH}
      title={SCAN_TITLE}
      subtitle={status.kind === "square" ? status.square.grid_ref : undefined}
    >
      <div className="fc-scan">
        <VisitCount done={done} />
        {body}
      </div>
    </PanelFrame>
  );
}
