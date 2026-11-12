import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../../api/client.js";
import { apiError, routeApi } from "../../test/apiRoutes.js";
import { meFixture, newcomerFixture } from "../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import { resetDraftsForTests } from "../drafts/store.js";
import type { Me } from "./api.js";
import { AccountRequiredError, useAccountUi, useRequireAccount } from "./requireAccount.js";
import { onPersonChanged, useSession } from "./session.js";

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

/** A stand-in for a feature that saves: it asks for an account and says what happened. */
function SaveProbe() {
  const requireAccount = useRequireAccount();
  const session = useSession();
  const [outcome, setOutcome] = useState("nothing yet");
  return (
    <div data-testid="probe">
      <span data-testid="status">{session.status}</span>
      <span data-testid="outcome">{outcome}</span>
      <button
        type="button"
        onClick={() =>
          requireAccount().then(
            (me) => setOutcome(`ready as ${me.handle}`),
            (error: unknown) => setOutcome(error instanceof AccountRequiredError ? "closed" : "error"),
          )
        }
      >
        Probe save
      </button>
    </div>
  );
}

function probe() {
  return within(screen.getByTestId("probe"));
}

describe("the session", () => {
  it("is signed out when /auth/me answers 401, and the rail shows the plain icon", async () => {
    routeApi(harness.fetchMock());
    renderShell("/", <SaveProbe />);
    await mapReady();
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-out"));
    expect(screen.queryByTestId("account-avatar")).toBeNull();
  });

  it("is signed in from /auth/me, and the rail shows the person's initials", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    renderShell("/", <SaveProbe />);
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-in"));
    const rail = screen.getByRole("navigation", { name: "Modes" });
    const avatar = within(rail).getByTestId("account-avatar");
    expect(avatar).toHaveTextContent("AL");
    expect(within(rail).getByRole("link", { name: "Account" })).toContainElement(avatar);
  });

  it("is unknown when the server can't be asked, which is not a crash", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => apiError(503, "unavailable", "Down.") });
    renderShell("/", <SaveProbe />);
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("unknown"));
  });

  it("signs the whole interface out when any request is answered 401", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    renderShell("/", <SaveProbe />);
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-in"));
    harness.fetchMock().mockImplementationOnce(async () => signedOutResponse());
    await act(async () => {
      await apiFetch("/findings", { method: "POST", body: {} }).catch(() => undefined);
    });
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-out"));
    expect(screen.queryByTestId("account-avatar")).toBeNull();
    expect(await screen.findByText("You've been signed out. Sign in again to save.")).toBeInTheDocument();
  });

  it("tells every person-change listener when someone signs out, but not on the first answer", async () => {
    const heard = vi.fn();
    const stop = onPersonChanged(heard);
    try {
      routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
      renderShell("/", <SaveProbe />);
      await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-in"));
      expect(heard).not.toHaveBeenCalled();
      harness.fetchMock().mockImplementationOnce(async () => signedOutResponse());
      await act(async () => {
        await apiFetch("/findings", { method: "POST", body: {} }).catch(() => undefined);
      });
      await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-out"));
      expect(heard).toHaveBeenCalledTimes(1);
    } finally {
      stop();
    }
  });

  it("asks again and opens the welcome sheet when any save is refused with onboarding_required", async () => {
    const routes = routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    renderShell("/", <SaveProbe />);
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-in"));
    expect(screen.queryByRole("dialog")).toBeNull();
    routes.on("GET /auth/me", () => json(newcomerFixture()));
    routes.on("PATCH /auth/me", () => apiError(403, "onboarding_required", "Finish joining first."));
    await act(async () => {
      await apiFetch("/auth/me", { method: "PATCH", body: {} }).catch(() => undefined);
    });
    expect(await screen.findByRole("dialog", { name: "Welcome to OpenAntiquity" })).toBeInTheDocument();
    await waitFor(() => expect(routes.callsTo("GET /auth/me").length).toBeGreaterThan(1));
  });

  it("asks again when another tab signs in", async () => {
    const routes = routeApi(harness.fetchMock());
    renderShell("/", <SaveProbe />);
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-out"));
    routes.on("GET /auth/me", () => json(meFixture()));
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "fieldclub.session-changed", newValue: "x" }));
    });
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-in"));
  });
});

describe("requireAccount", () => {
  it("resolves at once for someone signed in and through the welcome step", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    renderShell("/", <SaveProbe />);
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-in"));
    await userEvent.click(probe().getByRole("button", { name: "Probe save" }));
    await waitFor(() => expect(probe().getByTestId("outcome")).toHaveTextContent("ready as QuietBarrow42"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens the sign-in sheet for someone signed out, and rejects when they close it", async () => {
    routeApi(harness.fetchMock());
    renderShell("/", <SaveProbe />);
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-out"));
    await userEvent.click(probe().getByRole("button", { name: "Probe save" }));
    const sheet = await screen.findByRole("dialog", { name: "Sign in" });
    expect(probe().getByTestId("outcome")).toHaveTextContent("nothing yet");
    await userEvent.click(within(sheet).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(probe().getByTestId("outcome")).toHaveTextContent("closed"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("resolves once the person signs in and is welcomed, without leaving the page", async () => {
    const routes = routeApi(harness.fetchMock());
    renderShell("/", <SaveProbe />);
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("signed-out"));
    await userEvent.click(probe().getByRole("button", { name: "Probe save" }));
    await screen.findByRole("dialog", { name: "Sign in" });

    // Signed in elsewhere, for the first time: the welcome step comes next.
    routes.on("GET /auth/me", () => json(newcomerFixture()));
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "fieldclub.session-changed", newValue: "x" }));
    });
    const welcome = await screen.findByRole("dialog", { name: "Welcome to OpenAntiquity" });
    expect(probe().getByTestId("outcome")).toHaveTextContent("nothing yet");

    routes.on("POST /auth/welcome", () => json(meFixture()));
    await userEvent.click(within(welcome).getByRole("radio", { name: "18 or over" }));
    await userEvent.click(within(welcome).getByRole("checkbox", { name: "I accept the contributor terms" }));
    await userEvent.click(within(welcome).getByRole("button", { name: "Join OpenAntiquity" }));
    await waitFor(() => expect(probe().getByTestId("outcome")).toHaveTextContent("ready as QuietBarrow42"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens the welcome sheet for someone signed in who still owes it", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(newcomerFixture()) });
    renderShell("/", <SaveProbe />);
    // It offers itself once on arrival. Closed, it waits to be asked for.
    // jsdom has no modal dialogs, so focus never enters one and Escape can't
    // reach it. The end-to-end tests press Escape in a real browser.
    const first = await screen.findByRole("dialog", { name: "Welcome to OpenAntiquity" });
    await userEvent.click(within(first).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await userEvent.click(probe().getByRole("button", { name: "Probe save" }));
    const second = await screen.findByRole("dialog", { name: "Welcome to OpenAntiquity" });
    await userEvent.click(within(second).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(probe().getByTestId("outcome")).toHaveTextContent("closed"));
  });

  it("says it couldn't check, rather than treating the person as signed out, when the server can't be asked", async () => {
    routeApi(harness.fetchMock(), { "GET /auth/me": () => apiError(503, "unavailable", "Down.") });
    renderShell("/", <SaveProbe />);
    await waitFor(() => expect(probe().getByTestId("status")).toHaveTextContent("unknown"));
    await userEvent.click(probe().getByRole("button", { name: "Probe save" }));
    expect(await screen.findByText(/We couldn't check whether you're signed in/)).toBeInTheDocument();
    await waitFor(() => expect(probe().getByTestId("outcome")).toHaveTextContent("closed"));
    expect(screen.queryByRole("dialog", { name: "Sign in" })).toBeNull();
  });

  it("asks the server first when the session isn't known yet", async () => {
    let answer: (response: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      answer = resolve;
    });
    routeApi(harness.fetchMock(), { "GET /auth/me": () => pending });
    renderShell("/", <SaveProbe />);
    await mapReady();
    await userEvent.click(probe().getByRole("button", { name: "Probe save" }));
    const me: Me = meFixture();
    answer(json(me));
    await waitFor(() => expect(probe().getByTestId("outcome")).toHaveTextContent("ready as QuietBarrow42"));
  });
});
