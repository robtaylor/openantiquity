import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { forgetFailures, keepError } from "../../api/failures.js";
import { formatGridRef, type GridFigures, wgs84ToGrid } from "../../map/gridref.js";
import { useMapStore } from "../../map/store.js";
import { routeApi } from "../../test/apiRoutes.js";
import { squareFixture } from "../../test/fixtures/findingPage.js";
import { FINDINGS_CENTRE } from "../../test/fixtures/findings.js";
import { investigationFixture } from "../../test/fixtures/investigations.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { json, mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import { ReportProblemButton } from "./ReportProblem.js";

/**
 * The test that matters most: someone who sees a protected finding only as
 * its square makes a report beside it, and no route the report can go by
 * carries anything that places the finding more closely than the square
 * (Decision 0005). The report is built by the real form, on the finding's
 * page and on a page of an investigation holding it, with a failure kept
 * from each page and the map, at worst, looking straight at the finding.
 */

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

/** Ids made only of letters, which a scrub of figures alone would miss. */
const FINDING_ID = "KQXMBW";
const INVESTIGATION_ID = "HVZRTN";
/** Where the finding is. The page is shown only its square. */
const EXACT = FINDINGS_CENTRE;

const META = { ...metaFixture, app: { ...metaFixture.app, report_email: "reports@openantiquity.example" } };

/** Everything that would place the finding more closely than its square. */
function placings(): string[] {
  const grid = wgs84ToGrid(EXACT.lon, EXACT.lat);
  if (!grid) throw new Error("The test's finding isn't on a grid");
  const refs = ([6, 8, 10] as GridFigures[]).map((figures) => formatGridRef(grid, figures));
  return [
    FINDING_ID,
    INVESTIGATION_ID,
    ...refs,
    ...refs.map((ref) => ref.replaceAll(" ", "")),
    EXACT.lat.toFixed(2),
    EXACT.lon.toFixed(2),
    `/f/${FINDING_ID[0]}`,
    `/i/${INVESTIGATION_ID[0]}`,
    "://",
  ];
}

/** What would be sent by each route: shown, copied, the GitHub issue's title and body, the email's subject and body. */
async function everyRoute(user: ReturnType<typeof userEvent.setup>): Promise<Record<string, string>> {
  const dialog = await screen.findByRole("dialog", { name: "Report a problem" });
  const form = within(dialog);
  await user.type(form.getByLabelText("What were you doing, and what went wrong?"), "The page went blank.");
  const box = form.getByLabelText("Add where the map is looking");
  expect(box).toBeDisabled();
  expect(box).not.toBeChecked();
  expect(form.getByText("Not on this page: it shows a place that is kept back from you.")).toBeInTheDocument();
  await user.click(box);
  expect(box).not.toBeChecked();

  const shown = (form.getByLabelText("What will be sent") as HTMLTextAreaElement).value;
  await user.click(form.getByRole("button", { name: "Copy the details" }));
  await form.findByText("Copied. Paste it wherever you're sending the report.");
  const copied = await navigator.clipboard.readText();
  const issue = new URL(form.getByRole("link", { name: "Open a GitHub issue" }).getAttribute("href") ?? "");
  const email = form.getByRole("link", { name: "Email it" }).getAttribute("href") ?? "";
  const mail = new URLSearchParams(email.split("?")[1]);
  return {
    shown,
    copied,
    "issue title": issue.searchParams.get("title") ?? "",
    "issue body": issue.searchParams.get("body") ?? "",
    "issue address": issue.toString(),
    "email subject": mail.get("subject") ?? "",
    "email body": mail.get("body") ?? "",
    "email address": email,
  };
}

function expectNothingPlacesIt(routes: Record<string, string>): void {
  expect(routes.shown).toContain("## What went wrong lately");
  expect(routes.copied).toBe(routes.shown);
  expect(routes["issue body"]).toBe(routes.shown);
  expect(routes["email body"]).toBe(routes.shown);
  for (const [route, text] of Object.entries(routes)) {
    const decoded = route.endsWith("address") ? decodeURIComponent(text) : text;
    for (const placing of placings()) {
      if (route.endsWith("address") && placing === "://") continue;
      expect(decoded, `${route} holds ${placing}`).not.toContain(placing);
    }
    // No coordinates of any precision: no number with three decimal places or more.
    expect(decoded, `${route} holds a coordinate`).not.toMatch(/\d\.\d{3,}/);
  }
}

beforeEach(() => {
  forgetFailures();
});

/** Point the map straight at the finding, as someone who had zoomed in on its square might. */
function lookAtTheFinding(): void {
  useMapStore.getState().setCamera({ lng: EXACT.lon, lat: EXACT.lat, zoom: 18, bearing: 0, pitch: 0 });
}

describe("a report made beside a protected finding by someone who sees only its square", () => {
  it("holds nothing that places it, by any route, on the finding's page", async () => {
    const finding = squareFixture({ public_id: FINDING_ID });
    const path = `/findings/${FINDING_ID}`;
    routeApi(harness.fetchMock(), {
      "GET /meta": () => json(META),
      "GET /auth/me": () => signedOutResponse(),
      [`GET ${path}`]: () => json(finding),
      [`GET ${path}/comments`]: () => json({ error: { code: "internal_error", message: "Broke." } }, 500),
    });
    const user = userEvent.setup();
    renderShell(`/f/${FINDING_ID}`, <ReportProblemButton />);
    await mapReady();
    await screen.findByRole("complementary", { name: finding.title });
    await waitFor(() => expect(document.body.textContent).toContain("The discussion couldn't be loaded"));
    keepError(`Couldn't draw ${FINDING_ID} at ${EXACT.lat}, ${EXACT.lon}`);
    lookAtTheFinding();

    await user.click(screen.getByRole("button", { name: "Report a problem" }));
    const routes = await everyRoute(user);
    expect(routes.shown).toContain("- Page: /f/:id");
    expect(routes.shown).toContain("- Signed in: no");
    expect(routes.shown).toContain("GET /findings/{public_id}/comments: 500 internal_error");
    expectNothingPlacesIt(routes);
  });

  it("holds nothing that places it, by any route, on a page of an investigation holding it", async () => {
    const detail = investigationFixture({ public_id: INVESTIGATION_ID, item_count: 1, places_kept_back: true });
    routeApi(harness.fetchMock(), {
      "GET /meta": () => json(META),
      "GET /auth/me": () => signedOutResponse(),
      [`GET /investigations/${INVESTIGATION_ID}`]: () => json(detail),
      // A refusal, which isn't tried again.
      [`GET /investigations/${INVESTIGATION_ID}/items`]: () =>
        json({ error: { code: "invalid_cursor", message: "Broke." } }, 400),
    });
    const user = userEvent.setup();
    renderShell(`/i/${INVESTIGATION_ID}`);
    await mapReady();
    const page = await screen.findByRole("complementary", { name: detail.title });
    // The page's own error state offers the report.
    const failed = await within(page).findByRole("alert");
    expect(within(failed).getByText("What's in it couldn't be loaded")).toBeInTheDocument();
    lookAtTheFinding();

    await user.click(within(failed).getByRole("button", { name: "Report a problem" }));
    const routes = await everyRoute(user);
    expect(routes.shown).toContain("- Page: /i/:id");
    expect(routes.shown).toContain("GET /investigations/{public_id}/items: 400 invalid_cursor");
    expectNothingPlacesIt(routes);
  });
});
