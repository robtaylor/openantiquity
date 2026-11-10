import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { meFixture, newcomerFixture } from "../../test/fixtures/me.js";
import { json, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import {
  DRAFTS_STORAGE_KEY,
  DRAFTS_UNREADABLE_KEY,
  listDrafts,
  putDraft,
  resetDraftsForTests,
} from "../drafts/store.js";
import type { Me } from "./api.js";
import { useAccountUi } from "./requireAccount.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

beforeEach(() => {
  useAccountUi.setState(useAccountUi.getInitialState(), true);
  window.localStorage.clear();
  resetDraftsForTests();
});

async function openAccount(me: Me | null, routes: Parameters<typeof routeApi>[1] = {}) {
  const api: ApiRoutes = routeApi(harness.fetchMock(), {
    ...(me ? { "GET /auth/me": () => json(me) } : {}),
    ...routes,
  });
  renderShell("/account");
  const panel = await screen.findByRole("complementary", { name: "Account" });
  return { api, panel, p: within(panel) };
}

describe("the account page", () => {
  it("invites someone signed out to sign in", async () => {
    const { p } = await openAccount(null);
    expect(await p.findByRole("heading", { name: "You're not signed in" })).toBeInTheDocument();
    await userEvent.click(p.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("dialog", { name: "Sign in" })).toBeInTheDocument();
  });

  it("says when it couldn't check, and tries again", async () => {
    let up = false;
    const { p } = await openAccount(null, {
      "GET /auth/me": () => (up ? json(meFixture()) : apiError(503, "unavailable", "The server is restarting.")),
    });
    expect(await p.findByRole("heading", { name: "We couldn't check whether you're signed in" })).toBeInTheDocument();
    up = true;
    await userEvent.click(p.getByRole("button", { name: "Try again" }));
    expect(await p.findByText("@QuietBarrow42")).toBeInTheDocument();
  });

  it("shows the person, links to their public profile, and explains their picture", async () => {
    const { p } = await openAccount(meFixture());
    expect(await p.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(p.getByRole("link", { name: "See your public profile" })).toHaveAttribute("href", "/u/QuietBarrow42");
    expect(p.getByText(/other people see your initials/)).toBeInTheDocument();
    expect(p.getByText("Signed in as ada@example.org.")).toBeInTheDocument();
  });

  it("never shows a 16 or 17 year old a picture rule that would show their face", async () => {
    const { p } = await openAccount(meFixture({ age_band: "16_17", display_name: "QuietBarrow42" }));
    expect(await p.findByText(/Other people see only your handle/)).toBeInTheDocument();
  });

  it("saves only what changed, shows it at once, and keeps it", async () => {
    const { api, p } = await openAccount(meFixture(), {
      "PATCH /auth/me": (call) => json(meFixture(call.body as Partial<Me>)),
    });
    const name = await p.findByLabelText("Display name");
    expect(p.getByRole("button", { name: "Save changes" })).toBeDisabled();
    await userEvent.clear(name);
    await userEvent.type(name, "Ada L.");
    await userEvent.type(p.getByLabelText("About you"), "I walk the Ridgeway.");
    await userEvent.click(p.getByRole("button", { name: "Save changes" }));
    expect(await p.findByText("Ada L.", { selector: ".fc-account-who__name" })).toBeInTheDocument();
    expect(api.callsTo("PATCH /auth/me")[0]?.body).toEqual({ display_name: "Ada L.", bio: "I walk the Ridgeway." });
    expect(await screen.findByText("Your details are saved.")).toBeInTheDocument();
  });

  it("puts things back and says why when a save fails", async () => {
    let answer: (response: Response) => void = () => {};
    const { p } = await openAccount(meFixture(), {
      "PATCH /auth/me": () =>
        new Promise<Response>((resolve) => {
          answer = resolve;
        }),
    });
    const handle = await p.findByLabelText("Handle");
    await userEvent.clear(handle);
    await userEvent.type(handle, "Taken");
    await userEvent.click(p.getByRole("button", { name: "Save changes" }));
    // Optimistic: the new handle shows before the server answers.
    expect(await p.findByText("@Taken")).toBeInTheDocument();
    answer(apiError(409, "handle_taken", "Someone already has that name."));
    expect(await p.findByText("@QuietBarrow42")).toBeInTheDocument();
    expect(await screen.findByText(/Your changes weren't saved/)).toBeInTheDocument();
  });

  it("keeps the bio closed until the welcome step is done", async () => {
    const { p } = await openAccount(newcomerFixture());
    // The welcome sheet offers itself; close it to look at the page.
    const welcome = await screen.findByRole("dialog", { name: "Welcome to Field Club" });
    await userEvent.click(within(welcome).getByRole("button", { name: "Close" }));
    expect(p.getByLabelText("About you")).toBeDisabled();
    await userEvent.click(p.getByRole("button", { name: "Finish joining" }));
    expect(await screen.findByRole("dialog", { name: "Welcome to Field Club" })).toBeInTheDocument();
  });

  it("signs out everywhere at once", async () => {
    const { api, p } = await openAccount(meFixture(), {
      "POST /auth/logout": () => new Response(null, { status: 204 }),
    });
    await userEvent.click(await p.findByRole("button", { name: "Sign out" }));
    expect(await p.findByRole("heading", { name: "You're not signed in" })).toBeInTheDocument();
    expect(screen.queryByTestId("account-avatar")).toBeNull();
    expect(api.callsTo("POST /auth/logout")).toHaveLength(1);
  });

  it("asks whether to keep the drafts in this browser before signing out, and discards them when told", async () => {
    putDraft("probe", { note: "a" });
    window.localStorage.setItem(`${DRAFTS_UNREADABLE_KEY}.old`, "{bad");
    const { api, p } = await openAccount(meFixture(), {
      "POST /auth/logout": () => new Response(null, { status: 204 }),
    });
    await userEvent.click(await p.findByRole("button", { name: "Sign out" }));
    const dialog = await screen.findByRole("dialog", { name: "Keep your drafts?" });
    expect(within(dialog).getByText(/whoever uses this browser next will see it/)).toBeInTheDocument();
    expect(api.callsTo("POST /auth/logout")).toEqual([]);
    await userEvent.click(within(dialog).getByRole("button", { name: "Discard and sign out" }));
    expect(await p.findByRole("heading", { name: "You're not signed in" })).toBeInTheDocument();
    expect(listDrafts()).toEqual([]);
    expect(window.localStorage.getItem(`${DRAFTS_UNREADABLE_KEY}.old`)).toBeNull();
  });

  it("keeps the drafts when asked to, and signs out", async () => {
    putDraft("probe", { note: "a" });
    const { p } = await openAccount(meFixture(), {
      "POST /auth/logout": () => new Response(null, { status: 204 }),
    });
    await userEvent.click(await p.findByRole("button", { name: "Sign out" }));
    const dialog = await screen.findByRole("dialog", { name: "Keep your drafts?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep and sign out" }));
    expect(await p.findByRole("heading", { name: "You're not signed in" })).toBeInTheDocument();
    expect(listDrafts()).toHaveLength(1);
  });

  it("discards this browser's drafts with the account, unless told to keep them", async () => {
    putDraft("probe", { note: "a" });
    putDraft("probe", { note: "b" });
    const { p } = await openAccount(meFixture(), {
      "DELETE /auth/me": () => new Response(null, { status: 204 }),
    });
    await userEvent.click(await p.findByRole("button", { name: "Delete my account" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete your account?" });
    const discard = within(dialog).getByRole("checkbox", { name: "Also discard the 2 drafts kept in this browser" });
    expect(discard).toBeChecked();
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete my account" }));
    expect(await p.findByRole("heading", { name: "You're not signed in" })).toBeInTheDocument();
    expect(listDrafts()).toEqual([]);
    expect(JSON.parse(window.localStorage.getItem(DRAFTS_STORAGE_KEY) ?? "{}").drafts).toEqual([]);
  });

  it("deletes the account only after a dialog that says what happens to contributions", async () => {
    const { api, p } = await openAccount(meFixture(), {
      "DELETE /auth/me": () => new Response(null, { status: 204 }),
    });
    await userEvent.click(await p.findByRole("button", { name: "Delete my account" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete your account?" });
    expect(within(dialog).getByText(/credited to “Former member”/)).toBeInTheDocument();
    expect(within(dialog).getByText(/published under CC BY 4\.0/)).toBeInTheDocument();
    expect(within(dialog).getByText(/can't be undone/)).toBeInTheDocument();
    expect(api.callsTo("DELETE /auth/me")).toEqual([]);

    await userEvent.click(within(dialog).getByRole("button", { name: "Keep my account" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(api.callsTo("DELETE /auth/me")).toEqual([]);

    await userEvent.click(p.getByRole("button", { name: "Delete my account" }));
    const again = await screen.findByRole("dialog", { name: "Delete your account?" });
    await userEvent.click(within(again).getByRole("button", { name: "Delete my account" }));
    expect(await p.findByRole("heading", { name: "You're not signed in" })).toBeInTheDocument();
    expect(api.callsTo("DELETE /auth/me")).toHaveLength(1);
    expect(await screen.findByText("Your account has been deleted.")).toBeInTheDocument();
  });

  it("keeps the account and says so when deleting fails", async () => {
    const { p } = await openAccount(meFixture(), {
      "DELETE /auth/me": () => apiError(503, "unavailable", "The server is restarting."),
    });
    await userEvent.click(await p.findByRole("button", { name: "Delete my account" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete your account?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete my account" }));
    expect(await screen.findByText("The server is restarting.")).toBeInTheDocument();
    await waitFor(() => expect(p.getByText("@QuietBarrow42")).toBeInTheDocument());
  });
});
