import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useRef } from "react";
import { useLocation } from "react-router";
import { findOverlay, type Meta } from "../../api/meta.js";
import { useHoldOverlayWhile } from "../../map/heldOverlays.js";
import { useHideFindingsWhile } from "../../map/hiddenFindings.js";
import { isMapLive } from "../../map/MapPane.js";
import { useMainMap } from "../../map/mainMap.js";
import { screenPoint, useMapFrame } from "../../map/useMapFrame.js";
import { accountIdentity, useSession } from "../account/session.js";
import { seeViewAt, whenStageSettled } from "../finding/mapView.js";
import { useSavedAnswers } from "../finding/secondLook/answerDrafts.js";
import { useApplyFinding } from "../finding/useFinding.js";
import { useForgetClaimsWhile } from "./forgetClaims.js";
import { useReviewStore } from "./reviewStore.js";
import type { ReviewCard, ReviewPlace } from "./types.js";
import "./review.css";

export const REVIEW_PATH = "/review";

/** Why the findings overlay is held back. */
const HIDE_REASON = "second-look";

/**
 * Each new card moves the map to its place in the finder's view, once. The
 * person may then pan and change layer as they like: opening the layer
 * panel or coming back from it leaves the map be. Leaving the queue and
 * coming back moves it to the card again.
 */
function useMoveToCard(meta: Meta, card: ReviewCard | null, reviewing: boolean): void {
  const movedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!reviewing) movedFor.current = null;
    if (!card || movedFor.current === card.public_id) return;
    movedFor.current = card.public_id;
    // Once the panel, or the sheet at its stop, has settled, so the part of the map it leaves uncovered is known.
    return whenStageSettled(() => seeViewAt(meta, [card.place.lon, card.place.lat], card.view_state));
  }, [meta, card, reviewing]);
}

/**
 * An answer kept as a draft while signed out is saved by the drafts
 * machinery once the person has signed in. What its reply revealed is
 * shown on the card it answered, if that card is still up, or, when the
 * person hadn't yet asked to see how it compares, the detail is offered.
 */
function useSavedFromDraft(card: ReviewCard | null): void {
  const apply = useApplyFinding();
  const { me } = useSession();
  const identity = me ? accountIdentity(me) : null;
  const publicId = card?.public_id ?? null;
  const saved = useSavedAnswers((state) => (publicId === null ? undefined : state.saved[publicId]));
  useEffect(() => {
    if (!saved || publicId === null) return;
    // A held answer is kept for its person, who is known by the time a draft can be saved.
    if (saved.kind === "held" && identity === null) return;
    useSavedAnswers.getState().forget(publicId);
    if (saved.kind === "held") {
      if (identity !== null) useReviewStore.getState().hold({ visible: saved.observation.visible, by: identity });
      return;
    }
    apply(saved.reveal.finding);
    useReviewStore.getState().revealed(saved.reveal);
  }, [saved, publicId, identity, apply]);
}

/**
 * A frame round the card's place, open in the middle so it covers nothing
 * there. It marks where to look and says nothing about what anyone saw.
 */
function LookHere({ map, place }: { map: MapLibreMap; place: ReviewPlace }) {
  const { x, y } = screenPoint(map, [place.lon, place.lat]);
  return (
    <span className="fc-look-here" style={{ transform: `translate(${x}px, ${y}px)` }} aria-hidden="true">
      <span className="fc-look-here__corner fc-look-here__corner--nw" />
      <span className="fc-look-here__corner fc-look-here__corner--ne" />
      <span className="fc-look-here__corner fc-look-here__corner--sw" />
      <span className="fc-look-here__corner fc-look-here__corner--se" />
    </span>
  );
}

/**
 * What a second look does to the map: while the queue is open every
 * finding's marker is taken off, because a marker at the spot gives the game
 * away (Decision 0008), and what the cache held about findings is dropped.
 * The heritage records are held off the map too until the card is answered.
 * For each card the map goes to its place in the finder's view and a frame
 * marks the place. Mounted once, by the shell, so
 * it holds while the layer panel is open over the queue.
 */
export function ReviewLayer({ meta }: { meta: Meta }) {
  const map = useMainMap();
  const { pathname } = useLocation();
  const reviewing = pathname === REVIEW_PATH;
  const card = useReviewStore((state) => (reviewing ? state.current : null));
  // From the moment the queue opens, not only once a card is up: asked for before the first card arrives,
  // the findings in view would carry the title of the finding the card turns out to be.
  useHideFindingsWhile(HIDE_REASON, reviewing);
  // A scheduled monument's square at the spot would answer the question the card asks, so the heritage
  // records, the live sources' among them, are held off the map until the answer is in.
  const answered = useReviewStore((state) => state.reveal !== null);
  useHoldOverlayWhile(findOverlay(meta, "records")?.id ?? null, reviewing && !answered);
  useForgetClaimsWhile(reviewing);
  useMoveToCard(meta, card, reviewing);
  useSavedFromDraft(card);
  useMapFrame(card ? map : null);

  if (!card || !map || !isMapLive(map)) return null;
  return (
    <div className="fc-annotations">
      <LookHere map={map} place={card.place} />
    </div>
  );
}
