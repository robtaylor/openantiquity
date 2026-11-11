import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { pageFixture, suggestionsFixture } from "../../test/fixtures/findingPage.js";
import { meFixture } from "../../test/fixtures/me.js";
import { mentionFixture, paperMentionFixture, previewFixture } from "../../test/fixtures/mentions.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import type { Me } from "../account/api.js";
import { useAccountUi } from "../account/requireAccount.js";
import { resetDraftsForTests } from "../drafts/store.js";
import type { FindingDetail } from "../finding/types.js";
import type { Mention } from "./types.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

// Not the fixtures' `OTHER`, who added the mentions the page already holds.
const MEMBER = meFixture({ handle: "BrightBank3", display_name: "Gertrude Bell" });
const PATH = "/findings/f-ring/mentions";

beforeEach(() => {
  useAccountUi.setState({ sheet: null, waiting: [] });
  localStorage.clear();
  resetDraftsForTests();
});

function serve(finding: FindingDetail, mentions: Mention[], me: Me | null = MEMBER): ApiRoutes {
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : signedOutResponse()),
    "GET /findings/f-ring": () => json(finding),
    "GET /findings/f-ring/comments": () => json({ items: [], next_cursor: null }),
    "GET /findings/f-ring/suggested-records": () => json(suggestionsFixture([])),
    [`GET ${PATH}`]: () => json({ items: mentions, next_cursor: null }),
  });
}

async function open(routes: ApiRoutes, finding = pageFixture()) {
  void routes;
  renderShell(`/f/${finding.public_id}`);
  await mapReady();
  const panel = within(await screen.findByRole("complementary", { name: finding.title }));
  const section = within(await panel.findByRole("region", { name: "Mentions" }));
  return { panel, section };
}

describe("the mentions on a finding's page", () => {
  it("lists each with its title linked at its start time, what it is, who made it and who added it", async () => {
    const { section } = await open(
      serve(pageFixture(), [mentionFixture(), paperMentionFixture({ auto_detected: false })]),
    );
    const list = within(await section.findByRole("list", { name: "Mentions of this finding" }));
    const [video, paper] = list.getAllByRole("article");
    const link = within(video as HTMLElement).getByRole("link", { name: /Barrows of the Marlborough Downs/ });
    expect(link).toHaveAttribute("href", "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=754s");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
    expect(
      within(video as HTMLElement).getByText("Video · Downland Walks · 28 October 2026 · from 12:34"),
    ).toBeVisible();
    expect(within(video as HTMLElement).getByText("Added by Mary Anning on 6 November 2026")).toBeVisible();
    // The picture is fetched without telling its host which page asked.
    const picture = (video as HTMLElement).querySelector("img");
    expect(picture).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(picture).toHaveAttribute("src", "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg");
    // A paper has no picture, so it gets a placeholder.
    expect((paper as HTMLElement).querySelector("img")).toBeNull();
    expect((paper as HTMLElement).querySelector(".fc-mention__thumb--none")).not.toBeNull();
    expect(within(paper as HTMLElement).getByRole("link")).toHaveAttribute("href", "https://doi.org/10.5284/1040209");
  });

  it("marks those the channel scan found as found automatically", async () => {
    const { section } = await open(serve(pageFixture(), [mentionFixture({ auto_detected: true, added_by: null })]));
    expect(await section.findByText(/Found automatically/)).toBeVisible();
    expect(section.queryByText(/Added by/)).toBeNull();
  });

  it("says what to do when there are none, and links to the recent mentions everywhere", async () => {
    const { section } = await open(serve(pageFixture(), []));
    expect(await section.findByText(/Nobody has said where it was talked about yet/)).toBeVisible();
    expect(section.getByRole("link", { name: "Recent mentions everywhere" })).toHaveAttribute("href", "/mentions");
  });

  it("says when they couldn't be loaded, and tries again", async () => {
    const routes = serve(pageFixture(), []);
    let fail = true;
    routes.on(`GET ${PATH}`, () =>
      fail
        ? apiError(503, "unavailable", "The server is busy.")
        : json({ items: [mentionFixture()], next_cursor: null }),
    );
    const { section } = await open(routes);
    expect(await section.findByRole("alert")).toHaveTextContent("The mentions couldn't be loaded. The server is busy.");
    fail = false;
    await userEvent.setup().click(section.getByRole("button", { name: "Try again" }));
    expect(await section.findByRole("link", { name: /Barrows of the Marlborough Downs/ })).toBeVisible();
  });

  it("tells the person who added a hidden mention that only they and moderators still see it", async () => {
    const mine = { handle: MEMBER.handle, display_name: MEMBER.display_name, role: "member" };
    const { section } = await open(serve(pageFixture(), [mentionFixture({ added_by: mine, hidden: true })]));
    expect(await section.findByText(/Only you and moderators can still see it/)).toBeVisible();
  });
});

describe("adding a mention", () => {
  async function lookUp(section: ReturnType<typeof within>, address: string) {
    const user = userEvent.setup();
    await user.click(await section.findByRole("button", { name: "Add a mention" }));
    // The form opens at the address.
    expect(section.getByRole("textbox", { name: "Address" })).toHaveFocus();
    await user.type(section.getByLabelText("Address"), address);
    await user.click(section.getByRole("button", { name: "Look it up" }));
    return user;
  }

  it("shows what was found before saving, then shows the mention at once", async () => {
    const routes = serve(pageFixture(), [paperMentionFixture()]);
    routes.on("POST /mentions/preview", () => json(previewFixture()));
    let answer: (response: Response) => void = () => {};
    routes.on(
      "POST /findings/f-ring/mentions",
      () =>
        new Promise<Response>((resolve) => {
          answer = resolve;
        }),
    );
    const { section } = await open(routes);
    const user = await lookUp(section, "https://youtu.be/dQw4w9WgXcQ?t=754");
    expect(routes.callsTo("POST /mentions/preview")[0]?.body).toEqual({ url: "https://youtu.be/dQw4w9WgXcQ?t=754" });

    const form = within(await section.findByRole("form", { name: "Add a mention" }));
    expect(section.getByRole("link", { name: /Barrows of the Marlborough Downs/ })).toBeVisible();
    // The kind it looks like is chosen, and the start time in the link is filled in.
    expect(form.getByRole("radio", { name: "Video" })).toHaveAttribute("aria-checked", "true");
    expect(form.getByLabelText("Where it comes up (optional)")).toHaveValue("12:34");
    // What was found takes focus, so it is read out next.
    await waitFor(() => expect(document.activeElement).toHaveClass("fc-mention-add__result"));
    await user.type(form.getByLabelText("Note (optional)"), "The ring ditch is at the start.");
    await user.click(form.getByRole("button", { name: "Save the mention" }));

    expect(routes.callsTo("POST /findings/f-ring/mentions")[0]?.body).toEqual({
      url: "https://youtu.be/dQw4w9WgXcQ?t=754",
      kind: "video",
      start_seconds: 754,
      note: "The ring ditch is at the start.",
    });
    // Shown at once, newest first, while it is saved. The form stays where it was, busy, with focus kept on it.
    const list = within(section.getByRole("list", { name: "Mentions of this finding" }));
    const [first] = list.getAllByRole("article");
    expect(first).toHaveAttribute("aria-busy", "true");
    expect(within(first as HTMLElement).getByText("Saving…")).toBeVisible();
    const busy = form.getByRole("button", { name: "Saving…" });
    expect(busy).toBeVisible();
    expect(busy).toHaveFocus();
    expect(busy).toHaveAttribute("aria-disabled", "true");

    act(() =>
      answer(
        json(
          mentionFixture({ id: 9, note: "The ring ditch is at the start.", added_by: { ...MEMBER, role: "member" } }),
          201,
        ),
      ),
    );
    await waitFor(() => expect(list.getAllByRole("article")[0]).not.toHaveAttribute("aria-busy"));
    expect(section.getByText("The ring ditch is at the start.")).toBeVisible();
    expect(section.getByRole("button", { name: "Remove Barrows of the Marlborough Downs" })).toBeVisible();
    expect(section.getByRole("button", { name: "Add a mention" })).toBeVisible();
    // The saved mention takes focus where it is, and the change is said.
    await waitFor(() => expect(list.getAllByRole("listitem")[0]).toHaveFocus());
    expect(section.getByRole("status")).toHaveTextContent("Your mention is added, at the top of the list.");
  });

  it("takes away the last failure's toast when the person tries again", async () => {
    const routes = serve(pageFixture(), []);
    routes.on("POST /mentions/preview", () => json(previewFixture()));
    let fail = true;
    routes.on("POST /findings/f-ring/mentions", () =>
      fail ? apiError(503, "unavailable", "The server is busy.") : json(mentionFixture({ id: 9 }), 201),
    );
    const { section } = await open(routes);
    const user = await lookUp(section, "https://youtu.be/dQw4w9WgXcQ");
    await user.click(await section.findByRole("button", { name: "Save the mention" }));
    expect(await screen.findByText(/Your mention couldn't be added\./)).toBeInTheDocument();
    fail = false;
    await user.click(section.getByRole("button", { name: "Save the mention" }));
    expect(await section.findByRole("link", { name: /Barrows of the Marlborough Downs/ })).toBeVisible();
    expect(screen.queryByText(/Your mention couldn't be added\./)).toBeNull();
  });

  it("forgets what the last address found once a different one is typed", async () => {
    const routes = serve(pageFixture(), []);
    routes.on("POST /mentions/preview", (call) =>
      (call.body as { url: string }).url.includes("youtu")
        ? json(previewFixture())
        : apiError(503, "unavailable", "The server is busy."),
    );
    const { section } = await open(routes);
    const user = await lookUp(section, "https://youtu.be/dQw4w9WgXcQ?t=754");
    const form = within(await section.findByRole("form", { name: "Add a mention" }));
    expect(form.getByRole("radio", { name: "Video" })).toHaveAttribute("aria-checked", "true");
    const address = section.getByLabelText("Address");
    await user.clear(address);
    await user.type(address, "https://example.org/a");
    await user.click(section.getByRole("button", { name: "Look it up" }));
    expect(await section.findByText(/Its details couldn't be looked up\./)).toBeVisible();
    const again = within(section.getByRole("form", { name: "Add a mention" }));
    expect(again.queryByRole("radio", { checked: true })).toBeNull();
    expect(again.getByLabelText("Where it comes up (optional)")).toHaveValue("");
  });

  it("says plainly when nothing could be fetched, and saves the address alone", async () => {
    const routes = serve(pageFixture(), []);
    routes.on("POST /mentions/preview", () =>
      json(
        previewFixture({
          url: "https://news.example.org/barrows",
          canonical_url: "https://news.example.org/barrows",
          kind: "article",
          provider: "news.example.org",
          fetch_status: "failed",
          title: null,
          author_name: null,
          thumbnail_url: null,
          start_seconds: null,
          published_at: null,
        }),
      ),
    );
    routes.on("POST /findings/f-ring/mentions", () =>
      json(
        mentionFixture({
          id: 5,
          kind: "article",
          url: "https://news.example.org/barrows",
          canonical_url: "https://news.example.org/barrows",
          title: null,
          author_name: null,
          thumbnail_url: null,
          start_seconds: null,
          note: null,
          published_at: null,
        }),
        201,
      ),
    );
    const { section } = await open(routes);
    const user = await lookUp(section, "news.example.org/barrows");
    expect(
      await section.findByText(/couldn't get its title\. You can still save it with its address alone\./),
    ).toBeVisible();
    await user.click(section.getByRole("button", { name: "Save the mention" }));
    expect(await section.findByRole("link", { name: /news\.example\.org\/barrows/ })).toBeVisible();
    expect(routes.callsTo("POST /findings/f-ring/mentions")[0]?.body).toEqual({
      url: "news.example.org/barrows",
      kind: "article",
    });
  });

  it("still offers saving when the lookup itself fails", async () => {
    const routes = serve(pageFixture(), []);
    routes.on("POST /mentions/preview", () => apiError(429, "rate_limited", "Too many."));
    const { section } = await open(routes);
    await lookUp(section, "https://example.org/a");
    expect(await section.findByText(/Its details couldn't be looked up\./)).toHaveTextContent(
      /Try again a little later\. You can still save it with its address alone\./,
    );
    expect(section.getByRole("button", { name: "Save the mention" })).toBeEnabled();
  });

  it("says beside the address when it isn't one that can be linked to, and offers no save", async () => {
    const routes = serve(pageFixture(), []);
    routes.on("POST /mentions/preview", () => apiError(422, "invalid_address", "Bad."));
    const { section } = await open(routes);
    await lookUp(section, "not a link");
    expect(await section.findByText("That isn't a web address or a DOI we can link to.")).toBeVisible();
    expect(section.getByLabelText("Address")).toHaveAttribute("aria-invalid", "true");
    expect(section.queryByRole("button", { name: "Save the mention" })).toBeNull();
  });

  it.each([
    ["mention_exists", 409, "That's already listed on this finding.", "Address"],
    [
      "mention_hidden",
      409,
      "A moderator has hidden that address on this finding, so it can't be added again.",
      "Address",
    ],
    ["finding_withdrawn", 409, "This finding has been withdrawn, so it takes no more mentions.", null],
  ])("takes it back with a toast when the server says %s, and keeps the form", async (code, status, words, field) => {
    const routes = serve(pageFixture(), []);
    routes.on("POST /mentions/preview", () => json(previewFixture()));
    routes.on("POST /findings/f-ring/mentions", () => apiError(status, code, "server words"));
    const { section } = await open(routes);
    const user = await lookUp(section, "https://youtu.be/dQw4w9WgXcQ");
    await user.click(await section.findByRole("button", { name: "Save the mention" }));
    expect(await screen.findByText(`Your mention couldn't be added. ${words}`)).toBeInTheDocument();
    expect(section.queryByRole("list", { name: "Mentions of this finding" })).toBeNull();
    expect(section.getByLabelText("Address")).toHaveValue("https://youtu.be/dQw4w9WgXcQ");
    if (field) expect(section.getByLabelText(field)).toHaveAttribute("aria-invalid", "true");
    else expect(section.getByRole("alert")).toHaveTextContent(words);
  });

  it("refuses a start time that isn't one, before sending anything", async () => {
    const routes = serve(pageFixture(), []);
    routes.on("POST /mentions/preview", () => json(previewFixture({ start_seconds: null })));
    const { section } = await open(routes);
    const user = await lookUp(section, "https://youtu.be/dQw4w9WgXcQ");
    await user.type(await section.findByLabelText("Where it comes up (optional)"), "soon");
    await user.click(section.getByRole("button", { name: "Save the mention" }));
    expect(section.getByText("Write the time as minutes and seconds, such as 12:34.")).toBeVisible();
    expect(routes.callsTo("POST /findings/f-ring/mentions")).toHaveLength(0);
  });

  it("asks a signed-out visitor to sign in first", async () => {
    const { section } = await open(serve(pageFixture({ actions: signedOutActions() }), [], null));
    await userEvent.setup().click(await section.findByRole("button", { name: "Add a mention" }));
    await waitFor(() => expect(useAccountUi.getState().sheet).toBe("signin"));
    expect(section.queryByLabelText("Address")).toBeNull();
  });

  it("isn't offered on a withdrawn finding", async () => {
    const finding = pageFixture({
      assessment: { ...pageFixture().assessment, state: "withdrawn" },
    });
    const { section } = await open(serve(finding, [mentionFixture()]));
    expect(await section.findByRole("link", { name: /Barrows/ })).toBeVisible();
    expect(section.queryByRole("button", { name: "Add a mention" })).toBeNull();
  });
});

describe("removing a mention", () => {
  const mine = { handle: MEMBER.handle, display_name: MEMBER.display_name, role: "member" };

  it("is offered only to whoever added it, and takes it away at once", async () => {
    const routes = serve(pageFixture(), [mentionFixture({ id: 3, added_by: mine }), paperMentionFixture()]);
    routes.on("DELETE /mentions/3", () => new Response(null, { status: 204 }));
    const { section } = await open(routes);
    const list = within(await section.findByRole("list", { name: "Mentions of this finding" }));
    // Each button is named for its mention, so a list of the page's buttons tells them apart.
    expect(list.getAllByRole("button", { name: /^Remove/ })).toHaveLength(1);
    await userEvent.setup().click(list.getByRole("button", { name: "Remove Barrows of the Marlborough Downs" }));
    expect(list.getAllByRole("article")).toHaveLength(1);
    expect(routes.callsTo("DELETE /mentions/3")).toHaveLength(1);
    // Focus goes to the mention that took its place, not to the top of the page.
    expect(list.getByRole("listitem")).toHaveFocus();
    expect(section.getByRole("status")).toHaveTextContent("The mention is removed.");
  });

  it("puts it back with a toast when the server refuses", async () => {
    const routes = serve(pageFixture(), [mentionFixture({ id: 3, added_by: mine })]);
    routes.on("DELETE /mentions/3", () => apiError(403, "mention_forbidden", "No."));
    const { section } = await open(routes);
    await userEvent.setup().click(await section.findByRole("button", { name: /^Remove/ }));
    expect(
      await screen.findByText("That mention couldn't be removed. Only the person who added a mention can remove it."),
    ).toBeInTheDocument();
    expect(section.getByRole("link", { name: /Barrows/ })).toBeVisible();
  });
});

function signedOutActions(): FindingDetail["actions"] {
  return Object.fromEntries(
    Object.keys(pageFixture().actions).map((name) => [name, { allowed: false, reason: "unauthorised" }]),
  ) as FindingDetail["actions"];
}
