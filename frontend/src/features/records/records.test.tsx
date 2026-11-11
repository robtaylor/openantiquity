import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation } from "react-router";
import type { Mock } from "vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RECORD_LAYERS } from "../../map/overlayLayers.js";
import { useMapStore } from "../../map/store.js";
import { overlaySourceId } from "../../map/style.js";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import type { FakeMap } from "../../test/fakeMapLibre.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import {
  ABERDEENSHIRE_LIVE,
  ADS_LIVE,
  AVENUE_RECORD,
  BRISTOL_LIVE,
  CONTEXT_LINKS,
  DARTMOOR_LIVE,
  FIND_RECORD,
  HOSTILE_LIVE_ANSWER,
  HOSTILE_RECORD,
  LIVE_SOURCES,
  RECORD_SEARCH_PAGE_1,
  RECORD_SEARCH_PAGE_2,
  RECORDS_BY_ID,
  WILTSHIRE_LIVE,
  WILTSHIRE_RECORDED_ANSWER,
} from "../../test/fixtures/records.js";
import { json, mapReady, metaResponse, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import { useRecordFilters } from "./filters.js";
import type { FeatureCollection } from "./geojson.js";
import { useLiveStore } from "./live/store.js";
import { useRecordsOnScreen } from "./onScreen.js";
import { useRecordSearch } from "./searchStore.js";
import { useRecordSelection } from "./shape.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();
let api: ApiRoutes;
/** Requests to hosts other than this site, by host. */
let outside: Map<string, (url: URL) => Response | Promise<Response>>;

const RECORDS_SOURCE = overlaySourceId("records");

beforeEach(() => {
  for (const store of [useRecordFilters, useLiveStore, useRecordSearch, useRecordSelection, useRecordsOnScreen]) {
    (store as { setState: (state: unknown, replace: true) => void; getInitialState: () => unknown }).setState(
      store.getInitialState(),
      true,
    );
  }
  api = routeApi(harness.fetchMock(), {
    "GET /records/search": (call) =>
      json(call.url.searchParams.get("cursor") === "page-2" ? RECORD_SEARCH_PAGE_2 : RECORD_SEARCH_PAGE_1),
    "GET /context/links": () => json(CONTEXT_LINKS),
    "GET /context/live-sources": () => json({ items: LIVE_SOURCES }),
  });
  for (const record of Object.values(RECORDS_BY_ID)) api.on(`GET /records/${record.id}`, () => json(record));
  api.on("GET /records/999", () => apiError(404, "record_not_found", "No such record."));
  // Requests that leave the site go to `outside`, by host. Anything else falls through to the API routes.
  outside = new Map();
  const viaApi = harness.fetchMock().getMockImplementation();
  harness.fetchMock().mockImplementation(async (input: unknown, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    if (url.host !== "localhost") {
      const handler = outside.get(url.host);
      if (!handler) throw new TypeError(`Unexpected request to ${url.host}`);
      return handler(url);
    }
    return viaApi?.(input, init);
  });
});

/** The router's address, for a test to read. */
function Address() {
  const { pathname, search } = useLocation();
  return <output data-testid="address">{`${pathname}${search}`}</output>;
}

function outsideCalls(host: string): string[] {
  return (harness.fetchMock() as Mock).mock.calls
    .map(([input]) => new URL(String(input), "http://localhost"))
    .filter((url) => url.host === host)
    .map((url) => url.href);
}

function selection(map: FakeMap): FeatureCollection | undefined {
  return map.sourceData(`${RECORDS_SOURCE}-selection`) as FeatureCollection | undefined;
}

describe("a record's page", () => {
  it("shows what the record is, where it comes from, its licence and the original, and draws it", async () => {
    renderShell(`/r/${AVENUE_RECORD.id}`);
    const map = await mapReady();
    const panel = await screen.findByRole("complementary", { name: AVENUE_RECORD.name });
    expect(within(panel).getByText("Designations")).toBeInTheDocument();
    expect(within(panel).getByText("Scheduled monument")).toBeInTheDocument();
    // A period the vocabulary knows is shown by its label, and one it doesn't, as the source gave it.
    expect(within(panel).getByText(/Late Neolithic/)).toBeInTheDocument();
    expect(within(panel).getByText(/Exact to within about 5 m/)).toBeInTheDocument();
    expect(within(panel).getByText(AVENUE_RECORD.source.name)).toBeInTheDocument();
    const licence = within(panel).getByRole("link", { name: "OGL v3.0" });
    expect(licence).toHaveAttribute("href", AVENUE_RECORD.source.licence_url);
    expect(licence).toHaveAttribute("rel", expect.stringContaining("noopener"));
    const original = within(panel).getByRole("link", { name: /See the original record/ });
    expect(original).toHaveAttribute("href", AVENUE_RECORD.url);
    expect(original).toHaveAttribute("target", "_blank");
    expect(original.getAttribute("rel")?.split(" ")).toEqual(expect.arrayContaining(["noopener", "noreferrer"]));
    expect(within(panel).getByText(AVENUE_RECORD.source.attribution)).toBeInTheDocument();
    await waitFor(() => expect(selection(map)?.features.map((f) => f.geometry.type)).toEqual(["LineString", "Point"]));
  });

  it("draws a record published to a kilometre square as that square, dashed, and says so", async () => {
    // The map starts well away from the record, so its page has to go to it.
    window.history.replaceState(null, "", "/#m=12/53/-2/0/0");
    renderShell(`/r/${FIND_RECORD.id}`);
    const map = await mapReady();
    const panel = await screen.findByRole("complementary", { name: FIND_RECORD.name });
    expect(within(panel).getByText(/Published only to the one-kilometre square SU\d{4}/)).toBeInTheDocument();
    await waitFor(() => expect(selection(map)?.features).toHaveLength(1));
    expect(selection(map)?.features[0]?.geometry.type).toBe("Polygon");
    expect(selection(map)?.features[0]?.properties.imprecise).toBe(true);
    // Its page went to it, at a zoom that shows the whole square.
    expect(useMapStore.getState().camera).toMatchObject({ lng: FIND_RECORD.lon, lat: FIND_RECORD.lat, zoom: 13.5 });
  });

  it("puts a hostile record's words on the page as text, and links only to web addresses", async () => {
    const alerts = vi.spyOn(window, "alert").mockImplementation(() => {});
    renderShell(`/r/${HOSTILE_RECORD.id}`);
    await mapReady();
    const panel = await screen.findByRole("complementary", { name: HOSTILE_RECORD.name });
    expect(within(panel).getByText(HOSTILE_RECORD.summary ?? "")).toBeInTheDocument();
    expect(panel.querySelector("script, img, iframe, b")).toBeNull();
    for (const link of within(panel).queryAllByRole("link")) {
      const href = link.getAttribute("href") ?? "";
      expect(href.startsWith("/") || /^https?:/.test(href), href).toBe(true);
    }
    expect(within(panel).getByText("The source doesn't give a page for this record.")).toBeInTheDocument();
    // The licence's javascript: address is dropped, and its name kept as words.
    expect(within(panel).getByText(/Licence <img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    expect(alerts).not.toHaveBeenCalled();
  });

  it("says when there's no such record", async () => {
    renderShell("/r/999");
    await mapReady();
    expect(await screen.findByText("There's no record at this address")).toBeInTheDocument();
  });

  it("takes the record off the map when its page closes", async () => {
    const user = userEvent.setup();
    renderShell(`/r/${AVENUE_RECORD.id}`);
    const map = await mapReady();
    await screen.findByRole("complementary", { name: AVENUE_RECORD.name });
    await user.click(screen.getByRole("button", { name: "Close panel" }));
    await waitFor(() => expect(selection(map)?.features).toEqual([]));
  });
});

describe("records on the map", () => {
  it("opens a record's page when its square is clicked, and zooms into a count", async () => {
    renderShell();
    const map = await mapReady();
    map.rendered = [
      { id: 101, properties: { id: 101, source: "nhle-scheduled" }, layer: { id: RECORD_LAYERS.squares } },
    ];
    act(() => map.fire("click", { point: { x: 10, y: 10 }, lngLat: { lng: -1.85, lat: 51.43 } }));
    expect(await screen.findByRole("complementary", { name: AVENUE_RECORD.name })).toBeInTheDocument();

    const before = useMapStore.getState().camera.zoom;
    map.rendered = [
      { properties: { count: 12, category: "find", sources: "pas" }, layer: { id: RECORD_LAYERS.counts } },
    ];
    act(() => map.fire("click", { point: { x: 10, y: 10 }, lngLat: { lng: -1.9, lat: 51.4 } }));
    expect(useMapStore.getState().camera).toMatchObject({ lng: -1.9, lat: 51.4, zoom: before + 2 });
  });

  it("credits only the sources drawn on screen once the map has said which", async () => {
    renderShell();
    const map = await mapReady();
    // Until the map reports, every source is credited.
    expect(screen.getByRole("button", { name: /Historic England/ })).toBeInTheDocument();
    map.rendered = [];
    act(() => map.fire("idle"));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Historic England/ })).toBeNull());
    map.rendered = [
      {
        properties: { category: "designation", count: 3, sources: "nhle-scheduled" },
        layer: { id: RECORD_LAYERS.counts },
      },
    ];
    act(() => map.fire("idle"));
    expect(await screen.findByRole("button", { name: /Historic England/ })).toBeInTheDocument();
  });

  it("turns categories and sources off from the layer panel", async () => {
    const user = userEvent.setup();
    renderShell("/?panel=layers");
    const map = await mapReady();
    const kinds = screen.getByRole("group", { name: "Kinds of record to show" });
    const designations = within(kinds).getByRole("button", { name: "Designations" });
    expect(designations).toHaveAttribute("aria-pressed", "true");
    await user.click(designations);
    expect(designations).toHaveAttribute("aria-pressed", "false");
    expect(map.filters.get(RECORD_LAYERS.squares)).toEqual([
      "all",
      ["in", ["geometry-type"], ["literal", ["Point", "MultiPoint"]]],
      ["!", ["in", ["get", "category"], ["literal", ["designation"]]]],
    ]);
    await user.click(screen.getByText("Sources", { exact: true }));
    await user.click(
      within(screen.getByRole("group", { name: "Sources of designations to show" })).getByRole("button", {
        name: "Scheduled monuments in England",
      }),
    );
    expect(map.filters.get(RECORD_LAYERS.counts)).toEqual([
      "all",
      ["!", ["in", ["get", "category"], ["literal", ["designation"]]]],
      ["==", 1, 0],
    ]);
  });

  it("lists only the sources the records layer draws, by kind, folded away, with all and none", async () => {
    const [scheduled] = metaFixture.sources;
    if (!scheduled) throw new Error("The meta fixture has no source");
    const sources = [
      scheduled,
      { ...scheduled, key: "aim", name: "Aerial mapping", category: "monument" },
      { ...scheduled, key: "her", name: "County HER", category: "monument" },
      { ...scheduled, key: "ons-counties", name: "County boundaries", category: "boundary" },
      { ...scheduled, key: "os-names", name: "OS Open Names", category: "place" },
    ];
    api.on("GET /meta", () => metaResponse({ ...metaFixture, sources }));
    const user = userEvent.setup();
    renderShell("/?panel=layers");
    await mapReady();
    const folded = screen.getByText("Sources", { exact: true });
    expect(screen.queryByRole("group", { name: "Sources of monument records to show" })).not.toBeVisible();
    await user.click(folded);
    const monuments = screen.getByRole("group", { name: "Sources of monument records to show" });
    expect(
      within(monuments)
        .getAllByRole("button")
        .map((chip) => chip.textContent),
    ).toEqual(["Aerial mapping", "County HER"]);
    expect(screen.queryByText("County boundaries")).toBeNull();
    expect(screen.queryByText("OS Open Names")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Hide every source of monument records" }));
    expect(useRecordFilters.getState().hiddenSources).toEqual(["aim", "her"]);
    expect(screen.getByText("Sources (2 of 3 off)")).toBeInTheDocument();
    await user.click(within(monuments).getByRole("button", { name: "County HER" }));
    expect(useRecordFilters.getState().hiddenSources).toEqual(["aim"]);
    await user.click(screen.getByRole("button", { name: "Show every source of monument records" }));
    expect(useRecordFilters.getState().hiddenSources).toEqual([]);
  });

  it("opens other viewers for the spot that was right-clicked", async () => {
    renderShell();
    const map = await mapReady();
    act(() =>
      map.fire("contextmenu", {
        point: { x: 1, y: 1 },
        lngLat: { lng: -1.85421, lat: 51.42861 },
        preventDefault: () => {},
      }),
    );
    const panel = await screen.findByRole("complementary", { name: "Open elsewhere" });
    const link = await within(panel).findByRole("link", { name: /NLS georeferenced maps viewer/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")?.split(" ")).toEqual(expect.arrayContaining(["noopener", "noreferrer"]));
    expect(api.callsTo("GET /context/links")[0]?.url.searchParams.get("lon")).toBe("-1.85421");
    // Links nobody has checked carry a tag, explained once. A link that isn't a web address isn't shown at all.
    expect(within(panel).getAllByText("unchecked", { exact: true })).toHaveLength(2);
    expect(within(panel).getAllByText(/haven't been able to check/)).toHaveLength(1);
    expect(
      within(panel).getByRole("link", { name: /^Historic England Aerial Photo Explorer unchecked/ }),
    ).toBeVisible();
    expect(within(panel).queryByText(/at a point/)).toBeNull();
    expect(within(panel).queryByText(/A link that isn't one/)).toBeNull();
    expect(within(panel).getByRole("heading", { name: "England" })).toBeInTheDocument();
  });
});

describe("open elsewhere", () => {
  it("says once that no link could be checked, with no tag on each", async () => {
    api.on("GET /context/links", () =>
      json({ ...CONTEXT_LINKS, items: CONTEXT_LINKS.items.map((link) => ({ ...link, verified: "not_tested" })) }),
    );
    renderShell("/elsewhere?lon=-1.8542&lat=51.4286");
    const panel = await screen.findByRole("complementary", { name: "Open elsewhere" });
    await within(panel).findByRole("link", { name: /NLS georeferenced maps viewer/ });
    expect(within(panel).queryByText("unchecked", { exact: true })).toBeNull();
    expect(within(panel).getByText(/haven't been able to check these links/)).toBeInTheDocument();
  });
});

describe("the record search panel", () => {
  it("searches the map's view, pages on, and offers the results as GeoJSON", async () => {
    const user = userEvent.setup();
    renderShell("/records");
    await mapReady();
    const panel = await screen.findByRole("complementary", { name: "Search the records" });
    const first = await within(panel).findByRole("link", { name: AVENUE_RECORD.name });
    expect(first).toHaveAttribute("href", `/r/${AVENUE_RECORD.id}`);
    expect(within(panel).getByText(`From ${FIND_RECORD.source.name}`)).toBeInTheDocument();
    const call = api.callsTo("GET /records/search")[0];
    expect(call?.url.searchParams.get("bbox")).toMatch(/^-?\d+\.\d{4},/);

    await user.click(within(panel).getByRole("button", { name: "Show more" }));
    expect(await within(panel).findByRole("link", { name: "Avebury henge" })).toBeInTheDocument();
    expect(within(panel).queryByRole("button", { name: "Show more" })).toBeNull();

    await user.type(within(panel).getByRole("searchbox", { name: "Words to look for" }), "avenue");
    await user.click(within(panel).getByRole("radio", { name: "Everywhere" }));
    await user.click(within(panel).getByRole("button", { name: "Finds" }));
    await waitFor(() => {
      const last = api.callsTo("GET /records/search").at(-1)?.url.searchParams;
      expect(last?.get("q")).toBe("avenue");
      expect(last?.get("bbox")).toBeNull();
      expect(last?.get("category")).toBe("find");
    });
    const download = within(panel).getByRole("link", { name: /Download as GeoJSON/ });
    const href = new URL(download.getAttribute("href") ?? "", "http://localhost");
    expect(href.pathname).toBe("/api/v1/records/search");
    expect(href.searchParams.get("format")).toBe("geojson");
    expect(href.searchParams.get("q")).toBe("avenue");
  });

  it("says when nothing matches, and when the search took too long", async () => {
    api.on("GET /records/search", (call) =>
      call.url.searchParams.get("q") === "slow"
        ? apiError(503, "search_timeout", "That search took too long.")
        : json({ items: [], next_cursor: null }),
    );
    const user = userEvent.setup();
    renderShell("/records");
    await mapReady();
    expect(await screen.findByText("No records match")).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "Words to look for" }), "slow");
    expect(await screen.findByText("That search took too long")).toBeInTheDocument();
  });
});

describe("live sources", () => {
  async function openLive() {
    const user = userEvent.setup();
    renderShell("/?panel=layers");
    const map = await mapReady();
    await user.click(screen.getByText("Live sources"));
    return { user, map };
  }

  it("asks nothing until a source is turned on, then asks the publisher directly and draws what it sent", async () => {
    outside.set("maps.wiltshire.gov.uk", () => json(WILTSHIRE_RECORDED_ANSWER));
    const { user, map } = await openLive();
    const toggle = await screen.findByRole("switch", { name: WILTSHIRE_LIVE.name });
    // The catalogue entry that wants a record id isn't offered, nor are ones credited differently for each record.
    expect(screen.queryByRole("switch", { name: "ADS Data Catalogue single record" })).toBeNull();
    expect(screen.queryByRole("switch", { name: ADS_LIVE.name })).toBeNull();
    expect(screen.queryByRole("switch", { name: BRISTOL_LIVE.name })).toBeNull();
    expect(outsideCalls("maps.wiltshire.gov.uk")).toEqual([]);

    await user.click(toggle);
    const list = await screen.findByRole("list", { name: `Records from ${WILTSHIRE_LIVE.name}` });
    expect(within(list).getByText("Stone hole 41, Avebury henge")).toBeInTheDocument();
    expect(within(list).getAllByRole("link")[0]).toHaveAttribute(
      "href",
      "http://history.wiltshire.gov.uk/smr/getsmr.php?id=7753",
    );
    expect(outsideCalls("maps.wiltshire.gov.uk")).toHaveLength(1);
    const live = map.sourceData(`${RECORDS_SOURCE}-live`) as { features: unknown[] };
    expect(live.features).toHaveLength(4);
    // Credited while its records are on the map, with the publisher's credit and not the catalogue's notes.
    expect(screen.getAllByText(new RegExp(WILTSHIRE_LIVE.attribution.replace(/[()]/g, "\\$&"))).length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText(/Each record links to its page at Wiltshire Council\./)).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(WILTSHIRE_LIVE.licence.slice(0, 20)))).toBeNull();
    // Nothing the source sent went to our server.
    for (const call of api.calls) expect(JSON.stringify([call.url.href, call.body])).not.toContain("MWI");
  });

  it("turns off quietly, and stays off, when a source refuses this browser or fails", async () => {
    outside.set("services2.arcgis.com", () => Promise.reject(new TypeError("Failed to fetch")));
    outside.set("services-eu1.arcgis.com", () => new Response("Server error", { status: 500 }));
    const { user } = await openLive();
    const refusing = await screen.findByRole("switch", { name: ABERDEENSHIRE_LIVE.name });
    await user.click(refusing);
    await waitFor(() => expect(refusing).not.toBeChecked());
    expect(
      screen.getByText(/didn't answer this browser.*Some services don't let other websites ask them/),
    ).toBeInTheDocument();
    expect(outsideCalls("services2.arcgis.com")).toHaveLength(1);

    const failing = screen.getByRole("switch", { name: DARTMOOR_LIVE.name });
    await user.click(failing);
    await waitFor(() => expect(failing).not.toBeChecked());
    expect(screen.getByText(/answered with an error \(500\).*off for now/)).toBeInTheDocument();
    // Never asked again on its own.
    await new Promise((resolve) => setTimeout(resolve, 800));
    expect(outsideCalls("services-eu1.arcgis.com")).toHaveLength(1);
    expect(outsideCalls("services2.arcgis.com")).toHaveLength(1);
  });

  it("shows a clicked live record in the layer panel without losing the rest of the address", async () => {
    const line = "line=-1.853,51.4286,-1.849,51.4286";
    renderShell(`/profile?${line}&panel=layers`, <Address />);
    const map = await mapReady();
    useLiveStore.getState().setOn(WILTSHIRE_LIVE.key, true);
    map.rendered = [{ properties: { source: WILTSHIRE_LIVE.key, id: "20841088" }, layer: { id: RECORD_LAYERS.live } }];
    act(() => map.fire("click", { point: { x: 10, y: 10 }, lngLat: { lng: -1.85, lat: 51.43 } }));
    expect(useLiveStore.getState().picked).toBe(`${WILTSHIRE_LIVE.key}/20841088`);
    const address = new URL(screen.getByTestId("address").textContent ?? "", "http://localhost");
    expect(address.pathname).toBe("/profile");
    expect(address.searchParams.get("line")).toBe("-1.853,51.4286,-1.849,51.4286");
    expect(address.searchParams.get("panel")).toBe("layers");
  });

  it("asks nothing while zoomed out", async () => {
    outside.set("maps.wiltshire.gov.uk", () => json(WILTSHIRE_RECORDED_ANSWER));
    const { user, map } = await openLive();
    act(() => map.userMove({ zoom: 11 }));
    await user.click(await screen.findByRole("switch", { name: WILTSHIRE_LIVE.name }));
    expect(await screen.findByText("Zoom in closer to see its records.")).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 800));
    expect(outsideCalls("maps.wiltshire.gov.uk")).toEqual([]);
  });

  it("shows a hostile live record's name as text, with no link", async () => {
    outside.set("maps.wiltshire.gov.uk", () => json(HOSTILE_LIVE_ANSWER));
    const { user } = await openLive();
    await user.click(await screen.findByRole("switch", { name: WILTSHIRE_LIVE.name }));
    const list = await screen.findByRole("list", { name: `Records from ${WILTSHIRE_LIVE.name}` });
    expect(within(list).getByText('<img src=x onerror="alert(1)">Evil')).toBeInTheDocument();
    expect(list.querySelector("img, a")).toBeNull();
  });
});
