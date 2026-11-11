import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useLocation } from "react-router";
import { useMapStore } from "../../map/store.js";
import { useMapCover } from "../../map/visibleArea.js";
import { onDraftsSaved } from "../drafts/savers.js";
import { listDrafts } from "../drafts/store.js";
import { whenStageSettled } from "../finding/mapView.js";
import { isMarkPath } from "../mark/MarkLayer.js";
import { SCAN_PATH, type Square } from "./api.js";
import { scanKeys } from "./keys.js";
import { useScanStore } from "./scanStore.js";
import { frameSquare, keepMiddle } from "./square.js";
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
 */
function useFrameSquare(square: Square | null, scanning: boolean, onMap: boolean): void {
  const framedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!onMap) framedFor.current = null;
    if (!scanning || !square || framedFor.current === square.square) return;
    return whenStageSettled(() => {
      framedFor.current = square.square;
      showSquare(square);
    });
  }, [square, scanning, onMap]);
}

/**
 * Going from the scan to marking a finding, and back, keeps the ground in
 * the middle of the map where it was. On a phone the sheet drops from half-way
 * to peek for marking, which moves the middle of what shows, and with it the
 * cross that "Place it here" puts the mark under, down and out of the square
 * the person was looking at. `switching` is set as the route changes, in the
 * render before the shell tells the map what its chrome covers; the change of
 * cover that follows moves the camera, once the sheet has settled.
 */
function useKeepMiddleWhileMarking(switching: { current: boolean }): void {
  useEffect(
    () =>
      useMapCover.subscribe((next, previous) => {
        if (!switching.current) return;
        switching.current = false;
        const moved = keepMiddle(useMapStore.getState().camera, previous.cover, next.cover);
        if (!moved) return;
        whenStageSettled(() => useMapStore.getState().requestCamera(moved));
      }),
    [switching],
  );
}

/**
 * What a scan does to the map, mounted once by the shell so it holds while
 * the layer panel is open over the scan and while a finding is being marked
 * from it: the square is framed when it comes up, and outlined with
 * the ground outside shaded (drawn by `useScanOnMap`). Squares saved from
 * drafts after sign-in refresh the coverage layer.
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
  const stage = scanning ? "scan" : marking && fromScan.current ? "mark" : "other";
  const lastStage = useRef(stage);
  const switching = useRef(false);
  if (lastStage.current !== stage) {
    switching.current = stage !== "other" && lastStage.current !== "other";
    lastStage.current = stage;
  }
  useKeepMiddleWhileMarking(switching);
  // A switch that didn't change the cover, as on a desktop, is over once the stage has settled.
  // biome-ignore lint/correctness/useExhaustiveDependencies: a new stage is the trigger
  useEffect(
    () =>
      whenStageSettled(() => {
        switching.current = false;
      }),
    [stage],
  );
  const current = useScanStore((state) => state.current);
  const client = useQueryClient();

  useFrameSquare(current, scanning, onMap);

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
