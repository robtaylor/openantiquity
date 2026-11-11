import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useLocation } from "react-router";
import { useMapStore } from "../../map/store.js";
import { uncoveredBounds, useMapCover, visibleCentre } from "../../map/visibleArea.js";
import { onDraftsSaved } from "../drafts/savers.js";
import { listDrafts, useDrafts } from "../drafts/store.js";
import { whenStageSettled } from "../finding/mapView.js";
import { isMarkPath } from "../mark/MarkLayer.js";
import { useMarkReturn } from "../mark/markReturn.js";
import { useMarkStore } from "../mark/markStore.js";
import { SCAN_PATH, type Square } from "./api.js";
import { scanKeys } from "./keys.js";
import { useScanStore } from "./scanStore.js";
import { cameraBox, frameSquare, keepMiddle, samePlace, visibleShare } from "./square.js";
// Registers the saver for square drafts at start-up, so drafts left from before a sign-in are saved.
import "./squareDrafts.js";
import { useScanSquareOnMap } from "./useScanOnMap.js";

/** Room left at the foot of the map for the primary action, "Mark a finding", so it doesn't sit on the square. */
const PRIMARY_ACTION_ROOM = 64;
/** Room left at the top for the drafts bar under the search field, while there are drafts for it to show. */
const DRAFTS_BAR_ROOM = 52;

/** Move the map so the square fills most of the part of the map nothing covers, north up and flat. */
export function showSquare(square: Square): void {
  const { cover } = useMapCover.getState();
  const top = cover.top + (listDrafts().length > 0 ? DRAFTS_BAR_ROOM : 0);
  const room = { ...cover, top, bottom: cover.bottom + PRIMARY_ACTION_ROOM };
  const framing = frameSquare(square.bbox, window.innerWidth, window.innerHeight, room);
  useMapStore.getState().requestCamera({ ...framing, bearing: 0, pitch: 0 });
}

/**
 * Each new square moves the map to it, once, after the panel or the sheet
 * has stopped moving. The person may then pan, zoom and change layer as
 * they like: opening the layer panel or marking a finding and coming back
 * leaves the map be. Leaving the scan and coming back frames it again.
 *
 * The drafts bar comes up with the first draft, over the top of the map. A
 * square still framed as it was then is framed again to leave room for it.
 */
function useFrameSquare(square: Square | null, scanning: boolean, onMap: boolean): void {
  const framedFor = useRef<string | null>(null);
  /** Where the camera was put to frame the square, until the person moves it. */
  const framedAt = useRef<{ lng: number; lat: number; zoom: number } | null>(null);
  useEffect(() => {
    if (!onMap) {
      framedFor.current = null;
      framedAt.current = null;
    }
    if (!scanning || !square || framedFor.current === square.square) return;
    return whenStageSettled(() => {
      framedFor.current = square.square;
      showSquare(square);
      framedAt.current = useMapStore.getState().camera;
    });
  }, [square, scanning, onMap]);

  // Any draft brings the bar up, as `showSquare` reckons.
  const drafting = useDrafts().length > 0;
  const hadDrafts = useRef(drafting);
  useEffect(() => {
    const appeared = drafting && !hadDrafts.current;
    hadDrafts.current = drafting;
    const at = framedAt.current;
    if (!appeared || !scanning || !square || !at) return;
    const { camera } = useMapStore.getState();
    if (camera.zoom !== at.zoom || !samePlace(camera, at, camera.zoom)) return;
    return whenStageSettled(() => {
      showSquare(square);
      framedAt.current = useMapStore.getState().camera;
    });
  }, [drafting, scanning, square]);
}

type Stage = "scan" | "mark" | "other";

/** Less than this share of the square in sight, after marking, and it is framed again. */
const FRAME_AGAIN_BELOW = 0.5;

/**
 * Back on the scan from marking a finding, the square is framed again if
 * less than half of it is in sight: on a phone the form's sheet keeps the
 * new mark above it, which can push most of the square off the top.
 */
function useReframeAfterMarking(stage: Stage, square: Square | null): void {
  const previous = useRef(stage);
  useEffect(() => {
    const back = previous.current === "mark" && stage === "scan";
    previous.current = stage;
    if (!back || !square) return;
    return whenStageSettled(() => {
      const { camera } = useMapStore.getState();
      if (camera.bearing !== 0) return;
      const size = { width: window.innerWidth, height: window.innerHeight };
      const view = uncoveredBounds(cameraBox(camera, size.width, size.height), size, useMapCover.getState().cover);
      if (visibleShare(square.bbox, view) < FRAME_AGAIN_BELOW) showSquare(square);
    });
  }, [stage, square]);
}

/**
 * Going from the scan to marking a finding, and back, keeps the ground in
 * the middle of the map where it was. On a phone the sheet drops from half-way
 * to peek for marking, which moves the middle of what shows, and with it the
 * cross that "Place it here" puts the mark under, down and out of the square
 * the person was looking at.
 *
 * The ground in the middle is taken as the stage changes, in the render
 * before the shell tells the map what its chrome covers. From then on, every
 * change of cover brings that ground back to the middle, at once, until the
 * person moves the map, places the mark, or leaves. Nothing waits on a timer,
 * so it holds however late the cover arrives. "Place it here" pressed while
 * the map is still on its way puts the mark on that ground, which is where
 * the cross is headed.
 */
function useKeepMiddle(stage: Stage): void {
  const kept = useRef<{ lng: number; lat: number } | null>(null);
  const lastStage = useRef(stage);
  if (lastStage.current !== stage) {
    const switching = stage !== "other" && lastStage.current !== "other";
    lastStage.current = stage;
    kept.current = switching ? visibleCentre(useMapStore.getState().camera, useMapCover.getState().cover) : null;
  }

  useEffect(() => {
    /** Bring the kept ground to the middle of what the cover leaves. */
    const keep = (): void => {
      const middle = kept.current;
      if (!middle) return;
      const { camera, requestCamera } = useMapStore.getState();
      const target = keepMiddle(middle, camera, useMapCover.getState().cover);
      if (target) requestCamera(target);
    };
    const offCover = useMapCover.subscribe(keep);
    // A camera that no longer has the kept ground in the middle has been moved by the person.
    const offCamera = useMapStore.subscribe((next, previous) => {
      const middle = kept.current;
      if (!middle || next.camera === previous.camera) return;
      if (!samePlace(visibleCentre(next.camera, useMapCover.getState().cover), middle, next.camera.zoom)) {
        kept.current = null;
      }
    });
    const offMark = useMarkStore.subscribe((next, previous) => {
      const middle = kept.current;
      if (!middle || next.point === previous.point || previous.point !== null || next.point === null) return;
      kept.current = null;
      // Placed by the button, under the cross: the cross's place once the map has caught up.
      if (next.focusForm) useMarkStore.setState({ point: [middle.lng, middle.lat] });
    });
    return () => {
      offCover();
      offCamera();
      offMark();
    };
  }, []);
}

/** What the way back from marking a finding opened over the scan is called. */
const BACK_TO_SQUARE = { path: SCAN_PATH, label: "Back to the square" };

/**
 * What a scan does to the map, mounted once by the shell so it holds while
 * the layer panel is open over the scan and while a finding is being marked
 * from it: the square is framed when it comes up, and outlined with
 * the ground outside shaded (drawn by `useScanOnMap`). Squares saved from
 * drafts after sign-in refresh the coverage layer. Marking a finding from the
 * scan comes back to it once the finding is saved or kept as a draft, or the
 * marking panel is closed.
 */
export function ScanLayer() {
  const { pathname } = useLocation();
  const scanning = pathname === SCAN_PATH;
  // Marking a finding from the scan keeps the square in sight. Marking from anywhere else doesn't.
  const fromScan = useRef(false);
  const marking = isMarkPath(pathname);
  if (!marking) fromScan.current = scanning;
  const onMap = scanning || fromScan.current;
  // Into marking from the scan, or back from it to the scan.
  const stage: Stage = scanning ? "scan" : marking && fromScan.current ? "mark" : "other";
  useKeepMiddle(stage);
  const current = useScanStore((state) => state.current);
  const client = useQueryClient();

  useFrameSquare(current, scanning, onMap);
  useReframeAfterMarking(stage, current);

  useEffect(() => {
    if (stage === "mark") useMarkReturn.getState().set(BACK_TO_SQUARE);
    else if (useMarkReturn.getState().to === BACK_TO_SQUARE) useMarkReturn.getState().set(null);
  }, [stage]);

  useEffect(() => {
    useScanSquareOnMap.getState().setSquare(onMap ? current : null);
  }, [onMap, current]);
  useEffect(() => () => useScanSquareOnMap.getState().setSquare(null), []);

  useEffect(
    () =>
      onDraftsSaved((report) => {
        if (report.saved > 0) void client.invalidateQueries({ queryKey: scanKeys.allCoverage });
      }),
    [client],
  );

  return null;
}
