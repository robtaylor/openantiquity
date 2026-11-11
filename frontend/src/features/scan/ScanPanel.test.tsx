import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMapStore, useViewAreaStore } from "../../map/store.js";
import { overlaySourceId } from "../../map/style.js";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { findingCollection, findingPage } from "../../test/fixtures/findings.js";
import { meFixture } from "../../test/fixtures/me.js";
import { coverageOf, SQUARE_SPOT, squareAt, squareEastOf } from "../../test/fixtures/squares.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import { useToastStore } from "../../ui/toastStore.js";
import type { Me } from "../account/api.js";
import { useAccountUi } from "../account/requireAccount.js";
import { DRAFTS_STORAGE_KEY, listDrafts, resetDraftsForTests } from "../drafts/store.js";
import { findingDrafts } from "../mark/findingDrafts.js";
import type { Square } from "./api.js";
import { useScanStore } from "./scanStore.js";
import { SQUARE_LAYERS, SQUARE_SOURCES, useScanCoverage } from "./useScanOnMap.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

const MEMBER = meFixture({ handle: "KeenLynchet7", display_name: "Mary Anning" });
const FIRST = squareAt(...SQUARE_SPOT, 2);
const SECOND = squareEastOf(1);
const THIRD = squareEastOf(2);
const AT_CENTRE = { lon: FIRST.centre[0], lat: FIRST.centre[1] };

beforeEach(() => {
  useAccountUi.setState({ sheet: null, waiting: [] });
  useScanStore.getState().reset();
  useScanCoverage.setState({ summary: { status: "off", scanned: 0 } });
  localStorage.clear();
  sessionStorage.clear();
  resetDraftsForTests();
});

/** `GET /squares/next` hands out `squares` in turn, never one named in `exclude`. */
function serve(squares: Square[], me: Me | null = null): ApiRoutes {
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : signedOutResponse()),
    "GET /squares/next": (call) => {
      const left = new Set(call.url.searchParams.getAll("exclude"));
      const square = squares.find((each) => !left.has(each.square));
      return square ? json(square) : apiError(404, "no_square_available", "There's no square left to scan.");
    },
    "GET /squares/coverage": () => json(coverageOf([{ square: FIRST, scans: 2 }])),
  });
}

async function openScan() {
  renderShell(`/scan`);
  const map = await mapReady();
  const panel = within(screen.getByRole("complementary", { name: "Scan a square" }));
  return { map, panel };
}

describe("a square to scan", () => {
  it("asks for one near the map, frames it, outlines it and shades the ground outside", async () => {
    const routes = serve([FIRST]);
    const { map, panel } = await openScan();
    expect(await panel.findByText(FIRST.grid_ref, { selector: ".fc-mono" })).toBeInTheDocument();
    expect(panel.getByText("2 people have looked it over so far.")).toBeInTheDocument();

    const asked = routes.callsTo("GET /squares/next")[0]?.url;
    expect(asked?.searchParams.get("lon")).not.toBeNull();
    expect(asked?.searchParams.get("lat")).not.toBeNull();

    // The map goes to the square, close enough to see it whole.
    await waitFor(() => expect(useMapStore.getState().camera.zoom).toBeGreaterThan(13));
    expect(Math.abs(useMapStore.getState().camera.lat - FIRST.centre[1])).toBeLessThan(0.01);
    await waitFor(() => expect(map.getLayer(SQUARE_LAYERS.outline)).toBeDefined());
    expect(map.sourceData(SQUARE_SOURCES.outline)).toMatchObject({ features: [expect.anything()] });
    expect(map.sourceData(SQUARE_SOURCES.shade)).toMatchObject({ features: [expect.anything()] });
    expect(document.title).toBe("Scan a square · Field Club");
  });

  it("keeps the square through the layer panel, and takes it off the map on leaving the scan", async () => {
    const user = userEvent.setup();
    serve([FIRST, SECOND]);
    const { map, panel } = await openScan();
    await panel.findByText(FIRST.grid_ref, { selector: ".fc-mono" });
    await user.click(screen.getByRole("button", { name: "Layers" }));
    await screen.findByRole("complementary", { name: "Layers" });
    expect(map.sourceData(SQUARE_SOURCES.outline)).toMatchObject({ features: [expect.anything()] });
    await user.click(screen.getByRole("button", { name: "Layers" }));
    const back = within(await screen.findByRole("complementary", { name: "Scan a square" }));
    expect(back.getByText(FIRST.grid_ref, { selector: ".fc-mono" })).toBeInTheDocument();

    await user.click(within(screen.getByRole("navigation", { name: "Modes" })).getByRole("link", { name: "Explore" }));
    await waitFor(() => expect(map.sourceData(SQUARE_SOURCES.outline)).toMatchObject({ features: [] }));
  });
});

describe("marking a finding during a scan", () => {
  it("keeps the square in sight while marking from the scan, and not while marking from anywhere else", async () => {
    const user = userEvent.setup();
    serve([FIRST]);
    const { map, panel } = await openScan();
    await panel.findByText(FIRST.grid_ref, { selector: ".fc-mono" });
    const drawn = () => (map.sourceData(SQUARE_SOURCES.outline) as { features: unknown[] } | undefined)?.features ?? [];
    await waitFor(() => expect(drawn()).toHaveLength(1));

    await user.click(screen.getByRole("button", { name: "Mark a finding" }));
    await screen.findByRole("complementary", { name: "Mark a finding" });
    expect(drawn()).toHaveLength(1);

    const rail = within(screen.getByRole("navigation", { name: "Modes" }));
    await user.click(rail.getByRole("link", { name: "Explore" }));
    await waitFor(() => expect(drawn()).toEqual([]));
    await user.click(screen.getByRole("button", { name: "Mark a finding" }));
    await screen.findByRole("complementary", { name: "Mark a finding" });
    expect(drawn()).toEqual([]);
  });
});

describe("ending a square signed out", () => {
  it("keeps “nothing obvious” as a draft, counts it, and leaves it out of the next request", async () => {
    const user = userEvent.setup();
    const routes = serve([FIRST, SECOND]);
    const { panel } = await openScan();
    await panel.findByText(FIRST.grid_ref, { selector: ".fc-mono" });
    expect(panel.getByRole("button", { name: "I marked something" })).toBeDisabled();

    await user.click(panel.getByRole("button", { name: "Nothing obvious" }));
    expect(await panel.findByText(/is recorded: nothing obvious/)).toBeInTheDocument();
    expect(panel.getByText("Not saved yet")).toBeInTheDocument();
    expect(panel.getByText("1 square")).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Next square" })).toHaveFocus();
    expect(routes.callsTo(`PUT /squares/${FIRST.square}`)).toEqual([]);
    expect(localStorage.getItem(DRAFTS_STORAGE_KEY)).toContain(FIRST.square);

    await user.click(panel.getByRole("button", { name: "Next square" }));
    expect(await panel.findByText(SECOND.grid_ref, { selector: ".fc-mono" })).toBeInTheDocument();
    expect(routes.callsTo("GET /squares/next")[1]?.url.searchParams.getAll("exclude")).toEqual([FIRST.square]);
    // The count stays for the visit.
    expect(panel.getByText("1 square")).toBeInTheDocument();
  });

  it("counts a finding drafted in the square since it came up, and keeps “I marked something” with that count", async () => {
    const user = userEvent.setup();
    serve([FIRST]);
    const { panel } = await openScan();
    await panel.findByText(FIRST.grid_ref, { selector: ".fc-mono" });
    findingDrafts.put({
      point: FIRST.centre,
      feature_class: "enclosure",
      period: "unknown",
      title: "Enclosure in the square",
      description: null,
      outline: null,
      view_state: { layer: "composite", zoom: 15 },
    });
    expect(await panel.findByText("You've marked 1 finding in this square.")).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "I marked something" }));
    expect(await panel.findByText(/is recorded: you marked something/)).toBeInTheDocument();
    const square = listDrafts().find((draft) => draft.kind === "square");
    expect(square?.data).toMatchObject({ square: FIRST.square, survey: { result: "marked", findings_count: 1 } });
  });

  it("skips without a draft or a count, and goes straight to the next square", async () => {
    const user = userEvent.setup();
    const routes = serve([FIRST, SECOND]);
    const { panel } = await openScan();
    await panel.findByText(FIRST.grid_ref, { selector: ".fc-mono" });
    await user.click(panel.getByRole("button", { name: "Skip this square" }));
    expect(await panel.findByText(SECOND.grid_ref, { selector: ".fc-mono" })).toBeInTheDocument();
    expect(routes.callsTo("GET /squares/next")[1]?.url.searchParams.getAll("exclude")).toEqual([FIRST.square]);
    expect(listDrafts()).toEqual([]);
    expect(panel.queryByText(/looked over this visit/)).toBeNull();
    expect(routes.callsTo(`PUT /squares/${FIRST.square}`)).toEqual([]);
  });
});

describe("ending a square signed in", () => {
  it("sends the result at once, with the findings marked in the square", async () => {
    const user = userEvent.setup();
    const routes = serve([FIRST, SECOND], MEMBER);
    const now = new Date().toISOString();
    const [mine] = findingPage(findingCollection([{ at: AT_CENTRE, public_id: "mine", tier: "spotted" }])).items;
    routes.on("GET /findings", (call) =>
      json({
        items: call.url.searchParams.get("author") === MEMBER.handle && mine ? [{ ...mine, created_at: now }] : [],
        next_cursor: null,
      }),
    );
    routes.on(`PUT /squares/${FIRST.square}`, (call) =>
      json({ square: FIRST.square, grid_ref: FIRST.grid_ref, ...(call.body as object), created_at: now }, 201),
    );
    const { panel } = await openScan();
    expect(await panel.findByText("You've marked 1 finding in this square.")).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "I marked something" }));
    expect(await panel.findByText(/is recorded: you marked something/)).toBeInTheDocument();
    expect(panel.queryByText("Not saved yet")).toBeNull();
    await waitFor(() => expect(routes.callsTo(`PUT /squares/${FIRST.square}`)).toHaveLength(1));
    expect(routes.callsTo(`PUT /squares/${FIRST.square}`)[0]?.body).toMatchObject({
      result: "marked",
      findings_count: 1,
    });
    expect(listDrafts()).toEqual([]);
  });

  it("takes back a result the server refuses, and says why with a way to try again", async () => {
    const user = userEvent.setup();
    const routes = serve([FIRST], MEMBER);
    routes.on(`PUT /squares/${FIRST.square}`, () => json({ detail: "down" }, 503));
    const { panel } = await openScan();
    await panel.findByText(FIRST.grid_ref, { selector: ".fc-mono" });
    await user.click(panel.getByRole("button", { name: "Nothing obvious" }));
    await waitFor(() => expect(useToastStore.getState().toasts[0]?.message).toMatch(/couldn't be recorded/));
    expect(useToastStore.getState().toasts[0]?.action?.label).toBe("Try again");
    // Back on the square, uncounted.
    expect(await panel.findByRole("button", { name: "Nothing obvious" })).toBeInTheDocument();
    expect(panel.queryByText(/looked over this visit/)).toBeNull();
  });
});

describe("when there is no square to give", () => {
  it("says so when there's none left near here, and offers to look again", async () => {
    serve([]);
    const { panel } = await openScan();
    expect(await panel.findByRole("heading", { name: "No square left near here" })).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Look again from here" })).toBeInTheDocument();
  });

  it("says the server is busy, and tries again when asked", async () => {
    const user = userEvent.setup();
    const routes = serve([FIRST]);
    let busy = true;
    routes.on("GET /squares/next", () => (busy ? apiError(429, "rate_limited", "Slow down.") : json(FIRST)));
    const { panel } = await openScan();
    expect(await panel.findByRole("heading", { name: "The server is busy" })).toBeInTheDocument();
    busy = false;
    await user.click(panel.getByRole("button", { name: "Try again" }));
    expect(await panel.findByText(FIRST.grid_ref, { selector: ".fc-mono" })).toBeInTheDocument();
  });

  it("says when the square has no elevation, records nothing, and finds another", async () => {
    const user = userEvent.setup();
    const routes = serve([FIRST, SECOND, THIRD]);
    routes.on("GET /terrain/coverage", () => json({ type: "FeatureCollection", features: [] }));
    const { panel } = await openScan();
    expect(await panel.findByText(/There's no one-metre elevation for/)).toBeInTheDocument();
    expect(panel.queryByRole("button", { name: "Nothing obvious" })).toBeNull();
    await user.click(panel.getByRole("button", { name: "Find another square" }));
    await waitFor(() => expect(routes.callsTo("GET /squares/next")).toHaveLength(2));
    expect(routes.callsTo("GET /squares/next")[1]?.url.searchParams.getAll("exclude")).toEqual([FIRST.square]);
    expect(listDrafts()).toEqual([]);
  });
});

describe("the coverage layer", () => {
  it("is offered while scanning, and draws how many people scanned each square in view", async () => {
    const user = userEvent.setup();
    const routes = serve([FIRST]);
    const { map, panel } = await openScan();
    await panel.findByText(FIRST.grid_ref, { selector: ".fc-mono" });
    await user.click(panel.getByRole("switch", { name: "Scan coverage" }));
    expect(useMapStore.getState().overlays.coverage?.visible).toBe(true);
    expect(await panel.findByText(/1 square around here has been looked over/)).toBeInTheDocument();
    expect(routes.callsTo("GET /squares/coverage")[0]?.url.searchParams.get("bbox")).toMatch(/^-?\d/);
    expect(map.sourceData(overlaySourceId("coverage"))).toMatchObject({
      features: [expect.objectContaining({ properties: { square: FIRST.square, scans: 2 } })],
    });
  });

  it("refuses politely in the layer panel when zoomed out too far to ask", async () => {
    const routes = serve([FIRST]);
    renderShell("/?panel=layers");
    const map = await mapReady();
    act(() => useMapStore.getState().setOverlayVisible("coverage", true));
    await waitFor(() => expect(routes.callsTo("GET /squares/coverage")).toHaveLength(1));
    act(() => useViewAreaStore.getState().setArea([-3, 50.8, -0.7, 52], 8));
    const layers = within(await screen.findByRole("complementary", { name: "Layers" }));
    expect(await layers.findByText(/Zoom in to see scan coverage/)).toBeInTheDocument();
    // Nothing more is asked, and what was drawn for the closer view is taken off.
    expect(routes.callsTo("GET /squares/coverage")).toHaveLength(1);
    expect(map.sourceData(overlaySourceId("coverage"))).toMatchObject({ features: [] });
  });

  it("refreshes after a result is saved, so the square is counted", async () => {
    const user = userEvent.setup();
    const routes = serve([FIRST], MEMBER);
    routes.on(`PUT /squares/${FIRST.square}`, () =>
      json({
        square: FIRST.square,
        grid_ref: FIRST.grid_ref,
        result: "nothing",
        findings_count: 0,
        seconds: 1,
        created_at: "2026-11-11T10:00:00Z",
      }),
    );
    const { panel } = await openScan();
    await panel.findByText(FIRST.grid_ref, { selector: ".fc-mono" });
    await user.click(panel.getByRole("switch", { name: "Scan coverage" }));
    await waitFor(() => expect(routes.callsTo("GET /squares/coverage")).toHaveLength(1));
    await user.click(panel.getByRole("button", { name: "Nothing obvious" }));
    await waitFor(() => expect(routes.callsTo("GET /squares/coverage")).toHaveLength(2));
  });
});

describe("findings in the square", () => {
  it("doesn't count the person's findings from before the square came up", async () => {
    const routes = serve([FIRST], MEMBER);
    const [mine] = findingPage(findingCollection([{ at: AT_CENTRE, public_id: "old", tier: "spotted" }])).items;
    routes.on("GET /findings", () =>
      json({ items: mine ? [{ ...mine, created_at: "2020-01-01T00:00:00Z" }] : [], next_cursor: null }),
    );
    const { panel } = await openScan();
    await panel.findByText(FIRST.grid_ref, { selector: ".fc-mono" });
    await waitFor(() =>
      expect(
        routes.callsTo("GET /findings").some((call) => call.url.searchParams.get("author") === MEMBER.handle),
      ).toBe(true),
    );
    expect(panel.getByRole("button", { name: "I marked something" })).toBeDisabled();
  });
});
