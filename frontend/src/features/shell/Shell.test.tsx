import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { Link } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { META_RETRY_DELAY_MS } from "../../api/useMeta.js";
import { useMapStore } from "../../map/store.js";
import { RAKING_LAYER, viewLayerId } from "../../map/style.js";
import { FakeMap } from "../../test/fakeMapLibre.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { liveMaps, mapReady, renderShell, setUpShellTests, usePhoneLayout } from "../../test/shellHarness.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

describe("Shell", () => {
  it("loads /meta, then shows the map with every region of the layout", async () => {
    renderShell();
    expect(screen.getByRole("status")).toHaveTextContent("Loading the map");
    const map = await mapReady();
    expect(harness.requestsTo("/meta")).toBe(1);
    expect(harness.fetchMock().mock.calls[0]?.[0]).toBe("/api/v1/meta");

    const rail = screen.getByRole("navigation", { name: "Modes" });
    for (const name of [
      "Explore",
      "Second look",
      "Scan a square",
      "Help wanted",
      "Investigations",
      "Activity",
      "Account",
    ]) {
      expect(within(rail).getByRole("link", { name })).toBeInTheDocument();
    }
    expect(within(rail).getByRole("link", { name: "Explore" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("combobox", { name: /Search for a place/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Layers" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Mark a finding" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary")).toBeNull();

    // The map opens where /meta says, on the default view.
    expect(map.options.center).toEqual(metaFixture.layers.initial_view.center);
    expect(map.options.zoom).toBe(metaFixture.layers.initial_view.zoom);
    expect(map.options.attributionControl).toBe(false);
    expect(map.isVisible(viewLayerId("composite"))).toBe(true);
    expect(map.isVisible(viewLayerId("slope"))).toBe(false);
    expect(map.getCanvas()).toHaveAttribute("aria-label", "Map: Composite");

    // Status readout: the centre of the map, as there is no pointer yet.
    // The readout is a six-figure reference: the conversion behind it is not good enough for eight.
    expect(screen.getByTestId("status-gridref")).toHaveTextContent(/^SU 102 699$/);
    expect(screen.getByTestId("status-coords")).toHaveTextContent("51.42860, -1.85420");
    expect(screen.getByTestId("status-zoom")).toHaveTextContent("z14.0");
    // Attribution comes from /meta with links in it. The one-line readout shows the words only.
    const credits = screen.getByRole("button", { name: /Environment Agency/ });
    expect(credits).toHaveTextContent("OpenFreeMap © OpenMapTiles Data from OpenStreetMap");
    expect(credits.innerHTML).not.toContain("<a");
    // Heritage records are on by default, so the sources behind them are credited.
    expect(credits).toHaveTextContent("© Historic England");
  });

  it("has a main landmark, a top-level heading and distinct names for its controls", async () => {
    renderShell("/?panel=layers");
    await mapReady();
    expect(screen.getByRole("heading", { level: 1, name: metaFixture.app.name })).toBeInTheDocument();
    const main = screen.getByRole("main");
    expect(main.querySelector(".fc-map")).not.toBeNull();
    expect(within(main).getByRole("button", { name: "Mark a finding" })).toBeInTheDocument();
    // The panel and the status bar are landmarks of their own, outside main.
    expect(within(main).queryByRole("complementary")).toBeNull();
    expect(within(main).queryByTestId("status-gridref")).toBeNull();

    // Each opacity slider says whose opacity it is.
    const panel = screen.getByRole("complementary", { name: "Layers" });
    const names = within(panel)
      .getAllByRole("slider")
      .map((slider) => slider.getAttribute("aria-label"));
    expect(names).toEqual(["OpenStreetMap opacity", "Heritage records opacity", "Findings opacity"]);
  });

  it("follows the pointer in the status bar", async () => {
    renderShell();
    const map = await mapReady();
    act(() => map.fire("mousemove", { lngLat: { lng: -1.8262771, lat: 51.1788152 } }));
    expect(screen.getByTestId("status-gridref")).toHaveTextContent(/^SU 122 42\d$/);
    expect(screen.getByTestId("status-coords")).toHaveTextContent("51.17882, -1.82628");
    act(() => map.fire("mousemove", { lngLat: { lng: -5.9305779, lat: 54.5965219 } }));
    expect(screen.getByTestId("status-gridref")).toHaveTextContent(/^J 33\d 7\d\d$/);
    act(() => map.fire("mouseout"));
    expect(screen.getByTestId("status-gridref")).toHaveTextContent(/^SU 102 699$/);
    act(() => map.userMove({ lng: 2.35, lat: 48.86, zoom: 11.26 }));
    expect(screen.getByTestId("status-gridref")).toHaveTextContent("Off the grid");
    expect(screen.getByTestId("status-zoom")).toHaveTextContent("z11.3");
  });

  it("opens the layer panel, switches view and toggles compare", async () => {
    const user = userEvent.setup();
    renderShell();
    const map = await mapReady();

    await user.click(screen.getByRole("button", { name: "Layers" }));
    const panel = screen.getByRole("complementary", { name: "Layers" });
    expect(screen.getByRole("button", { name: "Layers" })).toHaveAttribute("aria-pressed", "true");
    expect(within(panel).getByRole("group", { name: "Terrain from LIDAR" })).toBeInTheDocument();
    expect(within(panel).getByRole("group", { name: "Modern maps" })).toBeInTheDocument();
    expect(within(panel).getAllByRole("radio")).toHaveLength(metaFixture.layers.views.length);
    const composite = within(panel).getByRole("radio", { name: "Composite" });
    expect(composite).toBeChecked();
    // The description is read once, as the description, not as part of the name.
    const description = metaFixture.layers.views.find((view) => view.id === "composite")?.description;
    expect(description).toBeTruthy();
    expect(composite).toHaveAccessibleDescription(description);

    await user.click(within(panel).getByRole("radio", { name: "Raking light" }));
    expect(useMapStore.getState().mainView).toBe("raking");
    expect(map.isVisible(RAKING_LAYER)).toBe(true);
    expect(map.isVisible(viewLayerId("composite"))).toBe(false);
    expect(map.getCanvas()).toHaveAttribute("aria-label", "Map: Raking light");
    // Raking light brings its sun controls, and credits the elevation data.
    const raking = screen.getByRole("region", { name: "Raking light" });
    expect(within(raking).getByRole("slider", { name: "Sun direction" })).toHaveAttribute("aria-valuenow", "315");
    // Once beside the chosen view, and once in the credits for everything on screen.
    expect(within(panel).getAllByText(/^Elevation: Mapzen terrain tiles/)).toHaveLength(2);

    expect(liveMaps()).toHaveLength(1);
    await user.click(within(panel).getByRole("switch", { name: "Compare two layers" }));
    await waitFor(() => expect(liveMaps()).toHaveLength(2));
    const [, compare] = liveMaps() as [FakeMap, FakeMap];
    expect(useMapStore.getState().compareView).toBe("osm_standard");
    await waitFor(() => expect(compare.isVisible(viewLayerId("osm_standard"))).toBe(true));
    expect(compare.isVisible(RAKING_LAYER)).toBe(false);
    expect(screen.getByRole("slider", { name: "Comparison divide" })).toHaveAttribute("aria-valuenow", "50");
    expect(within(panel).getByRole("tab", { name: /^Left/ })).toHaveTextContent("Raking light");
    expect(within(panel).getByRole("tab", { name: /^Right/ })).toHaveTextContent("OpenStreetMap");

    // The two cameras move together.
    act(() => map.userMove({ zoom: 16, lng: -1.83 }));
    expect(compare.getZoom()).toBe(16);
    expect(compare.getCenter().lng).toBe(-1.83);
    act(() => compare.userMove({ zoom: 12 }));
    expect(map.getZoom()).toBe(12);
    expect(useMapStore.getState().camera.zoom).toBe(12);

    await user.click(within(panel).getByRole("button", { name: "Swap sides" }));
    expect(useMapStore.getState().mainView).toBe("osm_standard");
    expect(map.isVisible(viewLayerId("osm_standard"))).toBe(true);
    expect(compare.isVisible(RAKING_LAYER)).toBe(true);

    await user.click(within(panel).getByRole("switch", { name: "Compare two layers" }));
    await waitFor(() => expect(liveMaps()).toHaveLength(1));
    expect(compare.removed).toBe(true);
    expect(screen.queryByRole("slider", { name: "Comparison divide" })).toBeNull();

    await user.click(within(panel).getByRole("button", { name: "Close panel" }));
    expect(screen.queryByRole("complementary")).toBeNull();
  });

  it("drives overlays, the sun and 3D from the controls", async () => {
    const user = userEvent.setup();
    renderShell("/?panel=layers");
    const map = await mapReady();
    const panel = screen.getByRole("complementary", { name: "Layers" });

    expect(map.isVisible("osm-road-major")).toBe(true);
    await user.click(within(panel).getByRole("switch", { name: "OpenStreetMap" }));
    expect(map.isVisible("osm-road-major")).toBe(false);
    expect(map.isVisible("findings-points")).toBe(true);
    expect(within(panel).queryByText(/OpenMapTiles/)).toBeNull();
    await user.click(within(panel).getByRole("switch", { name: "OpenStreetMap" }));
    // The overlay's own credit and the credits list keep the links, as real anchors that open in a new tab.
    const links = within(panel).getAllByRole("link", { name: "© OpenMapTiles" });
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "https://www.openmaptiles.org/");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
    await user.click(within(panel).getByRole("switch", { name: "OpenStreetMap" }));
    expect(map.isVisible("osm-road-major")).toBe(false);

    expect(map.isVisible("findings-ruled-out")).toBe(false);
    await user.click(within(panel).getByRole("switch", { name: "Show explained findings" }));
    expect(map.isVisible("findings-ruled-out")).toBe(true);

    // The 3D button keeps one name. Its pressed state says whether 3D is on.
    const threeD = screen.getByRole("button", { name: "Tilt into 3D" });
    expect(threeD).toHaveAttribute("aria-pressed", "false");
    await user.click(threeD);
    expect(map.setTerrain).toHaveBeenLastCalledWith({ source: "dem-terrain", exaggeration: 1.5 });
    expect(map.easeTo).toHaveBeenLastCalledWith(expect.objectContaining({ pitch: 60 }), expect.anything());
    expect(within(panel).getByRole("switch", { name: "Tilt into 3D" })).toBeChecked();
    expect(threeD).toHaveAttribute("aria-pressed", "true");
    expect(threeD).toHaveAccessibleName("Tilt into 3D");
    expect(threeD).toHaveAttribute("title", "Back to a flat map");
    await user.click(threeD);
    expect(map.setTerrain).toHaveBeenLastCalledWith(null);
    expect(map.getPitch()).toBe(0);

    act(() => useMapStore.getState().setMainView("raking"));
    const dial = screen.getByRole("slider", { name: "Sun direction" });
    dial.focus();
    await user.keyboard("{ArrowLeft}");
    expect(dial).toHaveAttribute("aria-valuenow", "310");
    expect(map.layer(RAKING_LAYER).paint?.["hillshade-illumination-direction"]).toBe(310);
    expect(screen.getByText("Light from the north-west")).toBeInTheDocument();
  });

  it("renders a titled panel for a route and returns to the bare map on close", async () => {
    const user = userEvent.setup();
    renderShell("/review");
    const map = await mapReady();
    const panel = screen.getByRole("complementary", { name: "Second look" });
    // The fixtures have nothing waiting for a second look.
    expect(await within(panel).findByRole("heading", { name: "Nothing waiting just now" })).toBeInTheDocument();
    const rail = screen.getByRole("navigation", { name: "Modes" });
    expect(within(rail).getByRole("link", { name: "Second look" })).toHaveAttribute("aria-current", "page");
    expect(within(rail).getByRole("link", { name: "Explore" })).not.toHaveAttribute("aria-current");
    expect(document.title).toBe("Second look · Field Club");

    await user.click(within(panel).getByRole("button", { name: "Close panel" }));
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(document.title).toBe("Field Club");
    // The map was never torn down.
    expect(map.removed).toBe(false);
    expect(liveMaps()).toHaveLength(1);
  });

  it.each([
    ["/f/abc123", "Finding not found", null],
    // The record's own page: the fixtures have no record 42, so it keeps its general title.
    ["/r/42", "Heritage record", null],
    ["/scan", "Scan a square", null],
    ["/help", "Help wanted", null],
    ["/i/xyz", "Investigation", "Investigation xyz"],
    ["/u/QuietBarrow42", "Profile", "@QuietBarrow42"],
    ["/about", "About Field Club", null],
    ["/guide", "Guide", null],
    ["/no/such/page", "Page not found", null],
  ])("titles the panel at %s", async (path, title, subtitle) => {
    renderShell(path);
    await mapReady();
    // A finding's page asks the server first, so its title can arrive a moment later.
    const panel = await screen.findByRole("complementary", { name: title });
    if (subtitle) expect(within(panel).getByText(subtitle)).toBeInTheDocument();
  });

  it("restores the view from the URL hash", async () => {
    window.history.replaceState(null, "", "/#m=16/51.1788/-1.8263/-20/0&v=slope&s=90/20&x=4&t=0/2&o=osm:40:h");
    renderShell();
    const map = await mapReady();
    expect(map.options.center).toEqual([-1.8263, 51.1788]);
    expect(map.options.zoom).toBe(16);
    expect(map.options.bearing).toBe(-20);
    expect(map.isVisible(viewLayerId("slope"))).toBe(true);
    expect(map.isVisible("osm-road-major")).toBe(false);
    expect(map.layer("osm-road-major").paint?.["line-opacity"]).toBeCloseTo(0.92 * 0.4, 3);
    expect(useMapStore.getState().sun).toEqual({ azimuth: 90, altitude: 20 });
  });

  it("opens the marking panel when the primary action is pressed", async () => {
    const user = userEvent.setup();
    renderShell();
    await mapReady();
    await user.click(screen.getByRole("button", { name: "Mark a finding" }));
    expect(screen.getByRole("complementary", { name: "Mark a finding" })).toBeInTheDocument();
    // While the mark is being placed, the primary action places it.
    expect(screen.getByRole("button", { name: "Place it here" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark a finding" })).toBeNull();
  });

  it("closes the layer panel back to the mode it was opened over", async () => {
    // As docs/UI.md says: changing layer is part of a second look or a scan, so
    // closing the layer panel must not throw the person out of what they were doing.
    const user = userEvent.setup();
    renderShell("/scan");
    await mapReady();
    await user.click(screen.getByRole("button", { name: "Layers" }));
    expect(screen.getByRole("complementary", { name: "Layers" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Scan a square" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Close panel" }));
    expect(screen.getByRole("complementary", { name: "Scan a square" })).toBeInTheDocument();
    // Closing the mode's own panel is what returns to the bare map.
    await user.click(screen.getByRole("button", { name: "Close panel" }));
    expect(screen.queryByRole("complementary")).toBeNull();
  });

  it("goes to the view a link inside the app carries, and leaves the map alone for a link without one", async () => {
    const user = userEvent.setup();
    renderShell(
      "/",
      <>
        <Link to="/f/abc#m=16/56.7968/-5.0036/0/0&v=slope">Saved view</Link>
        <Link to="/review">Plain link</Link>
      </>,
    );
    const map = await mapReady();
    await user.click(screen.getByRole("link", { name: "Saved view" }));
    expect(await screen.findByRole("complementary", { name: "Finding not found" })).toBeInTheDocument();
    expect(useMapStore.getState().mainView).toBe("slope");
    expect(useMapStore.getState().camera).toMatchObject({ zoom: 16, lat: 56.7968, lng: -5.0036 });
    expect(map.easeTo).toHaveBeenLastCalledWith(
      expect.objectContaining({ center: [-5.0036, 56.7968], zoom: 16 }),
      expect.anything(),
    );
    expect(map.isVisible(viewLayerId("slope"))).toBe(true);

    map.easeTo.mockClear();
    await user.click(screen.getByRole("link", { name: "Plain link" }));
    expect(screen.getByRole("complementary", { name: "Second look" })).toBeInTheDocument();
    expect(map.easeTo).not.toHaveBeenCalled();
    expect(useMapStore.getState().mainView).toBe("slope");
  });

  it("takes the map's word for where it is when a link asks for more than the map allows", async () => {
    window.history.replaceState(null, "", "/#m=22/51.4286/-1.8542/0/0&v=composite");
    renderShell();
    const map = await mapReady();
    expect(map.options.maxZoom).toBe(20);
    expect(map.getZoom()).toBe(20);
    expect(useMapStore.getState().camera.zoom).toBe(20);
    expect(screen.getByTestId("status-zoom")).toHaveTextContent("z20.0");
  });

  it("uses the tab bar and a bottom sheet on a phone", async () => {
    const user = userEvent.setup();
    usePhoneLayout();
    renderShell();
    await mapReady();
    const tabs = screen.getByRole("navigation", { name: "Modes" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Explore", "Second look", "Scan", "Help wanted"]);
    // Phones keep the grid reference and attribution only.
    expect(screen.getByTestId("status-gridref")).toBeInTheDocument();
    expect(screen.queryByTestId("status-coords")).toBeNull();

    await user.click(within(tabs).getByRole("button", { name: "More" }));
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual([
      "Explore",
      "Second look",
      "Scan",
      "Help wanted",
      "Investigations",
      "Activity",
      "Account",
      "Guide",
      "About",
    ]);
    await user.click(within(tabs).getByRole("link", { name: "Activity" }));
    const sheet = screen.getByRole("complementary", { name: "Activity" });
    expect(sheet).toHaveClass("fc-sheet");
    expect(sheet).toHaveAttribute("data-stop", "half");
    expect(within(tabs).queryByRole("link", { name: "Activity" })).toBeNull();
    expect(within(tabs).getByRole("button", { name: "More" })).toHaveClass("fc-tabbar__tab--active");
  });

  it("explains a failure to load /meta, after one quiet retry, and tries again on request", async () => {
    const user = userEvent.setup();
    const unavailable = async () =>
      new Response(JSON.stringify({ error: { code: "unavailable", message: "The service is restarting." } }), {
        status: 503,
      });
    harness.fetchMock().mockImplementationOnce(unavailable).mockImplementationOnce(unavailable);
    renderShell();
    const alert = await screen.findByRole("alert", {}, { timeout: META_RETRY_DELAY_MS + 2000 });
    expect(alert).toHaveTextContent("The map couldn't start");
    expect(alert).toHaveTextContent("The service is restarting.");
    expect(harness.requestsTo("/meta")).toBe(2);
    expect(FakeMap.instances).toHaveLength(0);

    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    await mapReady();
    expect(harness.requestsTo("/meta")).toBe(3);
  });

  it("recovers by itself from a single passing failure", async () => {
    harness.fetchMock().mockImplementationOnce(async () => {
      throw new TypeError("Failed to fetch");
    });
    renderShell();
    await waitFor(() => expect(document.querySelector('.fc-map[data-ready="true"]')).not.toBeNull(), {
      timeout: META_RETRY_DELAY_MS + 2000,
    });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(harness.requestsTo("/meta")).toBe(2);
  });

  it("refuses a /meta document it cannot build a map from", async () => {
    harness
      .fetchMock()
      .mockImplementationOnce(
        async () => new Response(JSON.stringify({ ...metaFixture, layers: { ...metaFixture.layers, views: [] } })),
      );
    renderShell();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent('Unexpected /meta document: "layers.views" is empty');
    // A malformed document will not get better, so it is not fetched twice.
    expect(harness.requestsTo("/meta")).toBe(1);
  });
});
