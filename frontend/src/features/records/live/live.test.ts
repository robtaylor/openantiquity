import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ABERDEENSHIRE_LIVE,
  ADS_LIVE,
  BRISTOL_LIVE,
  DARTMOOR_LIVE,
  HOSTILE_LIVE_ANSWER,
  LIVE_SOURCES,
  SINGLE_RECORD_LIVE,
  WILTSHIRE_LIVE,
  WILTSHIRE_RECORDED_ANSWER,
} from "../../../test/fixtures/records.js";
import {
  creditableOnScreen,
  LiveCatalogueError,
  liveRequestUrl,
  liveSourceFrom,
  liveSourcesFrom,
} from "./catalogue.js";
import { fetchLiveRecords, LIVE_TIMEOUT_MS, LiveSourceError, MAX_ANSWER_BYTES } from "./client.js";
import { fillLinkTemplate, LiveResponseError, MAX_LIVE_RECORDS, parseLiveAnswer } from "./parse.js";

const AREA = { west: -1.86, south: 51.426, east: -1.848, north: 51.431 };
/** How a plain GeoJSON source is read, with the name in `name` and no id field. */
const GEOJSON = { format: "geojson", nameField: "name", idField: null, linkTemplate: null } as const;

function source(item = WILTSHIRE_LIVE) {
  const found = liveSourceFrom(item);
  if (!found) throw new Error(`${item.key} should be usable`);
  return found;
}

describe("the live catalogue", () => {
  it("keeps the sources that can be asked about an area or a point, and drops one that wants a record id", () => {
    expect(liveSourcesFrom(LIVE_SOURCES).map((item) => item.key)).toEqual([
      WILTSHIRE_LIVE.key,
      ABERDEENSHIRE_LIVE.key,
      DARTMOOR_LIVE.key,
    ]);
    expect(liveSourceFrom(SINGLE_RECORD_LIVE)).toBeNull();
    const point = liveSourceFrom({
      ...WILTSHIRE_LIVE,
      key: "wiki",
      query_pattern: "https://commons.wikimedia.org/w/api.php?ggscoord={lat}|{lon}&origin=*",
    });
    expect(point?.query).toBe("point");
  });

  it("leaves out a source it can't credit as its publisher asks: a credit per record, or no link to its records", () => {
    // The Archaeology Data Service's terms and credit are per record, and Bristol's per contributing HER.
    expect(liveSourceFrom(ADS_LIVE)).toBeNull();
    expect(liveSourceFrom(BRISTOL_LIVE)).toBeNull();
    expect(creditableOnScreen({ ...WILTSHIRE_LIVE, attribution: "Use the per-record Copyright field" })).toBe(false);
    expect(creditableOnScreen({ ...WILTSHIRE_LIVE, attribution: "Per file, from extmetadata Artist" })).toBe(false);
    expect(
      creditableOnScreen({
        ...WILTSHIRE_LIVE,
        attribution: "© Exmoor National Park Authority; records containing NRHE data: 'This record includes ...'",
      }),
    ).toBe(false);
    expect(creditableOnScreen({ ...WILTSHIRE_LIVE, link_template: null })).toBe(false);
    expect(creditableOnScreen({ ...WILTSHIRE_LIVE, link_template: " " })).toBe(false);
    expect(creditableOnScreen(WILTSHIRE_LIVE)).toBe(true);
    expect(liveSourceFrom(DARTMOOR_LIVE)?.attribution).toBe(DARTMOOR_LIVE.attribution);
  });

  it("refuses an address that isn't https, or that points at this site", () => {
    expect(
      liveSourceFrom({ ...WILTSHIRE_LIVE, query_pattern: "http://example.org/q?b={west},{south},{east},{north}" }),
    ).toBeNull();
    expect(
      liveSourceFrom({ ...WILTSHIRE_LIVE, query_pattern: "javascript:alert({west}{south}{east}{north})" }),
    ).toBeNull();
    expect(() => liveRequestUrl(source(), AREA, "https://maps.wiltshire.gov.uk")).toThrow(LiveCatalogueError);
  });

  it("keeps the catalogue's reading hints: format, fields, cap and lowest zoom", () => {
    expect(source()).toMatchObject({
      format: "geojson",
      nameField: "Name",
      idField: "MonUID",
      limitParam: "resultRecordCount",
      maxLimit: 1000,
      minZoom: 13,
    });
    // A source with no lowest zoom of its own is asked from zoom 13.
    expect(source({ ...WILTSHIRE_LIVE, min_zoom: null }).minZoom).toBe(13);
    // An answer this browser has no reader for isn't offered.
    expect(liveSourceFrom({ ...WILTSHIRE_LIVE, answer_format: "ads_map" })).toBeNull();
  });

  it("asks for no more records than the map will draw, through the source's own cap parameter", () => {
    const url = new URL(liveRequestUrl(source(), AREA, "http://localhost"));
    expect(url.searchParams.get("resultRecordCount")).toBe(String(MAX_LIVE_RECORDS + 1));
    const small = new URL(liveRequestUrl(source({ ...WILTSHIRE_LIVE, max_limit: 50 }), AREA, "http://localhost"));
    expect(small.searchParams.get("resultRecordCount")).toBe("50");
    const uncapped = new URL(
      liveRequestUrl(source({ ...WILTSHIRE_LIVE, limit_param: null }), AREA, "http://localhost"),
    );
    expect(uncapped.searchParams.has("resultRecordCount")).toBe(false);
  });

  it("fills the area into the pattern, in the order the pattern asks for", () => {
    const url = new URL(liveRequestUrl(source(), AREA, "http://localhost"));
    expect(url.searchParams.get("geometry")).toBe("-1.86000,51.42600,-1.84800,51.43100");
    const ads = new URL(
      liveRequestUrl(
        { key: ADS_LIVE.key, query: "area", pattern: ADS_LIVE.query_pattern, limitParam: null, maxLimit: null },
        AREA,
        "http://localhost",
      ),
    );
    expect(ads.searchParams.get("bbox")).toBe("51.43100,-1.86000,51.42600,-1.84800");
  });
});

describe("reading a live answer", () => {
  it("reads the recorded Wiltshire answer, with each record's own address as its link", () => {
    const answer = parseLiveAnswer(WILTSHIRE_RECORDED_ANSWER, source());
    expect(answer.records.map((record) => record.name)).toEqual([
      "Avebury Vicarage",
      "Stone hole 41, Avebury henge",
      "Avebury",
      "Avebury Circle",
    ]);
    expect(answer.records[0]).toEqual({
      id: "MWI7839",
      name: "Avebury Vicarage",
      lon: -1.8587010167953852,
      lat: 51.42754558450793,
      url: "http://history.wiltshire.gov.uk/smr/getsmr.php?id=7753",
    });
  });

  it("keeps at most the cap and says it did", () => {
    const answer = parseLiveAnswer(WILTSHIRE_RECORDED_ANSWER, source(), 2);
    expect(answer.records).toHaveLength(2);
    expect(answer.truncated).toBe(true);
  });

  it("keeps a hostile name as text and drops a javascript: link", () => {
    const [record] = parseLiveAnswer(HOSTILE_LIVE_ANSWER, source()).records;
    expect(record?.name).toBe('<img src=x onerror="alert(1)">Evil');
    expect(record?.url).toBeNull();
  });

  it("reads the Archaeology Data Service's hits and MediaWiki's pages", () => {
    const ads = parseLiveAnswer(
      {
        hits: [
          {
            id: "abc",
            data: { title: { text: "Barrow cemetery" }, spatial: [{ geopoint: { lat: 51.4, lon: -1.8 } }] },
          },
        ],
      },
      { format: "ads_search", nameField: "data.title.text", idField: "id", linkTemplate: ADS_LIVE.link_template },
    );
    expect(ads.records).toEqual([
      {
        id: "abc",
        name: "Barrow cemetery",
        lon: -1.8,
        lat: 51.4,
        url: "https://archaeologydataservice.ac.uk/data-catalogue/resource/abc",
      },
    ]);
    const wiki = parseLiveAnswer(
      {
        query: {
          pages: { 7: { pageid: 7, title: "File:Avebury stones.jpg", coordinates: [{ lat: 51.42, lon: -1.85 }] } },
        },
      },
      {
        format: "mediawiki_query",
        nameField: "title",
        idField: "title",
        linkTemplate: "https://commons.wikimedia.org/wiki/{title}",
      },
    );
    expect(wiki.records[0]?.url).toBe("https://commons.wikimedia.org/wiki/File%3AAvebury%20stones.jpg");
    expect(parseLiveAnswer({ batchcomplete: "" }, { ...GEOJSON, format: "mediawiki_query" }).records).toEqual([]);
  });

  it("reads names and ids only from the fields the catalogue names, never by guessing", () => {
    const answer = parseLiveAnswer(
      {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            id: 9,
            geometry: { type: "Point", coordinates: [-1.8, 51.4] },
            properties: { Name: "Not the name field", Filename: "OBL-1.jpg" },
          },
        ],
      },
      { ...GEOJSON, idField: "Filename" },
    );
    expect(answer.records[0]).toMatchObject({ id: "OBL-1.jpg", name: "Record OBL-1.jpg" });
    // With no id field the feature's own id is used.
    const plain = parseLiveAnswer(
      {
        type: "FeatureCollection",
        features: [{ type: "Feature", id: 9, geometry: { type: "Point", coordinates: [-1.8, 51.4] }, properties: {} }],
      },
      GEOJSON,
    );
    expect(plain.records[0]?.id).toBe("9");
  });

  it("reads each format by its own reader, so one shape isn't taken for another", () => {
    expect(() => parseLiveAnswer({ hits: [] }, GEOJSON)).toThrow(LiveResponseError);
    expect(() =>
      parseLiveAnswer({ type: "FeatureCollection", features: [] }, { ...GEOJSON, format: "ads_search" }),
    ).toThrow(LiveResponseError);
  });

  it("says an answer was cut short when the source says it held back more", () => {
    // It was asked for four, and ArcGIS says it had more.
    expect(parseLiveAnswer(WILTSHIRE_RECORDED_ANSWER, source()).truncated).toBe(true);
    const whole = { ...WILTSHIRE_RECORDED_ANSWER, exceededTransferLimit: false, properties: {} };
    expect(parseLiveAnswer(whole, source()).truncated).toBe(false);
    const ads = parseLiveAnswer(
      { total: { value: 900 }, hits: [] },
      { format: "ads_search", nameField: null, idField: "id", linkTemplate: null },
    );
    expect(ads.truncated).toBe(true);
  });

  it("treats an error object or an unknown shape as unreadable", () => {
    expect(() => parseLiveAnswer({ error: { code: 400, message: "Invalid query" } }, source())).toThrow(
      LiveResponseError,
    );
    expect(() => parseLiveAnswer({ rows: [] }, source())).toThrow(LiveResponseError);
    expect(() => parseLiveAnswer("nope", source())).toThrow(LiveResponseError);
  });

  it("skips records with no position it can draw, and gives each one a distinct id", () => {
    const answer = parseLiveAnswer(
      {
        type: "FeatureCollection",
        features: [
          { type: "Feature", geometry: null, properties: { Name: "Nowhere" } },
          { type: "Feature", id: 1, geometry: { type: "Point", coordinates: [-1.8, 51.4] }, properties: {} },
          {
            type: "Feature",
            id: 1,
            geometry: {
              type: "Polygon",
              coordinates: [
                [
                  [-1.8, 51.4],
                  [-1.7, 51.4],
                  [-1.7, 51.5],
                  [-1.8, 51.4],
                ],
              ],
            },
            properties: { name: "A field" },
          },
        ],
      },
      GEOJSON,
    );
    expect(answer.records.map((record) => [record.id, record.name, record.lon, record.lat])).toEqual([
      ["1", "Record 1", -1.8, 51.4],
      ["1#2", "A field", -1.75, 51.45],
    ]);
  });
});

describe("fillLinkTemplate", () => {
  it("encodes each value, and lets only http and https through", () => {
    expect(fillLinkTemplate("https://example.org/r/{id lower-case}/", { id: "RC8kn" })).toBe(
      "https://example.org/r/rc8kn/",
    );
    expect(fillLinkTemplate("https://example.org/r/{id}", { id: "../../evil?x=1" })).toBe(
      "https://example.org/r/..%2F..%2Fevil%3Fx%3D1",
    );
    expect(fillLinkTemplate("{URL}", { URL: "javascript:alert(1)" })).toBeNull();
    expect(fillLinkTemplate("{URL}", { URL: "data:text/html,hi" })).toBeNull();
    expect(fillLinkTemplate("https://example.org/{missing}", {})).toBeNull();
    expect(fillLinkTemplate(null, { id: 1 })).toBeNull();
  });
});

describe("fetchLiveRecords", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("asks the publisher directly, with no cookies, and reads the answer", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(WILTSHIRE_RECORDED_ANSWER), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const answer = await fetchLiveRecords(source(), AREA);
    expect(answer.records).toHaveLength(4);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new URL(url).host).toBe("maps.wiltshire.gov.uk");
    expect(init).toMatchObject({ mode: "cors", credentials: "omit", method: "GET" });
  });

  it("calls a browser that gets no readable answer refused", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))),
    );
    await expect(fetchLiveRecords(source(), AREA)).rejects.toMatchObject({ kind: "refused" });
  });

  it("calls an error status or an unreadable answer failed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("oops", { status: 500 })),
    );
    await expect(fetchLiveRecords(source(), AREA)).rejects.toMatchObject({
      kind: "failed",
      message: expect.stringMatching(/500/),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<html>", { status: 200 })),
    );
    await expect(fetchLiveRecords(source(), AREA)).rejects.toBeInstanceOf(LiveSourceError);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ error: { message: "no" } }), { status: 200 })),
    );
    await expect(fetchLiveRecords(source(), AREA)).rejects.toMatchObject({ kind: "failed" });
  });

  it("gives up on a source that sends its headers and then never finishes", async () => {
    vi.useFakeTimers();
    try {
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new TextEncoder().encode('{"type":"FeatureCollection","features":['));
        },
      });
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => new Response(body, { status: 200 })),
      );
      const pending = fetchLiveRecords(source(), AREA);
      const settled = expect(pending).rejects.toMatchObject({ kind: "failed", message: "It didn't answer in time." });
      await vi.advanceTimersByTimeAsync(LIVE_TIMEOUT_MS + 1);
      await settled;
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops reading an answer past the size limit, whether or not it says how long it is", async () => {
    const chunk = new Uint8Array(1_000_000).fill(32);
    let sent = 0;
    const endless = () =>
      new ReadableStream<Uint8Array>({
        pull(controller) {
          sent += chunk.byteLength;
          controller.enqueue(chunk);
        },
      });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(endless(), { status: 200 })),
    );
    await expect(fetchLiveRecords(source(), AREA)).rejects.toMatchObject({
      kind: "failed",
      message: "Its answer was too big to show.",
    });
    expect(sent).toBeLessThanOrEqual(MAX_ANSWER_BYTES + 2 * chunk.byteLength);
  });

  it("passes a cancellation on as it is, not as a failure", async () => {
    const controller = new AbortController();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
          }),
      ),
    );
    const pending = fetchLiveRecords(source(), AREA, controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
