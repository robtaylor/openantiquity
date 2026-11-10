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
import { Shell } from "../shell/Shell.js";
import { DraftBadge } from "./DraftBadge.js";
import { registerDraftSaver, resetSaversForTests } from "./savers.js";
import { listDrafts, putDraft, resetDraftsForTests, setDraftsViewer } from "./store.js";
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
    expect(listDrafts()).toEqual([]);
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    expect(listDrafts()).toHaveLength(1);
  });

  it("saves every waiting draft exactly once on arrival signed in, as after a provider's round trip", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    putDraft(PROBE, { note: "a" });
    putDraft(PROBE, { note: "b" });
    renderApp();
    expect(await screen.findByText("Your 2 drafts are saved.")).toBeInTheDocument();
    expect(saved).toEqual(["a", "b"]);
    expect(listDrafts()).toEqual([]);
    expect(screen.queryByRole("region", { name: "Drafts" })).toBeNull();
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
    expect(b.getByText(/left in this browser before you signed in, perhaps by someone else/)).toBeInTheDocument();
    expect(b.getByText("Saying theirs")).toBeInTheDocument();
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
    expect(listDrafts()).toEqual([]);
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    expect(listDrafts()).toHaveLength(1);
    expect(saved).toEqual([]);
  });

  it("waits for the welcome step before saving", async () => {
    const routes = routeApi(harness.fetchMock(), {
      "GET /auth/me": () => json(newcomerFixture()),
      "POST /auth/welcome": () => json(meFixture()),
    });
    putDraft(PROBE, { note: "a" });
    renderApp();
    const welcome = within(await screen.findByRole("dialog", { name: "Welcome to Field Club" }));
    expect(saved).toEqual([]);
    await userEvent.click(welcome.getByRole("radio", { name: "18 or over" }));
    await userEvent.click(welcome.getByRole("checkbox", { name: "I accept the contributor terms" }));
    await userEvent.click(welcome.getByRole("button", { name: "Join Field Club" }));
    await waitFor(() => expect(saved).toEqual(["a"]));
    expect(routes.callsTo("POST /auth/welcome")).toHaveLength(1);
  });

  it("keeps a draft that fails, shows the reason, and tries again when asked", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    failWith = new ApiError(422, "validation_error", "That square isn't in Britain.");
    putDraft(PROBE, { note: "a" });
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
    expect(listDrafts()).toEqual([]);
  });
});

describe("DraftBadge", () => {
  it("says the thing isn't saved yet", () => {
    render(<DraftBadge />);
    expect(screen.getByText("Not saved yet")).toBeInTheDocument();
  });
});
