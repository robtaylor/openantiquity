import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client.js";
import { routeApi } from "../../test/apiRoutes.js";
import { meFixture, newcomerFixture } from "../../test/fixtures/me.js";
import { json, setUpShellTests } from "../../test/shellHarness.js";
import { useAccountUi } from "../account/requireAccount.js";
import { accountIdentity } from "../account/session.js";
import { Shell } from "../shell/Shell.js";
import { DraftBadge } from "./DraftBadge.js";
import { registerDraftSaver, resetSaversForTests } from "./savers.js";
import { listAllDrafts, noteSignInStarted, putDraft, resetDraftsForTests, setDraftsViewer } from "./store.js";
import { useDraftsUi } from "./uiStore.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();
const PROBE = "probe";
const saved: string[] = [];
let failWith: ApiError | null = null;
let stopSaver: () => void = () => {};

beforeEach(() => {
  useAccountUi.setState(useAccountUi.getInitialState(), true);
  useDraftsUi.setState({ open: false });
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetDraftsForTests();
  resetSaversForTests();
  saved.length = 0;
  failWith = null;
  stopSaver = registerDraftSaver<{ note: string }>({
    kind: PROBE,
    label: "Probe",
    parse: (data) =>
      typeof data === "object" && data !== null && "note" in data && typeof data.note === "string"
        ? { note: data.note }
        : null,
    save: async (data) => {
      if (failWith) throw failWith;
      saved.push(data.note);
    },
    describe: (data) => `Saying ${data.note}`,
  });
});

afterEach(() => {
  stopSaver();
});

/** As the real app renders: strict mode, so effects run twice. */
function renderApp(path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <Shell />
        </MemoryRouter>
      </QueryClientProvider>
    </StrictMode>,
  );
}

async function bar() {
  return within(await screen.findByRole("region", { name: "Drafts" }));
}

describe("the drafts bar", () => {
  it("shows nothing when there are no drafts", async () => {
    routeApi(harness.fetchMock());
    renderApp();
    await screen.findByRole("button", { name: "Layers" });
    expect(screen.queryByRole("region", { name: "Drafts" })).toBeNull();
  });

  it("says how many drafts are waiting, and saving opens the sign-in sheet", async () => {
    routeApi(harness.fetchMock());
    putDraft(PROBE, { note: "a" });
    putDraft(PROBE, { note: "b" });
    renderApp();
    const b = await bar();
    expect(b.getByRole("status")).toHaveTextContent("2 drafts not saved yet");
    await userEvent.click(b.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("dialog", { name: "Sign in" })).toBeInTheDocument();
    expect(saved).toEqual([]);
  });

  it("lists the drafts, explains what a draft is, and discards one with undo", async () => {
    routeApi(harness.fetchMock());
    putDraft(PROBE, { note: "a" });
    renderApp();
    const b = await bar();
    await userEvent.click(b.getByRole("button", { name: "Show drafts" }));
    expect(b.getByText(/A draft is kept only in this browser/)).toBeInTheDocument();
    expect(b.getByText("Saying a")).toBeInTheDocument();
    await userEvent.click(b.getByRole("button", { name: "Discard probe" }));
    expect(listAllDrafts()).toEqual([]);
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    expect(listAllDrafts()).toHaveLength(1);
  });

  it("saves every waiting draft exactly once on arrival signed in, as after a provider's round trip", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    putDraft(PROBE, { note: "a" });
    putDraft(PROBE, { note: "b" });
    // The person pressed a provider's button in this tab, and the provider sends them back to it.
    noteSignInStarted("provider");
    resetDraftsForTests();
    renderApp();
    // Someone else may have left the tab open, so nothing is sent until the person says (Decision 0024).
    const b = await bar();
    await waitFor(() => expect(b.getByRole("status")).toHaveTextContent("2 drafts to send"));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(saved).toEqual([]);
    expect(screen.getByText(/2 drafts from before you signed in are waiting/)).toBeInTheDocument();
    await userEvent.click(b.getByRole("button", { name: "Check" }));
    expect(b.getByText(/Made in this tab before you signed in/)).toBeInTheDocument();
    // The open bar says the same, so the toast, which would cover it on a phone, goes.
    expect(screen.queryByText(/2 drafts from before you signed in are waiting/)).toBeNull();
    await userEvent.click(b.getByRole("button", { name: "Send all" }));
    expect(await screen.findByText("Your 2 drafts are saved.")).toBeInTheDocument();
    expect(saved).toEqual(["a", "b"]);
    expect(listAllDrafts()).toEqual([]);
    expect(screen.queryByRole("region", { name: "Drafts" })).toBeNull();
  });

  it("never takes drafts left in the browser for someone who arrives already signed in", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    // Someone signed out marked two things here and left without signing in.
    putDraft(PROBE, { note: "a" });
    putDraft(PROBE, { note: "b" });
    // The next person opens the site in a new tab, with a session of their own.
    resetDraftsForTests({ newTab: true });
    renderApp();
    const b = await bar();
    await waitFor(() => expect(b.getByRole("status")).toHaveTextContent("2 drafts left here"));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(saved).toEqual([]);
    expect(listAllDrafts().every((draft) => draft.owner !== null && "signedOut" in draft.owner)).toBe(true);
  });

  it("holds a second look given before signing in until the person says to send it", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    const sent: unknown[] = [];
    const stop = registerDraftSaver<unknown>({
      kind: "observation",
      label: "Second look",
      parse: (data) => data,
      save: async (data) => {
        sent.push(data);
      },
    });
    try {
      putDraft("observation", { public_id: "ABC123", answer: { visible: "yes" }, reveal: true });
      noteSignInStarted("provider");
      resetDraftsForTests();
      renderApp();
      const b = await bar();
      await waitFor(() => expect(b.getByRole("status")).toHaveTextContent("1 second look to send"));
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(sent).toEqual([]);
      await userEvent.click(b.getByRole("button", { name: "Check" }));
      expect(b.getByText(/An answer is final, so send it only if you gave it/)).toBeInTheDocument();
      await userEvent.click(b.getByRole("button", { name: "Send" }));
      await waitFor(() => expect(sent).toHaveLength(1));
    } finally {
      stop();
    }
  });

  it("shows a signed-out visitor drafts an earlier visit left by kind alone, to discard", async () => {
    routeApi(harness.fetchMock());
    putDraft(PROBE, { note: "a private note" });
    resetDraftsForTests({ newTab: true });
    renderApp();
    const b = await bar();
    expect(b.getByRole("status")).toHaveTextContent("1 draft left here");
    expect(b.queryByRole("button", { name: "Save" })).toBeNull();
    await userEvent.click(b.getByRole("button", { name: "Check" }));
    expect(b.getByText(/left in this browser by an earlier visit, perhaps by someone else/)).toBeInTheDocument();
    expect(b.queryByText(/a private note/)).toBeNull();
    expect(b.queryByRole("button", { name: "Save as mine" })).toBeNull();
    await userEvent.click(b.getByRole("button", { name: "Discard it" }));
    expect(listAllDrafts()).toEqual([]);
  });

  it("saves, without asking, the person's drafts kept from before drafts were keyed to their id", async () => {
    const me = meFixture();
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(me) });
    // An earlier build kept the signed-in person's drafts under when their account was made.
    setDraftsViewer(me.created_at);
    putDraft(PROBE, { note: "kept" });
    setDraftsViewer(null);
    renderApp();
    expect(await screen.findByText("Your draft is saved.")).toBeInTheDocument();
    expect(saved).toEqual(["kept"]);
    expect(listAllDrafts()).toEqual([]);
  });

  it("asks before saving drafts someone else left in this browser", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    // Someone else signed in here, made a draft, and their session ran out.
    setDraftsViewer("someone-else");
    putDraft(PROBE, { note: "theirs" });
    setDraftsViewer(null);
    renderApp();
    const b = await bar();
    await waitFor(() => expect(b.getByRole("status")).toHaveTextContent("1 draft left here"));
    expect(saved).toEqual([]);

    await userEvent.click(b.getByRole("button", { name: "Check" }));
    expect(b.getByText(/left in this browser by an earlier visit, perhaps by someone else/)).toBeInTheDocument();
    // Someone else's draft is shown by its kind alone: what it says stays theirs.
    expect(b.getByText("Probe")).toBeInTheDocument();
    expect(b.queryByText("Saying theirs")).toBeNull();
    await userEvent.click(b.getByRole("button", { name: "Save as mine" }));
    expect(await screen.findByText("Your draft is saved.")).toBeInTheDocument();
    expect(saved).toEqual(["theirs"]);
  });

  it("discards drafts someone else left, with undo", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    setDraftsViewer("someone-else");
    putDraft(PROBE, { note: "theirs" });
    setDraftsViewer(null);
    renderApp();
    const b = await bar();
    await userEvent.click(await b.findByRole("button", { name: "Check" }));
    await userEvent.click(b.getByRole("button", { name: "Discard it" }));
    expect(listAllDrafts()).toEqual([]);
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    expect(listAllDrafts()).toHaveLength(1);
    expect(saved).toEqual([]);
  });

  it("waits for the welcome step before saving", async () => {
    const routes = routeApi(harness.fetchMock(), {
      "GET /auth/me": () => json(newcomerFixture()),
      "POST /auth/welcome": () => json(meFixture()),
    });
    putDraft(PROBE, { note: "a" });
    noteSignInStarted("provider");
    renderApp();
    const welcome = within(await screen.findByRole("dialog", { name: "Welcome to OpenAntiquity" }));
    expect(saved).toEqual([]);
    await userEvent.click(welcome.getByRole("radio", { name: "18 or over" }));
    await userEvent.click(welcome.getByRole("checkbox", { name: "I accept the contributor terms" }));
    await userEvent.click(welcome.getByRole("button", { name: "Join OpenAntiquity" }));
    const b = await bar();
    await userEvent.click(await b.findByRole("button", { name: "Check" }));
    await userEvent.click(b.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(saved).toEqual(["a"]));
    expect(routes.callsTo("POST /auth/welcome")).toHaveLength(1);
  });

  it("keeps a draft that fails, shows the reason, and tries again when asked", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    failWith = new ApiError(422, "validation_error", "That square isn't in Britain.");
    // A draft made while signed in, so it is saved without asking.
    setDraftsViewer(accountIdentity(meFixture()));
    putDraft(PROBE, { note: "a" });
    setDraftsViewer(null);
    renderApp();
    expect(
      await screen.findByText("One draft couldn't be saved. It's still here, with the reason."),
    ).toBeInTheDocument();
    const b = await bar();
    expect(b.getByRole("status")).toHaveTextContent("1 draft couldn't be saved");
    await userEvent.click(screen.getByRole("button", { name: "Show" }));
    expect(b.getByText("Couldn't be saved: That square isn't in Britain.")).toBeInTheDocument();
    failWith = null;
    await userEvent.click(b.getAllByRole("button", { name: "Try again" })[0] as HTMLElement);
    await waitFor(() => expect(saved).toEqual(["a"]));
    expect(listAllDrafts()).toEqual([]);
  });
});

describe("DraftBadge", () => {
  it("says the thing isn't saved yet", () => {
    render(<DraftBadge />);
    expect(screen.getByText("Not saved yet")).toBeInTheDocument();
  });
});
