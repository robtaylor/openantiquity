import { useQuery } from "@tanstack/react-query";
import { Landmark, MapPinned, Unplug } from "lucide-react";
import { type ReactNode, useEffect } from "react";
import { Link, useLocation, useParams } from "react-router";
import { ApiError, isTransient } from "../../api/client.js";
import type { Meta } from "../../api/meta.js";
import { useMeta } from "../../api/useMeta.js";
import { formatGridRef, wgs84ToGrid } from "../../map/gridref.js";
import { useMapStore, useViewAreaStore } from "../../map/store.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { AddToInvestigation } from "../investigations/AddToInvestigation.js";
import { useDocumentTitle } from "../placeholders.js";
import { firstArrival } from "../shell/arrival.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { fetchRecord, parseRecordId, type RecordOut, recordKeys } from "./api.js";
import { CategoryMark } from "./CategoryMark.js";
import { LinkedFindings } from "./LinkedFindings.js";
import { OriginalLink } from "./OriginalLink.js";
import { elsewherePath, wasOpenedFromMap } from "./paths.js";
import { SourceCredit } from "./SourceCredit.js";
import { precisionText, recordShape, useRecordSelection } from "./shape.js";
import { decodeEntities } from "./text.js";
import "./records.css";

/** The zoom a record is shown at when the map goes to it: close enough to see an earthwork, or a whole square. */
const RECORD_ZOOM = 16;
const SQUARE_ZOOM = 13.5;

function inside(bounds: readonly [number, number, number, number] | null, lon: number, lat: number): boolean {
  return bounds !== null && lon >= bounds[0] && lon <= bounds[2] && lat >= bounds[1] && lat <= bounds[3];
}

function showOnMap(record: RecordOut, imprecise: boolean): void {
  const { camera, requestCamera } = useMapStore.getState();
  const wanted = imprecise ? SQUARE_ZOOM : RECORD_ZOOM;
  requestCamera({ lng: record.lon, lat: record.lat, zoom: imprecise ? wanted : Math.max(camera.zoom, wanted) });
}

const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" });

function dateText(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : DATE.format(date);
}

/** Periods are shown by the vocabulary's label when the source used one of its ids, and as given otherwise. */
function periodLabel(meta: Meta, value: string): string {
  return meta.vocab.periods.find((period) => period.id === value)?.label ?? value;
}

function RecordBody({ record, meta }: { record: RecordOut; meta: Meta }) {
  const shape = recordShape(record);
  const grid = wgs84ToGrid(record.lon, record.lat);
  const copied = dateText(record.ingested_at);
  const changed = dateText(record.source_updated_at);
  const periods = record.periods.map((period) => periodLabel(meta, period));

  return (
    <div className="fc-record">
      <p className="fc-record__kind">
        <CategoryMark meta={meta} category={record.category} />
        {record.record_type ? <span className="fc-record__type">{record.record_type}</span> : null}
      </p>

      {periods.length > 0 || record.monument_types.length > 0 ? (
        <dl className="fc-record__facts">
          {periods.length > 0 ? (
            <div>
              <dt>Period</dt>
              <dd>{periods.join(", ")}</dd>
            </div>
          ) : null}
          {record.monument_types.length > 0 ? (
            <div>
              <dt>Recorded as</dt>
              <dd>{record.monument_types.join(", ")}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      {record.summary ? <p className="fc-record__summary">{record.summary}</p> : null}

      <section className="fc-record__section" aria-labelledby="record-where">
        <h3 className="fc-record__heading" id="record-where">
          Where it is
        </h3>
        {grid && !shape.imprecise ? <p className="fc-mono">{formatGridRef(grid, 8)}</p> : null}
        <p className="fc-record__precision">{precisionText(record.precision_m, shape.square)}</p>
        <div className="fc-record__actions">
          <Button
            size="sm"
            icon={<MapPinned size={16} aria-hidden />}
            onClick={() => showOnMap(record, shape.imprecise)}
          >
            Show on the map
          </Button>
          <Link className="fc-button fc-button--ghost fc-button--sm" to={elsewherePath(record.lon, record.lat)}>
            Open this spot elsewhere
          </Link>
          <AddToInvestigation item={() => ({ kind: "record", record_id: record.id })} what="This record" />
        </div>
      </section>

      <LinkedFindings recordId={record.id} meta={meta} />

      <section className="fc-record__section" aria-labelledby="record-source">
        <h3 className="fc-record__heading" id="record-source">
          Where it comes from
        </h3>
        <SourceCredit source={record.source} />
        <p className="fc-muted fc-record__small">
          Their reference: <span className="fc-mono">{record.external_id}</span>
          {changed ? ` · changed there on ${changed}` : null}
          {copied ? ` · copied here on ${copied}` : null}
        </p>
        <OriginalLink
          url={record.url}
          category={record.category}
          className="fc-button fc-button--secondary fc-button--md fc-record__original"
          fallback={<p className="fc-muted fc-record__small">The source doesn't give a page for this record.</p>}
        />
      </section>
    </div>
  );
}

/** `/r/:id`: one heritage record, drawn on the map while its page is open. */
export function RecordPage() {
  const params = useParams();
  const { pathname, state: arrivedWith } = useLocation();
  const meta = useMeta().data;
  const id = parseRecordId(params.id);
  const query = useQuery({
    queryKey: recordKeys.detail(id ?? 0),
    queryFn: ({ signal }) => {
      if (id === null) throw new Error("RecordPage asked for a record with no id");
      return fetchRecord(id, signal);
    },
    enabled: id !== null,
    staleTime: 10 * 60_000,
    retry: (failures, error) => failures < 1 && isTransient(error),
  });
  const record = query.data;
  const name = record ? decodeEntities(record.name) : "Heritage record";
  useDocumentTitle(name);

  // The open record is drawn on the map, and the map goes to it if it is out of sight, unless a
  // click on the map opened it: the person is then looking at the part of it they clicked.
  const openedFromMap = wasOpenedFromMap(arrivedWith);
  // It goes once for a visit to the page, and not again when the Layers panel has been over it.
  useEffect(() => {
    if (!record) return;
    const shape = recordShape(record);
    useRecordSelection.getState().setShape(shape.collection);
    if (firstArrival(pathname, "go to the record")) {
      const outOfSight = !inside(useViewAreaStore.getState().bounds, record.lon, record.lat);
      if (outOfSight && !openedFromMap) showOnMap(record, shape.imprecise);
    }
    return () => useRecordSelection.getState().setShape(null);
  }, [record, openedFromMap, pathname]);

  const notFound =
    id === null || (query.error instanceof ApiError && (query.error.status === 404 || query.error.status === 422));

  let body: ReactNode;
  if (notFound) {
    body = (
      <EmptyState
        icon={<Landmark size={22} />}
        title="There's no record at this address"
        action={
          <Link className="fc-button fc-button--secondary fc-button--md" to="/records">
            Search the records
          </Link>
        }
      >
        <p>It may have been taken out of the index when its source was last updated, or the link may be mistyped.</p>
      </EmptyState>
    );
  } else if (query.isError) {
    body = (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="This record couldn't be loaded"
        action={
          <Button variant="primary" onClick={() => void query.refetch()}>
            Try again
          </Button>
        }
      >
        <p>{query.error.message}</p>
      </EmptyState>
    );
  } else if (!record || !meta) {
    body = (
      <div role="status" className="fc-record">
        <span className="fc-visually-hidden">Loading the record</span>
        <Skeleton width="50%" height={18} />
        <Skeleton lines={4} />
      </div>
    );
  } else {
    body = <RecordBody record={record} meta={meta} />;
  }

  return (
    <PanelFrame panelKey={pathname} title={name} subtitle={record ? "Heritage record" : undefined}>
      {body}
    </PanelFrame>
  );
}
