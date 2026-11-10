import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMapStore } from "../../map/store.js";
import { apiError, routeApi } from "../../test/apiRoutes.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { json, mapReady, metaResponse, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import { resetDraftsForTests } from "../drafts/store.js";
import { useAccountUi } from "./requireAccount.js";
import { SIGNIN_ERROR_MESSAGES } from "./signinErrors.js";

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

/** Shows the router's address, so a test can see what the app navigated to. */
function Address() {
  const location = useLocation();
  return <output data-testid="address">{`${location.pathname}${location.search}${location.hash}`}</output>;
}

async function openSheet() {
  await mapReady();
  act(() => useAccountUi.getState().openSignIn());
  return screen.findByRole("dialog", { name: "Sign in" });
}

const allProviders = {
  ...metaFixture,
  auth: {
    providers: [
      { id: "google", label: "Google", enabled: true },
      { id: "apple", label: "Apple", enabled: true },
      { id: "microsoft", label: "Microsoft", enabled: true },
      { id: "facebook", label: "Facebook", enabled: true },
      { id: "osm", label: "OpenStreetMap", enabled: true },
      { id: "github", label: "GitHub", enabled: true },
      { id: "email", label: "Email link", enabled: true },
    ],
  },
};

describe("the sign-in sheet", () => {
  it("offers one button per enabled provider, in /meta's order and in each provider's words", async () => {
    routeApi(harness.fetchMock(), { "GET /meta": () => metaResponse(allProviders) });
    renderShell("/");
    const sheet = await openSheet();
    const names = within(sheet)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(names).toEqual([
      "Continue with Google",
      "Continue with Apple",
      "Sign in with Microsoft",
      "Continue with Facebook",
      "Sign in with OpenStreetMap",
      "Sign in with GitHub",
    ]);
    expect(within(sheet).getByText(/Saving needs an account/)).toBeInTheDocument();
    expect(within(sheet).getByRole("button", { name: "Email me a link" })).toBeInTheDocument();
  });

  it("leaves out providers /meta marks disabled, and the development sign-in unless /meta offers it", async () => {
    routeApi(harness.fetchMock());
    renderShell("/");
    const sheet = await openSheet();
    expect(within(sheet).queryByText("Continue with Apple")).toBeNull();
    expect(within(sheet).getByText("Continue with Google")).toBeInTheDocument();
    expect(within(sheet).queryByLabelText("Development sign-in")).toBeNull();
  });

  it("sends a provider button to the start route with next set to this view, map position included", async () => {
    routeApi(harness.fetchMock());
    renderShell("/review?panel=layers");
    await mapReady();
    act(() => useMapStore.getState().setCamera({ lng: -1.8263, lat: 51.1788, zoom: 12.5, bearing: 0, pitch: 0 }));
    act(() => useAccountUi.getState().openSignIn());
    const sheet = await screen.findByRole("dialog", { name: "Sign in" });
    const href = within(sheet).getByRole("link", { name: "Continue with Google" }).getAttribute("href") ?? "";
    const url = new URL(href, "http://localhost");
    expect(url.pathname).toBe("/api/v1/auth/oauth/google/start");
    const next = url.searchParams.get("next") ?? "";
    expect(next).toMatch(/^\/review\?panel=layers#m=12\.5\/51\.1788\/-1\.8263\/0\/0/);
  });

  it("signs in through the development sign-in when /meta offers it", async () => {
    const routes = routeApi(harness.fetchMock(), {
      "GET /meta": () => metaResponse({ ...metaFixture, auth: { ...metaFixture.auth, dev_login: true } }),
      "POST /auth/dev-login": (call) =>
        json({ ...(call.body as object), display_name: "Dev", role: "member", needs_welcome: false }),
    });
    renderShell("/");
    const sheet = await openSheet();
    const field = within(sheet).getByLabelText("Development sign-in");
    await userEvent.clear(field);
    await userEvent.type(field, "Tester");
    await userEvent.click(within(sheet).getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(routes.callsTo("POST /auth/dev-login")[0]?.body).toEqual({ handle: "Tester" });
  });

  it("says why there is no way to sign in when /meta enables none", async () => {
    const none = {
      ...metaFixture,
      auth: { providers: metaFixture.auth.providers.map((p) => ({ ...p, enabled: false })) },
    };
    routeApi(harness.fetchMock(), { "GET /meta": () => metaResponse(none) });
    renderShell("/");
    const sheet = await openSheet();
    expect(within(sheet).getByText("Signing in isn't available right now")).toBeInTheDocument();
  });
});

describe("email me a link", () => {
  async function askForLink(answer: () => Response) {
    const routes = routeApi(harness.fetchMock(), { "POST /auth/email/start": answer });
    renderShell("/f/abc");
    const sheet = await openSheet();
    await userEvent.click(within(sheet).getByRole("button", { name: "Email me a link" }));
    await userEvent.type(within(sheet).getByLabelText("Email address"), "ann@example.org");
    await userEvent.click(within(sheet).getByRole("button", { name: "Email me a link" }));
    return { routes, sheet };
  }

  it("posts the address and where to come back to, then says to check the inbox", async () => {
    const { routes, sheet } = await askForLink(() => json({ status: "sent", message: "x" }, 202));
    expect(await within(sheet).findByText("Check your inbox")).toBeInTheDocument();
    const call = routes.callsTo("POST /auth/email/start")[0];
    expect(call?.body).toMatchObject({ email: "ann@example.org", next: expect.stringMatching(/^\/f\/abc#m=/) });
    expect(call?.headers.get("X-FieldClub-Client")).toBe("web");
  });

  it("checks the address before sending anything", async () => {
    const routes = routeApi(harness.fetchMock());
    renderShell("/");
    const sheet = await openSheet();
    await userEvent.click(within(sheet).getByRole("button", { name: "Email me a link" }));
    await userEvent.type(within(sheet).getByLabelText("Email address"), "not an address");
    await userEvent.click(within(sheet).getByRole("button", { name: "Email me a link" }));
    expect(within(sheet).getByRole("alert")).toHaveTextContent("Enter your email address");
    expect(routes.callsTo("POST /auth/email/start")).toEqual([]);
  });

  it("says when too many links have been asked for", async () => {
    const { sheet } = await askForLink(() => apiError(429, "rate_limited", "Slow down."));
    expect(await within(sheet).findByRole("alert")).toHaveTextContent("You've asked for several links recently");
  });
});

describe("a failed provider sign-in", () => {
  it.each(Object.keys(SIGNIN_ERROR_MESSAGES))(
    "explains %s in the sheet and takes it out of the address",
    async (code) => {
      routeApi(harness.fetchMock());
      renderShell(`/f/abc?panel=layers&signin_error=${code}`, <Address />);
      const sheet = await screen.findByRole("dialog", { name: "Sign in" });
      const message = SIGNIN_ERROR_MESSAGES[code];
      expect(within(sheet).getByRole("alert")).toHaveTextContent(message?.title ?? "");
      await waitFor(() => expect(screen.getByTestId("address").textContent).toMatch(/^\/f\/abc\?panel=layers#m=/));
      // The providers are right there to try again.
      expect(within(sheet).getByText("Continue with Google")).toBeInTheDocument();
    },
  );

  it("gives a general message for an unknown code and never shows the parameter", async () => {
    routeApi(harness.fetchMock());
    renderShell("/?signin_error=%3Cimg%20src%3Dx%3EYou%20won%20a%20prize", <Address />);
    const sheet = await screen.findByRole("dialog", { name: "Sign in" });
    expect(within(sheet).getByRole("alert")).toHaveTextContent("Signing in didn't work");
    expect(document.body.textContent).not.toContain("prize");
    await waitFor(() => expect(screen.getByTestId("address").textContent).not.toContain("signin_error"));
  });
});
