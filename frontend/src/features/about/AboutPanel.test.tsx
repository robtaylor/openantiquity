import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Meta } from "../../api/meta.js";
import { apiError, routeApi } from "../../test/apiRoutes.js";
import { useFakeEventSource } from "../../test/fakeEventSource.js";
import { liveSourceFixture } from "../../test/fixtures/about.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { json, mapReady, renderShell, setUpShellTests } from "../../test/shellHarness.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

beforeEach(() => {
  useFakeEventSource();
});

function serve(meta: Meta = metaFixture, live: () => Response = () => json({ items: [liveSourceFixture()] })) {
  return routeApi(harness.fetchMock(), {
    "GET /meta": () => json(meta),
    "GET /context/live-sources": live,
  });
}

async function openPanel(path: string, title: string) {
  renderShell(path);
  await mapReady();
  return within(await screen.findByRole("complementary", { name: title }));
}

describe("the about page", () => {
  it("says what OpenAntiquity is, that it is free, how sites are protected, and who can join", async () => {
    serve();
    const panel = await openPanel("/about", "About OpenAntiquity");
    expect(panel.getByText(/a shared map for finding and checking/)).toBeInTheDocument();
    expect(panel.getByText(/free and non-commercial/)).toBeInTheDocument();
    expect(panel.getByText(metaFixture.notices.sensitivity)).toBeInTheDocument();
    expect(panel.getByText(/Contributors are 16 or over\./)).toBeInTheDocument();
    expect(panel.getByText(/There are no private messages, because/)).toBeInTheDocument();
    expect(panel.getByText(/the address that will be given here before OpenAntiquity opens/)).toBeInTheDocument();
    for (const title of ["Contributor terms", "Privacy notice", "Reporting something"]) {
      expect(panel.getByRole("link", { name: new RegExp(title) })).toBeInTheDocument();
    }
  });

  it("gives the contact address from /meta as a link", async () => {
    serve({ ...metaFixture, app: { ...metaFixture.app, contact: "hello@fieldclub.example" } });
    const panel = await openPanel("/about", "About OpenAntiquity");
    expect(panel.getByRole("link", { name: "hello@fieldclub.example" })).toHaveAttribute(
      "href",
      "mailto:hello@fieldclub.example",
    );
  });

  it("links to the source and the issue tracker, each in another tab", async () => {
    serve();
    const panel = await openPanel("/about", "About OpenAntiquity");
    for (const [name, href] of [
      ["the source code", "https://github.com/robtaylor/openantiquity"],
      ["the list of known problems", "https://github.com/robtaylor/openantiquity/issues"],
    ] as const) {
      const link = panel.getByRole("link", { name });
      expect(link).toHaveAttribute("href", href);
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
  });

  it("gives the commit the running build was made from beside the version", async () => {
    const commit = "0123456789abcdef0123456789abcdef01234567";
    serve({ ...metaFixture, app: { ...metaFixture.app, commit } });
    const panel = await openPanel("/about", "About OpenAntiquity");
    expect(panel.getByText("Version 0.1.0, commit 0123456")).toBeInTheDocument();
  });

  it("gives the version alone when the server can't tell its commit", async () => {
    serve({ ...metaFixture, app: { ...metaFixture.app, commit: null } });
    const panel = await openPanel("/about", "About OpenAntiquity");
    expect(panel.getByText("Version 0.1.0")).toBeInTheDocument();
  });

  it("credits every source the API lists, grouped, and finds them by search", async () => {
    const routes = serve();
    const user = userEvent.setup();
    const panel = await openPanel("/about", "About OpenAntiquity");
    expect(await panel.findByText("Looked up from your browser", { exact: false })).toBeInTheDocument();
    expect(routes.callsTo("GET /context/live-sources")).toHaveLength(1);
    expect(panel.getByText("Map layers", { exact: false })).toBeInTheDocument();
    expect(panel.getByText("Designations", { exact: false })).toBeInTheDocument();

    await user.type(panel.getByRole("searchbox", { name: "Search the sources" }), "wiltshire");
    await waitFor(() => expect(panel.getByRole("status", { name: "" })).toHaveTextContent("1 of"));
    expect(panel.getByText("Wiltshire and Swindon HER")).toBeVisible();
    expect(panel.queryByText("Scheduled monuments in England")).toBeNull();

    await user.clear(panel.getByRole("searchbox", { name: "Search the sources" }));
    await user.type(panel.getByRole("searchbox", { name: "Search the sources" }), "zzzz");
    expect(await panel.findByText("Nothing matches “zzzz”.")).toBeInTheDocument();
    await user.click(panel.getByRole("button", { name: "Clear the search" }));
    expect(panel.getByRole("searchbox", { name: "Search the sources" })).toHaveValue("");
  });

  it("says when the browser's own sources didn't load, and tries again", async () => {
    let fail = true;
    serve(metaFixture, () => (fail ? apiError(500, "server_error") : json({ items: [liveSourceFixture()] })));
    const user = userEvent.setup();
    const panel = await openPanel("/about", "About OpenAntiquity");
    expect(await panel.findByText(/didn't load/, {}, { timeout: 4000 })).toBeInTheDocument();
    expect(panel.getByText("Map layers", { exact: false })).toBeInTheDocument();
    fail = false;
    await user.click(panel.getByRole("button", { name: "Try again" }));
    expect(await panel.findByText("Looked up from your browser", { exact: false })).toBeInTheDocument();
  });
});

describe("the notices", () => {
  it("opens the terms from the address the welcome sheet links to, marked as a draft", async () => {
    serve();
    const panel = await openPanel("/about#terms", "Contributor terms");
    expect(panel.getByRole("note")).toHaveTextContent("Draft");
    expect(document.getElementById("terms")).not.toBeNull();
    expect(panel.getByText(/must be 16 or over/)).toBeInTheDocument();
    expect(panel.getByRole("link", { name: "CC BY 4.0 licence" })).toHaveAttribute(
      "href",
      "https://creativecommons.org/licenses/by/4.0/",
    );
  });

  it("lists each report reason from /meta, with the deadline the law sets", async () => {
    serve();
    const panel = await openPanel("/about/reporting", "Reporting something");
    for (const reason of metaFixture.vocab.report_reasons) {
      expect(panel.getByText(`${reason.label}.`)).toBeInTheDocument();
    }
    const due = metaFixture.vocab.report_reasons.find((reason) => reason.due_hours);
    expect(due).toBeDefined();
    expect(panel.getAllByText(new RegExp(`within ${due?.due_hours} hours`)).length).toBeGreaterThan(0);
  });

  it("says in the privacy notice what the server logs with each request's number, and what a report sends", async () => {
    serve();
    const panel = await openPanel("/about/privacy", "Privacy notice");
    expect(panel.getByText(/Each request is given a random number/)).toBeInTheDocument();
    expect(panel.getByText(/Our host, Fly\.io, says it keeps the log for seven days/)).toBeInTheDocument();
    expect(panel.getByText(/It isn't only a list of requests/)).toBeInTheDocument();
    expect(panel.getByText(/some of them name an account/)).toBeInTheDocument();
    expect(panel.getByText(/the words of an error the page didn't catch/)).toBeInTheDocument();
    expect(panel.getByText(/the one-kilometre square the map was centred on/)).toBeInTheDocument();
    expect(panel.getByText(/sent nowhere unless you use "Report a problem"/)).toBeInTheDocument();
  });

  it("says in the privacy notice what is kept, including the age band and the email from a provider", async () => {
    serve();
    const panel = await openPanel("/about/privacy", "Privacy notice");
    expect(panel.getByText(/Your age band \(16 or 17, or 18 and over\)/)).toBeInTheDocument();
    expect(panel.getByText(/Most providers tell us an email address/)).toBeInTheDocument();
    // Only the providers /meta offers, never a hard-coded list.
    expect(panel.getByText(/From the sign-in provider \(Google or OpenStreetMap\)/)).toBeInTheDocument();
    expect(panel.queryByText(/Apple|Microsoft|Facebook/)).toBeNull();
    expect(panel.getByText(/can't be read back without it/)).toBeInTheDocument();
    expect(panel.getByRole("note")).toHaveTextContent("Draft");
  });

  it.each([
    ["/about/privacy", "Privacy notice"],
    ["/about/terms", "Contributor terms"],
  ])("opens %s with what matters most, and keeps the detail closed until asked for", async (path, title) => {
    serve();
    const user = userEvent.setup();
    const panel = await openPanel(path, title);
    const short = within(panel.getByRole("region", { name: "In short" }));
    expect(short.getAllByRole("listitem")).toHaveLength(5);
    const parts = panel.getAllByRole("group");
    expect(parts.length).toBeGreaterThan(3);
    for (const part of parts) expect(part).not.toHaveAttribute("open");
    const first = parts[0] as HTMLElement;
    await user.click(first.querySelector("summary") as HTMLElement);
    expect(first).toHaveAttribute("open");
  });

  it("follows the minimum age, providers and licence /meta gives, and says the contact address only once", async () => {
    serve({
      ...metaFixture,
      app: { ...metaFixture.app, contribution_licence: "CC BY-SA 4.0" },
      auth: {
        ...metaFixture.auth,
        age_bands: ["18_plus"],
        providers: metaFixture.auth.providers.map((provider) => ({ ...provider, enabled: provider.id === "email" })),
      },
    });
    const panel = await openPanel("/about/privacy", "Privacy notice");
    expect(panel.getByText(/Your age band \(18 and over\)/)).toBeInTheDocument();
    expect(panel.queryByText(/16 and 17 year olds/)).toBeNull();
    expect(panel.queryByText(/From the sign-in provider/)).toBeNull();
    expect(panel.getByText(/If you ask for an emailed link: your email address/)).toBeInTheDocument();
    // The address isn't given yet: the notice points to the about page, which says so once.
    expect(panel.queryByText(/the address that will be given here/)).toBeNull();
    expect(panel.getAllByRole("link", { name: "about page" })[0]).toHaveAttribute("href", "/about");
  });

  it("explains how anyone asks for something to be taken down, and links the other notices", async () => {
    serve();
    const panel = await openPanel("/about/takedown", "Asking for something to be taken down");
    expect(panel.getByText(/within 48 hours of the report/)).toBeInTheDocument();
    // Whoever added a mention can remove it from the finding's page, as they can a comment or evidence.
    expect(
      panel.getByText(/delete your own comments, evidence and mentions from a finding's page/),
    ).toBeInTheDocument();
    const others = within(panel.getByRole("navigation", { name: "The other notices" }));
    expect(others.getByRole("link", { name: "Privacy notice" })).toHaveAttribute("href", "/about/privacy");
    expect(others.getByRole("link", { name: "About OpenAntiquity" })).toHaveAttribute("href", "/about");
  });

  it("says there is nothing at a notice that doesn't exist", async () => {
    serve();
    renderShell("/about/cookies");
    await mapReady();
    expect(await screen.findByRole("complementary", { name: "Page not found" })).toBeInTheDocument();
  });
});
