import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RasterView } from "../../api/meta.js";
import { coordinateText } from "../../map/StatusBar.js";
import { useMapStore } from "../../map/store.js";
import { useMapTool } from "../../map/tool.js";
import { viewTroubleKey } from "../../map/trouble.js";
import { useMapCover, visibleCentre } from "../../map/visibleArea.js";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { BORDER_COVERAGE } from "../../test/fixtures/coverage.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { json, mapReady, metaResponse, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import { useToastStore } from "../../ui/toastStore.js";
import { useCoverageStore } from "./coverage/store.js";
import { COVERAGE_LAYERS } from "./coverage/useCoverageOnMap.js";
import type { ProfileOut } from "./profile/api.js";
import { framingFor, MAX_LINE_POINTS } from "./profile/line.js";
import { useProfileHover } from "./profile/store.js";
import { PROFILE_LAYERS, PROFILE_SOURCE } from "./profile/useProfileOnMap.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

/** Open the app at an address, with the map's part of it in the address bar too, where the map reads it at start. */
function open(path: string): void {
  window.history.replaceState(null, "", path);
  renderShell(path);
}
let api: ApiRoutes;

/** A section across a bank and ditch: level, down into a ditch, up over a bank, then level. */
function profileAnswer(points: number): ProfileOut {
  const heights = [160, 160, 159.8, 156, 154, 156, 161, 165, 162, 161, 161];
  return {
    length_m: 100,
    resolution_m: 1,
    samples: heights.map((elevation, i) => ({
      distance_m: i * 10,
      elevation,
      lon: -1.853 + (i * 0.004) / (heights.length - 1),
      lat: 51.4286 + points * 0,
    })),
  };
}

beforeEach(() => {
  useCoverageStore.setState(useCoverageStore.getInitialState(), true);
  useProfileHover.setState({ hover: null });
  useMapTool.setState({ tool: null });
  api = routeApi(harness.fetchMock(), {
    "POST /terrain/profile": (call) => {
      const body = call.body as { line: { coordinates: unknown[] } };
      return json(profileAnswer(body.line.coordinates.length));
    },
    "GET /terrain/coverage": () => json(BORDER_COVERAGE),
  });
});

describe("the layer panel", () => {
  it("shows each terrain view with a preview and what it's good for, the default first", async () => {
    open("/?panel=layers");
    await mapReady();
    const panel = screen.getByRole("complementary", { name: "Layers" });
    const terrain = within(panel).getByRole("group", { name: "Terrain from LIDAR" });
    const radios = within(terrain).getAllByRole("radio");
    expect(radios[0]).toHaveAccessibleName("Composite");
    expect(radios[0]).toHaveAccessibleDescription(/Shows most earthworks/);
    // The term is explained where it first appears.
    expect(within(terrain).getByText(/LIDAR is a laser survey/)).toBeInTheDocument();

    // Each tiled view's preview is one of its own tiles, from the address /meta gives.
    const composite = metaFixture.layers.views.find((view) => view.id === "composite") as RasterView;
    const previews = terrain.querySelectorAll<HTMLImageElement>(".fc-view-preview img");
    // Every tiled terrain view, openness among them.
    expect(previews.length).toBe(6);
    expect(within(terrain).getByRole("radio", { name: "Openness" })).toHaveAccessibleDescription(/How much sky/);
    const first = new URL(previews[0]?.src ?? "");
    expect(first.origin + first.pathname).toBe(new URL(composite.tiles[0] ?? "").origin + first.pathname);
    expect(first.searchParams.get("bbox")?.split(",")).toHaveLength(4);
    // Raking light is drawn in the browser, so its preview is too.
    expect(terrain.querySelector(".fc-view-preview--raking")).not.toBeNull();
  });

  it("shows a plain preview, and keeps the panel up, for a tile address it can't fill", async () => {
    const views = metaFixture.layers.views.map((view) =>
      view.type === "raster" && view.id !== "composite"
        ? { ...view, tiles: ["https://{s}.tiles.example/{z}/{x}/{-y}.png"] }
        : view,
    );
    api.on("GET /meta", () => metaResponse({ ...metaFixture, layers: { ...metaFixture.layers, views } }));
    open("/?panel=layers");
    await mapReady();
    const terrain = within(screen.getByRole("complementary", { name: "Layers" })).getByRole("group", {
      name: "Terrain from LIDAR",
    });
    expect(terrain.querySelectorAll(".fc-view-preview img")).toHaveLength(1);
    expect(terrain.querySelectorAll(".fc-view-preview--empty").length).toBeGreaterThan(0);
  });

  it("shows the credit and licence of the view that is on, and of each overlay that is on", async () => {
    const user = userEvent.setup();
    open("/?panel=layers");
    await mapReady();
    const panel = screen.getByRole("complementary", { name: "Layers" });
    const credits = () => panel.querySelectorAll(".fc-layer-credit");
    // Composite is on, and so is the OpenStreetMap overlay, with its links.
    expect([...credits()].some((credit) => /Environment Agency/.test(credit.textContent ?? ""))).toBe(true);
    expect(within(panel).getAllByRole("link", { name: "OpenStreetMap" }).length).toBeGreaterThan(0);

    await user.click(within(panel).getByRole("radio", { name: "OpenStreetMap" }));
    const osmCredit = [...credits()].find((element) => element.textContent?.includes("contributors"));
    expect(osmCredit).toBeDefined();
    expect(within(osmCredit as HTMLElement).getByRole("link", { name: "OpenStreetMap" })).toHaveAttribute(
      "href",
      "https://www.openstreetmap.org/copyright",
    );
    // Its licence, by name, is one tap away beside the credit.
    expect(within(osmCredit as HTMLElement).getByRole("link", { name: "Open Database License 1.0" })).toHaveAttribute(
      "href",
      "https://www.openstreetmap.org/copyright",
    );
  });

  it("names a layer's licence once, when its credit already links it", async () => {
    const views = metaFixture.layers.views.map((view) =>
      view.id === "composite"
        ? {
            ...view,
            attribution: `© Environment Agency <a href="${view.licence_url}">Open Government Licence v3.0</a>`,
          }
        : view,
    );
    api.on("GET /meta", () => metaResponse({ ...metaFixture, layers: { ...metaFixture.layers, views } }));
    open("/?panel=layers");
    await mapReady();
    const panel = screen.getByRole("complementary", { name: "Layers" });
    const credit = [...panel.querySelectorAll(".fc-layer-credit")].find((each) =>
      each.textContent?.includes("Environment Agency"),
    );
    expect(within(credit as HTMLElement).getAllByRole("link", { name: "Open Government Licence v3.0" })).toHaveLength(
      1,
    );
  });

  it("opens the height profile from its terrain tools", async () => {
    const user = userEvent.setup();
    open("/?panel=layers");
    await mapReady();
    await user.click(screen.getByRole("link", { name: "Draw a height profile" }));
    expect(await screen.findByRole("heading", { name: "Height profile" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Layers" })).toBeNull();
  });
});

describe("the height profile", () => {
  it("draws a line from map clicks, asks for the heights, and charts them", async () => {
    open("/profile");
    const map = await mapReady();
    expect(screen.getByRole("heading", { name: "Draw a line on the map" })).toBeInTheDocument();
    expect(screen.getByTestId("profile-crosshair")).toBeInTheDocument();
    expect(useMapTool.getState().tool).toBe("profile");
    expect(map.doubleClickZoom.isEnabled()).toBe(false);

    act(() => map.fire("click", { point: { x: 10, y: 10 }, lngLat: { lng: -1.853, lat: 51.4286 } }));
    expect(await screen.findByRole("heading", { name: "Add one more point" })).toBeInTheDocument();
    act(() => map.fire("click", { point: { x: 90, y: 10 }, lngLat: { lng: -1.849, lat: 51.4286 } }));

    const chart = await screen.findByRole("slider", { name: "Height along the line" });
    const [call] = api.callsTo("POST /terrain/profile");
    expect(call?.headers.get("X-OpenAntiquity-Client")).toBe("web");
    expect(call?.body).toEqual({
      line: {
        type: "LineString",
        coordinates: [
          [-1.853, 51.4286],
          [-1.849, 51.4286],
        ],
      },
      // About one a metre along the 277.6 m line, so it is read from the 1 m grid.
      samples: 279,
    });
    expect(chart).toHaveAttribute("aria-valuemax", "100");
    expect(screen.getByText("every metre")).toBeInTheDocument();
    expect(screen.getByText("154.0 m")).toBeInTheDocument();
    expect(screen.getByText("165.0 m")).toBeInTheDocument();

    const drawn = map.sourceData(PROFILE_SOURCE) as { features: Array<{ properties: { kind: string } }> };
    expect(drawn.features.map((feature) => feature.properties.kind)).toEqual(["line", "point", "point"]);
    expect(map.getLayer(PROFILE_LAYERS.line)).toBeDefined();
  });

  it("is drawn by keyboard too: a point at the cross, then the chart's arrow keys", async () => {
    const user = userEvent.setup();
    open("/profile?line=-1.853,51.4286#m=16/51.4286/-1.85/0/0&v=composite");
    const map = await mapReady();
    // The cross is in the middle of the map the rail, the panel and the status bar leave showing.
    const cross = screen.getByTestId("profile-crosshair");
    expect(cross.style.left).toBe("calc(50% - 172px)");
    expect(cross.style.top).toBe("calc(50% - 14px)");
    await user.click(screen.getByRole("button", { name: "Add a point at the cross" }));
    const chart = await screen.findByRole("slider", { name: "Height along the line" });
    // And that is where the point goes, to the five places the address keeps: 172 px left of the map's middle, 14 px above it.
    const added = map.unproject([512 - 172, 384 - 14]);
    const body = api.callsTo("POST /terrain/profile")[0]?.body as { line: { coordinates: number[][] } };
    expect(body.line.coordinates[0]).toEqual([-1.853, 51.4286]);
    expect(body.line.coordinates[1]?.[0]).toBeCloseTo(added.lng, 4);
    expect(body.line.coordinates[1]?.[1]).toBeCloseTo(added.lat, 4);
    expect(added.lng).toBeLessThan(-1.85);

    chart.focus();
    await user.keyboard("{ArrowRight}");
    expect(chart).toHaveAttribute("aria-valuetext", "0 m along, 160.0 m high");
    await user.keyboard("{End}");
    expect(chart).toHaveAttribute("aria-valuetext", "100 m along, 161.0 m high");
    expect(screen.getByTestId("profile-chart-marker")).toBeInTheDocument();
    // The marker follows on the map.
    await waitFor(() => {
      const drawn = map.sourceData(PROFILE_SOURCE) as { features: Array<{ properties: { kind: string } }> };
      expect(drawn.features.at(-1)?.properties.kind).toBe("hover");
    });
    // Escape clears the marker and leaves the panel open.
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("profile-chart-marker")).toBeNull();
    expect(screen.getByRole("heading", { name: "Height profile" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remove the last point" }));
    expect(await screen.findByRole("heading", { name: "Add one more point" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start again" }));
    expect(screen.getByRole("heading", { name: "Draw a line on the map" })).toBeInTheDocument();
  });

  it("brings a line from a link out from under the panel", async () => {
    // The line's east end is on screen, but under the 400 px panel.
    open("/profile?line=-1.853,51.4286,-1.8455,51.4286#m=16/51.4286/-1.85/0/0&v=composite");
    await mapReady();
    await screen.findByRole("slider", { name: "Height along the line" });
    const { camera } = useMapStore.getState();
    const framing = framingFor(
      [
        [-1.853, 51.4286],
        [-1.8455, 51.4286],
      ],
      window.innerWidth,
      window.innerHeight,
      { left: 56, right: 400, top: 0, bottom: 28 },
    );
    expect(camera.lng).toBeCloseTo(framing?.lng ?? 0, 6);
    expect(camera.zoom).toBeCloseTo(framing?.zoom ?? 0, 6);
  });

  it("leaves the view alone when the whole line is already in sight", async () => {
    open("/profile?line=-1.853,51.4286,-1.851,51.4286#m=16/51.4286/-1.85/0/0&v=composite");
    await mapReady();
    await screen.findByRole("slider", { name: "Height along the line" });
    expect(useMapStore.getState().camera).toMatchObject({ lng: -1.85, zoom: 16 });
  });

  it("follows the pointer along the line on the map", async () => {
    open("/profile?line=-1.853,51.4286,-1.849,51.4286#m=16/51.4286/-1.851/0/0&v=composite");
    const map = await mapReady();
    await screen.findByRole("slider", { name: "Height along the line" });
    const sample = profileAnswer(2).samples[4];
    if (!sample) throw new Error("no sample");
    const at = map.project([sample.lon, sample.lat]);
    act(() => map.fire("mousemove", { point: at, lngLat: { lng: sample.lon, lat: sample.lat }, originalEvent: {} }));
    await waitFor(() => expect(useProfileHover.getState().hover).toBe(4));
    expect(screen.getByTestId("profile-chart-marker")).toHaveTextContent("40 m along: 154.0 m");
    // Far from the line, the marker goes.
    act(() =>
      map.fire("mousemove", { point: { x: at.x, y: at.y + 200 }, lngLat: { lng: 0, lat: 0 }, originalEvent: {} }),
    );
    await waitFor(() => expect(useProfileHover.getState().hover).toBeNull());
  });

  it("doesn't open a record under a point being placed", async () => {
    open("/profile");
    const map = await mapReady();
    map.rendered = [{ id: 7, properties: { id: 7, category: "designation" }, layer: { id: "records-squares" } }];
    act(() => map.fire("click", { point: { x: 10, y: 10 }, lngLat: { lng: -1.853, lat: 51.4286 } }));
    expect(await screen.findByRole("heading", { name: "Add one more point" })).toBeInTheDocument();
    expect(api.callsTo("GET /records/7")).toHaveLength(0);
  });

  it("says why when the server refuses a line, and offers another try when it fails", async () => {
    const user = userEvent.setup();
    api.on("POST /terrain/profile", () => apiError(400, "invalid_profile", "A profile line can be at most 5 km long."));
    open("/profile?line=-1.9,51.4,-1.8,51.45");
    await mapReady();
    expect(await screen.findByRole("heading", { name: "That line can't be profiled" })).toBeInTheDocument();
    expect(screen.getByText("A profile line can be at most 5 km long.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();

    let failing = true;
    api.on("POST /terrain/profile", () =>
      failing ? apiError(503, "http_503", "The server isn't answering.") : json(profileAnswer(2)),
    );
    await user.click(screen.getByRole("button", { name: "Remove the last point" }));
    await user.click(screen.getByRole("button", { name: "Add a point at the cross" }));
    expect(await screen.findByRole("heading", { name: "The heights couldn't be loaded" })).toBeInTheDocument();
    failing = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("slider", { name: "Height along the line" })).toBeInTheDocument();
  });

  it("lets the map have its clicks back when the panel closes", async () => {
    const user = userEvent.setup();
    open("/profile");
    const map = await mapReady();
    await user.click(screen.getByRole("button", { name: "Close panel" }));
    await waitFor(() => expect(useMapTool.getState().tool).toBeNull());
    expect(map.doubleClickZoom.isEnabled()).toBe(true);
    expect(screen.queryByTestId("profile-crosshair")).toBeNull();
  });

  it("says so when there is no height data anywhere along the line", async () => {
    api.on("POST /terrain/profile", () => {
      const answer = profileAnswer(2);
      return json({ ...answer, samples: answer.samples.map((sample) => ({ ...sample, elevation: null })) });
    });
    open("/profile?line=-1.853,51.4286,-1.849,51.4286#m=16/51.4286/-1.851/0/0&v=composite");
    await mapReady();
    expect(await screen.findByRole("heading", { name: "There's no height data along this line" })).toBeInTheDocument();
    expect(screen.queryByRole("slider", { name: "Height along the line" })).toBeNull();
    const panel = screen.getByRole("complementary", { name: "Height profile" });
    expect(within(panel).queryByText("– m")).toBeNull();
  });

  it("says why no more points can be added once the line has as many as it can take", async () => {
    const many = Array.from({ length: MAX_LINE_POINTS }, (_, i) => `${(-1.853 + i * 0.00002).toFixed(5)},51.4286`);
    open(`/profile?line=${many.join(",")}#m=16/51.4286/-1.851/0/0&v=composite`);
    const map = await mapReady();
    await screen.findByRole("slider", { name: "Height along the line" });
    expect(screen.getByRole("button", { name: "Add a point at the cross" })).toBeDisabled();
    expect(screen.getByText(/This line has the most points it can take, 200/)).toBeInTheDocument();
    const before = window.location.search;
    act(() => map.fire("click", { point: { x: 10, y: 10 }, lngLat: { lng: -1.84, lat: 51.4286 } }));
    expect(window.location.search).toBe(before);
  });
});

describe("coverage", () => {
  const BORDER = "/#m=11/51.65/-2.675/0/0&v=composite";

  it("shades the squares of a terrain view that have no data, and says so", async () => {
    open(BORDER);
    const map = await mapReady();
    await waitFor(() => expect(api.callsTo("GET /terrain/coverage")).toHaveLength(1));
    expect(api.callsTo("GET /terrain/coverage")[0]?.url.searchParams.get("bbox")).toBe("-3,51.5,-2.25,51.75");
    expect(await screen.findByTestId("coverage-notice")).toHaveTextContent("Shaded squares have no one-metre LIDAR");
    expect(map.isVisible(COVERAGE_LAYERS.gapsFill)).toBe(true);
    expect(map.isVisible(COVERAGE_LAYERS.coverageLine)).toBe(false);
    // The shading sits on the terrain, under every overlay.
    const ids = map.getStyle().layers.map((layer) => layer.id);
    expect(ids.indexOf(COVERAGE_LAYERS.gapsFill)).toBeGreaterThan(ids.indexOf("view-slope"));
    expect(ids.indexOf(COVERAGE_LAYERS.gapsFill)).toBeLessThan(ids.indexOf("osm-road-major"));

    // A map, not a terrain view, has nothing to shade.
    act(() => useMapStore.getState().setMainView("osm_standard"));
    await waitFor(() => expect(map.isVisible(COVERAGE_LAYERS.gapsFill)).toBe(false));
    expect(screen.queryByTestId("coverage-notice")).toBeNull();
  });

  it("outlines where the data is, with what it is, from the layer panel", async () => {
    const user = userEvent.setup();
    open(`/?panel=layers${BORDER.slice(1)}`);
    const map = await mapReady();
    const panel = screen.getByRole("complementary", { name: "Layers" });
    await user.click(within(panel).getByRole("switch", { name: "Where there's one-metre LIDAR" }));
    await waitFor(() => expect(map.isVisible(COVERAGE_LAYERS.coverageLine)).toBe(true));
    expect(await within(panel).findByTestId("coverage-summary")).toHaveTextContent(
      /In view: 2022 composite, flown between 2005 and 2022, with \d+ of \d+ squares empty\./,
    );
  });

  it("doesn't let the data in view stand unqualified when the terrain on screen isn't loading", async () => {
    const user = userEvent.setup();
    open(`/?panel=layers${BORDER.slice(1)}`);
    await mapReady();
    const panel = screen.getByRole("complementary", { name: "Layers" });
    await user.click(within(panel).getByRole("switch", { name: "Where there's one-metre LIDAR" }));
    const summary = await within(panel).findByTestId("coverage-summary");
    expect(summary).not.toHaveTextContent(/isn't loading/);
    act(() => useMapStore.getState().setSourceFailing(viewTroubleKey("composite"), true));
    expect(summary).toHaveTextContent(/The terrain isn't loading here at the moment/);
  });

  it("puts the switch for the map drawn over the terrain first, and says what it is for", async () => {
    open("/?panel=layers");
    await mapReady();
    const panel = screen.getByRole("complementary", { name: "Layers" });
    const switches = within(panel).getAllByRole("switch");
    expect(switches[0]).toHaveAccessibleName("OpenStreetMap");
    expect(switches[0]).toHaveAccessibleDescription(/Switch it off to see the terrain alone/);
    // Once, at the top, and not again among the other overlays.
    expect(within(panel).getAllByRole("switch", { name: "OpenStreetMap" })).toHaveLength(1);
  });

  it("says what the scan coverage overlay shows, as it is a different coverage", async () => {
    open("/?panel=layers");
    await mapReady();
    const panel = screen.getByRole("complementary", { name: "Layers" });
    expect(within(panel).getByRole("switch", { name: "Scan coverage" })).toHaveAccessibleDescription(
      /how many people have looked it over/,
    );
  });

  it("asks nothing when zoomed out too far to say square by square", async () => {
    open("/#m=7/52.5/-1.5/0/0&v=composite");
    await mapReady();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(api.callsTo("GET /terrain/coverage")).toHaveLength(0);
  });

  it("says when the terrain is still being prepared, and stops once it is in", async () => {
    open("/#m=15/51.4286/-1.8542/0/0&v=composite");
    const map = await mapReady();
    // Another source loading says nothing.
    act(() => map.fire("dataloading", { dataType: "source", sourceId: "overlay-records" }));
    act(() => map.fire("dataloading", { dataType: "source", sourceId: "view-composite" }));
    expect(screen.queryByText(/Preparing the terrain/)).toBeNull();
    expect(await screen.findByText(/Preparing the terrain here/, {}, { timeout: 3000 })).toBeInTheDocument();
    act(() => map.fire("sourcedata", { dataType: "source", sourceId: "view-composite", isSourceLoaded: true }));
    expect(screen.queryByText(/Preparing the terrain/)).toBeNull();
  });

  it("says that a zoomed-out view draws only places looked at closely", async () => {
    open("/#m=8/52.5/-1.5/0/0&v=composite");
    await mapReady();
    expect(await screen.findByTestId("coverage-notice")).toHaveTextContent(
      "Zoomed out this far, only places someone has looked at closely are drawn.",
    );
    // Not over a map that isn't terrain.
    act(() => useMapStore.getState().setMainView("osm_standard"));
    expect(screen.queryByTestId("coverage-notice")).toBeNull();
  });

  it("says the zoomed-out terrain is an overview once /meta says the overview is built", async () => {
    const terrain = { fine_minzoom: 12, catalogue_tiles: 5877, overview: { built: true, built_at: null, tiles: 412 } };
    api.on("GET /meta", () => json({ ...metaFixture, terrain }));
    open("/#m=8/52.5/-1.5/0/0&v=composite");
    await mapReady();
    expect(await screen.findByTestId("coverage-notice")).toHaveTextContent(
      "Zoomed out this far, the terrain is a coarse overview.",
    );
  });

  it("says plainly when the whole view has no data", async () => {
    api.on("GET /terrain/coverage", () => json({ type: "FeatureCollection", features: [] }));
    open("/#m=12/52.4/-3.9/0/0&v=composite");
    await mapReady();
    expect(await screen.findByTestId("coverage-notice")).toHaveTextContent("No one-metre LIDAR here.");
  });
});

describe("the camera and the status bar", () => {
  it("offers plan view whenever the map is tilted, and goes back to it", async () => {
    const user = userEvent.setup();
    open("/");
    const map = await mapReady();
    expect(screen.queryByRole("button", { name: "Back to plan view" })).toBeNull();
    act(() => map.userMove({ pitch: 45, bearing: 30 }));
    await user.click(await screen.findByRole("button", { name: "Back to plan view" }));
    expect(map.getPitch()).toBe(0);
    expect(map.getBearing()).toBe(0);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Back to plan view" })).toBeNull());
  });

  it("reads out the middle of what's showing, not of the window, when a panel covers part of the map", async () => {
    open("/profile#m=16/51.4286/-1.85/0/0&v=composite");
    await mapReady();
    const { cover } = useMapCover.getState();
    expect(cover.right).toBeGreaterThan(0);
    const middle = visibleCentre(useMapStore.getState().camera, cover);
    const coords = screen.getByTestId("status-coords");
    expect(coords).toHaveTextContent(coordinateText(middle.lng, middle.lat));
    expect(coords).not.toHaveTextContent(coordinateText(-1.85, 51.4286));
  });

  it("copies the grid reference of the middle of the map", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    open("/");
    await mapReady();
    await user.click(screen.getByRole("button", { name: "Copy the grid reference of the middle of the map" }));
    expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/^SU \d{3,4} \d{3,4}$/));
    expect(useToastStore.getState().toasts.at(-1)?.message).toMatch(/^Copied SU /);
  });
});
