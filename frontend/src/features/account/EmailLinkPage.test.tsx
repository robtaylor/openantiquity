import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { StrictMode } from "react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { meFixture } from "../../test/fixtures/me.js";
import { json, setUpShellTests } from "../../test/shellHarness.js";
import { listAllDrafts, noteSignInStarted, putDraft, resetDraftsForTests } from "../drafts/store.js";
import { Shell } from "../shell/Shell.js";
import { captureEmailLinkToken, emailLinkToken, resetEmailLinkForTests } from "./emailLink.js";
import { useAccountUi } from "./requireAccount.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();
const TOKEN = "s3cret-token-from-the-email";

beforeEach(() => {
  useAccountUi.setState(useAccountUi.getInitialState(), true);
  resetEmailLinkForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetDraftsForTests();
});

afterEach(() => {
  resetEmailLinkForTests();
});

function Address() {
  const location = useLocation();
  return <output data-testid="address">{`${location.pathname}${location.search}`}</output>;
}

/**
 * Open the link page as a browser would: the address bar has the fragment,
 * `main.tsx` captures it before the first render, and React runs in strict mode.
 */
function openLink(search = "?next=%2Ff%2Fabc", fragment = `#token=${TOKEN}`, { capture = true } = {}) {
  window.history.replaceState(null, "", `/signin/email${search}${fragment}`);
  if (capture) captureEmailLinkToken();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[`/signin/email${search}`]}>
          <Shell />
          <Address />
        </MemoryRouter>
      </QueryClientProvider>
    </StrictMode>,
  );
}

/** What verify answers for a link opened in the browser that asked for it. */
function signedInHere() {
  return { ...meFixture(), asked_here: true };
}

function verifyCalls(routes: ApiRoutes) {
  return routes.callsTo("POST /auth/email/verify");
}

/** The token went nowhere but the exchange. */
function expectTokenOnlyInExchange(routes: ApiRoutes): void {
  for (const call of routes.calls) {
    if (call.method === "POST" && call.path === "/auth/email/verify") continue;
    expect(call.url.href).not.toContain(TOKEN);
    expect(JSON.stringify(call.body ?? null)).not.toContain(TOKEN);
  }
  expect(JSON.stringify({ ...window.localStorage })).not.toContain(TOKEN);
  expect(JSON.stringify({ ...window.sessionStorage })).not.toContain(TOKEN);
  expect(window.location.href).not.toContain(TOKEN);
}

describe("captureEmailLinkToken", () => {
  it.each(["/signin/email/", "/SIGNIN/Email", "/Signin/email//"])(
    "keeps the token on %s, which the router shows the link page at",
    (path) => {
      window.history.replaceState(null, "", `${path}?next=%2F#token=${TOKEN}`);
      captureEmailLinkToken();
      expect(window.location.hash).toBe("");
      expect(emailLinkToken()).toBe(TOKEN);
    },
  );

  it("takes a token out of the address on any other page, without keeping it", () => {
    window.history.replaceState(null, "", `/signin//email#token=${TOKEN}`);
    captureEmailLinkToken();
    expect(window.location.href).not.toContain(TOKEN);
    expect(emailLinkToken()).toBeNull();
  });

  it("leaves another page's fragment alone, such as the map's position", () => {
    window.history.replaceState(null, "", "/#m=13/51.4/-1.85");
    captureEmailLinkToken();
    expect(window.location.hash).toBe("#m=13/51.4/-1.85");
  });
});

describe("the emailed link page", () => {
  it("takes the token out of the address, exchanges it once, and goes on to next", async () => {
    const routes = routeApi(harness.fetchMock(), { "POST /auth/email/verify": () => json(signedInHere()) });
    openLink();
    expect(window.location.hash).toBe("");
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/f\/abc$/));
    expect(verifyCalls(routes)).toHaveLength(1);
    expect(verifyCalls(routes)[0]?.body).toEqual({ token: TOKEN });
    expect(verifyCalls(routes)[0]?.headers.get("X-OpenAntiquity-Client")).toBe("web");
    // Signed in everywhere at once.
    expect(await screen.findByTestId("account-avatar")).toBeInTheDocument();
    expectTokenOnlyInExchange(routes);
  });

  it("takes the token itself if nothing did before it rendered", async () => {
    const routes = routeApi(harness.fetchMock(), { "POST /auth/email/verify": () => json(signedInHere()) });
    openLink(undefined, undefined, { capture: false });
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/f\/abc$/));
    expect(verifyCalls(routes)[0]?.body).toEqual({ token: TOKEN });
    expect(window.location.hash).not.toContain(TOKEN);
  });

  it.each([
    ["another origin", "https://evil.example/"],
    ["scheme-relative", "//evil.example"],
    ["a backslash", "/\\evil.example"],
    ["javascript:", "javascript:alert(1)"],
  ])("stays on the site when next is %s", async (_label, next) => {
    routeApi(harness.fetchMock(), { "POST /auth/email/verify": () => json(signedInHere()) });
    openLink(`?next=${encodeURIComponent(next)}`);
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/$/));
    expect(window.location.origin).toBe("http://localhost:3000");
  });

  it("asks for the address of a link from another browser, never fills it in, and sends it only when typed", async () => {
    const routes = routeApi(harness.fetchMock(), {
      "POST /auth/email/verify": (call) => {
        const { email } = call.body as { email?: string };
        if (email === undefined)
          return apiError(409, "confirmation_required", "Confirm the address.", { email: "a***@example.org" });
        return email === "ada@example.org"
          ? json({ ...meFixture(), asked_here: false })
          : apiError(409, "email_mismatch", "That isn't the address this link was sent to.");
      },
    });
    openLink();
    const panel = await screen.findByRole("complementary", { name: "Signing in" });
    expect(
      await within(panel).findByRole("heading", { name: "Which email address is this link for?" }),
    ).toBeInTheDocument();
    // The masked address the server gives isn't shown: a stranger's can look just like yours.
    expect(panel).not.toHaveTextContent("a***@example.org");
    const field = within(panel).getByLabelText("Your email address");
    expect(field).toHaveValue("");
    // Strict mode ran the page twice. Still one request, with no address.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(verifyCalls(routes).map((call) => call.body)).toEqual([{ token: TOKEN }]);

    await userEvent.type(field, "a9z@example.org");
    await userEvent.click(within(panel).getByRole("button", { name: "Sign me in" }));
    expect(await within(panel).findByText(/That isn't the address this link was sent to/)).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Ask for a new link" })).toBeInTheDocument();

    await userEvent.clear(within(panel).getByLabelText("Your email address"));
    await userEvent.type(within(panel).getByLabelText("Your email address"), "ada@example.org");
    await userEvent.click(within(panel).getByRole("button", { name: "Sign me in" }));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/f\/abc$/));
    expect(verifyCalls(routes).map((call) => call.body)).toEqual([
      { token: TOKEN },
      { token: TOKEN, email: "a9z@example.org" },
      { token: TOKEN, email: "ada@example.org" },
    ]);
    expectTokenOnlyInExchange(routes);
  });

  it("sends nothing more when the person says the link isn't theirs", async () => {
    const routes = routeApi(harness.fetchMock(), {
      "POST /auth/email/verify": () =>
        apiError(409, "confirmation_required", "Confirm the address.", { email: "a***@example.org" }),
    });
    openLink();
    const panel = await screen.findByRole("complementary", { name: "Signing in" });
    await userEvent.click(await within(panel).findByRole("button", { name: "It isn't mine" }));
    expect(within(panel).getByRole("heading", { name: "You haven't been signed in" })).toBeInTheDocument();
    expect(verifyCalls(routes)).toHaveLength(1);
  });

  it("takes over this tab's drafts only when this browser asked for the link and this tab began the sign-in", async () => {
    const draft = putDraft("probe", { note: "mine" });
    noteSignInStarted("email");
    routeApi(harness.fetchMock(), { "POST /auth/email/verify": () => json(signedInHere()) });
    openLink();
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/f\/abc$/));
    await waitFor(() => expect(listAllDrafts()[0]?.owner).toEqual({ account: `person:${meFixture().id}` }));
    expect(listAllDrafts().map((each) => each.id)).toEqual([draft.id]);
  });

  it("takes over no draft after a link this browser didn't ask for, whoever began a sign-in here", async () => {
    const draft = putDraft("probe", { note: "mine" });
    noteSignInStarted("email");
    routeApi(harness.fetchMock(), {
      "POST /auth/email/verify": (call) =>
        (call.body as { email?: string }).email
          ? json({ ...meFixture(), asked_here: false })
          : apiError(409, "confirmation_required", "Confirm the address.", { email: "a***@example.org" }),
    });
    openLink();
    const panel = await screen.findByRole("complementary", { name: "Signing in" });
    await userEvent.type(await within(panel).findByLabelText("Your email address"), "ada@example.org");
    await userEvent.click(within(panel).getByRole("button", { name: "Sign me in" }));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/f\/abc$/));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(listAllDrafts()).toEqual([draft]);
  });

  it("explains a used, expired or wrong link, and offers another", async () => {
    routeApi(harness.fetchMock(), {
      "POST /auth/email/verify": () => apiError(400, "link_invalid", "This sign-in link has expired."),
    });
    openLink();
    const panel = await screen.findByRole("complementary", { name: "Signing in" });
    expect(await within(panel).findByRole("heading", { name: "This link can't be used" })).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Ask for a new link" }));
    const sheet = await screen.findByRole("dialog", { name: "Sign in" });
    // The new link goes where the old one would have, not to the front page.
    const google = within(sheet).getByRole("link", { name: /Google/ });
    expect(new URL(google.getAttribute("href") ?? "", "http://x").searchParams.get("next")).toBe("/f/abc");
  });

  it("says so when the link has no token, and asks the server nothing", async () => {
    const routes = routeApi(harness.fetchMock());
    openLink("", "");
    const panel = await screen.findByRole("complementary", { name: "Signing in" });
    expect(within(panel).getByRole("heading", { name: "This link is incomplete" })).toBeInTheDocument();
    expect(verifyCalls(routes)).toEqual([]);
  });

  it("offers to try again when the server can't be reached, with the same token", async () => {
    let fail = true;
    const routes = routeApi(harness.fetchMock(), {
      "POST /auth/email/verify": () =>
        fail ? apiError(503, "unavailable", "The server is restarting.") : json(signedInHere()),
    });
    openLink();
    const panel = await screen.findByRole("complementary", { name: "Signing in" });
    expect(await within(panel).findByText("The server is restarting.")).toBeInTheDocument();
    fail = false;
    await userEvent.click(within(panel).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByTestId("address")).toHaveTextContent(/^\/f\/abc$/));
    expect(verifyCalls(routes).map((call) => call.body)).toEqual([{ token: TOKEN }, { token: TOKEN }]);
  });
});
