import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { type ApiRoutes, routeApi } from "../../test/apiRoutes.js";
import { seenFixture, suggestionsFixture } from "../../test/fixtures/findingPage.js";
import { meFixture } from "../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import type { TaskGroup, TaskItem } from "./api.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

function task(publicId: string, code: TaskItem["code"], title: string, missing: string[] = []): TaskItem {
  const blind = code === "need_observers";
  return {
    public_id: publicId,
    code,
    place: { lon: -1.85, lat: 51.42, obscured: false, grid_ref: "SU 1025 6996", square: null, outline: null },
    view_state: {},
    step: blind
      ? null
      : { code, prompt: "It needs two more kinds of evidence.", missing_strands: missing, pending_evidence: [] },
    finding: blind ? null : { title, feature_class: "enclosure", tier: "seen", state: "open" },
  };
}

const GROUPS: TaskGroup[] = [
  { code: "need_observers", total: 3, items: [task("blind-1", "need_observers", "")], next_cursor: null, strands: [] },
  {
    code: "need_strand",
    total: 2,
    items: [
      task("f-ring", "need_strand", "Ring ditch by the long barrow", ["historic_map", "aerial"]),
      task("f-bank", "need_strand", "Bank along the parish edge", ["aerial"]),
    ],
    next_cursor: null,
    strands: [
      { strand: "historic_map", total: 1 },
      { strand: "aerial", total: 2 },
    ],
  },
];

function serve(groups: TaskGroup[] = GROUPS): ApiRoutes {
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => json(meFixture()),
    "GET /review/tasks": (call) => {
      const code = call.url.searchParams.get("code");
      return json({ groups: code ? groups.filter((group) => group.code === code) : groups });
    },
  });
}

async function openHelp(path = "/help") {
  renderShell(path);
  await mapReady();
}

describe("help wanted", () => {
  it("lists the kinds of work by name, with what each is and how many findings want it", async () => {
    serve();
    await openHelp();
    const panel = within(screen.getByRole("complementary", { name: "Help wanted" }));
    const kinds = within(await panel.findByRole("list", { name: "Kinds of help" }));
    const looks = kinds.getByRole("link", { name: /^Second looks/ });
    expect(looks).toHaveAttribute("href", "/review");
    expect(looks).toHaveTextContent("3 findings");
    const maps = kinds.getByRole("link", { name: /^Map detectives/ });
    expect(maps).toHaveTextContent("Map detectives check old maps");
    expect(maps).toHaveTextContent("1 finding");
    expect(maps).toHaveAttribute("href", "/help/historic_map");
    expect(kinds.getByRole("link", { name: /^Sky checkers/ })).toHaveTextContent("2 findings");
    // Kinds with nothing waiting are named once, out of the way.
    expect(kinds.queryByRole("link", { name: /^Field walkers/ })).toBeNull();
    expect(panel.getByText(/Nothing waiting just now for .*field walkers/)).toBeInTheDocument();
  });

  it("never names a finding that wants a second look", async () => {
    serve();
    await openHelp();
    await screen.findByRole("list", { name: "Kinds of help" });
    expect(document.body.textContent).not.toContain("blind-1");
    expect(document.querySelector('a[href*="blind-1"]')).toBeNull();
  });

  it("opens a kind's list, and each finding opens its page with that form ready", async () => {
    const user = userEvent.setup();
    const routes = serve();
    const finding = seenFixture();
    routes.on(`GET /findings/${finding.public_id}`, () => json(finding));
    routes.on(`GET /findings/${finding.public_id}/comments`, () => json({ items: [], next_cursor: null }));
    routes.on(`GET /findings/${finding.public_id}/suggested-records`, () => json(suggestionsFixture([])));
    await openHelp();
    await user.click(await screen.findByRole("link", { name: /^Map detectives/ }));

    const panel = within(await screen.findByRole("complementary", { name: "Map detectives" }));
    const list = within(await panel.findByRole("list", { name: "Findings that need this" }));
    expect(list.getAllByRole("link")).toHaveLength(1);
    expect(document.title).toBe("Map detectives · Help wanted · OpenAntiquity");
    await user.click(list.getByRole("link", { name: /Ring ditch by the long barrow/ }));

    const page = within(await screen.findByRole("complementary", { name: finding.title }));
    expect(await page.findByRole("heading", { name: "Add old map" })).toBeInTheDocument();
    // The request is taken out of the address once the form is open.
    await waitFor(() => expect(window.location.search).toBe(""));
  });

  it("sends the address of second looks to the queue", async () => {
    serve();
    await openHelp("/help/second-look");
    expect(await screen.findByRole("complementary", { name: "Second look" })).toBeInTheDocument();
  });

  it("says when nothing needs a hand, and offers other work", async () => {
    serve([]);
    await openHelp();
    const panel = within(screen.getByRole("complementary", { name: "Help wanted" }));
    expect(await panel.findByRole("heading", { name: "Nothing needs a hand just now" })).toBeInTheDocument();
    expect(panel.getByRole("link", { name: "Give a second look" })).toHaveAttribute("href", "/review");
  });

  it("says when a kind's address is wrong", async () => {
    serve();
    await openHelp("/help/nonsense");
    const panel = within(screen.getByRole("complementary", { name: "Help wanted" }));
    expect(panel.getByRole("heading", { name: "There's no such kind of help" })).toBeInTheDocument();
  });
});
