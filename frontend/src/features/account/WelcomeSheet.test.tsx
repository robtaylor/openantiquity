import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ApiRoutes, apiError, routeApi } from "../../test/apiRoutes.js";
import { meFixture, newcomerFixture } from "../../test/fixtures/me.js";
import { json, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import { resetDraftsForTests } from "../drafts/store.js";
import { useAccountUi } from "./requireAccount.js";

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

async function openWelcome(routes: Record<string, Parameters<ApiRoutes["on"]>[1]> = {}) {
  const api = routeApi(harness.fetchMock(), { "GET /auth/me": () => json(newcomerFixture()), ...routes });
  renderShell("/");
  const sheet = await screen.findByRole("dialog", { name: "Welcome to Open Antiquity" });
  return { api, sheet, w: within(sheet) };
}

describe("the welcome sheet", () => {
  it("asks for a handle, the age band and the terms, and nothing else", async () => {
    const { sheet, w } = await openWelcome();
    expect(w.getByLabelText("Your name on the map")).toHaveValue("QuietBarrow42");
    expect(w.getByRole("radiogroup", { name: "How old are you?" })).toBeInTheDocument();
    expect(w.getAllByRole("radio").map((radio) => radio.textContent)).toEqual(["Under 16", "16 or 17", "18 or over"]);
    expect(w.getByRole("checkbox", { name: "I accept the contributor terms" })).not.toBeChecked();
    expect(w.getByText(/published under CC BY 4\.0/)).toBeInTheDocument();
    // The only fields are the handle and the terms box. The bands are buttons.
    expect(sheet.querySelectorAll("input, textarea, select")).toHaveLength(2);
  });

  it("links to the full contributor terms at the address /meta gives, in a new tab", async () => {
    const { w } = await openWelcome();
    const link = w.getByRole("link", { name: /Read the contributor terms/ });
    expect(link).toHaveAttribute("href", "/about#terms");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("draws another handle from the server", async () => {
    const { api, w } = await openWelcome({ "GET /auth/handle-suggestion": () => json({ handle: "MossyLynchet7" }) });
    await userEvent.click(w.getByRole("button", { name: "Suggest another" }));
    await waitFor(() => expect(w.getByLabelText("Your name on the map")).toHaveValue("MossyLynchet7"));
    expect(api.callsTo("GET /auth/handle-suggestion")).toHaveLength(1);
  });

  it("says what's missing before sending anything", async () => {
    const { api, w } = await openWelcome();
    await userEvent.clear(w.getByLabelText("Your name on the map"));
    await userEvent.type(w.getByLabelText("Your name on the map"), "9 lives");
    await userEvent.click(w.getByRole("button", { name: "Join Open Antiquity" }));
    expect(w.getByText(/A name is 3 to 30 letters/)).toBeInTheDocument();
    expect(w.getByText("Choose your age band.")).toBeInTheDocument();
    expect(w.getByText("Tick the box to accept the contributor terms.")).toBeInTheDocument();
    expect(api.callsTo("POST /auth/welcome")).toEqual([]);
  });

  it("sends the band and the terms, and the handle only when it changed", async () => {
    const { api, w } = await openWelcome({ "POST /auth/welcome": () => json(meFixture({ age_band: "16_17" })) });
    await userEvent.click(w.getByRole("radio", { name: "16 or 17" }));
    expect(w.getByText(/Other people will see only your handle/)).toBeInTheDocument();
    await userEvent.click(w.getByRole("checkbox", { name: "I accept the contributor terms" }));
    await userEvent.click(w.getByRole("button", { name: "Join Open Antiquity" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.callsTo("POST /auth/welcome")[0]?.body).toEqual({ age_band: "16_17", accept_terms: true });
  });

  it("says clearly when the handle is taken, and keeps everything else", async () => {
    const { api, w } = await openWelcome({ "POST /auth/welcome": () => apiError(409, "handle_taken", "Taken.") });
    await userEvent.clear(w.getByLabelText("Your name on the map"));
    await userEvent.type(w.getByLabelText("Your name on the map"), "Barrow");
    await userEvent.click(w.getByRole("radio", { name: "18 or over" }));
    await userEvent.click(w.getByRole("checkbox", { name: "I accept the contributor terms" }));
    await userEvent.click(w.getByRole("button", { name: "Join Open Antiquity" }));
    expect(await w.findByText(/Someone already has that name/)).toBeInTheDocument();
    expect(w.getByLabelText("Your name on the map")).toHaveAccessibleDescription(/Someone already has that name/);
    expect(w.getByRole("radio", { name: "18 or over" })).toHaveAttribute("aria-checked", "true");
    expect(api.callsTo("POST /auth/welcome")[0]?.body).toEqual({
      age_band: "18_plus",
      accept_terms: true,
      handle: "Barrow",
    });
  });

  it("explains a handle that isn't allowed", async () => {
    const { w } = await openWelcome({ "POST /auth/welcome": () => apiError(422, "invalid_handle", "Reserved.") });
    await userEvent.clear(w.getByLabelText("Your name on the map"));
    await userEvent.type(w.getByLabelText("Your name on the map"), "admin");
    await userEvent.click(w.getByRole("radio", { name: "18 or over" }));
    await userEvent.click(w.getByRole("checkbox", { name: "I accept the contributor terms" }));
    await userEvent.click(w.getByRole("button", { name: "Join Open Antiquity" }));
    expect(await w.findByText(/That name can't be used/)).toBeInTheDocument();
  });

  it("turns away someone under 16 kindly, and stores nothing", async () => {
    const { api, w } = await openWelcome({ "DELETE /auth/me": () => new Response(null, { status: 204 }) });
    await userEvent.click(w.getByRole("radio", { name: "Under 16" }));
    expect(w.getByText("Open Antiquity is for people aged 16 and over")).toBeInTheDocument();
    expect(w.queryByRole("button", { name: "Join Open Antiquity" })).toBeNull();
    expect(w.queryByRole("checkbox")).toBeNull();
    await userEvent.click(w.getByRole("button", { name: "Remove my sign-in" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.callsTo("POST /auth/welcome")).toEqual([]);
    expect(api.callsTo("DELETE /auth/me")).toHaveLength(1);
    expect(await screen.findByText(/Your sign-in has been removed/)).toBeInTheDocument();
  });

  it("shows the server's words when the minimum age is higher than the band chosen", async () => {
    const { w } = await openWelcome({
      "POST /auth/welcome": () => apiError(403, "below_minimum_age", "Contributors must be 18 or over."),
    });
    await userEvent.click(w.getByRole("radio", { name: "16 or 17" }));
    await userEvent.click(w.getByRole("checkbox", { name: "I accept the contributor terms" }));
    await userEvent.click(w.getByRole("button", { name: "Join Open Antiquity" }));
    expect(await w.findByText("Contributors must be 18 or over.")).toBeInTheDocument();
  });
});
