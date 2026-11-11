import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ADS_LIVE,
  BRISTOL_LIVE,
  HOSTILE_LIVE_ANSWER,
  LIVE_SOURCES,
  SINGLE_RECORD_LIVE,
  WILTSHIRE_LIVE,
  WILTSHIRE_RECORDED_ANSWER,
} from "../../../test/fixtures/records.js";
import { LiveCatalogueError, liveRequestUrl, liveSourceFrom, liveSourcesFrom } from "./catalogue.js";
import { fetchLiveRecords, LiveSourceError } from "./client.js";
import { fillLinkTemplate, LiveResponseError, parseLiveAnswer } from "./parse.js";

const AREA = { west: -1.86, south: 51.426, east: -1.848, north: 51.431 };

function source(item = WILTSHIRE_LIVE) {
  const found = liveSourceFrom(item);
  if (!found) throw new Error(`${item.key} should be usable`);
  return found;
}

describe("the live catalogue", () => {
  it("keeps the sources that can be asked about an area or a point, and drops one that wants a record id", () => {
    expect(liveSourcesFrom(LIVE_SOURCES).map((item) => item.key)).toEqual([
      WILTSHIRE_LIVE.key,
      ADS_LIVE.key,
      BRISTOL_LIVE.key,
    ]);
    expect(liveSourceFrom(SINGLE_RECORD_LIVE)).toBeNull();
    const point = liveSourceFrom({
      ...ADS_LIVE,
      key: "wiki",
      query_pattern: "https://commons.wikimedia.org/w/api.php?ggscoord={lat}|{lon}&origin=*",
    });
    expect(point?.query).toBe("point");
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

  it("fills the area into the pattern, in the order the pattern asks for", () => {
    const url = new URL(liveRequestUrl(source(), AREA, "http://localhost"));
    expect(url.searchParams.get("geometry")).toBe("-1.86000,51.42600,-1.84800,51.43100");
    const ads = new URL(liveRequestUrl(source(ADS_LIVE), AREA, "http://localhost"));
    expect(ads.searchParams.get("bbox")).toBe("51.43100,-1.86000,51.42600,-1.84800");
  });
});

describe("reading a live answer", () => {
  it("reads the recorded Wiltshire answer, with each record's own address as its link", () => {
    const answer = parseLiveAnswer(WILTSHIRE_RECORDED_ANSWER, source());
    expect(answer.truncated).toBe(false);
    expect(answer.records.map((record) => record.name)).toEqual([
      "Avebury Vicarage",
      "Stone hole 41, Avebury henge",
      "Avebury",
      "Avebury Circle",
    ]);
    expect(answer.records[0]).toEqual({
      id: "20841084",
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
      source(ADS_LIVE),
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
      { linkTemplate: "https://commons.wikimedia.org/wiki/{title}" },
    );
    expect(wiki.records[0]?.url).toBe("https://commons.wikimedia.org/wiki/File%3AAvebury%20stones.jpg");
    expect(parseLiveAnswer({ batchcomplete: "" }, { linkTemplate: null }).records).toEqual([]);
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
            properties: { Name: "A field" },
          },
        ],
      },
      { linkTemplate: null },
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
