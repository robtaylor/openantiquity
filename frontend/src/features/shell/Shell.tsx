import { Layers, MapPinPlus, Unplug } from "lucide-react";
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
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { IconButton } from "../../ui/IconButton.js";
import { SHEET_PEEK_HEIGHT, type SheetStop, sheetHeights } from "../../ui/Sheet.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { ToastViewport } from "../../ui/Toast.js";
import { toast } from "../../ui/toastStore.js";
import { LAYOUT } from "../../ui/tokens.js";
import { APP_NAME, NotFoundPanel, PLACEHOLDER_ROUTES, PlaceholderPanel } from "../placeholders.js";
import { BrandMark, ModeRail } from "./ModeRail.js";
import { PanelFrame } from "./PanelFrame.js";
import { type PanelEnvironment, PanelEnvironmentProvider } from "./panelContext.js";
import { SearchBox } from "./SearchBox.js";
import { TabBar } from "./TabBar.js";
import { useIsPhone, useIsShort, useWindowHeight } from "./useIsPhone.js";
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

  // The layer panel is a query parameter, so it can open over any mode and
  // the URL still says what is on screen.
  const layersOpen = searchParams.get("panel") === LAYERS_PARAM;
  const panelOpen = layersOpen || location.pathname !== "/";

  // Every sheet opens half-way. The stop is kept with the panel it belongs
  // to, so a different panel starts at half in the very render it appears.
  const panelKey = layersOpen ? LAYERS_PARAM : location.pathname;
  const [sheet, setSheet] = useState<{ panelKey: string; stop: SheetStop }>({ panelKey, stop: "half" });
  const sheetStop = sheet.panelKey === panelKey ? sheet.stop : "half";
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
  const toggleLayers = useCallback(() => {
    navigate({ pathname: location.pathname, search: layersOpen ? "" : `?panel=${LAYERS_PARAM}` });
  }, [layersOpen, location.pathname, navigate]);

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

      {isPhone ? null : <ModeRail compact={isShort} />}

      <main className="fc-shell__main">
        <MapView meta={meta} insets={insets} />

        <div className="fc-stage">
          <div className="fc-stage__search">
            <SearchBox />
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
          <div className="fc-stage__raking" inert={stageCovered}>
            <RakingControl meta={meta} />
          </div>
          <div className="fc-stage__primary" inert={stageCovered}>
            <Button
              variant="primary"
              size="lg"
              icon={<MapPinPlus size={20} aria-hidden />}
              onClick={() => toast("Marking a finding isn't built yet. It's the next piece of work.")}
            >
              Mark a finding
            </Button>
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
            <Route path="/" element={null} />
            {PLACEHOLDER_ROUTES.map((route) => (
              <Route key={route.path} path={route.path} element={<PlaceholderPanel route={route} />} />
            ))}
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

      <ToastViewport />
    </div>
  );
}
