import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { useFakeEventSource } from "../../test/fakeEventSource.js";
import { meFixture } from "../../test/fixtures/me.js";
import {
  actionFixture,
  eligibleFixture,
  profileFixture,
  queuedPhotoFixture,
  reportFixture,
  targetFixture,
} from "../../test/fixtures/people.js";
import { json, mapReady, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import { useToastStore } from "../../ui/toastStore.js";
import type { Me } from "../account/api.js";
import { useAccountUi } from "../account/requireAccount.js";
import type { Report } from "./api.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

beforeEach(() => {
  useFakeEventSource();
  useAccountUi.setState({ sheet: null, waiting: [] });
});

const MODERATOR = meFixture({ handle: "ModMorag", display_name: "Morag Kerr", role: "moderator" });
const TRUSTED = meFixture({ handle: "TrustyTess", display_name: "Tess Ford", role: "trusted" });

const PRIVACY = reportFixture();
const URGENT = reportFixture({
  id: 2,
  reason: "defamation",
  created_at: "2026-11-11T08:00:00Z",
  due_at: "2026-11-13T08:00:00Z",
  note: null,
  target: targetFixture({ id: 502, ref: "502", body: "He made that barrow up to sell books." }),
});
const PERSON = reportFixture({
  id: 3,
  reason: "under_age",
  note: null,
  target: targetFixture({
    kind: "user",
    id: 77,
    ref: "KeenLynchet7",
    finding: null,
    title: "Mary Anning",
    body: null,
  }),
});

function serve(me: Me | null, reports: Report[] = [PRIVACY, URGENT, PERSON]): ApiRoutes {
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : apiError(401, "unauthorised")),
    "GET /mod/reports": (call) => {
      const reason = call.url.searchParams.get("reason");
      return json({
        items: reports.filter((report) => reason === null || report.reason === reason),
        next_cursor: null,
      });
    },
    "GET /mod/media": () => json({ items: [queuedPhotoFixture()], next_cursor: null }),
    "GET /mod/users/eligible": () => json({ items: [eligibleFixture()], next_cursor: null }),
    "GET /mod/actions": () => json({ items: [actionFixture()], next_cursor: null }),
  });
}

async function openMod(path = "/mod", title = "Moderation") {
  renderShell(path);
  await mapReady();
  return within(await screen.findByRole("complementary", { name: title }));
}

/** The cards of a list, not the lists inside them. */
const cardsOf = (list: HTMLElement) => [...list.querySelectorAll<HTMLElement>(":scope > li")];

const messages = () => useToastStore.getState().toasts.map((toast) => toast.message);

describe("who sees moderation", () => {
  it("asks a signed-out person to sign in, and tells a member it isn't for them", async () => {
    serve(null);
    const panel = await openMod();
    expect(await panel.findByText("Sign in to moderate")).toBeInTheDocument();
  });

  it("tells a member it is for moderators, and asks for nothing", async () => {
    const routes = serve(meFixture());
    const panel = await openMod();
    expect(await panel.findByText("This part is for moderators")).toBeInTheDocument();
    expect(routes.callsTo("GET /mod/reports")).toHaveLength(0);
  });

  it("gives a trusted member the photo queue alone", async () => {
    const routes = serve(TRUSTED);
    const panel = await openMod("/mod", "Photos to approve");
    expect(await panel.findByRole("list", { name: "Photos waiting for approval" })).toBeInTheDocument();
    expect(panel.queryByRole("tab")).toBeNull();
    expect(routes.callsTo("GET /mod/reports")).toHaveLength(0);
  });

  it("asks a moderator who hasn't finished joining to do that first", async () => {
    const routes = serve(meFixture({ role: "moderator", needs_welcome: true, age_band: null }));
    const panel = await openMod();
    expect(await panel.findByText("Finish joining first")).toBeInTheDocument();
    expect(routes.callsTo("GET /mod/reports")).toHaveLength(0);
  });
});

describe("the report queue", () => {
  it("puts reports with a legal deadline first and marks them, with enough of each target to decide", async () => {
    serve(MODERATOR);
    const panel = await openMod();
    const list = await panel.findByRole("list", { name: "Open reports" });
    const cards = within(list).getAllByRole("listitem");
    expect(cards.map((card) => card.querySelector(".fc-mod-card__reason")?.textContent)).toEqual([
      "Untrue about a person",
      "Reveals personal details",
      "Under 16",
    ]);
    expect(cards[0]).toHaveTextContent(/Legal deadline · (Due by|Overdue since) Fri 13 Nov/);
    expect(cards[1]).not.toHaveTextContent("Legal deadline");
    const privacy = within(cards[1] as HTMLElement);
    expect(privacy.getByLabelText("The reporter's note")).toHaveTextContent("It names the farm and the farmer.");
    expect(privacy.getByText("The farmer at Lower Barn says you can park in his yard.")).toBeInTheDocument();
    expect(privacy.getByText(/Posted by/)).toHaveTextContent("Posted by Mary Anning @KeenLynchet7 · Member");
    expect(privacy.getByRole("link", { name: "See it in place" })).toHaveAttribute("href", "/f/f-ring");
    // A person is banned, never hidden.
    const person = within(cards[2] as HTMLElement);
    expect(person.queryByRole("button", { name: /^Hide/ })).toBeNull();
    expect(person.getByRole("button", { name: "Ban KeenLynchet7" })).toBeInTheDocument();
  });

  it("upholds a report and hides its target in one go, with a note for the log", async () => {
    const user = userEvent.setup();
    const routes = serve(MODERATOR);
    routes.on("POST /mod/comments/501/hide", () =>
      json({ target_kind: "comment", target_id: "501", hidden: true, hidden_at: "2026-11-11T10:00:00Z" }),
    );
    routes.on("POST /mod/reports/1/resolve", () => json({ report: { ...PRIVACY, status: "upheld" }, resolved: 1 }));
    const panel = await openMod();
    const list = await panel.findByRole("list", { name: "Open reports" });
    const card = within(within(list).getAllByRole("listitem")[1] as HTMLElement);
    await user.click(card.getByRole("button", { name: "Uphold" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Uphold this report?" }));
    expect(dialog.getByRole("checkbox", { name: /Hide it as well/ })).toBeChecked();
    await user.type(dialog.getByLabelText("Note for the log"), "Names a private landowner.");
    await user.click(dialog.getByRole("button", { name: "Uphold and hide" }));
    // Gone from the queue at once.
    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(2));
    await waitFor(() => expect(routes.callsTo("POST /mod/reports/1/resolve")).toHaveLength(1));
    expect(routes.callsTo("POST /mod/comments/501/hide")[0]?.body).toEqual({ reason: "Names a private landowner." });
    expect(routes.callsTo("POST /mod/reports/1/resolve")[0]?.body).toEqual({
      outcome: "upheld",
      note: "Names a private landowner.",
    });
    expect(messages()).toContain("Upheld and hidden.");
  });

  it("puts a dismissed report back, with a toast, when the server refuses", async () => {
    const user = userEvent.setup();
    const routes = serve(MODERATOR);
    routes.on("POST /mod/reports/1/resolve", () => apiError(409, "report_already_resolved", "Already resolved."));
    const panel = await openMod();
    const list = await panel.findByRole("list", { name: "Open reports" });
    await user.click(
      within(within(list).getAllByRole("listitem")[1] as HTMLElement).getByRole("button", { name: "Dismiss" }),
    );
    const dialog = within(await screen.findByRole("dialog", { name: "Dismiss this report?" }));
    expect(dialog.queryByRole("checkbox")).toBeNull();
    await user.type(dialog.getByLabelText("Note for the log"), "Public footpath.");
    await user.click(dialog.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(messages()).toContain("The report couldn't be resolved. Already resolved."));
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
  });

  it("says when there's nothing to do", async () => {
    serve(MODERATOR, []);
    const panel = await openMod();
    expect(await panel.findByText("No reports are waiting")).toBeInTheDocument();
  });

  it("says when the queue can't be loaded, and tries again", async () => {
    const user = userEvent.setup();
    const routes = serve(MODERATOR);
    routes.on("GET /mod/reports", () => apiError(400, "bad_request", "The queue is stuck."));
    const panel = await openMod();
    expect(await panel.findByText("The reports couldn't be loaded")).toBeInTheDocument();
    routes.on("GET /mod/reports", () => json({ items: [PRIVACY], next_cursor: null }));
    await user.click(panel.getByRole("button", { name: "Try again" }));
    expect(await panel.findByRole("list", { name: "Open reports" })).toBeInTheDocument();
  });
});

describe("photos, members and the log", () => {
  it("approves a photo and refuses another with a reason", async () => {
    const user = userEvent.setup();
    const routes = serve(MODERATOR);
    routes.on("GET /mod/media", () =>
      json({
        items: [queuedPhotoFixture(), queuedPhotoFixture({ id: 78, url: "/api/v1/media/78" })],
        next_cursor: null,
      }),
    );
    routes.on("POST /mod/media/77/approve", () => json(queuedPhotoFixture({ approved: true })));
    routes.on("POST /mod/media/78/reject", () => json(queuedPhotoFixture({ id: 78, rejected: true })));
    const panel = await openMod("/mod/photos");
    const list = await panel.findByRole("list", { name: "Photos waiting for approval" });
    const [first, second] = cardsOf(list);
    expect(within(first as HTMLElement).getByRole("img", { name: "Photo uploaded by Mary Anning" })).toHaveAttribute(
      "src",
      "/api/v1/media/77",
    );
    expect(within(first as HTMLElement).getByText(/200 KB/)).toBeInTheDocument();
    await user.click(within(first as HTMLElement).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(cardsOf(list)).toHaveLength(1));
    await user.click(within(second as HTMLElement).getByRole("button", { name: "Refuse" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Refuse this photo?" }));
    await user.type(dialog.getByLabelText("Why"), "Shows a house.");
    await user.click(dialog.getByRole("button", { name: "Refuse it" }));
    expect(await panel.findByText("No photos are waiting")).toBeInTheDocument();
    expect(routes.callsTo("POST /mod/media/78/reject")[0]?.body).toEqual({ reason: "Shows a house." });
  });

  it("lists who could be trusted with where their points came from, and makes one trusted", async () => {
    const user = userEvent.setup();
    const routes = serve(MODERATOR);
    routes.on("PUT /mod/users/KeenLynchet7/role", () => json({ ...eligibleFixture().user, role: "trusted" }));
    const panel = await openMod("/mod/members");
    const list = await panel.findByRole("list", { name: "Members who could be trusted" });
    const card = within(cardsOf(list)[0] as HTMLElement);
    expect(card.getByText("54 points · Joined September 2026")).toBeInTheDocument();
    expect(
      card.getByText("Their finding reached Seen by others, Corroborated and Checked on the ground."),
    ).toBeInTheDocument();
    expect(card.getByText("Second looks, counted together")).toBeInTheDocument();
    expect(card.getByText("Also on it: Sam Hill")).toBeInTheDocument();
    expect(card.getByText(/on 1 of 1/)).toBeInTheDocument();
    await user.click(card.getByRole("button", { name: "Make trusted" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Change KeenLynchet7's role" }));
    await user.type(dialog.getByLabelText("Why"), "Careful, independent work.");
    await user.click(dialog.getByRole("button", { name: "Make them trusted member" }));
    expect(await panel.findByText("Nobody is waiting")).toBeInTheDocument();
    expect(routes.callsTo("PUT /mod/users/KeenLynchet7/role")[0]?.body).toEqual({
      role: "trusted",
      reason: "Careful, independent work.",
    });
  });

  it("looks someone up by handle and offers only what may be done to them", async () => {
    const user = userEvent.setup();
    const routes = serve(MODERATOR);
    routes.on("GET /users/KeenLynchet7", () => json(profileFixture({ reputation: 12 })));
    routes.on("GET /users/ModMax", () =>
      json(profileFixture({ handle: "ModMax", display_name: "Max", role: "moderator" })),
    );
    routes.on("GET /users/Gone", () => apiError(404, "user_not_found", "No such person."));
    const members = await openMod("/mod/members?handle=KeenLynchet7");
    const panel = within(
      (await members.findByRole("heading", { name: "Find a member" })).closest("section") as HTMLElement,
    );
    await panel.findByText("Mary Anning");
    expect(panel.getByRole("button", { name: "Change role" })).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Ban KeenLynchet7" })).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "Change role" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Change KeenLynchet7's role" }));
    // Twelve points: not yet eligible for trusted.
    expect(dialog.getAllByRole("radio").map((radio) => radio.textContent)).toEqual(["Archaeologist"]);
    await user.click(dialog.getByRole("button", { name: "Cancel" }));

    const field = panel.getByLabelText("Handle");
    await user.clear(field);
    await user.type(field, "ModMax{Enter}");
    await panel.findByText("Max");
    expect(panel.queryByRole("button", { name: "Change role" })).toBeNull();
    expect(panel.queryByRole("button", { name: /^Ban/ })).toBeNull();

    await user.clear(field);
    await user.type(field, "Gone{Enter}");
    expect(await panel.findByText(/Nobody can be found as/)).toBeInTheDocument();
    // Whether they exist, are banned, or may be unbanned by this moderator is unknown, so nothing is offered.
    expect(panel.queryByRole("button", { name: /ban/i })).toBeNull();
    expect(routes.callsTo("GET /users/Gone")).toHaveLength(1);
  });

  it("stops offering a change of role once the person looked up is banned", async () => {
    const user = userEvent.setup();
    const routes = serve(MODERATOR);
    routes.on("GET /users/KeenLynchet7", () => json(profileFixture({ reputation: 12 })));
    routes.on("POST /mod/users/KeenLynchet7/ban", () =>
      json({ user: { ...eligibleFixture().user, banned: true }, sessions_ended: 1 }),
    );
    const members = await openMod("/mod/members?handle=KeenLynchet7");
    const panel = within(
      (await members.findByRole("heading", { name: "Find a member" })).closest("section") as HTMLElement,
    );
    await panel.findByText("Mary Anning");
    await user.click(panel.getByRole("button", { name: "Ban KeenLynchet7" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Ban KeenLynchet7?" }));
    // Decision 0019: a ban stops their evidence and verifications, not their answers and votes.
    expect(dialog.getByText(/evidence and verifications stop counting/)).toBeInTheDocument();
    expect(dialog.getByText(/second looks and votes keep counting as they were given/)).toBeInTheDocument();
    await user.type(dialog.getByLabelText("Why"), "Spam.");
    await user.click(dialog.getByRole("button", { name: "Ban them" }));
    expect(await panel.findByRole("button", { name: "Lift the ban on KeenLynchet7" })).toBeInTheDocument();
    expect(panel.queryByRole("button", { name: "Change role" })).toBeNull();
    expect(routes.callsTo("POST /mod/users/KeenLynchet7/ban")).toHaveLength(1);
  });

  it("writes the log as sentences, and shows something hidden again from it", async () => {
    const user = userEvent.setup();
    const routes = serve(MODERATOR);
    routes.on("POST /mod/comments/501/unhide", () =>
      json({ target_kind: "comment", target_id: "501", hidden: false, hidden_at: null }),
    );
    const panel = await openMod("/mod/log");
    const list = await panel.findByRole("list", { name: "Moderation log" });
    const entry = within(cardsOf(list)[0] as HTMLElement);
    expect(entry.getByText("Morag Kerr hid a comment on “Ring ditch by the long barrow”.")).toBeInTheDocument();
    expect(entry.getByLabelText("Their reason")).toHaveTextContent("Names a private landowner.");
    await user.click(entry.getByRole("button", { name: "Show this comment again" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Show this comment again?" }));
    await user.type(dialog.getByLabelText("Why"), "The landowner agreed.");
    await user.click(dialog.getByRole("button", { name: "Show it again" }));
    expect(await entry.findByRole("button", { name: "Hide this comment" })).toBeInTheDocument();
    expect(routes.callsTo("POST /mod/comments/501/unhide")).toHaveLength(1);
  });
});
