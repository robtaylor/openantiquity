import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { useFakeEventSource } from "../../test/fakeEventSource.js";
import { FINDER } from "../../test/fixtures/findingPage.js";
import { findingSummary, findingsData } from "../../test/fixtures/findings.js";
import { meFixture } from "../../test/fixtures/me.js";
import {
  contributionFixture,
  ownProfileFixture,
  pointFixture,
  profileFixture,
  youngProfileFixture,
} from "../../test/fixtures/people.js";
import { json, mapReady, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import type { Me } from "../account/api.js";
import { useAccountUi } from "../account/requireAccount.js";
import type { Profile } from "./api.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

beforeEach(() => {
  useFakeEventSource();
  useAccountUi.setState({ sheet: null, waiting: [] });
});

const FOUND = findingsData.features.slice(0, 2).map((feature) => findingSummary(feature));

function serve(profile: Profile, me: Me | null = null, found = FOUND): ApiRoutes {
  const base = `/users/${profile.handle}`;
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (me ? json(me) : apiError(401, "unauthorised")),
    [`GET ${base}`]: () => json(profile),
    [`GET ${base}/findings`]: () => json({ items: found, next_cursor: null }),
    [`GET ${base}/contributions`]: (call) =>
      json({
        items:
          call.url.searchParams.get("kind") === "second_look"
            ? [contributionFixture({ kind: "second_look", id: null, created_at: null, subkind: null })]
            : [contributionFixture(), contributionFixture({ id: 32, kind: "comment", subkind: null })],
        next_cursor: null,
      }),
    [`GET ${base}/points`]: () =>
      json({ items: [pointFixture(), pointFixture({ id: 6, delta: 1, reason: "known_record" })], next_cursor: null }),
  });
}

async function openProfile(path: string, title: string) {
  renderShell(path);
  await mapReady();
  return within(await screen.findByRole("complementary", { name: title }));
}

describe("a person's page", () => {
  it("shows what someone found and helped with, their role and when they joined", async () => {
    const user = userEvent.setup();
    const routes = serve(profileFixture({ role: "trusted" }));
    const panel = await openProfile("/u/KeenLynchet7", "Mary Anning");
    expect(panel.getByText("@KeenLynchet7")).toBeInTheDocument();
    expect(panel.getByText("Trusted member")).toBeInTheDocument();
    expect(
      panel.getByText("Trusted by a moderator after earning fifty points. Their checks count for more."),
    ).toBeInTheDocument();
    expect(panel.getByText("Joined October 2026")).toBeInTheDocument();
    expect(panel.getByText("Walks the downs most weekends.")).toBeInTheDocument();
    expect(document.title).toBe("Mary Anning · Field Club");

    const found = await panel.findByRole("list", { name: "Findings" });
    expect(within(found).getAllByRole("link")).toHaveLength(2);

    // Nobody else sees their points or second looks, and they aren't asked for.
    expect(panel.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Found", "Helped"]);
    expect(panel.queryByText("12 points")).toBeNull();
    expect(routes.callsTo("GET /users/KeenLynchet7/points")).toHaveLength(0);

    await user.click(panel.getByRole("tab", { name: "Helped" }));
    const helped = await panel.findByRole("list", { name: "Helped with" });
    expect(
      within(helped)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      expect.stringContaining("Added an aerial photo on 5 November 2026"),
      expect.stringContaining("Commented on 5 November 2026"),
    ]);
    expect(routes.callsTo("GET /users/KeenLynchet7/contributions")[0]?.url.searchParams.get("kind")).toBeNull();

    // There is no way to contact them, only to report them.
    expect(panel.getByText(/no private messages/)).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Report this person" })).toBeInTheDocument();
  });

  it("shows an account aged 16 or 17 by its handle alone, without looking broken", async () => {
    serve(youngProfileFixture(), null, []);
    const panel = await openProfile("/u/BrightCairn7", "BrightCairn7");
    // The handle is the name, so it isn't said twice, and there is no bio.
    expect(panel.queryByText("@BrightCairn7")).toBeNull();
    expect(panel.getByRole("img", { name: "BrightCairn7" })).toHaveTextContent("BC");
    expect(await panel.findByText("Nothing they've marked is on the map for you to see.")).toBeInTheDocument();
    expect(panel.getByText("Member")).toBeInTheDocument();
  });

  it("shows the person their own points and second looks, which nobody else sees", async () => {
    const user = userEvent.setup();
    const me = meFixture({ handle: FINDER.handle, display_name: FINDER.display_name });
    const routes = serve(ownProfileFixture(), me);
    const panel = await openProfile(`/u/${FINDER.handle}`, FINDER.display_name);
    expect(panel.getByText(/This is your page as others see it/)).toBeInTheDocument();
    expect(panel.queryByRole("button", { name: "Report this person" })).toBeNull();

    await user.click(panel.getByRole("tab", { name: "Second looks" }));
    const looks = await panel.findByRole("list", { name: "Second looks" });
    expect(within(looks).getByText("You took a second look")).toBeInTheDocument();
    expect(panel.getByText(/never says how you answered/)).toBeInTheDocument();
    expect(routes.callsTo("GET /users/QuietBarrow42/contributions")[0]?.url.searchParams.get("kind")).toBe(
      "second_look",
    );

    await user.click(panel.getByRole("tab", { name: "Points" }));
    const points = await panel.findByRole("list", { name: "Where your points came from" });
    expect(panel.getByText("8 points in all")).toBeInTheDocument();
    expect(
      within(points)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      expect.stringMatching(/^\+2Your finding reached Seen by others/),
      expect.stringMatching(/^\+1Your finding matched a known record/),
    ]);
  });

  it("says there's nobody here for a handle the server doesn't know, and offers a retry when it fails", async () => {
    const routes = serve(profileFixture());
    routes.on("GET /users/Nobody", () => apiError(404, "user_not_found", "No such person."));
    const missing = await openProfile("/u/Nobody", "Profile");
    expect(await missing.findByText("There's nobody here")).toBeInTheDocument();
  });

  it("offers a retry when the page can't be loaded", async () => {
    const user = userEvent.setup();
    const routes = serve(profileFixture());
    let fail = true;
    routes.on("GET /users/KeenLynchet7", () =>
      fail ? apiError(400, "bad_request", "Something broke.") : json(profileFixture()),
    );
    const panel = await openProfile("/u/KeenLynchet7", "Profile");
    expect(await panel.findByText("This page couldn't be loaded")).toBeInTheDocument();
    fail = false;
    await user.click(panel.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("complementary", { name: "Mary Anning" })).toBeInTheDocument());
  });

  it("asks a signed-out person to sign in before they report someone", async () => {
    const user = userEvent.setup();
    serve(profileFixture());
    const panel = await openProfile("/u/KeenLynchet7", "Mary Anning");
    await user.click(panel.getByRole("button", { name: "Report this person" }));
    await waitFor(() => expect(useAccountUi.getState().sheet).toBe("signin"));
    expect(screen.queryByRole("dialog", { name: "Report this person" })).toBeNull();
  });
});
