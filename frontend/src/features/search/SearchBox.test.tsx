import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMapStore } from "../../map/store.js";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import {
  AVENUE_RECORD,
  GEO_RESULTS,
  GRIDREF_RESULT,
  NHLE_SOURCE,
  OS_NAMES_SOURCE,
} from "../../test/fixtures/records.js";
import { json, mapReady, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import { useRecordSearch } from "../records/searchStore.js";
import type { GeoResult } from "./api.js";
import { SEARCH_DEBOUNCE_MS } from "./SearchBox.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();
let api: ApiRoutes;

beforeEach(() => {
  useRecordSearch.setState(useRecordSearch.getInitialState(), true);
  api = routeApi(harness.fetchMock(), {
    "GET /geo/search": (call) => {
      const q = call.url.searchParams.get("q") ?? "";
      if (q.startsWith("ave")) return json({ items: GEO_RESULTS });
      if (q.startsWith("su")) return json({ items: [GRIDREF_RESULT] });
      if (q === "slow") return apiError(503, "search_timeout", "That search took too long.");
      if (q === "broken") return apiError(500, "internal_error", "Oops");
      if (q === "refused") return apiError(422, "validation_error", "q is too long");
      return json({ items: [] });
    },
    [`GET /records/${AVENUE_RECORD.id}`]: () => json(AVENUE_RECORD),
  });
});

async function openSearch() {
  const user = userEvent.setup();
  renderShell();
  await mapReady();
  const box = screen.getByRole("combobox", { name: /Search for a place/ });
  return { user, box };
}

function searches(): string[] {
  return api.callsTo("GET /geo/search").map((call) => call.url.searchParams.get("q") ?? "");
}

describe("the search box", () => {
  it("waits for typing to pause, then asks once for what was typed", async () => {
    const { user, box } = await openSearch();
    await user.type(box, "ave");
    await screen.findByRole("option", { name: /West Kennet Avenue/ });
    expect(searches()).toEqual(["ave"]);
  });

  it("asks nothing for a single letter, which would match thousands of names", async () => {
    const { user, box } = await openSearch();
    await user.type(box, "a");
    await new Promise((resolve) => setTimeout(resolve, SEARCH_DEBOUNCE_MS + 100));
    expect(searches()).toEqual([]);
    expect(box).toHaveAttribute("aria-expanded", "false");
  });

  it("cancels a search that the text has moved past", async () => {
    const signals: AbortSignal[] = [];
    api.on("GET /geo/search", (call) => {
      if (call.url.searchParams.get("q") === "av") {
        const init = harness.fetchMock().mock.calls.at(-1)?.[1] as RequestInit | undefined;
        if (init?.signal) signals.push(init.signal);
        return new Promise<Response>(() => {});
      }
      return json({ items: GEO_RESULTS });
    });
    const { user, box } = await openSearch();
    await user.type(box, "av");
    await waitFor(() => expect(signals).toHaveLength(1));
    await user.type(box, "e");
    await screen.findByRole("option", { name: /West Kennet Avenue/ });
    expect(signals[0]?.aborted).toBe(true);
  });

  it("groups results by kind and is worked by keyboard alone", async () => {
    const { user, box } = await openSearch();
    await user.type(box, "ave");
    await screen.findByRole("option", { name: /West Kennet Avenue/ });
    const list = screen.getByRole("listbox", { name: "Search results" });
    expect(within(list).getByRole("group", { name: "Places" })).toBeInTheDocument();
    expect(within(list).getByRole("group", { name: "Heritage records" })).toBeInTheDocument();
    expect(within(list).getByRole("group", { name: "Findings" })).toBeInTheDocument();
    expect(box).toHaveAttribute("aria-expanded", "true");

    // Places come first, two of them, then the record.
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}");
    const active = screen.getByRole("option", { name: /West Kennet Avenue/ });
    expect(active).toHaveAttribute("aria-selected", "true");
    expect(box).toHaveAttribute("aria-activedescendant", active.id);
    // Up goes back, and down again comes forward.
    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("option", { name: /Avebury Trusloe/ })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowDown}{Enter}");

    // The map goes to the middle of the record's outline, and its page opens.
    const panel = await screen.findByRole("complementary", { name: AVENUE_RECORD.name });
    expect(within(panel).getByText("Scheduled monument")).toBeInTheDocument();
    const camera = useMapStore.getState().camera;
    expect(camera.zoom).toBe(16);
    expect(camera.lng).toBeCloseTo(AVENUE_RECORD.lon, 6);
    expect(box).toHaveValue(AVENUE_RECORD.name);
    expect(box).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the list with Escape, then clears the field with a second Escape", async () => {
    const { user, box } = await openSearch();
    await user.type(box, "ave");
    await screen.findByRole("option", { name: /Avebury Trusloe/ });
    await user.keyboard("{Escape}");
    expect(box).toHaveAttribute("aria-expanded", "false");
    expect(box).toHaveValue("ave");
    await user.keyboard("{Escape}");
    expect(box).toHaveValue("");
  });

  it("takes the first result when Enter is pressed before the results arrive", async () => {
    const { user, box } = await openSearch();
    await user.type(box, "su 1023 6987{Enter}");
    await waitFor(() => expect(useMapStore.getState().camera.zoom).toBe(17));
    expect(box).toHaveValue(GRIDREF_RESULT.label);
  });

  it("says plainly when nothing matches, when a search took too long, and when search is down", async () => {
    const { user, box } = await openSearch();
    await user.type(box, "zzz");
    expect(await screen.findByText(/Nothing matches “zzz”/)).toBeInTheDocument();
    await user.clear(box);
    await user.type(box, "slow");
    expect(await screen.findByText(/That search took too long/)).toBeInTheDocument();
    await user.clear(box);
    await user.type(box, "broken");
    expect(await screen.findByText(/Search isn't working right now/)).toBeInTheDocument();
  });

  it("asks nothing more once a result is chosen, until the text changes", async () => {
    const { user, box } = await openSearch();
    await user.type(box, "su");
    await user.click(await screen.findByRole("option", { name: new RegExp(GRIDREF_RESULT.label) }));
    expect(box).toHaveValue(GRIDREF_RESULT.label);
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(searches()).toEqual(["su"]);
    await user.type(box, "1");
    await waitFor(() => expect(searches()).toEqual(["su", `${GRIDREF_RESULT.label}1`]));
  });

  it("offers another try, as an option, when search is down", async () => {
    let down = true;
    api.on("GET /geo/search", () => (down ? apiError(500, "internal_error", "Oops") : json({ items: GEO_RESULTS })));
    const { user, box } = await openSearch();
    await user.type(box, "ave");
    const retry = await screen.findByRole("option", { name: "Try again" });
    expect(screen.getByText(/Search isn't working right now/)).toBeInTheDocument();
    down = false;
    await user.keyboard("{ArrowDown}");
    expect(retry).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("option", { name: /West Kennet Avenue/ })).toBeInTheDocument();
    expect(box).toHaveFocus();
    expect(searches()).toEqual(["ave", "ave"]);
  });

  it("offers the record search for the same words, last in the list", async () => {
    const { user, box } = await openSearch();
    await user.type(box, "barrow");
    await screen.findByText(/Nothing matches/);
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: /Search the heritage records for “barrow”/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("complementary", { name: "Search the records" })).toBeInTheDocument();
    expect(useRecordSearch.getState().q).toBe("barrow");
  });

  it("credits where the names come from, with each licence as a link", async () => {
    const { user, box } = await openSearch();
    await user.type(box, "ave");
    await screen.findByRole("option", { name: /West Kennet Avenue/ });
    const credits = screen.getByRole("list", { name: "Where these names come from" });
    const lines = within(credits).getAllByRole("listitem");
    // Each source once, though two places come from the gazetteer.
    expect(lines).toHaveLength(2);
    expect(lines[0]).toHaveTextContent(`${OS_NAMES_SOURCE.name} · ${OS_NAMES_SOURCE.licence}`);
    expect(within(lines[0] as HTMLElement).getByRole("link", { name: OS_NAMES_SOURCE.licence })).toHaveAttribute(
      "href",
      OS_NAMES_SOURCE.licence_url,
    );
    expect(lines[1]).toHaveTextContent(`${NHLE_SOURCE.name} · ${NHLE_SOURCE.licence}`);
  });

  it("goes straight there on Enter only for a sure match, and otherwise shows the list", async () => {
    const { user, box } = await openSearch();
    const before = useMapStore.getState().camera;
    // The first result, "Avebury", is only like "ave".
    await user.type(box, "ave");
    await screen.findByRole("option", { name: /West Kennet Avenue/ });
    await user.keyboard("{Enter}");
    expect(box).toHaveAttribute("aria-expanded", "true");
    expect(box).toHaveValue("ave");
    expect(useMapStore.getState().camera).toEqual(before);
    // A place named exactly what was typed, whatever the case, is taken.
    await user.clear(box);
    await user.type(box, "avebury{Enter}");
    await waitFor(() => expect(box).toHaveValue("Avebury"));
    await waitFor(() => expect(box).toHaveAttribute("aria-expanded", "false"));
    expect(useMapStore.getState().camera.zoom).toBe(14);
  });

  it("doesn't fly to a record that only shares a name, when Enter is pressed before the results arrive", async () => {
    const lookalike: GeoResult = { ...(GEO_RESULTS[1] as GeoResult), label: "STONEHENGE", zoom: 18 };
    api.on("GET /geo/search", () => json({ items: [lookalike] }));
    const { user, box } = await openSearch();
    await user.type(box, "Stonehenge{Enter}");
    expect(await screen.findByRole("option", { name: /STONEHENGE/ })).toBeInTheDocument();
    expect(box).toHaveAttribute("aria-expanded", "true");
    expect(useMapStore.getState().camera.zoom).not.toBe(18);
    expect(screen.queryByRole("complementary", { name: AVENUE_RECORD.name })).toBeNull();
  });

  it("stops at the server's limit, and asks for a shorter search, with no retry, when one is refused", async () => {
    const { user, box } = await openSearch();
    expect(box).toHaveAttribute("maxLength", "200");
    await user.type(box, "refused");
    expect(await screen.findByText(/more than can be searched for at once/)).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Try again" })).toBeNull();
  });

  it("shows a name's entities as the characters they stand for", async () => {
    api.on("GET /geo/search", () =>
      json({ items: [{ ...(GEO_RESULTS[1] as GeoResult), label: "Monitoring &amp; Recording" }] }),
    );
    const { user, box } = await openSearch();
    await user.type(box, "monitoring");
    expect(await screen.findByRole("option", { name: /Monitoring & Recording/ })).toBeInTheDocument();
    expect(screen.queryByText(/&amp;/)).toBeNull();
  });

  it("goes nowhere for a record whose id is not a record id", async () => {
    api.on("GET /geo/search", () => json({ items: [{ ...(GEO_RESULTS[1] as GeoResult), ref: "../account" }] }));
    const { user, box } = await openSearch();
    await user.type(box, "west");
    await user.click(await screen.findByRole("option", { name: /West Kennet Avenue/ }));
    expect(box).toHaveValue(AVENUE_RECORD.name);
    expect(screen.queryByRole("complementary")).toBeNull();
  });
});
