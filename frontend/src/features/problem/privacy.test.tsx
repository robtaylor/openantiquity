import { act, screen, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useNavigate } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client.js";
import { forgetFailures, keepError, keepRequestFailure } from "../../api/failures.js";
import { formatGridRef, type GridFigures, wgs84ToGrid } from "../../map/gridref.js";
import { useMapStore } from "../../map/store.js";
import { routeApi } from "../../test/apiRoutes.js";
import { pageFixture, squareFixture } from "../../test/fixtures/findingPage.js";
import { FINDINGS_CENTRE } from "../../test/fixtures/findings.js";
import { investigationFixture } from "../../test/fixtures/investigations.js";
import { meFixture } from "../../test/fixtures/me.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import { POSITION_HINT, ReportProblemButton } from "./ReportProblem.js";

/**
 * The test that matters most. A report goes to a public tracker, and a
 * signed-in member sees a protected finding exactly, so no report made by
 * anyone beside one may carry anything that places it more closely than its
 * one-kilometre square (Decision 0005). Each report is built by the real
 * form, with a failure kept that names the finding's id and place and the
 * map pointed straight at the finding, and every route out is searched.
 */

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

/** Ids made only of letters, which a scrub of figures alone would miss. */
const FINDING_ID = "KQXMBW";
const INVESTIGATION_ID = "HVZRTN";
/** Where the finding is. */
const EXACT = FINDINGS_CENTRE;
const REPORT_EMAIL = "reports@openantiquity.example";
const META = { ...metaFixture, app: { ...metaFixture.app, report_email: REPORT_EMAIL } };
const MEMBER = meFixture({ handle: "KeenLynchet7", display_name: "Mary Anning" });
const UNAVAILABLE = "Not on this page, because it shows a finding, a draft or an investigation.";

function gridRefs(figures: GridFigures[]): string[] {
  const grid = wgs84ToGrid(EXACT.lon, EXACT.lat);
  if (!grid) throw new Error("The test's finding isn't on a grid");
  const refs = figures.map((each) => formatGridRef(grid, each));
  return [...refs, ...refs.map((ref) => ref.replaceAll(" ", ""))];
}

/** The finding's square, which a report may carry once the person adds where the map was. */
const SQUARE = gridRefs([4])[0] ?? "";

/** Everything that would place the finding more closely than its square. */
function placings(): string[] {
  return [
    FINDING_ID,
    INVESTIGATION_ID,
    ...gridRefs([6, 8, 10]),
    EXACT.lat.toFixed(2),
    EXACT.lon.toFixed(2),
    `/f/${FINDING_ID[0]}`,
    `/i/${INVESTIGATION_ID[0]}`,
    "://",
  ];
}

/** Keep a failure that names the finding and its place, as a careless page might. */
function keepFailuresNamingIt(): void {
  keepRequestFailure("GET", `/findings/${FINDING_ID}/comments`, new ApiError(500, "internal_error", "Broke."));
  keepError(`Couldn't draw ${FINDING_ID} at ${EXACT.lat}, ${EXACT.lon} (SU 1025 6996)`);
}

/** Point the map straight at the finding, close in. */
function lookAtTheFinding(): void {
  useMapStore.getState().setCamera({ lng: EXACT.lon, lat: EXACT.lat, zoom: 18, bearing: 0, pitch: 0 });
}

type User = ReturnType<typeof userEvent.setup>;

async function openTheForm(user: User) {
  await user.click(screen.getAllByRole("button", { name: "Report a problem" }).at(-1) as HTMLElement);
  const dialog = await screen.findByRole("dialog", { name: "Report a problem" });
  const form = within(dialog);
  await user.type(form.getByLabelText("What were you doing, and what went wrong?"), "The page went blank.");
  return form;
}

/** What would be sent by each route: shown, copied, the issue's title, body and address, the email's. */
async function everyRoute(user: User, form: ReturnType<typeof within>): Promise<Record<string, string>> {
  const shown = (form.getByLabelText("What will be sent") as HTMLTextAreaElement).value;
  await user.click(form.getByRole("button", { name: "Copy the details" }));
  await form.findByText("Copied. Paste it wherever you're sending the report.");
  const copied = await navigator.clipboard.readText();
  const issue = new URL(form.getByRole("link", { name: "Open a GitHub issue" }).getAttribute("href") ?? "");
  const email = form.getByRole("link", { name: "Email it" }).getAttribute("href") ?? "";
  // The recipient is exactly the address /meta gave, with nothing added to it.
  expect(email.startsWith(`mailto:${REPORT_EMAIL}?subject=`)).toBe(true);
  const mail = new URLSearchParams(email.split("?")[1]);
  expect(copied).toBe(shown);
  expect(issue.searchParams.get("body")).toBe(shown);
  expect(mail.get("body")).toBe(shown);
  return {
    shown,
    copied,
    "issue title": issue.searchParams.get("title") ?? "",
    "issue body": issue.searchParams.get("body") ?? "",
    "issue address": decodeURIComponent(issue.toString()),
    "email subject": mail.get("subject") ?? "",
    "email body": mail.get("body") ?? "",
    "email address": decodeURIComponent(email),
  };
}

function expectNothingPlacesIt(routes: Record<string, string>, allowSquare: boolean): void {
  for (const [route, text] of Object.entries(routes)) {
    for (const placing of placings()) {
      if (route === "issue address" && placing === "://") continue;
      expect(text, `${route} holds ${placing}`).not.toContain(placing);
    }
    // No coordinates of any precision: no number with three decimal places or more.
    expect(text, `${route} holds a coordinate`).not.toMatch(/\d\.\d{3,}/);
    if (!allowSquare) expect(text, `${route} holds the square`).not.toContain(SQUARE);
  }
}

async function expectTheBoxUnavailable(form: ReturnType<typeof within>, user: User): Promise<void> {
  const box = form.getByLabelText("Add where the map is looking");
  expect(box).toBeDisabled();
  expect(form.getByText(UNAVAILABLE)).toBeInTheDocument();
  await user.click(box);
  expect(box).not.toBeChecked();
}

function serve(routes: Record<string, () => Response>, signedIn: boolean): void {
  routeApi(harness.fetchMock(), {
    "GET /meta": () => json(META),
    "GET /auth/me": () => (signedIn ? json(MEMBER) : signedOutResponse()),
    ...routes,
  });
}

beforeEach(() => {
  forgetFailures();
});

/** Where a test can go to another page under the open form. */
const steer: { navigate: ((to: string) => void) | null } = { navigate: null };

function Steer() {
  steer.navigate = useNavigate();
  return null;
}

const EXACT_FINDING = pageFixture({ public_id: FINDING_ID, sensitivity: "protected" });
const refused = () => json({ error: { code: "invalid_cursor", message: "Broke." } }, 400);

/** The pages that show a finding, a draft or an investigation, each served as it shows the finding. */
const PAGES: Array<{ name: string; path: string; routes: Record<string, () => Response> }> = [
  {
    name: "the finding's page",
    path: `/f/${FINDING_ID}`,
    routes: { [`GET /findings/${FINDING_ID}`]: () => json(EXACT_FINDING) },
  },
  {
    name: "a second look at it",
    path: "/review",
    routes: {
      "GET /review/next": () =>
        json({
          items: [
            {
              public_id: FINDING_ID,
              place: { lon: EXACT.lon, lat: EXACT.lat, grid_ref: "SU 1025 6996" },
              shape_revision: 0,
              view_state: { layer: "slope", zoom: 18, bearing: 0, pitch: 0, sun_azimuth: 200, sun_altitude: 30 },
            },
          ],
          next_cursor: null,
        }),
    },
  },
  {
    name: "a change of its shape",
    path: `/mark/finding/${FINDING_ID}`,
    routes: { [`GET /findings/${FINDING_ID}`]: () => json(EXACT_FINDING) },
  },
  {
    name: "an investigation holding it",
    path: `/i/${INVESTIGATION_ID}`,
    routes: {
      [`GET /investigations/${INVESTIGATION_ID}`]: () =>
        json(investigationFixture({ public_id: INVESTIGATION_ID, item_count: 1 })),
      [`GET /investigations/${INVESTIGATION_ID}/items`]: refused,
    },
  },
];

describe("a report made beside a protected finding by a signed-in member, who sees it exactly", () => {
  it.each(PAGES)("offers no position and holds nothing that places it on $name", async ({ path, routes }) => {
    serve(routes, true);
    const user = userEvent.setup();
    renderShell(path, <ReportProblemButton />);
    await mapReady();
    keepFailuresNamingIt();
    lookAtTheFinding();
    const form = await openTheForm(user);
    await expectTheBoxUnavailable(form, user);
    const sent = await everyRoute(user, form);
    expect(sent.shown).toContain("- Signed in: yes");
    expect(sent.shown).toContain("- Where the map was: not included");
    expectNothingPlacesIt(sent, false);
  });

  it("gives only the square and the zoom from the bare map centred on it, when the person adds it", async () => {
    serve({}, true);
    const user = userEvent.setup();
    renderShell("/", <ReportProblemButton />);
    await mapReady();
    keepFailuresNamingIt();
    lookAtTheFinding();
    const form = await openTheForm(user);
    expect(form.getByText(POSITION_HINT)).toBeInTheDocument();
    await user.click(form.getByLabelText("Add where the map is looking"));
    const sent = await everyRoute(user, form);
    expect(sent.shown).toContain(`- Where the map was: ${SQUARE} at zoom 18`);
    for (const route of ["shown", "copied", "issue body", "email body"]) expect(sent[route]).toContain(SQUARE);
    expectNothingPlacesIt(sent, true);
  });

  it("still offers no position when the page under the open form changes to the bare map", async () => {
    serve(PAGES[0]?.routes ?? {}, true);
    const user = userEvent.setup();
    renderShell(
      `/f/${FINDING_ID}`,
      <>
        <Steer />
        <ReportProblemButton />
      </>,
    );
    await mapReady();
    lookAtTheFinding();
    const form = await openTheForm(user);
    act(() => steer.navigate?.("/"));
    await expectTheBoxUnavailable(form, user);
    const sent = await everyRoute(user, form);
    expect(sent.shown).toContain("- Page: /f/:id");
    expectNothingPlacesIt(sent, false);
  });
});

it("works out the same square the server shows the finding as", () => {
  // Were the two to differ, a report's square and the public one would cross and narrow the place.
  expect(SQUARE).toBe(squareFixture().location.grid_ref);
});

describe("a report made beside a protected finding by someone who sees only its square", () => {
  it("holds nothing that places it, by any route, on the finding's page", async () => {
    const finding = squareFixture({ public_id: FINDING_ID });
    const path = `/findings/${FINDING_ID}`;
    serve(
      {
        [`GET ${path}`]: () => json(finding),
        [`GET ${path}/comments`]: () => json({ error: { code: "internal_error", message: "Broke." } }, 500),
      },
      false,
    );
    const user = userEvent.setup();
    renderShell(`/f/${FINDING_ID}`, <ReportProblemButton />);
    await mapReady();
    await screen.findByRole("complementary", { name: finding.title });
    await screen.findByText(/The discussion couldn't be loaded/);
    keepFailuresNamingIt();
    lookAtTheFinding();
    const form = await openTheForm(user);
    await expectTheBoxUnavailable(form, user);
    const sent = await everyRoute(user, form);
    expect(sent.shown).toContain("- Page: /f/:id");
    expect(sent.shown).toContain("- Signed in: no");
    expect(sent.shown).toContain("GET /findings/{public_id}/comments: 500 internal_error");
    expectNothingPlacesIt(sent, false);
  });

  it("holds nothing that places it, by any route, on a page of an investigation holding it", async () => {
    const detail = investigationFixture({ public_id: INVESTIGATION_ID, item_count: 1 });
    serve(
      {
        [`GET /investigations/${INVESTIGATION_ID}`]: () => json(detail),
        [`GET /investigations/${INVESTIGATION_ID}/items`]: refused,
      },
      false,
    );
    const user = userEvent.setup();
    renderShell(`/i/${INVESTIGATION_ID}`);
    await mapReady();
    const page = await screen.findByRole("complementary", { name: detail.title });
    // The page's own error state offers the report.
    const failed = await within(page).findByRole("alert");
    expect(within(failed).getByText("What's in it couldn't be loaded")).toBeInTheDocument();
    keepFailuresNamingIt();
    lookAtTheFinding();
    const form = await openTheForm(user);
    await expectTheBoxUnavailable(form, user);
    const sent = await everyRoute(user, form);
    expect(sent.shown).toContain("- Page: /i/:id");
    expect(sent.shown).toContain("GET /investigations/{public_id}/items: 400 invalid_cursor");
    expectNothingPlacesIt(sent, false);
  });
});
