import { useQuery } from "@tanstack/react-query";
import { Crosshair, ExternalLink, Globe, Unplug } from "lucide-react";
import { type ReactNode, useEffect } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router";
import { isTransient } from "../../api/client.js";
import { safeHref } from "../../map/attribution.js";
import { coordinateText } from "../../map/StatusBar.js";
import { useMapStore } from "../../map/store.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { useDebounced } from "../../ui/useDebounced.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { type ContextLink, fetchContextLinks, recordKeys } from "./api.js";
import { ELSEWHERE_PATH, elsewherePath } from "./paths.js";
import { useRecordSelection } from "./shape.js";
import "./records.css";

/**
 * Headings for the coverages the link catalogue uses. A coverage it gains
 * later is shown under its own name until it has one here.
 */
const COVERAGE_LABELS: Readonly<Record<string, string>> = {
  england: "England",
  scotland: "Scotland",
  wales: "Wales",
  northern_ireland: "Northern Ireland",
  gb: "Great Britain",
  uk: "The whole UK",
  wider: "Anywhere",
};
const COVERAGE_ORDER = Object.keys(COVERAGE_LABELS);
/** How long the map must hold still before the links for its middle are asked for. */
const LINKS_SETTLE_MS = 500;

/** What the catalogue's `verified` says, for a link that wasn't checked to open the right place. */
function unverifiedNote(verified: string): string | null {
  if (verified === "yes") return null;
  if (verified === "redirect_only") return "Not checked: we could only see that it redirects.";
  return "Not checked: we couldn't test this link, so it may not open at the right place.";
}

export interface LinkGroup {
  coverage: string;
  label: string;
  links: ContextLink[];
}

/** The links grouped by the area each viewer covers, the most local first. Links that aren't web addresses are dropped. */
export function groupLinks(links: readonly ContextLink[]): LinkGroup[] {
  const groups = new Map<string, ContextLink[]>();
  for (const link of links) {
    if (!safeHref(link.url)) continue;
    const list = groups.get(link.coverage) ?? [];
    list.push(link);
    groups.set(link.coverage, list);
  }
  const rank = (coverage: string): number => {
    const index = COVERAGE_ORDER.indexOf(coverage);
    return index === -1 ? COVERAGE_ORDER.length : index;
  };
  return [...groups.entries()]
    .sort(([a], [b]) => rank(a) - rank(b))
    .map(([coverage, list]) => ({ coverage, label: COVERAGE_LABELS[coverage] ?? coverage, links: list }));
}

function readPoint(params: URLSearchParams): { lon: number; lat: number } | null {
  const lon = Number(params.get("lon"));
  const lat = Number(params.get("lat"));
  if (!params.has("lon") || !params.has("lat") || !Number.isFinite(lon) || !Number.isFinite(lat)) return null;
  if (Math.abs(lon) > 180 || Math.abs(lat) > 90) return null;
  return { lon: Number(lon.toFixed(5)), lat: Number(lat.toFixed(5)) };
}

function LinkItem({ link }: { link: ContextLink }) {
  const href = safeHref(link.url);
  if (!href) return null;
  const note = unverifiedNote(link.verified);
  return (
    <li className="fc-elsewhere__link">
      <a href={href} target="_blank" rel="noopener noreferrer external">
        <ExternalLink size={16} aria-hidden />
        <span>{link.name}</span>
        <span className="fc-visually-hidden"> (opens in a new tab)</span>
      </a>
      {note ? <p className="fc-elsewhere__note">{note}</p> : null}
    </li>
  );
}

/**
 * `/elsewhere?lon=&lat=`: the same spot in other people's viewers, which we
 * can't show inside Field Club, each opening in a new tab. Without a spot in
 * the address it uses the middle of the map.
 */
export function OpenElsewherePanel() {
  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const camera = useMapStore((state) => state.camera);
  useDocumentTitle("Open elsewhere");

  const given = readPoint(params);
  const wanted = given ?? { lon: Number(camera.lng.toFixed(5)), lat: Number(camera.lat.toFixed(5)) };
  const wantedZoom = Math.min(20, Math.max(1, Math.round(camera.zoom)));
  // The middle of the map follows a drag, so it is asked about once the map has stopped.
  const settled = useDebounced(`${wanted.lon},${wanted.lat},${wantedZoom}`, LINKS_SETTLE_MS);
  const [lon, lat, zoom] = settled.split(",").map(Number) as [number, number, number];
  const point = { lon, lat };
  const query = useQuery({
    queryKey: recordKeys.links(lon, lat, zoom),
    queryFn: ({ signal }) => fetchContextLinks(lon, lat, zoom, signal),
    staleTime: 60 * 60_000,
    retry: (failures, error) => failures < 1 && isTransient(error),
  });

  // The spot is ringed on the map while the panel is open.
  const ringed = given ? `${given.lon},${given.lat}` : null;
  useEffect(() => {
    if (ringed === null) return;
    const coordinates = ringed.split(",").map(Number) as [number, number];
    useRecordSelection.getState().setShape({
      type: "FeatureCollection",
      features: [{ type: "Feature", geometry: { type: "Point", coordinates }, properties: {} }],
    });
    return () => useRecordSelection.getState().setShape(null);
  }, [ringed]);

  const groups = query.data ? groupLinks(query.data.items) : [];
  let body: ReactNode;
  if (query.isError) {
    body = (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="The links couldn't be loaded"
        action={
          <Button variant="primary" onClick={() => void query.refetch()}>
            Try again
          </Button>
        }
      >
        <p>{query.error.message}</p>
      </EmptyState>
    );
  } else if (!query.data) {
    body = (
      <div role="status">
        <span className="fc-visually-hidden">Loading the links</span>
        <Skeleton lines={5} />
      </div>
    );
  } else if (groups.length === 0) {
    body = (
      <EmptyState icon={<Globe size={22} />} title="No other viewers cover this spot">
        <p>Try somewhere in the UK. Most of the viewers we link to cover one nation.</p>
      </EmptyState>
    );
  } else {
    body = groups.map((group) => (
      <section key={group.coverage} className="fc-elsewhere__group" aria-labelledby={`elsewhere-${group.coverage}`}>
        <h3 className="fc-record__heading" id={`elsewhere-${group.coverage}`}>
          {group.label}
        </h3>
        <ul className="fc-elsewhere__links">
          {group.links.map((link) => (
            <LinkItem key={link.key} link={link} />
          ))}
        </ul>
      </section>
    ));
  }

  return (
    <PanelFrame panelKey={pathname || ELSEWHERE_PATH} title="Open elsewhere" subtitle="This spot in other viewers">
      <div className="fc-elsewhere">
        <div className="fc-elsewhere__where">
          <p>{given ? "The spot you chose" : "The middle of the map"}</p>
          <p className="fc-mono">{query.data?.grid_ref ?? coordinateText(point.lon, point.lat)}</p>
          {given ? (
            <Button
              size="sm"
              variant="ghost"
              icon={<Crosshair size={16} aria-hidden />}
              onClick={() => navigate(elsewherePath(camera.lng, camera.lat), { replace: true })}
            >
              Use the middle of the map instead
            </Button>
          ) : (
            <p className="fc-field__hint">Right-click the map to choose another spot.</p>
          )}
        </div>
        <p className="fc-field__hint">Each opens in a new tab, on the publisher's own site.</p>
        {body}
      </div>
    </PanelFrame>
  );
}
