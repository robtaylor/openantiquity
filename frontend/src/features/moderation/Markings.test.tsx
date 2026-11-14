import { type QueryClient, useQueryClient } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { components } from "../../api/schema.js";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { useFakeEventSource } from "../../test/fakeEventSource.js";
import { lineFixture, MODERATOR_ACTIONS, OTHER, suggestionsFixture } from "../../test/fixtures/findingPage.js";
import { findingSummary, offset } from "../../test/fixtures/findings.js";
import { meFixture } from "../../test/fixtures/me.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { json, mapReady, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import type { Me } from "../account/api.js";
import { useAccountUi } from "../account/requireAccount.js";
import { EventRow } from "../activity/EventRow.js";
import { activityKeys } from "../activity/keys.js";
import type { FindingDetail } from "../finding/types.js";
import { useSelectedFinding } from "../findings/selection.js";
import { moderationKeys } from "./keys.js";
import { RESTORE_LAYERS, RESTORE_SOURCE } from "./RemoveMarkingPanel.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

type EarlierShape = components["schemas"]["EarlierShapeOut"];

const harness = setUpShellTests();

beforeEach(() => {
  useFakeEventSource();
  useAccountUi.setState({ sheet: null, waiting: [] });
  useSelectedFinding.getState().clear();
});

const ADMIN = meFixture({ handle: "AdminAnwen", display_name: "Anwen Price", role: "admin" });
const MODERATOR = meFixture({ handle: "ModMorag", display_name: "Morag Kerr", role: "moderator" });
const MEMBER = meFixture({ handle: OTHER.handle, display_name: OTHER.display_name });
const GONE = { handle: "former-member-1", display_name: "Former member", role: "member" };

function Address() {
  const location = useLocation();
  return <output data-testid="address">{location.pathname}</output>;
}

function address(): string {
  return screen.getByTestId("address").textContent ?? "";
}

/** The admin's view of an orphaned line: offering it and removing it allowed. */
function orphanedLine(overrides: Partial<FindingDetail> = {}): FindingDetail {
  return lineFixture({
    keeper: GONE,
    actions: {
      ...MODERATOR_ACTIONS,
      hand_on: { allowed: true, reason: null },
      remove_marking: { allowed: true, reason: null },
    },
    ...overrides,
  });
}

const BEFORE = [offset(-100, 0), offset(0, -40)];

/** Two changes, newest first: an extension by the keeper since gone, and the first drawing from a spot. */
const EARLIER: EarlierShape[] = [
  {
    revision: 3,
    kind: "extended",
    by: GONE,
    created_at: "2026-11-09T10:00:00Z",
    path_before: {
      closed: false,
      curve: "catmull-rom-centripetal-1",
      points: BEFORE.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
    },
    restorable: true,
  },
  {
    revision: 2,
    kind: "reshaped",
    by: GONE,
    created_at: "2026-11-05T10:00:00Z",
    path_before: {
      closed: true,
      curve: "catmull-rom-centripetal-1",
      points: [offset(0, 0), offset(50, 0), offset(50, 50)].map(({ lon, lat }) => ({
        lon,
        lat,
        kind: "corner" as const,
      })),
    },
    restorable: false,
  },
  { revision: 1, kind: "drawn", by: GONE, created_at: "2026-11-01T10:00:00Z", path_before: null, restorable: true },
];

function serve(me: Me, finding: FindingDetail = orphanedLine()): ApiRoutes {
  const path = `/findings/${finding.public_id}`;
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => json(me),
    [`GET ${path}`]: () => json(finding),
    [`GET ${path}/comments`]: () => json({ items: [], next_cursor: null }),
    [`GET ${path}/suggested-records`]: () => json(suggestionsFixture([])),
    [`GET ${path}/observations`]: () => json({ items: [], next_cursor: null }),
    [`GET /mod${path}/shapes`]: () => json({ items: EARLIER, next_cursor: null }),
    "GET /mod/markings/orphaned": () =>
      json({
        items: [
          {
            finding: findingSummary(
              {
                type: "Feature",
                geometry: { type: "Point", coordinates: [offset(0, 0).lon, offset(0, 0).lat] },
                properties: { public_id: "f-ring", tier: "seen", state: "open", obscured: false },
              },
              { title: "Ring ditch by the long barrow" },
            ),
            keeper: GONE,
            keeper_gone: "deleted",
          },
        ],
        next_cursor: null,
      }),
    "GET /mod/reports": () => json({ items: [], next_cursor: null }),
  });
}

describe("the list of markings without a keeper", () => {
  it("is a section of moderation for admins, listing each with who kept it and what became of them", async () => {
    serve(ADMIN);
    renderShell("/mod/markings", <Address />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Moderation" }));
    expect(panel.getByRole("tab", { name: "No keeper" })).toHaveAttribute("aria-selected", "true");
    const list = within(await panel.findByRole("list", { name: "Markings without a keeper" }));
    expect(list.getByRole("link", { name: "Ring ditch by the long barrow" })).toHaveAttribute("href", "/f/f-ring");
    expect(list.getByText(/Kept by Former member, whose account is deleted/)).toBeInTheDocument();
  });

  it("isn't offered to a moderator, who is taken to their own first section, and isn't asked for", async () => {
    const routes = serve(MODERATOR);
    renderShell("/mod/markings", <Address />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Moderation" }));
    await waitFor(() => expect(address()).toBe("/mod"));
    expect(panel.queryByRole("tab", { name: "No keeper" })).toBeNull();
    expect(routes.callsTo("GET /mod/markings/orphaned")).toHaveLength(0);
  });

  it("is opened from the notification an admin gets when an account that kept markings is deleted", async () => {
    render(
      <MemoryRouter>
        <EventRow
          meta={metaFixture}
          facts={{
            kind: "keeper_gone",
            actor: null,
            finding: null,
            investigationTitle: null,
            details: { markings: 2 } as never,
          }}
          createdAt="2026-11-14T09:00:00Z"
          investigation={null}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: /A deleted account left 2 markings without a keeper/ })).toHaveAttribute(
      "href",
      "/mod/markings",
    );
  });
});

describe("an orphaned marking's page, for an admin", () => {
  it("says it has no keeper, and offers it to someone and its removal", async () => {
    const user = userEvent.setup();
    serve(ADMIN);
    renderShell("/f/f-ring", <Address />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Ring ditch by the long barrow" }));
    expect(panel.getByText(/Its keeper's account is deleted or banned/)).toBeInTheDocument();
    // An admin offers it from here, not as its keeper.
    expect(panel.queryByRole("button", { name: "Hand it on" })).toBeNull();
    await user.click(panel.getByRole("button", { name: "Offer it to someone" }));
    expect(await screen.findByRole("dialog", { name: "Offer it to someone" })).toBeInTheDocument();
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    await user.click(panel.getByRole("button", { name: "Remove the marking" }));
    await waitFor(() => expect(address()).toBe("/mod/markings/f-ring"));
  });
});

describe("removing an orphaned marking", () => {
  async function openRemoval(me: Me = ADMIN, finding = orphanedLine()) {
    const routes = serve(me, finding);
    renderShell("/mod/markings/f-ring", <Address />);
    const map = await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Remove the marking" }));
    return { map, routes, panel };
  }

  it("lists the earlier shapes, draws the chosen one clearly over the shape it would replace, and says what stays", async () => {
    const user = userEvent.setup();
    const { map, panel } = await openRemoval();
    expect(panel.getByText(/The finding, its second looks and its evidence stay/)).toBeInTheDocument();
    const choices = within(await panel.findByRole("radiogroup", { name: "Put it back to" }));
    const restorable = choices.getByRole("radio", { name: /As it was until 9 November 2026/ });
    expect(choices.getByRole("radio", { name: /As it was until 5 November 2026/ })).toBeDisabled();
    expect(choices.getByRole("radio", { name: /No line or shape/ })).toBeInTheDocument();
    await user.click(restorable);
    const data = map.sourceData(RESTORE_SOURCE) as { features: Array<{ geometry: { type: string } }> };
    expect(data.features).toHaveLength(1);
    expect(data.features[0]?.geometry.type).toBe("LineString");
    expect(map.getLayer(RESTORE_LAYERS.line)).toBeDefined();
  });

  it("puts back the chosen shape with a reason, naming the revision it saw, and opens the finding", async () => {
    const user = userEvent.setup();
    const { routes, panel } = await openRemoval();
    routes.on("PUT /mod/findings/f-ring/marking", () => json(orphanedLine()));
    await user.click(await panel.findByRole("radio", { name: /As it was until 9 November 2026/ }));
    await user.click(panel.getByRole("button", { name: "Put this shape back" }));
    expect(await panel.findByText("Say why, for the moderation log.")).toBeInTheDocument();
    expect(routes.callsTo("PUT /mod/findings/f-ring/marking")).toHaveLength(0);
    await user.type(panel.getByLabelText("Why"), "Drawn across a farm track after a dispute.");
    await user.click(panel.getByRole("button", { name: "Put this shape back" }));
    await waitFor(() => expect(routes.callsTo("PUT /mod/findings/f-ring/marking")).toHaveLength(1));
    expect(routes.callsTo("PUT /mod/findings/f-ring/marking")[0]?.body).toEqual({
      to_revision: 2,
      shape_revision: 3,
      reason: "Drawn across a farm track after a dispute.",
    });
    await waitFor(() => expect(address()).toBe("/f/f-ring"));
    expect(await screen.findByText(/The marking is taken back/)).toBeInTheDocument();
  });

  it("takes the shape away, leaving a spot, when that is chosen", async () => {
    const user = userEvent.setup();
    const { routes, panel } = await openRemoval();
    routes.on("PUT /mod/findings/f-ring/marking", () => json(orphanedLine()));
    await user.click(await panel.findByRole("radio", { name: /No line or shape/ }));
    await user.type(panel.getByLabelText("Why"), "Spam drawn over the whole down.");
    await user.click(panel.getByRole("button", { name: "Remove the marking" }));
    await waitFor(() => expect(routes.callsTo("PUT /mod/findings/f-ring/marking")).toHaveLength(1));
    expect(routes.callsTo("PUT /mod/findings/f-ring/marking")[0]?.body).toMatchObject({ to_revision: null });
  });

  for (const [who, me] of [
    ["a moderator", MODERATOR],
    ["a member", MEMBER],
  ] as const) {
    it(`shows ${who} what a page that isn't theirs shows, and asks for no earlier shapes`, async () => {
      const finding = lineFixture({
        actions: { ...MODERATOR_ACTIONS, remove_marking: { allowed: false, reason: "admins_only" } },
      });
      const { routes, panel } = await openRemoval(me, finding);
      expect(await panel.findByText("This part is for admins")).toBeInTheDocument();
      expect(panel.queryByRole("radiogroup")).toBeNull();
      expect(routes.callsTo("GET /mod/findings/f-ring/shapes")).toHaveLength(0);
    });
  }
});

const seeded: { client: QueryClient | null } = { client: null };

/** Puts the admins' list and a page of the feed in the cache, as having opened them would. */
function Seed() {
  const client = useQueryClient();
  seeded.client = client;
  if (!client.getQueryData(moderationKeys.orphaned)) {
    client.setQueryData(moderationKeys.orphaned, { pages: [], pageParams: [] });
    client.setQueryData(activityKeys.feed(null, []), { pages: [], pageParams: [] });
  }
  return null;
}

describe("a removal the server refuses", () => {
  for (const [what, status, code, message, said] of [
    [
      "a keeper who is still a member",
      409,
      "not_orphaned",
      "This marking's keeper is still a member. A moderator hides it, or bans its keeper, first.",
      /keeper is still a member/,
    ],
    [
      "a shape changed meanwhile",
      409,
      "shape_changed",
      "The shape was changed somewhere else.",
      /changed while you were looking/,
    ],
  ] as const) {
    it(`says so for ${what}, and keeps the reason typed`, async () => {
      const user = userEvent.setup();
      const routes = serve(ADMIN);
      routes.on("PUT /mod/findings/f-ring/marking", () => apiError(status, code, message));
      renderShell("/mod/markings/f-ring", <Address />);
      await mapReady();
      const panel = within(await screen.findByRole("complementary", { name: "Remove the marking" }));
      await user.click(await panel.findByRole("radio", { name: /No line or shape/ }));
      await user.type(panel.getByLabelText("Why"), "Spam.");
      await user.click(panel.getByRole("button", { name: "Remove the marking" }));
      expect(await panel.findByRole("alert")).toHaveTextContent(said);
      expect(panel.getByLabelText("Why")).toHaveValue("Spam.");
      expect(address()).toBe("/mod/markings/f-ring");
    });
  }
});

describe("lists that change with an admin's acts", () => {
  const stale = (key: readonly unknown[]) => seeded.client?.getQueryState(key)?.isInvalidated === true;

  it("asks for the markings without a keeper and the feed again after a removal", async () => {
    const user = userEvent.setup();
    const routes = serve(ADMIN);
    routes.on("PUT /mod/findings/f-ring/marking", () => json(orphanedLine()));
    renderShell("/mod/markings/f-ring", <Seed />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Remove the marking" }));
    await user.click(await panel.findByRole("radio", { name: /No line or shape/ }));
    await user.type(panel.getByLabelText("Why"), "Spam.");
    await user.click(panel.getByRole("button", { name: "Remove the marking" }));
    await waitFor(() => expect(stale(moderationKeys.orphaned)).toBe(true));
    expect(stale(activityKeys.feed(null, []))).toBe(true);
  });

  it("asks for the markings without a keeper again after an admin's offer", async () => {
    const user = userEvent.setup();
    const routes = serve(ADMIN);
    routes.on("PUT /findings/f-ring/keeping/offer", () =>
      json(orphanedLine({ keeping: { offered_to: OTHER, offered_at: "2026-11-14T09:00:00Z" } })),
    );
    renderShell("/f/f-ring", <Seed />);
    await mapReady();
    const panel = within(await screen.findByRole("complementary", { name: "Ring ditch by the long barrow" }));
    await user.click(panel.getByRole("button", { name: "Offer it to someone" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Offer it to someone" }));
    await user.type(dialog.getByLabelText("Their handle"), OTHER.handle);
    await user.click(dialog.getByRole("button", { name: "Offer it" }));
    await waitFor(() => expect(stale(moderationKeys.orphaned)).toBe(true));
  });
});
