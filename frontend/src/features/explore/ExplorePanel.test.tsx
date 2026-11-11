import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation, useNavigate } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RECORD_LAYERS } from "../../map/overlayLayers.js";
import { overlayTroubleKey, useMapStore, useViewAreaStore } from "../../map/store.js";
import { FINDINGS_MIN_ZOOM } from "../../map/useFindingsOverlay.js";
import { apiError, routeApi } from "../../test/apiRoutes.js";
import { findingCollection, findingPage, findingsData, offset } from "../../test/fixtures/findings.js";
import { json, mapReady, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import { FINDINGS_PAGE_SIZE } from "../findings/api.js";
import { useFindingFilters } from "../findings/filters.js";
import { useSelectedFinding } from "../findings/selection.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

function Address() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output data-testid="address">{`${location.pathname}${location.search}`}</output>
      <button type="button" onClick={() => void navigate(-1)}>
        Test: go back
      </button>
    </>
  );
}

beforeEach(() => {
  useFindingFilters.getState().clear();
  useSelectedFinding.getState().clear();
});

function explore() {
  return within(screen.getByRole("complementary", { name: "Explore" }));
}

function isList(url: URL): boolean {
  return url.pathname === "/api/v1/findings" && url.searchParams.get("format") !== "geojson";
}

describe("the Explore panel", () => {
  it("lists the findings in view with their step, class and state, and an obscured one by its square", async () => {
    routeApi(harness.fetchMock());
    renderShell("/");
    await mapReady();
    const list = await screen.findByRole("list", { name: "Findings in view" });
    // Ruled-out findings are hidden from the list as they are from the map.
    const shown = findingsData.features.filter((feature) => feature.properties.state !== "ruled_out");
    expect(within(list).getAllByRole("listitem")).toHaveLength(shown.length);
    expect(explore().getByText(`${shown.length} findings in view`)).toBeInTheDocument();

    const seen = within(list).getByRole("link", { name: /Finding tier-seen/ });
    expect(seen).toHaveAttribute("href", "/f/tier-seen");
    expect(within(seen).getByText("Seen by others")).toBeInTheDocument();
    expect(within(seen).getByText("Enclosure")).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: /Finding disputed/ })).toHaveTextContent("Disputed");

    const hidden = within(list).getByRole("link", { name: /Finding protected/ });
    expect(hidden).toHaveTextContent(/Somewhere in square SU \d{2} \d{2}/);
  });

  it("asks the server with the filters, for the list and the map alike", async () => {
    const user = userEvent.setup();
    const routes = routeApi(harness.fetchMock());
    renderShell("/");
    await mapReady();
    await screen.findByRole("list", { name: "Findings in view" });
    await user.click(explore().getByRole("button", { name: "Filters" }));
    await user.click(
      within(explore().getByRole("group", { name: "Step" })).getByRole("button", { name: "Seen by others" }),
    );
    await user.click(
      within(explore().getByRole("group", { name: "What it looks like" })).getByRole("button", { name: "Moat" }),
    );

    await waitFor(() => {
      const last = routes.calls.filter((call) => isList(call.url)).at(-1)?.url;
      expect(last?.searchParams.getAll("tier")).toEqual(["seen"]);
      expect(last?.searchParams.getAll("feature_class")).toEqual(["moat"]);
    });
    await waitFor(() => {
      const box = routes.calls.filter((call) => call.url.searchParams.get("format") === "geojson").at(-1)?.url;
      expect(box?.searchParams.getAll("tier")).toEqual(["seen"]);
      expect(box?.searchParams.getAll("feature_class")).toEqual(["moat"]);
    });
    // Both ask for the same box. The list leaves out the ruled-out findings the map is hiding, which the
    // map fetches anyway so that showing them is immediate.
    const list = routes.calls.filter((call) => isList(call.url)).at(-1)?.url;
    const box = routes.calls.filter((call) => call.url.searchParams.get("format") === "geojson").at(-1)?.url;
    expect(list?.searchParams.get("bbox")).toBe(box?.searchParams.get("bbox"));
    expect(list?.searchParams.getAll("state")).toEqual(["disputed", "known", "open"]);
    expect(box?.searchParams.getAll("state")).toEqual([]);

    // Nothing in view is both, so the list says so and offers the way out.
    expect(await explore().findByRole("heading", { name: "Nothing here matches the filters" })).toBeInTheDocument();
    const [clear] = explore().getAllByRole("button", { name: "Clear filters" });
    if (!clear) throw new Error("No way to clear the filters");
    await user.click(clear);
    expect(await explore().findByRole("list", { name: "Findings in view" })).toBeInTheDocument();
    expect(explore().getByRole("button", { name: "Filters" })).toBeInTheDocument();
  });

  it("opens a finding chosen from the list, and marks it on the map", async () => {
    const user = userEvent.setup();
    routeApi(harness.fetchMock());
    renderShell("/", <Address />);
    await mapReady();
    const list = await screen.findByRole("list", { name: "Findings in view" });
    await user.click(within(list).getByRole("link", { name: /Finding tier-probable/ }));
    expect(screen.getByTestId("address")).toHaveTextContent("/f/tier-probable");
    expect(document.querySelector(".fc-highlight-ring")).not.toBeNull();
  });

  it("marks an obscured finding by its square, never a point", async () => {
    const user = userEvent.setup();
    routeApi(harness.fetchMock());
    renderShell("/", <Address />);
    await mapReady();
    const list = await screen.findByRole("list", { name: "Findings in view" });
    await user.click(within(list).getByRole("link", { name: /Finding restricted/ }));
    expect(screen.getByTestId("address")).toHaveTextContent("/f/restricted");
    expect(document.querySelector(".fc-highlight-ring")).toBeNull();
    expect(document.querySelector(".fc-highlight-square")).not.toBeNull();
  });

  it("opens a finding clicked on the map", async () => {
    routeApi(harness.fetchMock());
    renderShell("/", <Address />);
    const map = await mapReady();
    const feature = findingsData.features.find((f) => f.properties.public_id === "tier-seen");
    map.rendered = [
      {
        layer: { id: "findings-points" },
        properties: { public_id: "tier-seen" },
        ...(feature ? { geometry: feature.geometry } : {}),
      },
    ];
    act(() => map.click(500, 380));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("/f/tier-seen"));
    expect(useSelectedFinding.getState().selected?.point).toEqual(feature?.geometry.coordinates);
  });

  it("opens the finding, not the record, when a click lands on both", async () => {
    // Findings sit above heritage records.
    routeApi(harness.fetchMock());
    renderShell("/", <Address />);
    const map = await mapReady();
    const feature = findingsData.features.find((f) => f.properties.public_id === "tier-seen");
    map.rendered = [
      {
        layer: { id: "findings-points" },
        properties: { public_id: "tier-seen" },
        ...(feature ? { geometry: feature.geometry } : {}),
      },
      { id: 101, layer: { id: RECORD_LAYERS.squares }, properties: { id: 101, source: "nhle-scheduled" } },
    ];
    act(() => map.click(500, 380));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("/f/tier-seen"));
    // The record's page was never opened on the way: one step back is Explore.
    await userEvent.setup().click(screen.getByRole("button", { name: "Test: go back" }));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/$/));
  });

  it("leaves a click on a record to the record, and a click on a record while marking to the mark", async () => {
    routeApi(harness.fetchMock());
    renderShell("/", <Address />);
    const map = await mapReady();
    map.rendered = [
      { id: 101, layer: { id: RECORD_LAYERS.squares }, properties: { id: 101, source: "nhle-scheduled" } },
    ];
    act(() => map.click(500, 380));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("/r/101"));

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Mark a finding" }));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/mark/));
    act(() => map.click(500, 380));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.getByTestId("address")).toHaveTextContent(/^\/mark/);
  });

  it("pages when there are many", async () => {
    const user = userEvent.setup();
    const many = findingCollection(
      Array.from({ length: FINDINGS_PAGE_SIZE + 5 }, (_, i) => ({
        at: offset(i * 10, 0),
        public_id: `f${i}`,
        tier: "spotted",
      })),
    );
    const routes = routeApi(harness.fetchMock(), {
      "GET /findings": (call) => {
        if (call.url.searchParams.get("format") === "geojson") return json(many);
        const start = Number(call.url.searchParams.get("cursor") ?? 0);
        const page = findingCollection([]);
        page.features = many.features.slice(start, start + FINDINGS_PAGE_SIZE);
        const next = start + FINDINGS_PAGE_SIZE < many.features.length ? String(start + FINDINGS_PAGE_SIZE) : null;
        return json(findingPage(page, next));
      },
    });
    renderShell("/");
    await mapReady();
    const list = await screen.findByRole("list", { name: "Findings in view" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(FINDINGS_PAGE_SIZE);
    expect(explore().getByText(`${FINDINGS_PAGE_SIZE} or more findings in view`)).toBeInTheDocument();
    await user.click(explore().getByRole("button", { name: "Show more" }));
    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(FINDINGS_PAGE_SIZE + 5));
    expect(explore().queryByRole("button", { name: "Show more" })).toBeNull();
    expect(
      routes.calls
        .filter((call) => isList(call.url))
        .at(-1)
        ?.url.searchParams.get("cursor"),
    ).toBe(String(FINDINGS_PAGE_SIZE));
  });

  it("says what to do when there is nothing here, when it fails, and when zoomed out", async () => {
    const user = userEvent.setup();
    let fail = true;
    routeApi(harness.fetchMock(), {
      "GET /findings": (call) =>
        call.url.searchParams.get("format") === "geojson"
          ? json(findingCollection([]))
          : fail
            ? apiError(500, "internal", "The database isn't answering.")
            : json(findingPage(findingCollection([]))),
    });
    renderShell("/");
    await mapReady();
    // A server error may pass, so it is tried once more before the person is told.
    expect(
      await explore().findByRole("heading", { name: "The findings couldn't be loaded" }, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(explore().getByText("The database isn't answering.")).toBeInTheDocument();
    fail = false;
    await user.click(explore().getByRole("button", { name: "Try again" }));
    expect(await explore().findByRole("heading", { name: "No findings here yet" })).toBeInTheDocument();
    expect(explore().getByRole("button", { name: "Mark a finding" })).toBeInTheDocument();

    const bounds = useViewAreaStore.getState().bounds;
    if (!bounds) throw new Error("The map has not said what it shows");
    act(() => useViewAreaStore.getState().setArea(bounds, FINDINGS_MIN_ZOOM - 1));
    expect(await explore().findByRole("heading", { name: "Zoom in to see findings" })).toBeInTheDocument();
  });

  it.each([
    ["the list's", "list"],
    ["the layer's", "layer"],
  ] as const)("tries the list and the map's findings layer again together, from %s Try again", async (_, from) => {
    const user = userEvent.setup();
    let fail = true;
    routeApi(harness.fetchMock(), {
      "GET /findings": (call) =>
        fail
          ? apiError(500, "internal", "The database isn't answering.")
          : call.url.searchParams.get("format") === "geojson"
            ? json(findingCollection([]))
            : json(findingPage(findingCollection([]))),
    });
    renderShell("/");
    await mapReady();
    expect(
      await explore().findByRole("heading", { name: "The findings couldn't be loaded" }, { timeout: 4000 }),
    ).toBeInTheDocument();
    const layerKey = overlayTroubleKey("findings");
    await waitFor(() => expect(useMapStore.getState().failing[layerKey]).toBe(true), { timeout: 4000 });
    fail = false;
    if (from === "list") await user.click(explore().getByRole("button", { name: "Try again" }));
    else act(() => useMapStore.getState().retrySource(layerKey));
    expect(await explore().findByRole("heading", { name: "No findings here yet" })).toBeInTheDocument();
    expect(useMapStore.getState().failing[layerKey]).toBe(false);
  });

  it("puts itself away for the bare map", async () => {
    const user = userEvent.setup();
    routeApi(harness.fetchMock());
    renderShell("/", <Address />);
    await mapReady();
    await user.click(explore().getByRole("button", { name: "Close panel" }));
    expect(screen.getByTestId("address")).toHaveTextContent("/?panel=none");
    expect(screen.queryByRole("complementary", { name: "Explore" })).toBeNull();
  });
});
