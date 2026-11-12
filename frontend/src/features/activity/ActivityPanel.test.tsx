import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useViewAreaStore } from "../../map/store.js";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { FakeEventSource, useFakeEventSource } from "../../test/fakeEventSource.js";
import { pageFixture, seenFixture, suggestionsFixture } from "../../test/fixtures/findingPage.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import { useSelectedFinding } from "../findings/selection.js";
import type { ActivityItem } from "./api.js";
import { useLiveStatus } from "./LiveEvents.js";
import { useFeedFilters } from "./useActivityFeed.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

beforeEach(() => {
  useFeedFilters.getState().clear();
  useSelectedFinding.getState().clear();
  useLiveStatus.setState({ status: null });
  useFakeEventSource();
});

const ADA = { handle: "QuietBarrow42", display_name: "Ada Lovelace", role: "member" };
const RING = pageFixture();

function activityItem(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    id: 1,
    kind: "finding_created",
    created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    actor: null,
    finding: {
      public_id: RING.public_id,
      title: RING.title,
      feature_class: RING.feature_class,
      tier: "spotted",
      state: "open",
      location: RING.location,
    },
    investigation: null,
    details: {},
    ...overrides,
  };
}

const SQUARE_FINDING = {
  public_id: "f-barrow",
  title: "Round barrow in SU 10 69",
  feature_class: "round_barrow" as const,
  tier: "spotted" as const,
  state: "open" as const,
  location: { lon: -1.855, lat: 51.425, obscured: true, grid_ref: null, square: "SU1069", outline: null },
};

const FEED: ActivityItem[] = [
  activityItem({ id: 3, kind: "tier_changed", details: { tier_from: "spotted", tier_to: "seen" } }),
  activityItem({ id: 2, kind: "finding_created", actor: ADA, finding: SQUARE_FINDING }),
  activityItem({
    id: 1,
    kind: "investigation_published",
    actor: ADA,
    finding: null,
    investigation: { public_id: "i-ridge", title: "Barrows of the Ridgeway" },
  }),
];

function serve(items: ActivityItem[] = FEED): ApiRoutes {
  const path = `/findings/${RING.public_id}`;
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => signedOutResponse(),
    "GET /activity": () => json({ items, next_cursor: null }),
    [`GET ${path}`]: () => json(RING),
    [`GET ${path}/comments`]: () => json({ items: [], next_cursor: null }),
    [`GET ${path}/suggested-records`]: () => json(suggestionsFixture([])),
  });
}

async function openFeed() {
  renderShell("/activity");
  await mapReady();
  const panel = within(await screen.findByRole("complementary", { name: "Activity" }));
  const list = within(await panel.findByRole("list", { name: "What has happened" }));
  return { panel, list };
}

describe("the activity feed", () => {
  it("says what happened, newest first, naming nobody the server didn't name", async () => {
    serve();
    const { list } = await openFeed();
    const rows = list.getAllByRole("listitem").map((row) => row.textContent);
    expect(rows[0]).toMatch(/^Ring ditch by the long barrow moved up to Seen by others\.5 minutes ago$/);
    expect(rows[1]).toMatch(/^Ada Lovelace marked Round barrow in SU 10 69\..*Somewhere in square SU 10 69$/);
    expect(rows[2]).toMatch(/^Ada Lovelace published Barrows of the Ridgeway\./);
    expect(list.getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
      "/f/f-ring",
      "/f/f-barrow",
      "/i/i-ridge",
    ]);
  });

  it("opens an item's finding, marked on the map by its square when that is all the viewer may see", async () => {
    const user = userEvent.setup();
    serve();
    const { list } = await openFeed();
    await user.click(list.getByRole("link", { name: /Ada Lovelace marked/ }));
    expect(useSelectedFinding.getState().selected?.square).not.toBeNull();
    await user.click(screen.getByRole("link", { name: "Activity" }));
    await user.click((await openedList()).getByRole("link", { name: /moved up to Seen by others/ }));
    expect(await screen.findByRole("complementary", { name: RING.title })).toBeInTheDocument();
    expect(useSelectedFinding.getState().selected).toMatchObject({ publicId: RING.public_id, square: null });
  });

  it("narrows to the map's view and to kinds of activity, and says what to do when nothing matches", async () => {
    const user = userEvent.setup();
    const routes = serve();
    const { panel } = await openFeed();
    act(() => useViewAreaStore.getState().setArea([-1.9, 51.4, -1.8, 51.45], 14));
    await user.click(panel.getByRole("button", { name: "Filters" }));
    await user.click(panel.getByRole("radio", { name: "In the map's view" }));
    await waitFor(() => expect(routes.callsTo("GET /activity").at(-1)?.url.searchParams.get("bbox")).not.toBeNull());
    // Widened by half a grid square, because the server matches each event by its square's centre.
    const [west, south] = (routes.callsTo("GET /activity").at(-1)?.url.searchParams.get("bbox") ?? "")
      .split(",")
      .map(Number);
    expect(west).toBeLessThan(-1.9);
    expect(south).toBeLessThan(51.4);

    routes.on("GET /activity", () => json({ items: [], next_cursor: null }));
    await user.click(panel.getByRole("button", { name: "Steps and states" }));
    await waitFor(() =>
      expect(routes.callsTo("GET /activity").at(-1)?.url.searchParams.getAll("kind")).toEqual([
        "tier_changed",
        "state_changed",
      ]),
    );
    expect(await panel.findByText("Nothing like that has happened here yet")).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Filters (2)" })).toBeInTheDocument();
    await user.click(panel.getAllByRole("button", { name: "Clear filters" })[0] as HTMLElement);
    // Everywhere and every kind, as the feed first asked.
    expect(await panel.findByRole("list", { name: "What has happened" })).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Filters" })).toBeInTheDocument();
  });

  it("says when nothing has happened, and offers a retry when the feed fails", async () => {
    const user = userEvent.setup();
    const routes = serve([]);
    renderShell("/activity");
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Activity" }));
    expect(await panel.findByText("Nothing has happened yet")).toBeInTheDocument();

    routes.on("GET /activity", () => apiError(500, "internal", "The server tripped over."));
    await user.click(screen.getByRole("link", { name: "Explore" }));
    useFeedFilters.getState().setGroups(["looks"]);
    await user.click(screen.getByRole("link", { name: "Activity" }));
    // A server error is tried once more before the person is told.
    const failed = await screen.findByRole("alert", undefined, { timeout: 4000 });
    expect(failed).toHaveTextContent("The activity couldn't be loaded");
    expect(failed).toHaveTextContent("The server tripped over.");
    routes.on("GET /activity", () => json({ items: FEED, next_cursor: null }));
    await user.click(within(failed).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("list", { name: "What has happened" })).toBeInTheDocument();
  });
});

async function openedList() {
  const panel = within(await screen.findByRole("complementary", { name: "Activity" }));
  return within(await panel.findByRole("list", { name: "What has happened" }));
}

describe("live events", () => {
  it("opens one stream for the whole app, and asks the feed again when something happens", async () => {
    const user = userEvent.setup();
    const routes = serve();
    const { panel } = await openFeed();
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.current().url).toBe("/api/v1/events/stream");
    act(() => FakeEventSource.current().open());
    expect(panel.getByRole("status")).toHaveTextContent("New activity shows here as it happens.");

    const before = routes.callsTo("GET /activity").length;
    routes.on("GET /activity", () =>
      json({
        items: [activityItem({ id: 4, kind: "comment_added", actor: ADA }), ...FEED],
        next_cursor: null,
      }),
    );
    act(() => {
      FakeEventSource.current().activity({ id: 4, kind: "comment_added", finding: RING.public_id, actor: ADA.handle });
      FakeEventSource.current().activity({ id: 5, kind: "observation_added", finding: RING.public_id });
    });
    expect(await panel.findByText(/commented on/, undefined, { timeout: 3000 })).toBeInTheDocument();
    // Two events close together are one refetch.
    expect(routes.callsTo("GET /activity").length).toBe(before + 1);

    await user.click(screen.getByRole("link", { name: "Explore" }));
    await user.click(screen.getByRole("link", { name: "Activity" }));
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("moves a finding's page up a step as it happens, and refetches the page on a resync", async () => {
    let finding = pageFixture();
    const path = `/findings/${finding.public_id}`;
    const routes = routeApi(harness.fetchMock(), {
      "GET /auth/me": () => signedOutResponse(),
      [`GET ${path}`]: () => json(finding),
      [`GET ${path}/comments`]: () => json({ items: [], next_cursor: null }),
      [`GET ${path}/suggested-records`]: () => json(suggestionsFixture([])),
    });
    renderShell(`/f/${finding.public_id}`);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: finding.title }));
    const badges = document.querySelector(".fc-finding__badges") as HTMLElement;
    expect(within(badges).getByText("Spotted")).toBeInTheDocument();
    act(() => FakeEventSource.current().open());

    finding = seenFixture();
    act(() =>
      FakeEventSource.current().activity({ id: 9, kind: "tier_changed", finding: finding.public_id, actor: null }),
    );
    expect(await within(badges).findByText("Seen by others")).toBeInTheDocument();
    expect(panel.getByRole("meter", { name: "Confidence" })).toHaveAttribute("aria-valuenow", "36");
    expect(panel.getByText(/It has moved up to Seen by others/)).toBeInTheDocument();

    // An event about another finding leaves this page alone.
    const asked = routes.callsTo(`GET ${path}`).length;
    act(() => FakeEventSource.current().activity({ id: 10, kind: "comment_added", finding: "f-other" }));
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(routes.callsTo(`GET ${path}`).length).toBe(asked);

    act(() => FakeEventSource.current().signal("resync"));
    await waitFor(() => expect(routes.callsTo(`GET ${path}`).length).toBe(asked + 1));
  });
});
