import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { useFakeEventSource } from "../../test/fakeEventSource.js";
import {
  commentFixture,
  EXPERT,
  evidenceFixture,
  FINDER,
  OTHER,
  seenFixture,
  suggestionsFixture,
} from "../../test/fixtures/findingPage.js";
import { meFixture } from "../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import { useToastStore } from "../../ui/toastStore.js";
import type { Me } from "../account/api.js";
import { useAccountUi } from "../account/requireAccount.js";
import type { Comment, FindingDetail } from "../finding/types.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

beforeEach(() => {
  useFakeEventSource();
  useAccountUi.setState({ sheet: null, waiting: [] });
});

const VIEWER = meFixture({ handle: "SharpEyedSam", display_name: "Sam Hill" });
const MODERATOR = meFixture({ handle: "ModMorag", display_name: "Morag Kerr", role: "moderator" });
const COMMENT = commentFixture({ id: 501 });

function serve(finding: FindingDetail, me: Me | null, comments: Comment[] = [COMMENT]): ApiRoutes {
  const path = `/findings/${finding.public_id}`;
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : signedOutResponse()),
    [`GET ${path}`]: () => json(finding),
    [`GET ${path}/comments`]: () => json({ items: comments, next_cursor: null }),
    [`GET ${path}/suggested-records`]: () => json(suggestionsFixture([])),
    "GET /mod/actions": () => json({ items: [], next_cursor: null }),
    "POST /reports": (call) => {
      const body = call.body as { target_kind: string; target_id: string; reason: string };
      return json({ id: 1, ...body, created_at: "2026-11-11T10:00:00Z" }, 201);
    },
  });
}

async function open(finding: FindingDetail, me: Me | null, routes = serve(finding, me)) {
  renderShell(`/f/${finding.public_id}`);
  await mapReady();
  const panel = within(await screen.findByRole("complementary", { name: finding.title }));
  return { panel, routes };
}

describe("reporting", () => {
  it("reports a comment with a reason from /meta and a note, and says plainly what happens next", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(seenFixture(), VIEWER);
    await panel.findByText(COMMENT.body ?? "");
    await user.click(panel.getByRole("button", { name: "Report this comment" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Report this comment" }));
    expect(dialog.getByRole("group", { name: "What's wrong?" })).toBeInTheDocument();
    expect(dialog.getAllByRole("radio")).toHaveLength(10);
    expect(
      dialog.getByText("It identifies a person, a home or a private garden, or says who owns the land."),
    ).toBeVisible();

    await user.click(dialog.getByRole("button", { name: "Send report" }));
    expect(dialog.getByRole("alert")).toHaveTextContent("Choose what's wrong first.");
    expect(routes.callsTo("POST /reports")).toHaveLength(0);

    await user.click(dialog.getByRole("radio", { name: /Reveals personal details/ }));
    await user.type(dialog.getByLabelText(/Anything the moderators should know/), "It names the farmer.");
    await user.click(dialog.getByRole("button", { name: "Send report" }));
    await waitFor(() => expect(routes.callsTo("POST /reports")).toHaveLength(1));
    expect(routes.callsTo("POST /reports")[0]?.body).toEqual({
      target_kind: "comment",
      target_id: "501",
      reason: "privacy",
      note: "It names the farmer.",
    });
    const sent = within(await screen.findByRole("dialog", { name: "Thanks, your report is in" }));
    expect(sent.getByRole("status")).toHaveTextContent("A moderator will look at it.");
    expect(sent.getByRole("status")).toHaveTextContent("You won't hear back about what they decide.");
    await user.click(sent.getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says a report with a legal deadline is dealt with in that time", async () => {
    const user = userEvent.setup();
    const { panel } = await open(seenFixture(), VIEWER);
    await user.click(panel.getByRole("button", { name: "Report this finding" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Report this finding" }));
    await user.click(dialog.getByRole("radio", { name: /Untrue about a person/ }));
    await user.click(dialog.getByRole("button", { name: "Send report" }));
    expect(await dialog.findByText(/within 48 hours/)).toBeInTheDocument();
  });

  it("explains a second report on the same thing, and keeps the form", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(seenFixture(), VIEWER);
    routes.on("POST /reports", () => apiError(409, "already_reported", "Already reported."));
    await user.click(panel.getByRole("button", { name: "Report this finding" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Report this finding" }));
    await user.click(dialog.getByRole("radio", { name: /Spam/ }));
    await user.click(dialog.getByRole("button", { name: "Send report" }));
    expect(await dialog.findByRole("alert")).toHaveTextContent("You've already reported this");
    expect(dialog.getByRole("radio", { name: /Spam/ })).toBeChecked();
  });

  it("says a moderator has just looked at it when the server is cooling off", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(seenFixture(), VIEWER);
    routes.on("POST /reports", () => apiError(409, "recently_dismissed", "Dismissed recently."));
    await user.click(panel.getByRole("button", { name: "Report this finding" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Report this finding" }));
    await user.click(dialog.getByRole("radio", { name: /Spam/ }));
    await user.click(dialog.getByRole("button", { name: "Send report" }));
    expect(await dialog.findByRole("alert")).toHaveTextContent(
      "A moderator has just looked at your report on this. You can report it again tomorrow.",
    );
  });

  it("offers no report on your own work", async () => {
    const own = meFixture({ handle: FINDER.handle, display_name: FINDER.display_name });
    const finding = seenFixture({ evidence: [evidenceFixture({ contributor: FINDER })] });
    const { panel } = await open(finding, own, serve(finding, own, [commentFixture({ author: FINDER })]));
    await panel.findByText(COMMENT.body ?? "");
    expect(panel.queryByRole("button", { name: /^Report/ })).toBeNull();
  });

  it("asks a signed-out person to sign in first", async () => {
    const user = userEvent.setup();
    const { panel } = await open(seenFixture(), null);
    await user.click(panel.getByRole("button", { name: "Report this finding" }));
    await waitFor(() => expect(useAccountUi.getState().sheet).toBe("signin"));
  });

  it("reports a photo apart from the evidence it belongs to", async () => {
    const user = userEvent.setup();
    const finding = seenFixture({
      evidence: [evidenceFixture({ id: 9, kind: "photo", media_id: 77, contributor: OTHER })],
    });
    const { panel, routes } = await open(finding, VIEWER);
    await user.click(panel.getByRole("button", { name: "Report this photo" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Report this photo" }));
    await user.click(dialog.getByRole("radio", { name: /Intimate image/ }));
    await user.click(dialog.getByRole("button", { name: "Send report" }));
    await waitFor(() =>
      expect(routes.callsTo("POST /reports")[0]?.body).toEqual({
        target_kind: "photo",
        target_id: "77",
        reason: "intimate_image",
      }),
    );
  });
});

describe("moderating on a finding's page", () => {
  it("offers a moderator hide, never delete, on someone else's comment, and shows it at once", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(seenFixture(), MODERATOR);
    routes.on("POST /mod/comments/501/hide", () =>
      json({ target_kind: "comment", target_id: "501", hidden: true, hidden_at: "2026-11-11T10:00:00Z" }),
    );
    await panel.findByText(COMMENT.body ?? "");
    const comment = within(panel.getByText(COMMENT.body ?? "").closest("li") as HTMLElement);
    expect(comment.queryByRole("button", { name: "Remove" })).toBeNull();
    await user.click(comment.getByRole("button", { name: "Hide this comment" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Hide this comment?" }));
    await user.click(dialog.getByRole("button", { name: "Hide it" }));
    expect(dialog.getByRole("alert")).toHaveTextContent("Say why, for the log.");
    await user.type(dialog.getByLabelText("Why"), "Names a landowner.");
    await user.click(dialog.getByRole("button", { name: "Hide it" }));
    expect(await comment.findByText(/A moderator hid this comment/)).toBeInTheDocument();
    expect(routes.callsTo("POST /mod/comments/501/hide")[0]?.body).toEqual({ reason: "Names a landowner." });
    expect(comment.getByRole("button", { name: "Show this comment again" })).toBeInTheDocument();
  });

  it("puts a hidden comment back, with a toast, when the server refuses", async () => {
    const user = userEvent.setup();
    const { panel, routes } = await open(seenFixture(), MODERATOR);
    routes.on("POST /mod/comments/501/hide", () => apiError(403, "own_content", "That's your own."));
    await panel.findByText(COMMENT.body ?? "");
    await user.click(panel.getByRole("button", { name: "Hide this comment" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Hide this comment?" }));
    await user.type(dialog.getByLabelText("Why"), "Spam.");
    await user.click(dialog.getByRole("button", { name: "Hide it" }));
    await waitFor(() =>
      expect(useToastStore.getState().toasts.map((toast) => toast.message)).toContain(
        "The comment couldn't be hidden. That's your own.",
      ),
    );
    expect(panel.queryByText(/A moderator hid this comment/)).toBeNull();
  });

  it("offers nobody but a moderator the moderation tools, and a moderator none on their own finding", async () => {
    const { panel } = await open(seenFixture(), VIEWER);
    await panel.findByText(COMMENT.body ?? "");
    expect(panel.queryByRole("button", { name: /^Hide/ })).toBeNull();
    expect(panel.queryByRole("heading", { name: "Moderation" })).toBeNull();
  });

  it("lets a moderator hide someone else's finding and lower its level, each with a reason", async () => {
    const user = userEvent.setup();
    const finding = seenFixture({ sensitivity: "restricted", evidence: [evidenceFixture({ contributor: EXPERT })] });
    const { panel, routes } = await open(finding, MODERATOR);
    routes.on("PUT /mod/findings/f-ring/sensitivity", () => json({ ...finding, sensitivity: "open" }));
    routes.on("POST /mod/findings/f-ring/hide", () =>
      json({ target_kind: "finding", target_id: "f-ring", hidden: true, hidden_at: "2026-11-11T10:00:00Z" }),
    );
    const section = within(
      (await panel.findByRole("heading", { name: "Moderation" })).closest("section") as HTMLElement,
    );
    await user.click(await section.findByRole("button", { name: "Change its level" }));
    let dialog = within(await screen.findByRole("dialog", { name: "Change its level" }));
    expect(dialog.getByRole("button", { name: "Change it" })).toBeDisabled();
    await user.click(dialog.getByRole("radio", { name: "Open" }));
    await user.type(dialog.getByLabelText("Why"), "A field boundary, not a barrow.");
    await user.click(dialog.getByRole("button", { name: "Change it" }));
    await waitFor(() =>
      expect(routes.callsTo("PUT /mod/findings/f-ring/sensitivity")[0]?.body).toEqual({
        level: "open",
        reason: "A field boundary, not a barrow.",
      }),
    );

    await waitFor(() => expect(section.getByRole("button", { name: "Hide it" })).toBeEnabled());
    await user.click(section.getByRole("button", { name: "Hide it" }));
    dialog = within(await screen.findByRole("dialog", { name: "Hide this finding?" }));
    await user.type(dialog.getByLabelText("Why"), "Asked by the landowner.");
    await user.click(dialog.getByRole("button", { name: "Hide it" }));
    expect(await section.findByRole("button", { name: "Show it again" })).toBeInTheDocument();
    expect(section.getByText(/This finding is hidden/)).toBeInTheDocument();
  });

  it("gives a moderator none of it on their own finding", async () => {
    const own = meFixture({ handle: FINDER.handle, display_name: FINDER.display_name, role: "moderator" });
    const { panel } = await open(seenFixture(), own, serve(seenFixture(), own, [commentFixture({ author: FINDER })]));
    await panel.findByText(COMMENT.body ?? "");
    expect(panel.queryByRole("heading", { name: "Moderation" })).toBeNull();
    expect(panel.queryByRole("button", { name: /^Hide/ })).toBeNull();
  });
});
