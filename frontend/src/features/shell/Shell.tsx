import { Layers, Unplug } from "lucide-react";
import {
  type CSSProperties,
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Route, Routes, useLocation, useNavigate, useSearchParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { useMeta } from "../../api/useMeta.js";
import { CameraControls } from "../../map/CameraControls.js";
import { LayerPanel } from "../../map/LayerPanel.js";
import { type MapInsets, MapView } from "../../map/MapView.js";
import { decodePermalink } from "../../map/permalink.js";
import { RakingControl } from "../../map/RakingControl.js";
import { StatusBar } from "../../map/StatusBar.js";
import { useMapStore } from "../../map/store.js";
import { usePermalink } from "../../map/usePermalink.js";
import { useMapCover } from "../../map/visibleArea.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { IconButton } from "../../ui/IconButton.js";
import { SHEET_PEEK_HEIGHT, type SheetStop, sheetHeights } from "../../ui/Sheet.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { ToastViewport } from "../../ui/Toast.js";
import { LAYOUT } from "../../ui/tokens.js";
import { ABOUT_PATH, AboutPanel, NOTICE_ROUTE, NoticePanel } from "../about/AboutPanel.js";
import { AccountLayer } from "../account/AccountLayer.js";
import { AccountPage } from "../account/AccountPage.js";
import { EmailLinkPage } from "../account/EmailLinkPage.js";
import { EMAIL_LINK_PATH } from "../account/emailLink.js";
import { ACTIVITY_PATH, ActivityPanel } from "../activity/ActivityPanel.js";
import { LiveEvents } from "../activity/LiveEvents.js";
import { DraftsBar } from "../drafts/DraftsBar.js";
import { ExploreLayer } from "../explore/ExploreLayer.js";
import { ExplorePanel } from "../explore/ExplorePanel.js";
import { FindingPanel } from "../finding/FindingPanel.js";
import { GUIDE_PATH, GuidePanel } from "../guide/GuidePanel.js";
import { HELP_PATH, HelpKindPanel, HelpPanel } from "../help/HelpPanel.js";
import { INVESTIGATIONS_PATH } from "../investigations/api.js";
import { InvestigationPage } from "../investigations/InvestigationPage.js";
import { InvestigationsPanel } from "../investigations/InvestigationsPanel.js";
import { CoverageNotice, FindingsCutShortNotice } from "../layers/MapNotices.js";
import { PROFILE_PATH } from "../layers/profile/line.js";
import { ProfilePanel } from "../layers/profile/ProfilePanel.js";
import { ChangeShapePanel } from "../mark/ChangeShapePanel.js";
import { MarkButton } from "../mark/MarkButton.js";
import { isMarkPath, MarkLayer } from "../mark/MarkLayer.js";
import { MARK_PATH, MarkPanel } from "../mark/MarkPanel.js";
import { SearchOrGuide } from "../mark/SearchOrGuide.js";
import { RECENT_MENTIONS_PATH } from "../mentions/paths.js";
import { RecentMentionsPanel } from "../mentions/RecentMentionsPanel.js";
import { MOD_ROUTE, ModerationPanel } from "../moderation/ModerationPanel.js";
import { NotificationAnnouncer } from "../notifications/NotificationAnnouncer.js";
import { ProfilePanel as PersonPanel, PROFILE_ROUTE } from "../people/ProfilePanel.js";
import { APP_NAME, NotFoundPanel } from "../placeholders.js";
import { OpenElsewherePanel } from "../records/OpenElsewherePanel.js";
import { ELSEWHERE_PATH, RECORD_SEARCH_PATH } from "../records/paths.js";
import { RecordPage } from "../records/RecordPage.js";
import { RecordSearchPanel } from "../records/RecordSearchPanel.js";
import { REVIEW_PATH, ReviewLayer } from "../review/ReviewLayer.js";
import { ReviewPanel } from "../review/ReviewPanel.js";
import { SCAN_PATH } from "../scan/api.js";
import { ScanLayer } from "../scan/ScanLayer.js";
import { ScanPanel } from "../scan/ScanPanel.js";
import { beginVisits, leftFor } from "./arrival.js";
import { BrandMark, ModeRail } from "./ModeRail.js";
import { BARE_MAP_PARAM, searchWithPanel } from "./navigation.js";
import { PanelFrame } from "./PanelFrame.js";
import { type PanelEnvironment, PanelEnvironmentProvider } from "./panelContext.js";
import { TabBar } from "./TabBar.js";
import { useIsPhone, useIsShort, useWindowHeight } from "./useIsPhone.js";
import { useSearchSlotHeight } from "./useSearchSlotHeight.js";
import "./shell.css";

/** The component gallery is a development aid, so it is left out of production builds. */
const Gallery = import.meta.env.DEV
  ? lazy(() => import("../../ui/Gallery.js").then((module) => ({ default: module.Gallery })))
  : null;

/** Room left above a fully open sheet, so the search field stays in reach. */
const SHEET_TOP_GAP = 68;
/**
 * The least height of map a phone must have left, between the search field
 * and the status bar, for the raking light card and the primary button to
 * fit. With less than this they are put away until the sheet is lowered.
 */
const MIN_STAGE_ROOM = 232;
/**
 * Width of the strip down the right of the map that the floating buttons
 * take up: a gap, the button, a gap. Mirrors `--gap` and `--control-height`.
 */
const CONTROLS_STRIP = 64;

const LAYERS_PARAM = "layers";

function BootScreen({ error, onRetry }: { error?: Error | null; onRetry?: () => void }) {
  return (
    <div className="fc-boot">
      <div className="fc-boot__card">
        <div className="fc-boot__brand">
          <BrandMark size={36} />
          <h1>{APP_NAME}</h1>
        </div>
        {error ? (
          <EmptyState
            tone="error"
            icon={<Unplug size={22} />}
            title="The map couldn't start"
            action={
              <Button variant="primary" onClick={onRetry}>
                Try again
              </Button>
            }
          >
            <p>{error.message}</p>
          </EmptyState>
        ) : (
          <div role="status">
            <span className="fc-visually-hidden">Loading the map</span>
            <Skeleton lines={3} />
          </div>
        )}
      </div>
    </div>
  );
}

/** The app shell: the map, with every control and panel layered over it. */
export function Shell() {
  const meta = useMeta();
  const ready = useMapStore((state) => state.meta !== null);

  useEffect(() => {
    const store = useMapStore.getState();
    if (meta.data && store.meta === null) store.initialise(meta.data, decodePermalink(window.location.hash));
  }, [meta.data]);

  if (meta.isError) return <BootScreen error={meta.error} onRetry={() => void meta.refetch()} />;
  if (!meta.data || !ready) return <BootScreen />;
  return <ReadyShell meta={meta.data} />;
}

function ReadyShell({ meta }: { meta: Meta }) {
  usePermalink();
  const isPhone = useIsPhone();
  const isShort = useIsShort();
  const windowHeight = useWindowHeight();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const terrainOn = useMapStore((state) => state.terrain.enabled);
  const setTerrainEnabled = useMapStore((state) => state.setTerrainEnabled);
  const layersButton = useRef<HTMLButtonElement>(null);
  const searchSlot = useRef<HTMLDivElement>(null);
  const searchSlotHeight = useSearchSlotHeight(searchSlot);

  // The layer panel is a query parameter, so it can open over any mode and
  // the URL still says what is on screen. So is the bare map: `/` is Explore,
  // and `/?panel=none` is the map with Explore put away.
  const layersOpen = searchParams.get("panel") === LAYERS_PARAM;
  const bareMap = location.pathname === "/" && searchParams.get("panel") === BARE_MAP_PARAM;
  const panelOpen = !bareMap;

  // A sheet opens half-way, except where the map is the point: Explore, and
  // marking until the mark is placed, start at peek. The stop is kept with
  // the panel it belongs to, so a different panel starts at its own stop in
  // the very render it appears.
  const panelKey = layersOpen ? LAYERS_PARAM : isMarkPath(location.pathname) ? MARK_PATH : location.pathname;
  const firstStop: SheetStop = panelKey === "/" || panelKey === MARK_PATH ? "peek" : "half";
  const [sheet, setSheet] = useState<{ panelKey: string; stop: SheetStop }>({ panelKey, stop: firstStop });
  const sheetStop = sheet.panelKey === panelKey ? sheet.stop : firstStop;
  const setSheetStop = useCallback((stop: SheetStop) => setSheet({ panelKey, stop }), [panelKey]);

  const insets = useMemo<MapInsets>(
    () => ({
      left: isPhone ? 0 : LAYOUT.railWidth,
      right: !isPhone && panelOpen ? LAYOUT.panelWidth : 0,
      controls: CONTROLS_STRIP,
    }),
    [isPhone, panelOpen],
  );

  const sheetHeight = Math.max(SHEET_PEEK_HEIGHT, windowHeight - LAYOUT.tabBarHeight - SHEET_TOP_GAP);
  const sheetVisible = isPhone && panelOpen ? sheetHeights(sheetHeight)[sheetStop] : 0;
  // The floating controls ride above the sheet, so the primary action, the
  // status bar and the sun dial stay in sight and in reach while a panel is
  // open. A full sheet, or a short window, leaves them no room. Then they are
  // put away, and made inert so the keyboard cannot land on what is hidden.
  const stageRoom = windowHeight - LAYOUT.tabBarHeight - sheetVisible - LAYOUT.statusHeight - SHEET_TOP_GAP;
  const sheetFull = sheetVisible > 0 && sheetStop === "full";
  const stageCovered = sheetVisible > 0 && (sheetFull || stageRoom < MIN_STAGE_ROOM);
  const sheetClear = stageCovered ? 0 : sheetVisible;

  // How much of the foot of the map is hidden, so map controls can centre on what is left.
  const coveredBottom = isPhone
    ? LAYOUT.tabBarHeight + (stageCovered ? sheetVisible : sheetClear + LAYOUT.statusHeight)
    : LAYOUT.statusHeight;
  // The same, for every edge, for map tools that mean "the middle of what shows".
  const setMapCover = useMapCover((state) => state.setCover);
  useEffect(() => {
    setMapCover({ left: insets.left, right: insets.right, top: isPhone ? SHEET_TOP_GAP : 0, bottom: coveredBottom });
  }, [setMapCover, insets, isPhone, coveredBottom]);

  // A panel takes keyboard focus when it opens, with two exceptions. One that
  // is already there when the page loads leaves focus alone, as any page
  // does. And one that is only back in view because the layer panel over it
  // closed leaves focus with the Layers button, where closing put it.
  const settled = useRef(false);
  useEffect(() => {
    const timer = setTimeout(() => {
      settled.current = true;
    }, 0);
    return () => clearTimeout(timer);
  }, []);
  const layersNow = useRef(layersOpen);
  layersNow.current = layersOpen;
  const layersBefore = useRef(layersOpen);
  // Runs after the panels' own layout effects, which read the value from before this render.
  useLayoutEffect(() => {
    layersBefore.current = layersOpen;
  }, [layersOpen]);
  const shouldTakeFocus = useCallback(
    (): boolean => settled.current && !(layersBefore.current && !layersNow.current),
    [],
  );

  const environment = useMemo<PanelEnvironment>(
    () => ({
      isPhone,
      sheetHeight,
      stop: sheetStop,
      setStop: setSheetStop,
      shouldTakeFocus,
      // A panel opened by a link that has since gone hands focus to the map.
      fallbackFocus: () => document.querySelector<HTMLElement>(".fc-map__pane--main canvas"),
    }),
    [isPhone, sheetHeight, sheetStop, setSheetStop, shouldTakeFocus],
  );

  // Closing the layer panel goes back to whatever it was opened over. Over a
  // mode such as Second look or Scan a square that is the mode's own panel,
  // because changing layer is part of doing the mode's work, not a way out of it.
  // Opened over the bare map, it closes back to the bare map rather than to Explore.
  // The rest of the query is kept, so a panel that keeps its state there, such
  // as a height profile's line, is as it was when the layer panel closes.
  const layersOverBareMap = useRef(false);
  // What the last press asked for. The router draws a change of address as a
  // transition, so a second press can arrive while this render still says the
  // panel is shut. It has to undo the first press, not repeat it.
  const layersWanted = useRef(layersOpen);
  // Brought back in step whenever the address changes, so a press that another
  // navigation overtook doesn't leave it saying the panel is open.
  // biome-ignore lint/correctness/useExhaustiveDependencies: location.key is the signal, not a value read
  useEffect(() => {
    layersWanted.current = layersOpen;
  }, [layersOpen, location.key]);
  // What a page does on arriving is done once for each visit to an address, not each time the
  // Layers panel has been over it (`arrival.ts`). A shell just made has been nowhere yet, and
  // says so before any page inside it arrives.
  const visiting = useRef(false);
  if (!visiting.current) {
    visiting.current = true;
    beginVisits();
  }
  useEffect(() => {
    leftFor(location.pathname);
  }, [location.pathname]);
  const toggleLayers = useCallback(() => {
    const open = layersWanted.current;
    layersWanted.current = !open;
    if (!open) layersOverBareMap.current = bareMap;
    const back = layersOverBareMap.current && location.pathname === "/" ? BARE_MAP_PARAM : null;
    navigate({
      pathname: location.pathname,
      search: searchWithPanel(location.search, open ? back : LAYERS_PARAM),
    });
  }, [bareMap, location.pathname, location.search, navigate]);

  return (
    <div
      className="fc-shell"
      data-layout={isPhone ? "phone" : "desktop"}
      data-panel={panelOpen ? "open" : "closed"}
      data-sheet={sheetVisible > 0 ? sheetStop : undefined}
      data-stage={stageCovered ? "covered" : undefined}
      style={{ "--map-covered-bottom": `${coveredBottom}px`, "--sheet-clear": `${sheetClear}px` } as CSSProperties}
    >
      <h1 className="fc-visually-hidden">{meta.app.name}</h1>
      <NotificationAnnouncer />

      {isPhone ? null : <ModeRail compact={isShort} />}

      <main className="fc-shell__main">
        <MapView meta={meta} insets={insets} />
        <ExploreLayer meta={meta} />
        <MarkLayer />
        <ReviewLayer meta={meta} />
        <ScanLayer />

        <div
          className="fc-stage"
          style={
            searchSlotHeight === null
              ? undefined
              : ({ "--search-slot-height": `${searchSlotHeight}px` } as CSSProperties)
          }
        >
          <div className="fc-stage__search" ref={searchSlot}>
            <SearchOrGuide />
          </div>
          <div className="fc-stage__controls" inert={sheetFull}>
            <IconButton floating label="Layers" pressed={layersOpen} onClick={toggleLayers} ref={layersButton}>
              <Layers size={20} aria-hidden />
            </IconButton>
            <IconButton
              floating
              label="Tilt into 3D"
              title={terrainOn ? "Back to a flat map" : "Tilt into 3D"}
              pressed={terrainOn}
              onClick={() => setTerrainEnabled(!terrainOn)}
            >
              <span className="fc-stage__3d" aria-hidden="true">
                3D
              </span>
            </IconButton>
            <CameraControls />
          </div>
          <div className="fc-stage__notice" inert={sheetFull}>
            <CoverageNotice meta={meta} />
            <FindingsCutShortNotice />
          </div>
          <div className="fc-stage__drafts" inert={sheetFull}>
            <DraftsBar />
          </div>
          <div className="fc-stage__raking" inert={stageCovered}>
            <RakingControl meta={meta} collapsible={isPhone} />
          </div>
          <div className="fc-stage__primary" inert={stageCovered}>
            <MarkButton isPhone={isPhone} />
          </div>
        </div>
      </main>

      <div className="fc-shell__status" inert={stageCovered}>
        <StatusBar meta={meta} compact={isPhone} />
      </div>

      <PanelEnvironmentProvider value={environment}>
        {layersOpen ? (
          <PanelFrame
            panelKey={LAYERS_PARAM}
            title="Layers"
            onClose={toggleLayers}
            fallbackFocus={() => layersButton.current}
          >
            <LayerPanel meta={meta} />
          </PanelFrame>
        ) : (
          <Routes>
            <Route path="/" element={bareMap ? null : <ExplorePanel meta={meta} />} />
            <Route path="/mark/finding/:publicId" element={<ChangeShapePanel meta={meta} />} />
            <Route path="/mark/:draftId?" element={<MarkPanel meta={meta} />} />
            <Route path="/f/:id" element={<FindingPanel meta={meta} />} />
            <Route path={REVIEW_PATH} element={<ReviewPanel meta={meta} />} />
            <Route path={HELP_PATH} element={<HelpPanel meta={meta} />} />
            <Route path={`${HELP_PATH}/:kind`} element={<HelpKindPanel meta={meta} />} />
            <Route path={SCAN_PATH} element={<ScanPanel meta={meta} />} />
            <Route path={ACTIVITY_PATH} element={<ActivityPanel meta={meta} />} />
            <Route path="/account" element={<AccountPage />} />
            <Route path={PROFILE_ROUTE} element={<PersonPanel meta={meta} />} />
            <Route path={MOD_ROUTE} element={<ModerationPanel meta={meta} />} />
            <Route path={EMAIL_LINK_PATH} element={<EmailLinkPage />} />
            <Route path="/r/:id" element={<RecordPage />} />
            <Route path={RECORD_SEARCH_PATH} element={<RecordSearchPanel />} />
            <Route path={ELSEWHERE_PATH} element={<OpenElsewherePanel />} />
            <Route path={PROFILE_PATH} element={<ProfilePanel />} />
            <Route path={RECENT_MENTIONS_PATH} element={<RecentMentionsPanel meta={meta} />} />
            <Route path={INVESTIGATIONS_PATH} element={<InvestigationsPanel />} />
            <Route path="/i/:id" element={<InvestigationPage meta={meta} />} />
            <Route path={GUIDE_PATH} element={<GuidePanel meta={meta} />} />
            <Route path={ABOUT_PATH} element={<AboutPanel meta={meta} />} />
            <Route path={NOTICE_ROUTE} element={<NoticePanel meta={meta} />} />
            {Gallery ? (
              <Route
                path="/_ui"
                element={
                  <PanelFrame panelKey="/_ui" title="Interface kit" subtitle="Development only">
                    <Suspense fallback={null}>
                      <Gallery meta={meta} />
                    </Suspense>
                  </PanelFrame>
                }
              />
            ) : null}
            <Route path="*" element={<NotFoundPanel />} />
          </Routes>
        )}
      </PanelEnvironmentProvider>

      {isPhone ? <TabBar /> : null}

      <AccountLayer meta={meta} />
      <LiveEvents />

      <ToastViewport />
    </div>
  );
}
