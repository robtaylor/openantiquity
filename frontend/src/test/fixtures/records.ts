import type { ContextLinks, LiveSourceOut, RecordOut, RecordPage, SourceRef } from "../../features/records/api.js";
import type { GeoResult } from "../../features/search/api.js";
import { FINDINGS_CENTRE, offset } from "./findings.js";

/**
 * Stand-ins for the record index, the search box and the context catalogue,
 * around the fixture's opening view at Avebury, in the shapes the backend's
 * schema gives. Used by unit tests, the end-to-end stubs and the design
 * screenshots.
 */

export const NHLE_SOURCE: SourceRef = {
  key: "nhle-scheduled",
  name: "Scheduled monuments in England",
  publisher: "Historic England",
  licence: "OGL v3.0",
  licence_url: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  attribution: "© Historic England. Contains Ordnance Survey data © Crown copyright and database right.",
  reuse: "open",
};

const PAS_SOURCE: SourceRef = {
  key: "pas-finds",
  name: "Portable Antiquities Scheme finds",
  publisher: "British Museum",
  licence: "CC BY 4.0",
  licence_url: "https://creativecommons.org/licenses/by/4.0/",
  attribution: 'Portable Antiquities Scheme, <a href="https://finds.org.uk">finds.org.uk</a>',
  reuse: "open",
};

/** A source whose name, credit and links are hostile, as an outside service might send. */
const HOSTILE_SOURCE: SourceRef = {
  key: "hostile",
  name: '<b onmouseover="alert(1)">Hostile</b>',
  publisher: "<script>alert(1)</script>",
  licence: "Licence <img src=x onerror=alert(1)>",
  licence_url: "javascript:alert(1)",
  attribution: '<a href="javascript:alert(1)">Click me</a><script>alert(2)</script><img src=x onerror="alert(3)">',
  reuse: "open",
};

const AVENUE_AT = offset(0, -120);
const FIND_AT = offset(260, 180);

/** A scheduled monument with an outline, exact to a few metres. */
export const AVENUE_RECORD: RecordOut = {
  id: 101,
  source_key: NHLE_SOURCE.key,
  external_id: "1008411",
  name: "West Kennet Avenue",
  summary: "A double line of standing stones running south-east from Avebury henge towards the Sanctuary.",
  category: "designation",
  record_type: "Scheduled monument",
  monument_types: ["STONE AVENUE", "STANDING STONE"],
  periods: ["neolithic", "Late Neolithic"],
  lon: AVENUE_AT.lon,
  lat: AVENUE_AT.lat,
  precision_m: 5,
  url: "https://historicengland.org.uk/listing/the-list/list-entry/1008411",
  geometry: {
    type: "LineString",
    coordinates: [
      [AVENUE_AT.lon - 0.002, AVENUE_AT.lat + 0.0012],
      [AVENUE_AT.lon + 0.002, AVENUE_AT.lat - 0.0012],
    ],
  },
  source: NHLE_SOURCE,
  source_updated_at: "2026-09-14T00:00:00Z",
  ingested_at: "2026-11-10T03:12:00Z",
};

/** A find published only to a one-kilometre square. */
export const FIND_RECORD: RecordOut = {
  id: 202,
  source_key: PAS_SOURCE.key,
  external_id: "WILT-1A2B3C",
  name: "Roman coin",
  summary: null,
  category: "find",
  record_type: "Coin",
  monument_types: [],
  periods: ["Roman"],
  lon: FIND_AT.lon,
  lat: FIND_AT.lat,
  precision_m: 1000,
  url: "https://finds.org.uk/database/artefacts/record/id/123456",
  geometry: { type: "Point", coordinates: [FIND_AT.lon, FIND_AT.lat] },
  source: PAS_SOURCE,
  source_updated_at: null,
  ingested_at: "2026-11-10T03:12:00Z",
};

/** Everything an outside source could put in a record to break the page. */
export const HOSTILE_RECORD: RecordOut = {
  ...AVENUE_RECORD,
  id: 666,
  source_key: HOSTILE_SOURCE.key,
  external_id: '"><script>alert(1)</script>',
  name: '<img src=x onerror="alert(1)">Hostile record',
  summary: "<script>alert('summary')</script>",
  record_type: "<iframe src=javascript:alert(1)>",
  monument_types: ["<b>BOLD</b>"],
  url: "javascript:alert(document.cookie)",
  source: HOSTILE_SOURCE,
};

export const RECORDS_BY_ID: Readonly<Record<number, RecordOut>> = {
  [AVENUE_RECORD.id]: AVENUE_RECORD,
  [FIND_RECORD.id]: FIND_RECORD,
  [HOSTILE_RECORD.id]: HOSTILE_RECORD,
};

function summary(record: RecordOut): RecordPage["items"][number] {
  const { id, source_key, name, category, record_type, lon, lat, precision_m, url, source } = record;
  return { id, source_key, name, category, record_type, lon, lat, precision_m, url, source };
}

/** A first page of a record search, with a cursor to a second. */
export const RECORD_SEARCH_PAGE_1: RecordPage = {
  items: [summary(AVENUE_RECORD), summary(FIND_RECORD)],
  next_cursor: "page-2",
};

export const RECORD_SEARCH_PAGE_2: RecordPage = {
  items: [{ ...summary(AVENUE_RECORD), id: 103, name: "Avebury henge", category: "monument", record_type: "Henge" }],
  next_cursor: null,
};

/** What `GET /geo/search?q=ave` answers: a place, a record and a finding. */
export const GEO_RESULTS: GeoResult[] = [
  {
    type: "place",
    label: "Avebury",
    detail: "Wiltshire",
    lon: FINDINGS_CENTRE.lon,
    lat: FINDINGS_CENTRE.lat,
    zoom: 14,
    ref: "9",
    obscured: false,
    bbox: null,
    source: null,
  },
  {
    type: "record",
    label: AVENUE_RECORD.name,
    detail: `Scheduled monument · ${NHLE_SOURCE.name}`,
    lon: AVENUE_RECORD.lon,
    lat: AVENUE_RECORD.lat,
    zoom: 16,
    ref: String(AVENUE_RECORD.id),
    obscured: false,
    bbox: [
      AVENUE_RECORD.lon - 0.002,
      AVENUE_RECORD.lat - 0.0012,
      AVENUE_RECORD.lon + 0.002,
      AVENUE_RECORD.lat + 0.0012,
    ],
    source: NHLE_SOURCE,
  },
  {
    type: "place",
    label: "Avebury Trusloe",
    detail: "Wiltshire",
    lon: FINDINGS_CENTRE.lon - 0.01,
    lat: FINDINGS_CENTRE.lat,
    zoom: 15,
    ref: "10",
    obscured: false,
    bbox: null,
    source: null,
  },
  {
    type: "finding",
    label: "Enclosure near the avenue",
    detail: "Seen by others",
    lon: FINDINGS_CENTRE.lon + 0.004,
    lat: FINDINGS_CENTRE.lat + 0.002,
    zoom: 15,
    ref: "fx7k2p",
    obscured: false,
    bbox: null,
    source: null,
  },
];

export const GRIDREF_RESULT: GeoResult = {
  type: "gridref",
  label: "SU 10235 69874",
  detail: "A 10 m square",
  lon: FINDINGS_CENTRE.lon,
  lat: FINDINGS_CENTRE.lat,
  zoom: 17,
  ref: null,
  obscured: false,
  bbox: null,
  source: null,
};

/** What `GET /context/links` answers for a spot at Avebury. */
export const CONTEXT_LINKS: ContextLinks = {
  grid_ref: "SU 1023 6987",
  items: [
    {
      key: "he-apex-viewer",
      name: "Historic England Aerial Photo Explorer at a point",
      url: "https://historicengland.org.uk/images-books/archive/collections/aerial-photos/?lat=51.42860&lon=-1.85420",
      coverage: "england",
      verified: "not_tested",
      no_frame: true,
    },
    {
      key: "nls-explore-at-point",
      name: "NLS georeferenced maps viewer at a point",
      url: "https://maps.nls.uk/geo/explore/#zoom=15&lat=51.42860&lon=-1.85420",
      coverage: "gb",
      verified: "yes",
      no_frame: false,
    },
    {
      key: "britain-from-above-map",
      name: "Britain from Above map at a point",
      url: "https://britainfromabove.org.uk/en/map?lat=51.42860&lon=-1.85420",
      coverage: "uk",
      verified: "redirect_only",
      no_frame: false,
    },
    {
      key: "hostile-link",
      name: "<script>alert(1)</script>A link that isn't one",
      url: "javascript:alert(1)",
      coverage: "wider",
      verified: "yes",
      no_frame: true,
    },
  ],
};

/**
 * Entries of the live catalogue as the backend serves them. Wiltshire,
 * Aberdeenshire and Dartmoor credit the whole source in one line and link
 * each record, so they are offered. The others are not: the Archaeology Data
 * Service and Bristol credit each record differently, and one asks for a
 * single record rather than an area.
 */
export const WILTSHIRE_LIVE: LiveSourceOut = {
  key: "wiltshire-her-monuments",
  name: "Wiltshire and Swindon HER monuments (daily extract)",
  publisher: "Wiltshire Council",
  coverage: "england",
  endpoint: "https://maps.wiltshire.gov.uk/arcgis/rest/services/Website/Monuments/MapServer/2",
  query_pattern:
    "https://maps.wiltshire.gov.uk/arcgis/rest/services/Website/Monuments/MapServer/2/query?where=1%3D1&geometry={west},{south},{east},{north}&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&f=geojson",
  response_fields: "GeoJSON FeatureCollection; MonUID, PrefRef, RecordType, Name, MonType, Period, URL",
  licence: "Unstated. Service sits in the 'Website' folder, not Wiltshire's 'OpenData' folder.",
  attribution: "Wiltshire Council Archaeology Service (Wiltshire and Swindon HER)",
  link_template: "{URL}",
  limits: "maxRecordCount 1000; pagination supported",
};

export const ADS_LIVE: LiveSourceOut = {
  key: "ads-catalogue-search",
  name: "ADS Data Catalogue search (bbox)",
  publisher: "Archaeology Data Service, University of York",
  coverage: "uk",
  endpoint: "https://archaeologydataservice.ac.uk/data-catalogue-api/api/search",
  query_pattern:
    "https://archaeologydataservice.ac.uk/data-catalogue-api/api/search?q=&size=50&page=1&bbox={north},{west},{south},{east}",
  response_fields: "hits[].id; hits[].data.title.text; data.spatial[].geopoint {lat,lon}",
  licence: "Per record (accessRights). ADS-published records: ADS Terms of Use and Access.",
  attribution:
    "Original depositor, funder if different, and 'Archaeology Data Service (distributor)' with DOI or record link",
  link_template: "https://archaeologydataservice.ac.uk/data-catalogue/resource/{id}",
  limits: null,
};

export const BRISTOL_LIVE: LiveSourceOut = {
  key: "bristol-kyp-her-2026",
  name: "Know Your Place HER layer: Bristol",
  publisher: "Bristol City Council on behalf of Know Your Place partner HERs",
  coverage: "england",
  endpoint: "https://maps2.bristol.gov.uk/server2/rest/services/ext/her_2026/MapServer/34",
  query_pattern:
    "https://maps2.bristol.gov.uk/server2/rest/services/ext/her_2026/MapServer/34/query?where=1%3D1&geometry={west},{south},{east},{north}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326&f=geojson",
  response_fields: "GeoJSON FeatureCollection",
  licence: "'GIS User Agreement for external use'",
  attribution: "Per source HER; service copyrightText 'Bristol City Council'",
  link_template: null,
  limits: null,
};

export const ABERDEENSHIRE_LIVE: LiveSourceOut = {
  key: "aberdeenshire-her",
  name: "Aberdeenshire Council HER (Aberdeenshire, Moray, Angus, Aberdeen City)",
  publisher: "Aberdeenshire Council",
  coverage: "scotland",
  endpoint:
    "https://services2.arcgis.com/VIguPNrHLCWUHr2B/arcgis/rest/services/Historic_Environment_Records/FeatureServer/1",
  query_pattern:
    "https://services2.arcgis.com/VIguPNrHLCWUHr2B/arcgis/rest/services/Historic_Environment_Records/FeatureServer/1/query?where=1%3D1&geometry={west},{south},{east},{north}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326&f=geojson",
  response_fields: "GeoJSON FeatureCollection; HER_Refere, Name, Summary, Monument_U",
  licence: "'Copyright is reserved... intended to be used for personal research only'",
  attribution: "Aberdeenshire Council",
  link_template: "{Monument_U}",
  limits: "maxRecordCount 1000-2000",
};

export const DARTMOOR_LIVE: LiveSourceOut = {
  key: "dnpa-dartmoor-her",
  name: "Dartmoor National Park HER",
  publisher: "Dartmoor National Park Authority",
  coverage: "england",
  endpoint:
    "https://services-eu1.arcgis.com/ygaMbwTQr2O0LMlb/arcgis/rest/services/Heritage_Environment_Record/FeatureServer/0",
  query_pattern:
    "https://services-eu1.arcgis.com/ygaMbwTQr2O0LMlb/arcgis/rest/services/Heritage_Environment_Record/FeatureServer/0/query?where=1%3D1&geometry={west},{south},{east},{north}&geometryType=esriGeometryEnvelope&inSR=4326&outFields=*&outSR=4326&f=geojson",
  response_fields: "GeoJSON FeatureCollection; monuid, name, montype",
  licence: "Unstated. Item credits: '© Crown copyright and database rights 2026 OS AC0000823576'.",
  attribution: "Dartmoor National Park Authority; © Crown copyright and database rights 2026 OS AC0000823576",
  link_template:
    "https://historicengland.org.uk/listing/heritage-gateway/results/record/c39bc47e-3b72-4a06-9863-681629e456a2/{monuid}",
  limits: "maxRecordCount 2000",
};

/** Asks for one record by id, so it can't be asked about an area and is left out. */
export const SINGLE_RECORD_LIVE: LiveSourceOut = {
  ...ADS_LIVE,
  key: "ads-catalogue-record",
  name: "ADS Data Catalogue single record",
  query_pattern: "https://archaeologydataservice.ac.uk/data-catalogue-api/api/getRecord/{id}",
};

export const LIVE_SOURCES: LiveSourceOut[] = [
  WILTSHIRE_LIVE,
  ADS_LIVE,
  BRISTOL_LIVE,
  ABERDEENSHIRE_LIVE,
  DARTMOOR_LIVE,
  SINGLE_RECORD_LIVE,
];

/**
 * Wiltshire's map service, asked for a small box at Avebury on 11 November
 * 2026 with `resultRecordCount=4`. Recorded once and replayed, so no test
 * asks the real service anything. Editing fields that named council staff
 * were taken out.
 */
export const WILTSHIRE_RECORDED_ANSWER = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: 20841084,
      geometry: { type: "Point", coordinates: [-1.8587010167953852, 51.42754558450793] },
      properties: {
        OBJECTID: 20841084,
        MonUID: "MWI7839",
        PrefRef: "SU06NE525",
        RecordType: "FS",
        Name: "Avebury Vicarage",
        MonType: "FINDSPOT",
        Period: "Post Medieval",
        URL: "http://history.wiltshire.gov.uk/smr/getsmr.php?id=7753",
      },
    },
    {
      type: "Feature",
      id: 20841088,
      geometry: { type: "Point", coordinates: [-1.8558619323110508, 51.42970777865219] },
      properties: {
        OBJECTID: 20841088,
        MonUID: "MWI15562",
        PrefRef: "SU17SW182",
        RecordType: "MON",
        Name: "Stone hole 41, Avebury henge",
        MonType: "BURIAL",
        Period: "Bronze Age",
        URL: "http://history.wiltshire.gov.uk/smr/getsmr.php?id=15294",
      },
    },
    {
      type: "Feature",
      id: 20841596,
      geometry: { type: "Point", coordinates: [-1.8546010049999058, 51.426944919840494] },
      properties: {
        OBJECTID: 20841596,
        MonUID: "MWI13402",
        PrefRef: "SU16NW308",
        RecordType: "FS",
        Name: "Avebury",
        MonType: "FINDSPOT",
        Period: "Roman",
        URL: "http://history.wiltshire.gov.uk/smr/getsmr.php?id=14109",
      },
    },
    {
      type: "Feature",
      id: 20841618,
      geometry: { type: "Point", coordinates: [-1.8545666585398903, 51.4280613056132] },
      properties: {
        OBJECTID: 20841618,
        MonUID: "MWI14377",
        PrefRef: "SU16NW404",
        RecordType: "FS",
        Name: "Avebury Circle",
        MonType: "FINDSPOT",
        Period: "Early Medieval (Saxon)",
        URL: "http://history.wiltshire.gov.uk/smr/getsmr.php?id=14145",
      },
    },
  ],
  exceededTransferLimit: true,
  properties: { exceededTransferLimit: true },
} as const;

/** A live answer whose record carries a hostile name and a `javascript:` address. */
export const HOSTILE_LIVE_ANSWER = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      id: 1,
      geometry: { type: "Point", coordinates: [FINDINGS_CENTRE.lon, FINDINGS_CENTRE.lat] },
      properties: { Name: '<img src=x onerror="alert(1)">Evil', URL: "javascript:alert(1)" },
    },
  ],
};
