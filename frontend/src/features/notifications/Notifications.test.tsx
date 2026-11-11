import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { FakeEventSource, useFakeEventSource } from "../../test/fakeEventSource.js";
import { pageFixture } from "../../test/fixtures/findingPage.js";
import { meFixture } from "../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests, usePhoneLayout } from "../../test/shellHarness.js";
import { useToastStore } from "../../ui/toastStore.js";
import type { Notification, NotificationPage } from "./api.js";
import { markLocally, type NotificationPages, unmarkLocally, withUnreadCount } from "./readState.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

beforeEach(() => {
  useFakeEventSource();
});

const ME = meFixture();
const RING = pageFixture();
const MARY = { handle: "KeenLynchet7", display_name: "Mary Anning", avatar_url: null, role: "member" };

function notification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: 1,
    kind: "tier_changed",
    created_at: new Date(Date.now() - 60 * 60_000).toISOString(),
    read: false,
    actor: null,
    finding: {
      public_id: RING.public_id,
      title: RING.title,
      feature_class: RING.feature_class,
      tier: "seen",
      state: "open",
      location: RING.location,
    },
    investigation: null,
    details: { tier_from: "spotted", tier_to: "seen" },
    ...overrides,
  };
}

const INBOX: Notification[] = [
  notification({ id: 12 }),
  notification({ id: 11, kind: "comment_added", actor: MARY, details: {} }),
  notification({ id: 10, kind: "evidence_added", actor: MARY, read: true, details: { evidence_kind: "aerial" } }),
  notification({
    id: 9,
    kind: "investigation_invitation",
    actor: MARY,
    finding: null,
    investigation: "i-ridge",
    read: true,
    details: {},
  }),
];

function inbox(items: Notification[], unread = items.filter((item) => !item.read).length): NotificationPage {
  return { items, next_cursor: null, unread_count: unread };
}

function serve(items: Notification[] = INBOX, signedIn = true): ApiRoutes {
  let current = items.map((item) => ({ ...item }));
  return routeApi(harness.fetchMock(), {
    "GET /auth/me": () => (signedIn ? json(ME) : json({ error: { code: "unauthorised", message: "No" } }, 401)),
    "GET /notifications": () => json(inbox(current)),
    "POST /notifications/read": (call) => {
      const body = call.body as { ids?: number[]; all?: boolean; up_to?: number };
      current = current.map((item) =>
        body.ids?.includes(item.id) || (body.all && item.id <= (body.up_to ?? Number.MAX_SAFE_INTEGER))
          ? { ...item, read: true }
          : item,
      );
      const unread = current.filter((item) => !item.read).length;
      return json({ marked: 1, unread_count: unread });
    },
  });
}

/** Rows never come into sight by themselves, so a test can say when they do. */
function holdSight(): { show: (element: Element) => void } {
  const observers: Array<{ callback: IntersectionObserverCallback; targets: Set<Element> }> = [];
  class Observer {
    readonly targets = new Set<Element>();
    constructor(readonly callback: IntersectionObserverCallback) {
      observers.push(this);
    }
    observe(target: Element) {
      this.targets.add(target);
    }
    unobserve(target: Element) {
      this.targets.delete(target);
    }
    disconnect() {
      this.targets.clear();
    }
  }
  vi.stubGlobal("IntersectionObserver", Observer);
  return {
    show: (element) => {
      for (const observer of observers) {
        if (!observer.targets.has(element)) continue;
        const entry = { target: element, intersectionRatio: 1, isIntersecting: true } as IntersectionObserverEntry;
        observer.callback([entry], observer as unknown as IntersectionObserver);
      }
    },
  };
}

describe("the unread count", () => {
  it("is never shown, nor asked for, for someone who isn't signed in", async () => {
    const routes = serve(INBOX, false);
    renderShell();
    await mapReady();
    expect(screen.getByRole("link", { name: "Account" })).toBeInTheDocument();
    expect(screen.queryByTestId("notification-count")).toBeNull();
    expect(routes.callsTo("GET /notifications")).toHaveLength(0);
  });

  it("sits quietly on the Account item, and says the number in words", async () => {
    serve();
    renderShell();
    await mapReady();
    const account = await screen.findByRole("link", { name: "Account, 2 new notifications" });
    expect(within(account).getByTestId("notification-count")).toHaveTextContent("2");
  });

  it("on a phone, shows on More and on the Account item under it", async () => {
    const user = userEvent.setup();
    usePhoneLayout();
    serve();
    renderShell();
    await mapReady();
    const tabs = screen.getByRole("navigation", { name: "Modes" });
    const more = await within(tabs).findByRole("button", { name: "More, 2 new notifications" });
    expect(within(more).getByTestId("notification-count")).toHaveTextContent("2");
    await user.click(more);
    expect(within(tabs).getByRole("link", { name: "Account, 2 new notifications" })).toBeInTheDocument();
  });
});

describe("the list of notifications", () => {
  it("says what happened and to which finding, and marks each read once it has been seen", async () => {
    const sight = holdSight();
    const routes = serve();
    renderShell("/account");
    await mapReady();
    const list = within(await screen.findByRole("list", { name: "Your notifications" }));
    const rows = list.getAllByRole("listitem");
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringMatching(/^Ring ditch by the long barrow moved up to Seen by others\.New1 hour ago$/),
      expect.stringMatching(/^Mary Anning commented on Ring ditch by the long barrow\.New/),
      expect.stringMatching(/^Mary Anning added evidence to Ring ditch by the long barrow: aerial photo\.1 hour ago$/),
      expect.stringMatching(/^Mary Anning invited you to join an investigation\./),
    ]);
    expect(list.getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual([
      "/f/f-ring",
      "/f/f-ring",
      "/f/f-ring",
      "/i/i-ridge",
    ]);
    expect(routes.callsTo("POST /notifications/read")).toHaveLength(0);

    // The first two come into sight together: one request, and the count falls at once.
    act(() => {
      sight.show(rows[0] as Element);
      sight.show(rows[1] as Element);
    });
    await waitFor(() => expect(routes.callsTo("POST /notifications/read")).toHaveLength(1));
    expect(routes.callsTo("POST /notifications/read")[0]?.body).toEqual({ ids: [12, 11], all: false });
    expect(routes.callsTo("POST /notifications/read")[0]?.headers.get("X-FieldClub-Client")).toBe("web");
    expect(await screen.findByRole("link", { name: "Account" })).toBeInTheDocument();
    expect(screen.queryByTestId("notification-count")).toBeNull();
    // Still marked new while the page is open, so the person can tell what had arrived.
    expect(rows[0]).toHaveTextContent("New");
  });

  it("marks them all read at once, up to the newest shown", async () => {
    const user = userEvent.setup();
    holdSight();
    const routes = serve();
    renderShell("/account");
    await mapReady();
    await screen.findByRole("list", { name: "Your notifications" });
    await user.click(screen.getByRole("button", { name: "Mark all as read" }));
    expect(screen.getByRole("link", { name: "Account" })).toBeInTheDocument();
    await waitFor(() => expect(routes.callsTo("POST /notifications/read")[0]?.body).toEqual({ all: true, up_to: 12 }));
    expect(screen.queryByRole("button", { name: "Mark all as read" })).toBeNull();
  });

  it("puts them back, with a toast, when the server won't mark them", async () => {
    const user = userEvent.setup();
    holdSight();
    const routes = serve();
    routes.on("POST /notifications/read", () => apiError(500, "internal", "No."));
    useToastStore.getState().clear();
    renderShell("/account");
    await mapReady();
    await screen.findByRole("list", { name: "Your notifications" });
    await user.click(screen.getByRole("button", { name: "Mark all as read" }));
    expect(await screen.findByText(/couldn't be marked as read/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Account, 2 new notifications" })).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    serve([]);
    renderShell("/account");
    await mapReady();
    expect(await screen.findByText(/Nothing yet\. You'll hear here when a finding you follow changes\./)).toBeVisible();
  });

  it("is asked for again when someone else does something, but not for the person's own actions", async () => {
    const routes = serve();
    renderShell();
    await mapReady();
    await screen.findByRole("link", { name: "Account, 2 new notifications" });
    act(() => FakeEventSource.current().open());
    const before = routes.callsTo("GET /notifications").length;

    act(() =>
      FakeEventSource.current().activity({ id: 20, kind: "comment_added", finding: "f-ring", actor: ME.handle }),
    );
    await new Promise((resolve) => setTimeout(resolve, 2300));
    expect(routes.callsTo("GET /notifications").length).toBe(before);

    act(() => FakeEventSource.current().activity({ id: 21, kind: "tier_changed", finding: "f-ring", actor: null }));
    await waitFor(() => expect(routes.callsTo("GET /notifications").length).toBe(before + 1), { timeout: 3000 });
  });
});

describe("marking read in the cache", () => {
  const pages: NotificationPages = {
    pages: [inbox(INBOX.slice(0, 2)), inbox(INBOX.slice(2), 9)],
    pageParams: [null, "c"],
  };

  it("marks the chosen ones, drops the count by those, and puts exactly those back", () => {
    const { data, changed } = markLocally(pages, { ids: [11, 10] });
    expect(changed).toEqual([11]);
    expect(data.pages[0]?.unread_count).toBe(1);
    expect(data.pages[0]?.items.map((item) => item.read)).toEqual([false, true]);
    const back = unmarkLocally(data, changed);
    expect(back.pages[0]?.unread_count).toBe(2);
    expect(back.pages[0]?.items.map((item) => item.read)).toEqual([false, false]);
  });

  it("marks every one up to the newest seen, and takes the server's count", () => {
    const { data, changed } = markLocally(pages, { upTo: 11 });
    expect(changed).toEqual([11]);
    expect(data.pages[0]?.unread_count).toBe(1);
    expect(withUnreadCount(data, 3).pages[0]?.unread_count).toBe(3);
  });
});
