import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useViewAreaStore } from "../../map/store.js";
import { type ApiRoutes, routeApi } from "../../test/apiRoutes.js";
import {
  ADA,
  AVEBURY_AREA,
  FakeInvestigations,
  GUS,
  itemFinding,
  itemRecord,
  MARY,
} from "../../test/fixtures/investigations.js";
import { meFixture } from "../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import { useInvestigationArea } from "./area.js";
import { AREA_SOURCE } from "./useAreaOnMap.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();
let api: ApiRoutes;
let fake: FakeInvestigations;
let signedIn: typeof ADA | null;

const ADA_ME = meFixture();
const MARY_ME = meFixture({ id: 7, handle: MARY.handle, display_name: MARY.display_name });

function signIn(person: typeof ADA | null): void {
  signedIn = person;
  const me = person === ADA ? ADA_ME : person === MARY ? MARY_ME : null;
  api.on("GET /auth/me", () =>
    me ? json(me) : json({ error: { code: "unauthorised", message: "Sign in first." } }, 401),
  );
}

beforeEach(() => {
  useInvestigationArea.setState({ shape: null });
  signedIn = null;
  fake = new FakeInvestigations({ me: () => signedIn, people: [ADA, MARY, GUS] });
  api = routeApi(harness.fetchMock());
  const viaApi = harness.fetchMock().getMockImplementation();
  harness.fetchMock().mockImplementation(async (input: unknown, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const path = url.pathname.replace(/^\/api\/v1/, "");
    if (path.startsWith("/investigations")) {
      api.calls.push({
        method: init?.method ?? "GET",
        path,
        url,
        body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
        headers: new Headers(init?.headers),
      });
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
      const answer = fake.handle(init?.method ?? "GET", path, url.searchParams, body);
      if (answer) return answer.status === 204 ? new Response(null, { status: 204 }) : json(answer.body, answer.status);
    }
    return viaApi?.(input, init);
  });
  signIn(null);
});

function Address() {
  const { pathname, search } = useLocation();
  return <output data-testid="address">{`${pathname}${search}`}</output>;
}

async function panel(name: string | RegExp): Promise<HTMLElement> {
  return screen.findByRole("complementary", { name });
}

describe("the list", () => {
  it("shows the public ones signed out, and asks for sign-in for one's own", async () => {
    fake.seed({ title: "Barrows of Overton Down", owner: GUS, visibility: "public", summary: "Walking the down." });
    fake.seed({ title: "Secret notebook", owner: GUS });
    const user = userEvent.setup();
    renderShell("/investigations");
    const list = await panel("Investigations");
    expect(await within(list).findByRole("link", { name: /Barrows of Overton Down/ })).toBeInTheDocument();
    expect(within(list).getByText("Walking the down.")).toBeInTheDocument();
    expect(within(list).queryByText("Secret notebook")).toBeNull();
    expect(within(list).getByRole("tab", { name: "Public" })).toHaveAttribute("aria-selected", "true");

    await user.click(within(list).getByRole("tab", { name: "Yours" }));
    expect(within(list).getByText("Sign in to see your investigations")).toBeInTheDocument();
    // Nothing that needs an account is asked for.
    expect(api.calls.some((call) => call.url.searchParams.get("scope") === "mine")).toBe(false);
  });

  it("narrows the public list to those whose area is in view", async () => {
    fake.seed({ title: "Near", owner: GUS, visibility: "public", area: AVEBURY_AREA });
    fake.seed({ title: "Far away", owner: GUS, visibility: "public" });
    const user = userEvent.setup();
    renderShell("/investigations?list=public");
    await mapReady();
    act(() => useViewAreaStore.getState().setArea([-1.9, 51.4, -1.8, 51.45], 14));
    const list = await panel("Investigations");
    await within(list).findByRole("link", { name: /Far away/ });
    await user.click(within(list).getByRole("switch", { name: "Only those whose area is in view" }));
    await waitFor(() => expect(within(list).queryByRole("link", { name: /Far away/ })).toBeNull());
    expect(within(list).getByRole("link", { name: /Near/ })).toBeInTheDocument();
    const asked = api.calls.filter((call) => call.url.searchParams.has("bbox"));
    expect(asked.at(-1)?.url.searchParams.get("bbox")).toBe("-1.900,51.400,-1.800,51.450");
  });

  it("starts one with a title and nothing else, and opens it", async () => {
    signIn(ADA);
    const user = userEvent.setup();
    renderShell("/investigations", <Address />);
    const list = await panel("Investigations");
    await within(list).findByText("You haven't started one yet");
    await user.click(within(list).getByRole("button", { name: "Start" }));
    expect(within(list).getByRole("alert")).toHaveTextContent("Give it a title");
    await user.type(within(list).getByLabelText("Start an investigation"), "Hollow ways");
    await user.click(within(list).getByRole("button", { name: "Start" }));
    await panel("Hollow ways");
    expect(screen.getByTestId("address")).toHaveTextContent("/i/inv1");
    expect(api.calls.find((call) => call.method === "POST")?.body).toEqual({ title: "Hollow ways" });
  });

  it("lets someone invited accept from the list", async () => {
    signIn(MARY);
    const id = fake.seed({ title: "Enclosures of the Kennet", owner: GUS, visibility: "unlisted" });
    fake.invite(id, MARY, "editor");
    const user = userEvent.setup();
    renderShell("/investigations?list=invited", <Address />);
    const list = await panel("Investigations");
    await within(list).findByRole("link", { name: /Enclosures of the Kennet/ });
    await user.click(within(list).getByRole("button", { name: "Accept" }));
    await panel("Enclosures of the Kennet");
    expect(screen.getByTestId("address")).toHaveTextContent(`/i/${id}`);
    expect(fake.store.get(id)?.members.find((member) => member.user.handle === MARY.handle)?.accepted).toBe(true);
  });
});

describe("a notebook", () => {
  it("renders its notes as Markdown and never as HTML, and draws its area on the map", async () => {
    const id = fake.seed({
      title: "Hollow ways",
      owner: GUS,
      visibility: "public",
      area: AVEBURY_AREA,
      notes:
        "# Plan\n\nWalk the **east** side. <img src=x onerror=alert(1)> [HER](https://example.org/her) [bad](javascript:alert(1))",
    });
    renderShell(`/i/${id}`);
    const map = await mapReady();
    const page = await panel("Hollow ways");
    expect(within(page).getByRole("heading", { name: "Plan" })).toBeInTheDocument();
    expect(within(page).getByText("east").tagName).toBe("STRONG");
    expect(page.querySelector("img")).toBeNull();
    expect(within(page).getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    expect(within(page).getByRole("link", { name: /HER/ })).toHaveAttribute("href", "https://example.org/her");
    expect(within(page).queryByRole("link", { name: /bad/ })).toBeNull();
    await waitFor(() => {
      const data = map.sourceData(AREA_SOURCE) as { features: unknown[] } | undefined;
      expect(data?.features).toHaveLength(1);
    });
    // A reader is offered nothing to change.
    expect(within(page).queryByRole("button", { name: /Edit the title/ })).toBeNull();
    expect(within(page).queryByRole("button", { name: "Add a note" })).toBeNull();
  });

  it("draws each kind of item for what it is, and one it may not show as a line saying why", async () => {
    signIn(ADA);
    const id = fake.seed({ title: "Everything", owner: ADA }, [
      { kind: "finding", finding: itemFinding().public_id, note: "Seen from the **ridge**." },
      { kind: "record", record_id: itemRecord().id },
      { kind: "view", view: { centre: [-1.85, 51.43], zoom: 16, layer: "composite" }, title: "From the south" },
      {
        kind: "reference",
        title: "Wiltshire barrows",
        reference: { url: "https://example.org/b", citation: "Grinsell 1957" },
      },
      { kind: "note", note: "Plain words" },
    ]);
    fake.store.get(id)?.items.push({
      id: 999,
      kind: "record",
      position: 5,
      title: null,
      note: null,
      unavailable: "gone",
      added_by: ADA,
      created_at: "2026-11-10T10:00:00Z",
    });
    renderShell(`/i/${id}`);
    const page = await panel("Everything");
    const items = await within(page).findAllByRole("listitem");
    const cards = items.filter((item) => item.classList.contains("fc-inv-item"));
    expect(cards).toHaveLength(6);
    expect(within(cards[0] as HTMLElement).getByRole("link", { name: /Round barrow on Overton Hill/ })).toHaveAttribute(
      "href",
      `/f/${itemFinding().public_id}`,
    );
    expect(within(cards[0] as HTMLElement).getByText("ridge").tagName).toBe("STRONG");
    expect(within(cards[1] as HTMLElement).getByRole("link", { name: /West Kennet Avenue/ })).toHaveAttribute(
      "href",
      "/r/101",
    );
    expect(within(cards[2] as HTMLElement).getByRole("button", { name: "Show this view" })).toBeInTheDocument();
    expect(within(cards[3] as HTMLElement).getByText("Grinsell 1957")).toBeInTheDocument();
    expect(within(cards[4] as HTMLElement).getByText("Plain words")).toBeInTheDocument();
    expect(
      within(cards[5] as HTMLElement).getByText("This record has left the index since it was added."),
    ).toBeInTheDocument();
  });

  it("moves an item at once, saves it, and puts it back with a toast when the server refuses", async () => {
    signIn(ADA);
    const id = fake.seed({ title: "Order", owner: ADA }, [
      { kind: "note", note: "Alpha" },
      { kind: "note", note: "Bravo" },
    ]);
    const user = userEvent.setup();
    renderShell(`/i/${id}`);
    const page = await panel("Order");
    await within(page).findByText("Alpha");
    await user.click(within(page).getByRole("button", { name: "Move “Bravo” up" }));
    const texts = () => [...page.querySelectorAll(".fc-inv-item .fc-inv-item__note")].map((note) => note.textContent);
    expect(texts()).toEqual(["Bravo", "Alpha"]);
    await waitFor(() => expect(fake.store.get(id)?.items.map((item) => item.note)).toEqual(["Bravo", "Alpha"]));
    const move = api.calls.find((call) => call.path.endsWith("/move"));
    expect(move?.body).toEqual({ after: null });

    // By the keyboard, on the handle, which keeps focus.
    const handle = within(page).getByRole("button", { name: /^Move “Bravo”, place 1 of 2/ });
    handle.focus();
    await user.keyboard("{ArrowDown}");
    expect(texts()).toEqual(["Alpha", "Bravo"]);
    await waitFor(() =>
      expect(within(page).getByRole("button", { name: /^Move “Bravo”, place 2 of 2/ })).toHaveFocus(),
    );

    fake.failNext("POST", /\/move$/);
    await user.click(within(page).getByRole("button", { name: "Move “Bravo” up" }));
    expect(await screen.findByText(/The new order couldn't be saved/)).toBeInTheDocument();
    await waitFor(() => expect(texts()).toEqual(["Alpha", "Bravo"]));
  });

  it("adds a note at once, and takes one out", async () => {
    signIn(ADA);
    const id = fake.seed({ title: "Notes", owner: ADA });
    const user = userEvent.setup();
    renderShell(`/i/${id}`);
    const page = await panel("Notes");
    await within(page).findAllByText("Nothing in it yet");
    await user.click(within(page).getByRole("button", { name: "Add a note" }));
    const dialog = screen.getByRole("dialog", { name: "Add a note" });
    await user.type(within(dialog).getByLabelText("Note"), "Look at the hedge line");
    await user.click(within(dialog).getByRole("button", { name: "Add the note" }));
    expect(await within(page).findByText("Look at the hedge line")).toBeInTheDocument();
    await waitFor(() => expect(fake.store.get(id)?.items).toHaveLength(1));
    await user.click(within(page).getByRole("button", { name: "Take “Look at the hedge line” out" }));
    await waitFor(() => expect(within(page).queryByText("Look at the hedge line")).toBeNull());
    await waitFor(() => expect(fake.store.get(id)?.items).toHaveLength(0));
  });

  it("explains that inviting needs it public or unlisted, and offers nothing the server would refuse", async () => {
    signIn(ADA);
    const id = fake.seed({ title: "Mine alone", owner: ADA });
    const user = userEvent.setup();
    renderShell(`/i/${id}`);
    const page = await panel("Mine alone");
    expect(await within(page).findByText(/A private investigation has one member, you/)).toBeInTheDocument();
    expect(within(page).queryByLabelText("Invite someone by their handle")).toBeNull();
    expect(within(page).queryByRole("button", { name: "Make it private" })).toBeNull();

    await user.click(within(page).getByRole("button", { name: "Publish it" }));
    const dialog = screen.getByRole("dialog", { name: "Publish this investigation?" });
    expect(dialog).toHaveTextContent("lists it for everyone");
    await user.click(within(dialog).getByRole("button", { name: "Publish it" }));
    await waitFor(() => expect(fake.store.get(id)?.visibility).toBe("public"));

    await user.type(await within(page).findByLabelText("Invite someone by their handle"), "@KeenLynchet7");
    await user.click(within(page).getByRole("button", { name: "Invite" }));
    expect(await within(page).findByText(/invited, hasn't accepted yet/)).toBeInTheDocument();
    // An invitation waiting means it can't go back to private.
    expect(within(page).queryByRole("button", { name: "Make it private" })).toBeNull();

    await user.type(within(page).getByLabelText("Invite someone by their handle"), "Nobody99");
    await user.click(within(page).getByRole("button", { name: "Invite" }));
    expect(await within(page).findByText("Nobody has that handle. Check it on their profile.")).toBeInTheDocument();
  });

  it("asks before deleting, and before a member leaves", async () => {
    signIn(MARY);
    const id = fake.seed({ title: "Shared", owner: GUS, visibility: "public" });
    fake.invite(id, MARY, "viewer", true);
    const user = userEvent.setup();
    renderShell(`/i/${id}`, <Address />);
    const page = await panel("Shared");
    expect(within(page).queryByRole("button", { name: "Delete this investigation" })).toBeNull();
    await user.click(await within(page).findByRole("button", { name: "Leave this investigation" }));
    const dialog = screen.getByRole("dialog", { name: "Leave this investigation?" });
    expect(fake.store.get(id)?.members).toHaveLength(2);
    await user.click(within(dialog).getByRole("button", { name: "Leave" }));
    await waitFor(() => expect(fake.store.get(id)?.members).toHaveLength(1));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent("/investigations"));
  });

  it("says when there's no such investigation", async () => {
    renderShell("/i/nothing-here");
    const page = await panel("Investigation");
    expect(await within(page).findByText("There's no investigation at this address")).toBeInTheDocument();
  });
});

describe("adding from elsewhere", () => {
  it("offers the investigations this person may add to, and a new one", async () => {
    signIn(ADA);
    const own = fake.seed({ title: "Mine", owner: ADA });
    const edited = fake.seed({ title: "Gus's, as an editor", owner: GUS, visibility: "public" });
    fake.invite(edited, ADA, "editor", true);
    const read = fake.seed({ title: "Gus's, as a reader", owner: GUS, visibility: "public" });
    fake.invite(read, ADA, "viewer", true);
    api.on("GET /records/101", () =>
      json({
        ...itemRecord(),
        external_id: "1",
        summary: null,
        monument_types: [],
        periods: [],
        geometry: null,
        source_updated_at: null,
        ingested_at: "2026-11-10T00:00:00Z",
      }),
    );
    api.on("GET /records/101/findings", () => json({ items: [], next_cursor: null }));
    const user = userEvent.setup();
    renderShell("/r/101");
    const page = await panel("West Kennet Avenue");
    await user.click(await within(page).findByRole("button", { name: "Add to an investigation" }));
    const dialog = await screen.findByRole("dialog", { name: "Add to an investigation" });
    expect(await within(dialog).findByRole("radio", { name: /Gus's, as an editor/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /^Mine/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole("radio", { name: /as a reader/ })).toBeNull();

    await user.click(within(dialog).getByRole("radio", { name: "A new investigation" }));
    await user.type(within(dialog).getByLabelText("Its title"), "Avenues");
    await user.click(within(dialog).getByRole("button", { name: "Start it and add" }));
    expect(await screen.findByText("Added to “Avenues”.")).toBeInTheDocument();
    const created = [...fake.store.values()].find((stored) => stored.title === "Avenues");
    expect(created?.items.map((item) => item.kind)).toEqual(["record"]);
    expect(fake.store.get(own)?.items).toHaveLength(0);
  });
});
