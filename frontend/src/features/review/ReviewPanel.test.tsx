import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FindingsMapData } from "../../map/findingsData.js";
import { useHiddenFindings } from "../../map/hiddenFindings.js";
import { RECORD_LAYERS } from "../../map/overlayLayers.js";
import { useMapStore } from "../../map/store.js";
import { overlaySourceId } from "../../map/style.js";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { observationFixture, pageFixture, revealFixture } from "../../test/fixtures/findingPage.js";
import { meFixture } from "../../test/fixtures/me.js";
import {
  json,
  mapReady,
  renderShell,
  setUpShellTests,
  signedOutResponse,
  usePhoneLayout,
} from "../../test/shellHarness.js";
import type { Me } from "../account/api.js";
import { useAccountUi } from "../account/requireAccount.js";
import { DRAFTS_STORAGE_KEY, resetDraftsForTests } from "../drafts/store.js";
import { useSavedAnswers } from "../finding/secondLook/answerDrafts.js";
import type { ObservationIn } from "../finding/types.js";
import { CARD_STORAGE_KEY, useReviewStore } from "./reviewStore.js";
import type { ReviewCard } from "./types.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

const MEMBER = meFixture({ handle: "KeenLynchet7", display_name: "Mary Anning" });
/** The finding behind the first card, which nothing may name before the answer. */
const CLAIMED = pageFixture();
const CLAIM_WORDS = [CLAIMED.title, "Round barrow or mound", "round_barrow", "Bronze Age", "Ada Lovelace"];
/** The claim's words that the detail's own choices can't hold: it offers every class by name. */
const CLAIM_BEYOND_THE_CHOICES = CLAIM_WORDS.filter((words) => words !== "Round barrow or mound");

function card(publicId: string, lon = CLAIMED.location.lon): ReviewCard {
  return {
    public_id: publicId,
    place: { lon, lat: CLAIMED.location.lat, grid_ref: "SU 1025 6996" },
    shape_revision: 0,
    view_state: { layer: "slope", zoom: 16.5, bearing: 12, pitch: 0, sun_azimuth: 200, sun_altitude: 30 },
  };
}

beforeEach(() => {
  useAccountUi.setState({ sheet: null, waiting: [] });
  useSavedAnswers.getState().clear();
  useReviewStore.getState().reset();
  useHiddenFindings.setState({ reasons: [] });
  localStorage.clear();
  sessionStorage.clear();
  resetDraftsForTests();
});

/** The queue serves `cards`, and an answer reveals the finding behind the card it was sent to. */
function serve(cards: ReviewCard[], me: Me | null = MEMBER): ApiRoutes {
  const routes = routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : signedOutResponse()),
    "GET /review/next": () => json({ items: cards, next_cursor: null }),
  });
  // The answer goes alone and is held for its detail, which comes with the request for the reveal.
  for (const each of cards) {
    let given: ObservationIn["visible"] = "yes";
    routes.on(`PUT /findings/${each.public_id}/observation`, (call) => {
      given = (call.body as ObservationIn).visible;
      return json({ revealed: false, observation: observationFixture({ visible: given, revealed: false }) });
    });
    routes.on(`POST /findings/${each.public_id}/observation/reveal`, (call) => {
      const detail = call.body as Partial<ObservationIn>;
      const answer = observationFixture({ visible: given, feature_class: detail.feature_class ?? null });
      return json(
        revealFixture(answer, pageFixture({ public_id: each.public_id }), { moved_up: true, tier_after: "seen" }),
      );
    });
  }
  return routes;
}

async function openQueue() {
  renderShell("/review");
  await mapReady();
  return within(screen.getByRole("complementary", { name: "Second look" }));
}

function pageText(): string {
  return `${document.body.textContent ?? ""} ${document.title} ${window.location.href}`;
}

describe("a blind card", () => {
  it("shows the place in the finder's view and nothing of the finder's claim, anywhere", async () => {
    const routes = serve([card("f-ring")]);
    const panel = await openQueue();
    expect(await panel.findByRole("group", { name: "Can you see it?" })).toBeInTheDocument();
    expect(panel.getByText("SU 1025 6996")).toBeInTheDocument();

    // The map takes the finder's view at the place, and holds every finding's marker back.
    await waitFor(() => expect(useMapStore.getState().mainView).toBe("slope"));
    expect(useMapStore.getState().sun.azimuth).toBe(200);
    expect(useMapStore.getState().camera.zoom).toBe(16.5);
    expect(useHiddenFindings.getState().reasons).toEqual(["second-look"]);

    // Nothing of the claim is in the page, its title or the address, nor was anything asked that could carry it.
    for (const words of CLAIM_WORDS) expect(pageText()).not.toContain(words);
    expect(document.title).toBe("Second look · OpenAntiquity");
    expect(routes.calls.map((call) => call.path)).not.toContain("/findings/f-ring");
    expect(routes.calls.filter((call) => call.path === "/findings")).toEqual([]);
    expect(document.querySelector(".fc-highlight-ring")).toBeNull();
  });

  it("takes every finding's marker off the map while the queue is open, and puts them back after", async () => {
    const user = userEvent.setup();
    serve([card("f-ring")]);
    renderShell("/?panel=none");
    const map = await mapReady();
    const drawn = () => (map.sourceData(overlaySourceId("findings")) as FindingsMapData | undefined)?.features ?? [];
    await waitFor(() => expect(drawn().length).toBeGreaterThan(0));
    const rail = screen.getByRole("navigation", { name: "Modes" });
    await user.click(within(rail).getByRole("link", { name: "Second look" }));
    await screen.findByRole("group", { name: "Can you see it?" });
    await waitFor(() => expect(drawn()).toEqual([]));
    await user.click(within(rail).getByRole("link", { name: "Explore" }));
    await waitFor(() => expect(drawn().length).toBeGreaterThan(0));
  });

  it("holds the heritage records off the map while a card is up, and lets them back once it is answered", async () => {
    // A scheduled monument's square at the spot would answer the question the card asks.
    const user = userEvent.setup();
    serve([card("f-ring")]);
    renderShell("/?panel=none");
    const map = await mapReady();
    const recordLayers = [RECORD_LAYERS.squares, RECORD_LAYERS.busyCounts, RECORD_LAYERS.live];
    const shown = () => recordLayers.map((layer) => map.isVisible(layer));
    expect(shown()).toEqual([true, true, true]);
    const rail = screen.getByRole("navigation", { name: "Modes" });
    await user.click(within(rail).getByRole("link", { name: "Second look" }));
    const panel = within(screen.getByRole("complementary", { name: "Second look" }));
    await panel.findByRole("group", { name: "Can you see it?" });
    await waitFor(() => expect(shown()).toEqual([false, false, false]));
    // The person's own switch is left as it was.
    expect(useMapStore.getState().overlays.records?.visible).toBe(true);

    await user.click(panel.getByRole("button", { name: "I can see it" }));
    // Still held back between the steps: the answer is in, but the question the detail asks is still open.
    await panel.findByText(/Your answer is in/);
    expect(shown()).toEqual([false, false, false]);
    await user.click(panel.getByRole("button", { name: "See how it compares" }));
    expect(await panel.findByRole("heading", { name: CLAIMED.title })).toBeInTheDocument();
    await waitFor(() => expect(shown()).toEqual([true, true, true]));
  });

  it("lets the heritage records back when the queue closes", async () => {
    const user = userEvent.setup();
    serve([card("f-ring")]);
    renderShell("/review");
    const map = await mapReady();
    await screen.findByRole("group", { name: "Can you see it?" });
    await waitFor(() => expect(map.isVisible(RECORD_LAYERS.squares)).toBe(false));
    await user.click(screen.getByRole("button", { name: "Close panel" }));
    await waitFor(() => expect(map.isVisible(RECORD_LAYERS.squares)).toBe(true));
  });

  it("asks for nearby findings first, from where the map is", async () => {
    window.history.replaceState(null, "", "/review#m=13/52.1234/-0.5678/0/0&v=composite");
    const routes = serve([card("f-ring")]);
    await openQueue();
    await waitFor(() => expect(routes.callsTo("GET /review/next")).toHaveLength(1));
    const url = routes.callsTo("GET /review/next")[0]?.url;
    expect(url?.searchParams.get("lon")).toBe("-0.568");
    expect(url?.searchParams.get("lat")).toBe("52.123");
  });

  it("answers with one press on the keys 1, 2 and 3, but not while a text field has focus", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring")]);
    const panel = await openQueue();
    await panel.findByRole("group", { name: "Can you see it?" });
    await user.keyboard("1");
    await waitFor(() => expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(1));
    expect(routes.callsTo("PUT /findings/f-ring/observation")[0]?.body).toEqual({
      visible: "yes",
      detail_follows: true,
      shape_revision: 0,
    });
    expect(await panel.findByText(/Your answer is in/)).toHaveTextContent("You can see it.");
    // After a key, the button that shows the comparison has focus, so Enter would show it.
    await waitFor(() => expect(panel.getByRole("button", { name: "See how it compares" })).toHaveFocus());
    const note = panel.getByLabelText("Note (optional)");
    await user.click(note);
    await user.keyboard("2");
    expect(note).toHaveValue("2");
    await user.click(panel.getByText(/Anything to add\?/));
    await user.keyboard("3");
    expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(1);
  });

  it("sends the answer at once, then the detail with the reveal, shows the reward, then goes on with one press", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring"), card("f-next", -1.86)]);
    const panel = await openQueue();
    await user.click(await panel.findByRole("button", { name: "I can see it" }));
    expect(await panel.findByText(/Your answer is in/)).toHaveFocus();
    // Between the steps nothing of the claim has reached the page, and no finding was asked for.
    for (const words of CLAIM_BEYOND_THE_CHOICES) expect(pageText()).not.toContain(words);
    expect(routes.calls.map((call) => call.path)).not.toContain("/findings/f-ring");
    await user.click(panel.getByRole("radio", { name: "Round barrow or mound" }));
    await user.click(panel.getByRole("button", { name: "Add this and see how it compares" }));

    expect(await panel.findByRole("heading", { name: CLAIMED.title })).toBeInTheDocument();
    expect(routes.callsTo("PUT /findings/f-ring/observation").map((call) => call.body)).toEqual([
      { visible: "yes", detail_follows: true, shape_revision: 0 },
    ]);
    expect(routes.callsTo("POST /findings/f-ring/observation/reveal").map((call) => call.body)).toEqual([
      { feature_class: "round_barrow" },
    ]);
    expect(panel.getByText(/2 other people can see it and 1 isn't sure\./)).toBeInTheDocument();
    expect(panel.getByText(/The finder marked it as: Round barrow or mound\. So did you\./)).toBeInTheDocument();
    expect(panel.getByText(/Your answer helped\. It has moved up to Seen by others\./)).toBeInTheDocument();
    expect(panel.getByRole("link", { name: "Open its page" })).toHaveAttribute("href", "/f/f-ring");
    expect(panel.getByRole("button", { name: "Next finding" })).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(await panel.findByRole("button", { name: "I can see it" })).toHaveAttribute("aria-pressed", "false");
    expect(panel.queryByRole("heading", { name: CLAIMED.title })).toBeNull();
    expect(useReviewStore.getState().current?.public_id).toBe("f-next");
    // The button that was pressed has gone: the next card's question has focus, not the top of the page.
    expect(panel.getByText(/Can you see a feature there\?/)).toHaveFocus();
  });

  it("shows the reveal when another tab finished the answer first, and says the detail here wasn't kept", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring")]);
    const finished = observationFixture({ visible: "yes", feature_class: "enclosure" });
    routes.on("POST /findings/f-ring/observation/reveal", (call) =>
      Object.keys(call.body as object).length > 0
        ? apiError(409, "answer_final", "You've already answered.")
        : json(
            revealFixture(finished, pageFixture({ public_id: "f-ring" }), { moved_up: false, tier_after: "spotted" }),
          ),
    );
    const panel = await openQueue();
    await user.click(await panel.findByRole("button", { name: "I can see it" }));
    await user.click(await panel.findByRole("radio", { name: "Round barrow or mound" }));
    await user.click(panel.getByRole("button", { name: "Add this and see how it compares" }));

    expect(await panel.findByRole("heading", { name: CLAIMED.title })).toBeInTheDocument();
    expect(routes.callsTo("POST /findings/f-ring/observation/reveal").map((call) => call.body)).toEqual([
      { feature_class: "round_barrow" },
      {},
    ]);
    expect(screen.getByText(/already finished in another tab/)).toBeInTheDocument();
  });

  it("answers by key and shows the comparison with Enter, with nothing added", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring")]);
    const panel = await openQueue();
    await panel.findByRole("group", { name: "Can you see it?" });
    await user.keyboard("2");
    await waitFor(() => expect(panel.getByRole("button", { name: "See how it compares" })).toHaveFocus());
    await user.keyboard("{Enter}");
    expect(await panel.findByRole("heading", { name: CLAIMED.title })).toBeInTheDocument();
    expect(routes.callsTo("PUT /findings/f-ring/observation").map((call) => call.body)).toEqual([
      { visible: "unsure", detail_follows: true, shape_revision: 0 },
    ]);
    expect(routes.callsTo("POST /findings/f-ring/observation/reveal").map((call) => call.body)).toEqual([{}]);
  });

  it("offers the detail again to someone who left the queue between the steps", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring")]);
    const panel = await openQueue();
    await user.click(await panel.findByRole("button", { name: "Not sure" }));
    await panel.findByText(/Your answer is in/);
    const rail = screen.getByRole("navigation", { name: "Modes" });
    await user.click(within(rail).getByRole("link", { name: "Explore" }));
    await user.click(within(rail).getByRole("link", { name: "Second look" }));
    const again = within(await screen.findByRole("complementary", { name: "Second look" }));
    expect(await again.findByText(/Your answer is in/)).toHaveTextContent("You weren't sure.");
    expect(again.queryByRole("group", { name: "Can you see it?" })).toBeNull();
    await user.click(again.getByRole("button", { name: "See how it compares" }));
    expect(await again.findByRole("heading", { name: CLAIMED.title })).toBeInTheDocument();
    expect(routes.callsTo("PUT /findings/f-ring/observation")).toHaveLength(1);
  });

  it("comes back to a card whose answer waits for its detail only for the person who gave it", async () => {
    // As after a reload: the card and its held answer were kept, for the account that answered.
    serve([card("f-other", -1.86)]);
    act(() => {
      useReviewStore.getState().show(card("f-ring"));
      useReviewStore.getState().hold({ visible: "yes", by: "person:7" });
    });
    const panel = await openQueue();
    // Someone else is signed in now: the card goes, and the queue moves on to one of their own.
    await waitFor(() => expect(useReviewStore.getState().current?.public_id).toBe("f-other"));
    expect(await panel.findByRole("group", { name: "Can you see it?" })).toBeInTheDocument();
    expect(panel.queryByText(/Your answer is in/)).toBeNull();
  });

  it("comes back to its own held answer after a reload, with the detail offered", async () => {
    serve([card("f-other", -1.86)]);
    act(() => {
      useReviewStore.getState().show(card("f-ring"));
      useReviewStore.getState().hold({ visible: "no", by: "person:42" });
    });
    const panel = await openQueue();
    expect(await panel.findByText(/Your answer is in/)).toHaveTextContent("You can't see it.");
    expect(useReviewStore.getState().current?.public_id).toBe("f-ring");
  });

  it("skips a card without sending anything", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring"), card("f-next", -1.86)]);
    const panel = await openQueue();
    await user.click(await panel.findByRole("button", { name: "Skip this one" }));
    await waitFor(() => expect(useReviewStore.getState().current?.public_id).toBe("f-next"));
    expect(routes.calls.filter((call) => call.method === "PUT")).toEqual([]);
  });

  it("says a refused answer plainly and offers the answers again", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring")]);
    routes.on("PUT /findings/f-ring/observation", () =>
      json({ error: { code: "location_hidden", message: "You can't see this one exactly." } }, 403),
    );
    const panel = await openQueue();
    await user.click(await panel.findByRole("button", { name: "Not sure" }));
    expect(
      await screen.findByText(/Your answer couldn't be sent\. You can't see this one exactly\./),
    ).toBeInTheDocument();
    expect(await panel.findByRole("button", { name: "Not sure" })).toBeEnabled();
    expect(panel.queryByText(/Your answer is in/)).toBeNull();
  });

  it("brings a phone's sheet down to half-way while the person answers, so the place stays in sight", async () => {
    const user = userEvent.setup();
    usePhoneLayout();
    serve([card("f-ring")]);
    renderShell("/review");
    await mapReady();
    const sheet = await screen.findByRole("complementary", { name: "Second look" });
    await within(sheet).findByRole("group", { name: "Can you see it?" });
    const handle = within(sheet).getByRole("button", { name: /Press to resize/ });
    await user.click(handle);
    expect(sheet).toHaveAttribute("data-stop", "full");
    await user.click(within(sheet).getByRole("button", { name: "I can see it" }));
    await waitFor(() => expect(sheet).toHaveAttribute("data-stop", "half"));
  });
});

describe("the queue's other states", () => {
  it("says warmly when nothing is waiting, and offers other work", async () => {
    serve([]);
    const panel = await openQueue();
    expect(await panel.findByRole("heading", { name: "Nothing waiting just now" })).toBeInTheDocument();
    expect(panel.getByRole("link", { name: "Scan a square" })).toHaveAttribute("href", "/scan");
    expect(panel.getByRole("link", { name: "Help wanted" })).toHaveAttribute("href", "/help");
  });

  it("offers the skipped ones again once the rest are done", async () => {
    const user = userEvent.setup();
    serve([card("f-ring")]);
    const panel = await openQueue();
    await user.click(await panel.findByRole("button", { name: "Skip this one" }));
    await user.click(await panel.findByRole("button", { name: "Look at the one you skipped" }));
    expect(await panel.findByRole("button", { name: "Skip this one" })).toBeInTheDocument();
    expect(useReviewStore.getState().current?.public_id).toBe("f-ring");
  });

  it("says when the queue can't be fetched, and tries again", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring")]);
    routes.on("GET /review/next", () =>
      json({ error: { code: "boom", message: "The server is having a moment." } }, 500),
    );
    const panel = await openQueue();
    // A server error is tried once more, after a pause, before it is shown.
    expect(
      await panel.findByRole("heading", { name: "The next finding couldn't be fetched" }, { timeout: 4000 }),
    ).toBeInTheDocument();
    routes.on("GET /review/next", () => json({ items: [card("f-ring")], next_cursor: null }));
    await user.click(panel.getByRole("button", { name: "Try again" }));
    expect(await panel.findByRole("group", { name: "Can you see it?" })).toBeInTheDocument();
  });
});

describe("signed out", () => {
  it("keeps the answer and its detail as a draft that can still change, reveals nothing, and offers sign-in", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring")], null);
    const panel = await openQueue();
    await user.click(await panel.findByRole("button", { name: "Not sure" }));
    expect(await panel.findByText("Not saved yet")).toBeInTheDocument();
    expect(panel.getByText(/It's kept in this browser until you sign in\./)).toHaveTextContent("You weren't sure.");
    expect(useAccountUi.getState().sheet).toBeNull();
    expect(routes.calls.filter((call) => call.method === "PUT" || call.method === "POST")).toEqual([]);
    for (const words of CLAIM_BEYOND_THE_CHOICES) expect(pageText()).not.toContain(words);
    // The card is kept for a provider's round trip, with nothing of the claim in it.
    expect(sessionStorage.getItem(CARD_STORAGE_KEY)).toContain("f-ring");

    // Changing it replaces the draft rather than adding a second.
    await user.click(panel.getByRole("button", { name: "Change my answer" }));
    await user.click(await panel.findByRole("button", { name: "I can see it" }));
    await user.click(await panel.findByRole("radio", { name: "Round barrow or mound" }));
    await user.click(panel.getByRole("button", { name: "Sign in to see how it compares" }));
    await waitFor(() => expect(useAccountUi.getState().sheet).toBe("signin"));
    act(() => useAccountUi.getState().close());
    await panel.findByText("Not saved yet");
    const stored = JSON.parse(localStorage.getItem(DRAFTS_STORAGE_KEY) ?? "{}");
    expect(stored.drafts).toHaveLength(1);
    expect(stored.drafts[0]).toMatchObject({
      kind: "observation",
      data: { public_id: "f-ring", answer: { visible: "yes", feature_class: "round_barrow" }, reveal: true },
    });
    expect(routes.calls.filter((call) => call.method === "PUT" || call.method === "POST")).toEqual([]);
  });

  it("shows what the answer revealed once the draft is saved", async () => {
    serve([card("f-ring")], null);
    const panel = await openQueue();
    await panel.findByRole("group", { name: "Can you see it?" });
    act(() =>
      useSavedAnswers
        .getState()
        .record("f-ring", { kind: "revealed", reveal: revealFixture(observationFixture(), CLAIMED, {}) }),
    );
    expect(await panel.findByRole("heading", { name: CLAIMED.title })).toBeInTheDocument();
    expect(useSavedAnswers.getState().saved).toEqual({});
  });

  it("offers the detail once a draft saved without its reveal is in", async () => {
    serve([card("f-ring")]);
    const panel = await openQueue();
    await panel.findByRole("group", { name: "Can you see it?" });
    const held = observationFixture({ visible: "no", revealed: false });
    act(() => useSavedAnswers.getState().record("f-ring", { kind: "held", observation: held }));
    expect(await panel.findByText(/Your answer is in/)).toHaveTextContent("You can't see it.");
    for (const words of CLAIM_BEYOND_THE_CHOICES) expect(pageText()).not.toContain(words);
  });
});
