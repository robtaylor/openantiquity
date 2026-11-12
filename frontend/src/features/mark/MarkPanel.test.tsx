import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useMapStore } from "../../map/store.js";
import { apiError, routeApi } from "../../test/apiRoutes.js";
import { createdFinding } from "../../test/fixtures/findings.js";
import { meFixture } from "../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import { useAccountUi } from "../account/requireAccount.js";
import {
  DRAFTS_STORAGE_KEY,
  listDrafts,
  noteSignInStarted,
  resetDraftsForTests,
  updateDrafts,
} from "../drafts/store.js";
import type { FindingCreate } from "../findings/types.js";
import { findingDrafts } from "./findingDrafts.js";
import { NUDGE_FAST_PX, NUDGE_PX } from "./MarkLayer.js";
import { useMarkStore } from "./markStore.js";
import { usePendingFindings } from "./pending.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

function Address() {
  const location = useLocation();
  return <output data-testid="address">{location.pathname}</output>;
}

function address(): string {
  return screen.getByTestId("address").textContent ?? "";
}

beforeEach(() => {
  window.localStorage.clear();
  resetDraftsForTests();
  useAccountUi.setState(useAccountUi.getInitialState(), true);
  useMarkStore.getState().start();
  usePendingFindings.setState({ pending: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function panel() {
  return within(screen.getByRole("complementary", { name: "Mark a finding" }));
}

function point(): [number, number] {
  const at = useMarkStore.getState().point;
  if (!at) throw new Error("No mark has been placed");
  return at;
}

async function openMarking(signedIn = true) {
  const routes = routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (signedIn ? json(meFixture()) : signedOutResponse()),
  });
  renderShell("/mark", <Address />);
  const map = await mapReady();
  return { map, routes };
}

describe("placing the mark", () => {
  it("puts the map in placing mode, and a click places the mark and a later one moves it", async () => {
    const { map } = await openMarking();
    expect(map.getCanvas()).toHaveClass("fc-canvas--placing");
    expect(screen.getByTestId("reticle")).toBeInTheDocument();
    expect(panel().getByText("Click the map where you see it.")).toBeInTheDocument();

    act(() => map.click(300, 200));
    const first = point();
    expect(first[0]).toBeCloseTo(map.unproject([300, 200]).lng, 9);
    expect(screen.queryByTestId("reticle")).toBeNull();
    expect(screen.getByRole("button", { name: /^Your mark at SU/ })).toBeInTheDocument();
    expect(panel().getByText(/^SU \d{4} \d{4}$/)).toBeInTheDocument();

    act(() => map.click(320, 260));
    expect(point()).not.toEqual(first);
  });

  it("places the mark under the cross with the primary action, so a keyboard can do it", async () => {
    const user = userEvent.setup();
    await openMarking();
    await user.click(screen.getByRole("button", { name: "Place it here" }));
    expect(useMarkStore.getState().point).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Place it here" })).toBeNull();
    // The button has gone, so focus goes on to the question that comes next, not to the foot of the page.
    expect(panel().getByRole("heading", { name: "What does it look like?" })).toHaveFocus();
  });

  it("offers the same in the panel, straight after its heading, and focus goes on from there too", async () => {
    const user = userEvent.setup();
    await openMarking();
    await user.click(panel().getByRole("button", { name: "Place it under the cross" }));
    expect(useMarkStore.getState().point).not.toBeNull();
    expect(panel().getByRole("heading", { name: "What does it look like?" })).toHaveFocus();
  });

  it("leaves focus where it is when the mark is placed on the map", async () => {
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    expect(panel().getByRole("heading", { name: "What does it look like?" })).not.toHaveFocus();
  });

  it("nudges the mark with the arrow keys, further with Shift", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    const handle = screen.getByRole("button", { name: /^Your mark/ });
    handle.focus();
    await user.keyboard("{ArrowRight}");
    expect(map.project(point()).x).toBeCloseTo(400 + NUDGE_PX, 6);
    await user.keyboard("{Shift>}{ArrowUp}{/Shift}");
    expect(map.project(point()).y).toBeCloseTo(300 - NUDGE_FAST_PX, 6);
    expect(handle).toHaveFocus();
  });

  it("drags the mark with a pointer, without moving the map", async () => {
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    const handle = screen.getByRole("button", { name: /^Your mark/ });
    fireEvent.pointerDown(handle, { pointerId: 1, button: 0, pointerType: "touch", clientX: 400, clientY: 300 });
    fireEvent.pointerMove(handle, { pointerId: 1, pointerType: "touch", clientX: 450, clientY: 330 });
    fireEvent.pointerUp(handle, { pointerId: 1, pointerType: "touch", clientX: 450, clientY: 330 });
    // The fake map's container sits at the top left of the page, so client and map pixels agree.
    expect(map.project(point()).x).toBeCloseTo(450, 6);
    expect(map.project(point()).y).toBeCloseTo(330, 6);
    // A move after the pointer is lifted does nothing.
    fireEvent.pointerMove(handle, { pointerId: 1, pointerType: "touch", clientX: 10, clientY: 10 });
    expect(map.project(point()).x).toBeCloseTo(450, 6);
  });

  it("leaves with Escape, from the map as from the panel", async () => {
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    fireEvent.keyDown(screen.getByRole("button", { name: /^Your mark/ }), { key: "Escape" });
    await waitFor(() => expect(address()).toBe("/"));
    expect(screen.queryByRole("complementary", { name: "Mark a finding" })).toBeNull();
    expect(map.getCanvas()).not.toHaveClass("fc-canvas--placing");
  });
});

describe("the form", () => {
  it("asks only for the class, explains a protected class's level, and carries the finds notice", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("button", { name: "Save finding" }));
    expect(panel().getByRole("alert")).toHaveTextContent("Choose what it looks like.");

    await user.click(panel().getByRole("radio", { name: "Round barrow or mound" }));
    expect(panel().queryByText("Choose what it looks like.")).toBeNull();
    expect(panel().getByText(/only signed-in members will see exactly where it is/)).toBeInTheDocument();
    await user.click(panel().getByRole("radio", { name: "Enclosure" }));
    expect(panel().queryByText(/only signed-in members/)).toBeNull();

    expect(panel().getByText(/This map is for earthworks, not objects/)).toBeInTheDocument();
    expect(panel().getByLabelText("Period")).toHaveValue("unknown");
    expect(panel().getByLabelText("Title")).toHaveAttribute(
      "placeholder",
      expect.stringMatching(/^Enclosure in SU \d{2} \d{2}$/),
    );
  });

  it("draws an outline: corners by tapping, undo, and closing on the first corner", async () => {
    const user = userEvent.setup();
    const { map } = await openMarking();
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("button", { name: "Draw an outline" }));
    expect(screen.getByTestId("reticle")).toBeInTheDocument();
    act(() => map.click(380, 280));
    act(() => map.click(420, 280));
    act(() => map.click(440, 330));
    act(() => map.click(500, 500));
    expect(useMarkStore.getState().point).toEqual(point());
    expect(useMarkStore.getState().outline?.points).toHaveLength(4);
    await user.click(panel().getByRole("button", { name: "Undo corner" }));
    expect(useMarkStore.getState().outline?.points).toHaveLength(3);
    // A tap on the first corner closes the shape.
    act(() => map.click(381, 281));
    expect(useMarkStore.getState().outline?.shape).toBe("polygon");
    expect(panel().getByText("A closed shape with 3 corners.")).toBeInTheDocument();
    // Taps move the mark again once the shape is done.
    act(() => map.click(410, 300));
    expect(map.project(point()).x).toBeCloseTo(410, 6);
  });
});

describe("saving, signed in", () => {
  it("shows the mark at once, sends what the finder was looking at, and opens the finding's page", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking();
    let answer: (response: Response) => void = () => {};
    routes.on(
      "POST /findings",
      (call) =>
        new Promise<Response>((resolve) => {
          answer = resolve;
          void call;
        }),
    );
    act(() => useMapStore.getState().setSun({ azimuth: 120, altitude: 15 }));
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("radio", { name: "Enclosure" }));
    await user.type(panel().getByLabelText("Note (optional)"), "Faint ring by the barn.");
    await user.click(panel().getByRole("button", { name: "Save finding" }));

    // Optimistic: on the map before the server has answered.
    expect(await screen.findByRole("img", { name: /^Enclosure in SU \d{2} \d{2}, saving$/ })).toBeInTheDocument();
    const [call] = routes.callsTo("POST /findings");
    const body = call?.body as FindingCreate;
    expect(body).toMatchObject({
      location: { type: "Point", coordinates: point() },
      feature_class: "enclosure",
      period: "unknown",
      title: expect.stringMatching(/^Enclosure in SU \d{2} \d{2}$/),
      description: "Faint ring by the barn.",
      view_state: { layer: "composite", sun_azimuth: 120, sun_altitude: 15, zoom: 14, bearing: 0, pitch: 0 },
    });

    expect(body.client_ref).toEqual(expect.any(String));

    act(() => answer(json(createdFinding(body, "abc123"), 201)));
    await waitFor(() => expect(address()).toBe("/f/abc123"));
    await waitFor(() => expect(usePendingFindings.getState().pending).toEqual([]));
    expect(routes.callsTo("POST /findings")).toHaveLength(1);
  });

  it("takes the mark back when the server refuses the place, says why and what to do, and keeps the form", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking();
    routes.on("POST /findings", () => apiError(422, "outside_british_isles", "That position is outside them."));
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("radio", { name: "Moat" }));
    await user.type(panel().getByLabelText("Title"), "Square moat");
    await user.click(panel().getByRole("button", { name: "Save finding" }));

    const toast = await screen.findByText(/Your finding couldn't be saved\. OpenAntiquity covers the land/);
    expect(usePendingFindings.getState().pending).toEqual([]);
    expect(screen.queryByRole("img", { name: /saving$/ })).toBeNull();
    expect(address()).toBe("/mark");
    expect(panel().getByRole("radio", { name: "Moat" })).toHaveAttribute("aria-checked", "true");
    expect(panel().getByLabelText("Title")).toHaveValue("Square moat");
    expect(panel().getByRole("alert")).toHaveTextContent(/Move the mark onto it/);
    // Sending the same place again would be refused the same way, so the toast doesn't offer it.
    const toastBox = toast.closest(".fc-toast") as HTMLElement;
    expect(within(toastBox).queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("says beside the title when the server refuses one that says where a protected finding is", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking();
    routes.on("POST /findings", () =>
      json(
        {
          error: {
            code: "position_in_text",
            message: "A protected or restricted finding's title and description can't say where it is.",
            details: [{ field: "body.title", message: "The title gives a position finer than the 1 km square." }],
          },
        },
        422,
      ),
    );
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("radio", { name: "Round barrow or mound" }));
    await user.type(panel().getByLabelText("Title"), "Barrow at SU 1025 6996");
    await user.click(panel().getByRole("button", { name: "Save finding" }));

    const title = panel().getByLabelText("Title");
    await waitFor(() => expect(title).toHaveAttribute("aria-invalid", "true"));
    await waitFor(() => expect(title).toHaveFocus());
    expect(
      panel().getByText(/Take the grid reference, coordinates or three-word address out of the title\./),
    ).toBeInTheDocument();
    expect(panel().getByLabelText("Note (optional)")).not.toHaveAttribute("aria-invalid");
    const toast = await screen.findByText(/Your finding couldn't be saved\./);
    expect(within(toast.closest(".fc-toast") as HTMLElement).queryByRole("button", { name: "Try again" })).toBeNull();
    await user.type(title, "!");
    expect(title).not.toHaveAttribute("aria-invalid");
  });

  it("says beside the note when a draft saved after sign-in was refused for a position in it", async () => {
    const draft = findingDrafts.put({
      point: [-1.8542, 51.4286],
      feature_class: "round_barrow",
      period: "unknown",
      title: "Round barrow or mound in SU 10 69",
      description: "Clearest at SU 1025 6996",
      outline: null,
      view_state: {},
    });
    updateDrafts((drafts) =>
      drafts.map((each) => ({
        ...each,
        state: "failed",
        failure: { code: "position_in_text", message: "It says where it is.", fields: ["body.description"] },
      })),
    );
    // Made before a provider's sign-in from this tab, which sends the person back here.
    noteSignInStarted("provider");
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    renderShell(`/mark/${draft.id}`);
    await mapReady();
    const note = await panel().findByLabelText("Note (optional)");
    await waitFor(() => expect(note).toHaveAttribute("aria-invalid", "true"));
    expect(panel().getByText(/out of the note\./)).toBeInTheDocument();
    expect(panel().getByLabelText("Title")).not.toHaveAttribute("aria-invalid");
  });

  it("offers to try again after a failure that may pass, and sends the same finding", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking();
    routes.on("POST /findings", () => apiError(503, "unavailable", "The server is busy."));
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("radio", { name: "Moat" }));
    await user.click(panel().getByRole("button", { name: "Save finding" }));
    const toast = await screen.findByText(/Your finding couldn't be saved\. The server is busy\./);

    routes.on("POST /findings", (call) => json(createdFinding(call.body as FindingCreate, "moat1"), 201));
    const toastBox = toast.closest(".fc-toast") as HTMLElement;
    await user.click(within(toastBox).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(address()).toBe("/f/moat1"));
    const [first, second] = routes.callsTo("POST /findings").map((call) => (call.body as FindingCreate).client_ref);
    expect(routes.callsTo("POST /findings")).toHaveLength(2);
    // Tried again, it is the same finding to the server, so a save that went through unheard isn't made twice.
    expect(second).toBe(first);
  });
});

describe("saving, signed out", () => {
  it("sends a draft taken over at sign-in when Save is pressed on its own form", async () => {
    const user = userEvent.setup();
    const draft = findingDrafts.put({
      point: [-1.8542, 51.4286],
      feature_class: "round_barrow",
      period: "unknown",
      title: "Round barrow or mound in SU 10 69",
      description: "",
      outline: null,
      view_state: {},
    });
    // Made before a provider's sign-in from this tab, which sends the person back here.
    noteSignInStarted("provider");
    const routes = routeApi(harness.fetchMock(), {
      "GET /auth/me": () => json(meFixture()),
      "POST /findings": (call) => json(createdFinding(call.body as FindingCreate, "abc123"), 201),
    });
    renderShell(`/mark/${draft.id}`, <Address />);
    await mapReady();

    // Taken over and held: nothing is sent until the person says so (Decision 0024).
    const save = await panel().findByRole("button", { name: "Save finding" });
    await waitFor(() => expect(listDrafts()[0]?.held).toBe(true));
    expect(routes.callsTo("POST /findings")).toHaveLength(0);

    // Pressing Save on the draft's own form is the person saying so.
    await user.click(save);
    await waitFor(() => expect(routes.callsTo("POST /findings")).toHaveLength(1));
    await waitFor(() => expect(address()).toBe("/f/abc123"));
    expect(listDrafts()).toEqual([]);
  });

  it("keeps it as a draft at its own address and opens the sign-in sheet, sending nothing", async () => {
    const user = userEvent.setup();
    const { map, routes } = await openMarking(false);
    act(() => map.click(400, 300));
    await user.click(panel().getByRole("radio", { name: "Hillfort" }));
    await user.click(panel().getByRole("button", { name: "Save finding" }));

    expect(await screen.findByRole("dialog", { name: "Sign in" })).toBeInTheDocument();
    const [draft] = listDrafts();
    expect(draft).toMatchObject({ kind: "finding", data: { feature_class: "hillfort", point: point() } });
    expect(address()).toBe(`/mark/${draft?.id}`);
    expect(window.localStorage.getItem(DRAFTS_STORAGE_KEY)).toContain("hillfort");
    expect(routes.callsTo("POST /findings")).toHaveLength(0);

    // Closing the sheet keeps the draft, marked as not saved yet.
    await user.click(within(screen.getByRole("dialog", { name: "Sign in" })).getByRole("button", { name: "Close" }));
    expect(panel().getByText("Not saved yet", { selector: ".fc-draft-badge" })).toBeInTheDocument();
    expect(await screen.findByText(/Kept in this browser as a draft until you sign in/)).toBeInTheDocument();
  });
});
