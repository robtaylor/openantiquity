import type {
  ContextLinks,
  LinkedFindingPage,
  LiveSourceOut,
  RecordOut,
  RecordPage,
  SourceRef,
} from "../../features/records/api.js";
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

/** The gazetteer the search box's place names come from. */
export const OS_NAMES_SOURCE: SourceRef = {
  key: "os-open-names",
  name: "OS Open Names",
  publisher: "Ordnance Survey",
  licence: "OGL v3.0",
  licence_url: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  attribution: "Contains OS data © Crown copyright and database right 2026",
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
    source: OS_NAMES_SOURCE,
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
    source: OS_NAMES_SOURCE,
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

/** What `GET /records/{id}/findings` answers for the avenue: the findings whose evidence links it. */
export const AVENUE_LINKED_FINDINGS: LinkedFindingPage = {
  items: [
    {
      public_id: "f-7k2m9q",
      title: "Bank beside the avenue",
      feature_class: "linear_bank_or_ditch",
      tier: "seen",
      state: "known",
    },
    {
      public_id: "f-3p8x1z",
      title: "Low mound near the stones",
      feature_class: "round_barrow",
      tier: "spotted",
      state: "open",
    },
  ],
  next_cursor: null,
};

/** What `GET /context/links` answers for a spot at Avebury. */
export const CONTEXT_LINKS: ContextLinks = {
  grid_ref: "SU 1023 6987",
  items: [
    {
      key: "he-apex-viewer",
      shows: "aerial_photographs",
      name: "Historic England Aerial Photo Explorer at a point",
      title: "Historic England Aerial Photo Explorer",
      url: "https://historicengland.org.uk/images-books/archive/collections/aerial-photos/?lat=51.42860&lon=-1.85420",
      coverage: "england",
      verified: "not_tested",
      no_frame: true,
    },
    {
      key: "nls-explore-at-point",
      shows: "historic_maps",
      name: "NLS georeferenced maps viewer at a point",
      title: "National Library of Scotland maps",
      url: "https://maps.nls.uk/geo/explore/#zoom=15&lat=51.42860&lon=-1.85420",
      coverage: "gb",
      verified: "yes",
      no_frame: false,
    },
    {
      key: "britain-from-above-map",
      shows: "aerial_photographs",
      name: "Britain from Above map at a point",
      title: "Britain from Above",
      url: "https://britainfromabove.org.uk/en/map?lat=51.42860&lon=-1.85420",
      coverage: "uk",
      verified: "redirect_only",
      no_frame: false,
    },
    {
      key: "hostile-link",
      shows: "other",
      name: "<script>alert(1)</script>A link that isn't one",
      title: "<script>alert(1)</script>A link that isn't one",
      url: "javascript:alert(1)",
      coverage: "wider",
      verified: "yes",
      no_frame: true,
    },
  ],
};

/**
 * Entries of the live catalogue, copied from the backend's
 * `data/live_sources.json`. The server sends only the sources it shows
 * (`shown`), each with the credit and licence to show. Wiltshire,
 * Wolverhampton and Dartmoor are credited in one line for the whole source.
 * Wikimedia Commons is credited file by file, from fields of each answer.
 * The Archaeology Data Service and Bristol aren't shown, so the server
 * leaves them out; they are here to prove the browser leaves them out too,
 * as it does one that asks for a single record rather than an area.
 */
export const WILTSHIRE_LIVE: LiveSourceOut = {
  key: "wiltshire-her-monuments",
  name: "Wiltshire and Swindon HER monuments (daily extract)",
  publisher: "Wiltshire Council",
  coverage: "england",
  endpoint: "https://maps.wiltshire.gov.uk/arcgis/rest/services/Website/Monuments/MapServer/2",
  query_pattern:
    "https://maps.wiltshire.gov.uk/arcgis/rest/services/Website/Monuments/MapServer/2/query?where=1%3D1&geometry={west},{south},{east},{north}&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&f=geojson",
  response_fields:
    "GeoJSON FeatureCollection: features[].properties (fields listed in gotchas), features[].geometry in EPSG:4326 via outSR=4326; MonUID (MWInnn), PrefRef, RecordType, Name, MonType, Period, URL",
  licence: "Unstated. Service sits in the 'Website' folder, not Wiltshire's 'OpenData' folder.",
  attribution: "Wiltshire Council Archaeology Service (Wiltshire and Swindon HER)",
  link_template: "{URL}",
  limits: "maxRecordCount 1000; pagination supported",
  answer_format: "geojson",
  name_field: "Name",
  id_field: "MonUID",
  limit_param: "resultRecordCount",
  max_limit: 1000,
  min_zoom: 13,
  shown: true,
  credit: "Wiltshire Council Archaeology Service (Wiltshire and Swindon HER)",
  licence_label: "No licence stated",
  homepage: "https://services.wiltshire.gov.uk/HistoryEnvRecord/Home/Index",
  credit_field: null,
  licence_field: null,
  preferred_credit_field: null,
};

export const ADS_LIVE: LiveSourceOut = {
  key: "ads-catalogue-search",
  name: "ADS Data Catalogue search (bbox)",
  publisher: "Archaeology Data Service, University of York",
  coverage: "uk",
  endpoint: "https://archaeologydataservice.ac.uk/data-catalogue-api/api/search",
  query_pattern:
    "https://archaeologydataservice.ac.uk/data-catalogue-api/api/search?q=&page=1&bbox={north},{west},{south},{east}",
  response_fields:
    "total.value; hits[].id; hits[].data.title.text; data.description.text; data.resourceType; data.ariadneSubject[].prefLabel; data.spatial[].geopoint {lat,lon} or boundingbox/polygon WKT with centroid; data.landingPage (null for many inventory records); data.accessRights; data.publisher[]; data.originalId; data.otherId",
  licence:
    "Per record (accessRights). ADS-published records: ADS Terms of Use and Access (research, learning and teaching only; no supply to third parties). PAS: CC-BY. HES and Historic England wrecks: OGL v3. RCAHMW: CC BY NC ND. No API terms published.",
  attribution:
    "Original depositor, funder if different, and 'Archaeology Data Service (distributor)' with DOI or record link",
  link_template: "https://archaeologydataservice.ac.uk/data-catalogue/resource/{id}",
  limits:
    "No published limits; about 350 requests at 1 per second saw no throttling. 50 per page, 10,000-result window.",
  answer_format: "ads_search",
  name_field: "data.title.text",
  id_field: "id",
  limit_param: "size",
  max_limit: 50,
  min_zoom: 14,
  shown: false,
  credit: null,
  licence_label: null,
  homepage: "https://archaeologydataservice.ac.uk/",
  credit_field: null,
  licence_field: null,
  preferred_credit_field: null,
};

export const BRISTOL_LIVE: LiveSourceOut = {
  key: "bristol-kyp-her-2026",
  name: "Know Your Place HER layer: Bristol",
  publisher: "Bristol City Council on behalf of Know Your Place partner HERs",
  coverage: "england",
  endpoint: "https://maps2.bristol.gov.uk/server2/rest/services/ext/her_2026/MapServer/34",
  query_pattern:
    "https://maps2.bristol.gov.uk/server2/rest/services/ext/her_2026/MapServer/34/query?where=1%3D1&geometry={west},{south},{east},{north}&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&f=geojson",
  response_fields:
    "GeoJSON FeatureCollection: features[].properties (fields listed in gotchas), features[].geometry in EPSG:4326 via outSR=4326",
  licence: "'GIS User Agreement for external use'",
  attribution: "Per source HER; service copyrightText 'Bristol City Council'",
  link_template: null,
  limits: "maxRecordCount 1000 or 2000 per service; pagination supported",
  answer_format: "geojson",
  name_field: null,
  id_field: "PRN",
  limit_param: "resultRecordCount",
  max_limit: 1000,
  min_zoom: 13,
  shown: false,
  credit: null,
  licence_label: null,
  homepage: "https://maps.bristol.gov.uk/kyp/",
  credit_field: null,
  licence_field: null,
  preferred_credit_field: null,
};

export const WOLVERHAMPTON_LIVE: LiveSourceOut = {
  key: "wolverhampton-walsall-her",
  name: "Wolverhampton and Walsall HER",
  publisher: "City of Wolverhampton Council",
  coverage: "england",
  endpoint: "https://services2.arcgis.com/5K9ykSNwoxdIgeYH/arcgis/rest/services/HER_points_260121/FeatureServer/0",
  query_pattern:
    "https://services2.arcgis.com/5K9ykSNwoxdIgeYH/arcgis/rest/services/HER_points_260121/FeatureServer/0/query?where=1%3D1&geometry={west},{south},{east},{north}&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&f=geojson",
  response_fields:
    "GeoJSON FeatureCollection: features[].properties (fields listed in gotchas), features[].geometry in EPSG:4326 via outSR=4326; MonUID (MBLnnn), PrefRef, RecordType, Name, Summary, MonType, Period, Dates, More_info",
  licence:
    "Unstated on the ArcGIS items. The 2016 data.gov.uk record cites 'Public Sector End User Licence - INSPIRE' and has no resources.",
  attribution: "City of Wolverhampton Council / Wolverhampton and Walsall HER",
  link_template: "{More_info}",
  limits: "maxRecordCount 2000",
  answer_format: "geojson",
  name_field: "Name",
  id_field: "MonUID",
  limit_param: "resultRecordCount",
  max_limit: 2000,
  min_zoom: 13,
  shown: true,
  credit: "City of Wolverhampton Council / Wolverhampton and Walsall HER",
  licence_label: "No licence stated",
  homepage: null,
  credit_field: null,
  licence_field: null,
  preferred_credit_field: null,
};

export const DARTMOOR_LIVE: LiveSourceOut = {
  key: "dnpa-dartmoor-her",
  name: "Dartmoor National Park HER",
  publisher: "Dartmoor National Park Authority",
  coverage: "england",
  endpoint:
    "https://services-eu1.arcgis.com/ygaMbwTQr2O0LMlb/arcgis/rest/services/Heritage_Environment_Record/FeatureServer/0",
  query_pattern:
    "https://services-eu1.arcgis.com/ygaMbwTQr2O0LMlb/arcgis/rest/services/Heritage_Environment_Record/FeatureServer/0/query?where=1%3D1&geometry={west},{south},{east},{north}&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&f=geojson",
  response_fields:
    "GeoJSON FeatureCollection: features[].properties (fields listed in gotchas), features[].geometry in EPSG:4326 via outSR=4326; monuid (MDVnnn), name, montype",
  licence: "Unstated. Item credits: '© Crown copyright and database rights 2026 OS AC0000823576'.",
  attribution: "Dartmoor National Park Authority; © Crown copyright and database rights 2026 OS AC0000823576",
  link_template:
    "https://historicengland.org.uk/listing/heritage-gateway/results/record/c39bc47e-3b72-4a06-9863-681629e456a2/{monuid}",
  limits: "maxRecordCount 2000",
  answer_format: "geojson",
  name_field: "name",
  id_field: "monuid",
  limit_param: "resultRecordCount",
  max_limit: 2000,
  min_zoom: 13,
  shown: true,
  credit: "Dartmoor National Park Authority; © Crown copyright and database rights 2026 OS AC0000823576",
  licence_label: "No licence stated",
  homepage: null,
  credit_field: null,
  licence_field: null,
  preferred_credit_field: null,
};

export const COMMONS_LIVE: LiveSourceOut = {
  key: "wikimedia-commons-geosearch",
  name: "Wikimedia Commons geosearch (photos near here)",
  publisher: "Wikimedia Foundation",
  coverage: "wider",
  endpoint: "https://commons.wikimedia.org/w/api.php",
  query_pattern:
    "https://commons.wikimedia.org/w/api.php?action=query&generator=geosearch&ggscoord={lat}|{lon}&ggsradius=1000&ggsnamespace=6&prop=coordinates|imageinfo&iiprop=url|extmetadata&iiurlwidth=320&iiextmetadatafilter=LicenseShortName|Artist|AttributionRequired|LicenseUrl|Attribution&format=json&origin=*",
  response_fields:
    "query.pages{}.title, coordinates[0].lat/lon, imageinfo[0].thumburl, imageinfo[0].extmetadata.Artist / LicenseShortName / AttributionRequired",
  licence: "Per file (sampled files were CC BY-SA 2.0)",
  attribution: "Per file, from extmetadata Artist, Attribution and LicenseShortName",
  link_template: "https://commons.wikimedia.org/wiki/{title}",
  limits: "ggsradius 10-10,000 m; 429 with retry-after: 8 on rapid anonymous bursts",
  answer_format: "mediawiki_query",
  name_field: "title",
  id_field: "title",
  limit_param: "ggslimit",
  max_limit: 500,
  min_zoom: 14,
  shown: true,
  credit: "Wikimedia Commons",
  licence_label: "Licensed file by file",
  homepage: "https://commons.wikimedia.org/",
  credit_field: "imageinfo.0.extmetadata.Artist.value",
  licence_field: "imageinfo.0.extmetadata.LicenseShortName.value",
  preferred_credit_field: "imageinfo.0.extmetadata.Attribution.value",
};

/** Asks for one record by id, so it can't be asked about an area and is left out. */
export const SINGLE_RECORD_LIVE: LiveSourceOut = {
  ...ADS_LIVE,
  key: "ads-catalogue-record",
  name: "ADS Data Catalogue single record",
  query_pattern: "https://archaeologydataservice.ac.uk/data-catalogue-api/api/getRecord/{id}",
  answer_format: "ads_record",
  limit_param: null,
  max_limit: null,
  min_zoom: null,
};

export const LIVE_SOURCES: LiveSourceOut[] = [
  WILTSHIRE_LIVE,
  ADS_LIVE,
  BRISTOL_LIVE,
  WOLVERHAMPTON_LIVE,
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
