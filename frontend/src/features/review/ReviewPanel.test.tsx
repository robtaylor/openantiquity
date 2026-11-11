import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FindingsMapData } from "../../map/findingsData.js";
import { useHiddenFindings } from "../../map/hiddenFindings.js";
import { useMapStore } from "../../map/store.js";
import { overlaySourceId } from "../../map/style.js";
import { type ApiRoutes, routeApi } from "../../test/apiRoutes.js";
import { observationFixture, pageFixture, revealFixture } from "../../test/fixtures/findingPage.js";
import { meFixture } from "../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
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

function card(publicId: string, lon = CLAIMED.location.lon): ReviewCard {
  return {
    public_id: publicId,
    place: { lon, lat: CLAIMED.location.lat, grid_ref: "SU 1025 6996" },
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
  for (const each of cards) {
    routes.on(`PUT /findings/${each.public_id}/observation`, (call) => {
      const body = call.body as ObservationIn;
      const answer = observationFixture({ visible: body.visible, feature_class: body.feature_class ?? null });
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
    expect(document.title).toBe("Second look · Field Club");
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

  it("asks for nearby findings first, from where the map is", async () => {
    window.history.replaceState(null, "", "/review#m=13/52.1234/-0.5678/0/0&v=composite");
    const routes = serve([card("f-ring")]);
    await openQueue();
    await waitFor(() => expect(routes.callsTo("GET /review/next")).toHaveLength(1));
    const url = routes.callsTo("GET /review/next")[0]?.url;
    expect(url?.searchParams.get("lon")).toBe("-0.568");
    expect(url?.searchParams.get("lat")).toBe("52.123");
  });

  it("answers on the keys 1, 2 and 3, but not while a text field has focus", async () => {
    const user = userEvent.setup();
    serve([card("f-ring")]);
    const panel = await openQueue();
    await panel.findByRole("group", { name: "Can you see it?" });
    await user.keyboard("1");
    expect(panel.getByRole("button", { name: "I can see it" })).toHaveAttribute("aria-pressed", "true");
    expect(panel.getByText("What do you think it is?")).toBeInTheDocument();
    await user.keyboard("3");
    expect(panel.getByRole("button", { name: "I can't see it" })).toHaveAttribute("aria-pressed", "true");
    const note = panel.getByLabelText("Note (optional)");
    await user.click(note);
    await user.keyboard("2");
    expect(note).toHaveValue("2");
    expect(panel.getByRole("button", { name: "I can't see it" })).toHaveAttribute("aria-pressed", "true");
    expect(panel.getByRole("button", { name: "Not sure" })).toHaveAttribute("aria-pressed", "false");
  });

  it("sends the answer and its detail, reveals the finding and the reward, then goes on with one press", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring"), card("f-next", -1.86)]);
    const panel = await openQueue();
    await user.click(await panel.findByRole("button", { name: "I can see it" }));
    await user.click(panel.getByRole("radio", { name: "Round barrow or mound" }));
    await user.click(panel.getByRole("button", { name: "Send “I can see it”" }));

    expect(await panel.findByRole("heading", { name: CLAIMED.title })).toBeInTheDocument();
    expect(routes.callsTo("PUT /findings/f-ring/observation").map((call) => call.body)).toEqual([
      { visible: "yes", feature_class: "round_barrow" },
    ]);
    expect(panel.getByText(/2 other people can see it and 1 isn't sure\./)).toBeInTheDocument();
    expect(panel.getByText(/The finder marked it as: Round barrow or mound\. So did you\./)).toBeInTheDocument();
    expect(panel.getByText(/Your answer helped\. It has moved up to Seen by others\./)).toBeInTheDocument();
    expect(panel.getByRole("link", { name: "Open its page" })).toHaveAttribute("href", "/f/f-ring");
    // The answer keys are off once the answer is given.
    expect(panel.getByRole("button", { name: "Next finding" })).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(await panel.findByRole("button", { name: "I can see it" })).toHaveAttribute("aria-pressed", "false");
    expect(panel.queryByRole("heading", { name: CLAIMED.title })).toBeNull();
    expect(useReviewStore.getState().current?.public_id).toBe("f-next");
  });

  it("skips a card without sending anything", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring"), card("f-next", -1.86)]);
    const panel = await openQueue();
    await user.click(await panel.findByRole("button", { name: "Skip this one" }));
    await waitFor(() => expect(useReviewStore.getState().current?.public_id).toBe("f-next"));
    expect(routes.calls.filter((call) => call.method === "PUT")).toEqual([]);
  });

  it("says a failed send plainly and tries it again", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring")]);
    routes.on("PUT /findings/f-ring/observation", () =>
      json({ error: { code: "location_hidden", message: "You can't see this one exactly." } }, 403),
    );
    const panel = await openQueue();
    await user.click(await panel.findByRole("button", { name: "Not sure" }));
    await user.click(panel.getByRole("button", { name: "Send “Not sure”" }));
    expect(
      await screen.findByText(/Your answer couldn't be sent\. You can't see this one exactly\./),
    ).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Send “Not sure”" })).toBeEnabled();
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
  it("keeps the answer as a draft that can still change, reveals nothing, and offers sign-in", async () => {
    const user = userEvent.setup();
    const routes = serve([card("f-ring")], null);
    const panel = await openQueue();
    await user.click(await panel.findByRole("button", { name: "Not sure" }));
    expect(panel.getByText(/You're not signed in, so it's kept in this browser/)).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "Send “Not sure”" }));
    await waitFor(() => expect(useAccountUi.getState().sheet).toBe("signin"));
    act(() => useAccountUi.getState().close());

    expect(await panel.findByText("Not saved yet")).toBeInTheDocument();
    expect(panel.getByText(/Until then you can change it\. Once it's saved it's final/)).toBeInTheDocument();
    expect(routes.calls.filter((call) => call.method === "PUT")).toEqual([]);
    for (const words of CLAIM_WORDS) expect(pageText()).not.toContain(words);
    // The card is kept for a provider's round trip, with nothing of the claim in it.
    expect(sessionStorage.getItem(CARD_STORAGE_KEY)).toContain("f-ring");

    // Changing it replaces the draft rather than adding a second.
    await user.click(panel.getByRole("button", { name: "Change my answer" }));
    expect(panel.getByRole("button", { name: "Not sure" })).toHaveAttribute("aria-pressed", "true");
    await user.click(panel.getByRole("button", { name: "I can see it" }));
    await user.click(panel.getByRole("button", { name: "Send “I can see it”" }));
    await waitFor(() => expect(useAccountUi.getState().sheet).toBe("signin"));
    act(() => useAccountUi.getState().close());
    await panel.findByText("Not saved yet");
    const stored = JSON.parse(localStorage.getItem(DRAFTS_STORAGE_KEY) ?? "{}");
    expect(stored.drafts).toHaveLength(1);
    expect(stored.drafts[0]).toMatchObject({
      kind: "observation",
      data: { public_id: "f-ring", answer: { visible: "yes" } },
    });
  });

  it("shows what the answer revealed once the draft is saved", async () => {
    serve([card("f-ring")], null);
    const panel = await openQueue();
    await panel.findByRole("group", { name: "Can you see it?" });
    act(() => useSavedAnswers.getState().record(revealFixture(observationFixture(), CLAIMED, {})));
    expect(await panel.findByRole("heading", { name: CLAIMED.title })).toBeInTheDocument();
    expect(useSavedAnswers.getState().revealed).toEqual({});
  });
});
