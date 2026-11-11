import { screen, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { pageFixture, squareFixture, suggestionsFixture } from "../../test/fixtures/findingPage.js";
import { recentMentionFixture } from "../../test/fixtures/mentions.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import type { FindingDetail } from "../finding/types.js";
import { useSelectedFinding } from "../findings/selection.js";
import type { RecentMention } from "./types.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

beforeEach(() => {
  useSelectedFinding.getState().clear();
});

function serve(items: RecentMention[], finding: FindingDetail = pageFixture()): ApiRoutes {
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => signedOutResponse(),
    "GET /mentions/recent": () => json({ items, next_cursor: null }),
    "GET /findings/f-ring": () => json(finding),
    "GET /findings/f-ring/comments": () => json({ items: [], next_cursor: null }),
    "GET /findings/f-ring/suggested-records": () => json(suggestionsFixture([])),
    "GET /findings/f-ring/mentions": () => json({ items: [], next_cursor: null }),
  });
}

async function open() {
  renderShell("/mentions");
  await mapReady();
  return within(await screen.findByRole("complementary", { name: "Recent mentions" }));
}

describe("the recent mentions across the map", () => {
  it("lists each with its finding, and belongs to the Activity mode", async () => {
    void serve([recentMentionFixture()]);
    const panel = await open();
    const list = within(await panel.findByRole("list", { name: "Recent mentions" }));
    const [item] = list.getAllByRole("article");
    const mention = within(item as HTMLElement);
    expect(mention.getByRole("link", { name: /Barrows of the Marlborough Downs/ })).toHaveAttribute(
      "href",
      "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=754s",
    );
    const finding = mention.getByRole("link", { name: /About the finding/ });
    expect(finding).toHaveAttribute("href", "/f/f-ring");
    expect(finding).toHaveTextContent(pageFixture().title);
    expect(document.title).toBe("Recent mentions · Field Club");
    // The rail shows the Activity mode as the one open.
    expect(screen.getByRole("link", { name: "Activity" })).toHaveClass("fc-rail__link--active");
  });

  it("is offered from the Activity page", async () => {
    void serve([recentMentionFixture()]);
    renderShell("/activity");
    await mapReady();
    const activity = within(await screen.findByRole("complementary", { name: "Activity" }));
    await userEvent.setup().click(activity.getByRole("link", { name: "Recent mentions" }));
    expect(await screen.findByRole("complementary", { name: "Recent mentions" })).toBeVisible();
  });

  it("gives a finding whose place is kept back as its square, and selects it as the square", async () => {
    void serve([recentMentionFixture({}, { obscured: true })], squareFixture());
    const panel = await open();
    const finding = await panel.findByRole("link", { name: /About the finding/ });
    expect(finding).toHaveTextContent("Somewhere in square SU 10 69");
    await userEvent.setup().click(finding);
    const { selected } = useSelectedFinding.getState();
    expect(selected?.publicId).toBe("f-ring");
    // Marked on the map as its square's corners, never as a point.
    expect(selected?.square).toHaveLength(5);
  });

  it("says what to do when nobody has mentioned anything", async () => {
    void serve([]);
    const panel = await open();
    expect(await panel.findByRole("heading", { name: "No mentions yet" })).toBeVisible();
    expect(panel.getByRole("link", { name: "Explore the findings" })).toHaveAttribute("href", "/");
  });

  it("says when they couldn't be loaded, and tries again", async () => {
    const routes = serve([]);
    let fail = true;
    routes.on("GET /mentions/recent", () =>
      fail
        ? apiError(503, "unavailable", "The server is busy.")
        : json({ items: [recentMentionFixture()], next_cursor: null }),
    );
    const panel = await open();
    // Asked once more, a moment later, before it says so.
    expect(await panel.findByText("The mentions couldn't be loaded", {}, { timeout: 3000 })).toBeVisible();
    expect(routes.callsTo("GET /mentions/recent")).toHaveLength(2);
    fail = false;
    await userEvent.setup().click(panel.getByRole("button", { name: "Try again" }));
    expect(await panel.findByRole("link", { name: /Barrows of the Marlborough Downs/ })).toBeVisible();
  });
});
