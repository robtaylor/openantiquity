import { render, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client.js";
import { forgetFailures, keepError, keepRequestFailure } from "../../api/failures.js";
import type { Meta } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { routeApi } from "../../test/apiRoutes.js";
import { useFakeEventSource } from "../../test/fakeEventSource.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { json, mapReady, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { ErrorReportContext } from "../../ui/errorReport.js";
import { ReportProblemButton } from "./ReportProblem.js";
import { CUT_NOTE, positionOf } from "./report.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();
const COMMIT = "0123456789abcdef0123456789abcdef01234567";

beforeEach(() => {
  forgetFailures();
  useFakeEventSource();
});

function serve(app: Partial<Meta["app"]> = {}) {
  return routeApi(harness.fetchMock(), {
    "GET /meta": () => json({ ...metaFixture, app: { ...metaFixture.app, commit: COMMIT, ...app } }),
    "GET /context/live-sources": () => json({ items: [] }),
  });
}

async function openFromAbout(app: Partial<Meta["app"]> = {}) {
  serve(app);
  const user = userEvent.setup();
  renderShell("/about");
  await mapReady();
  const about = await screen.findByRole("complementary", { name: "About OpenAntiquity" });
  const button = within(about).getByRole("button", { name: "Report a problem" });
  await user.click(button);
  const dialog = await screen.findByRole("dialog", { name: "Report a problem" });
  return { user, button, form: within(dialog), dialog };
}

function sent(form: ReturnType<typeof within>): string {
  return (form.getByLabelText("What will be sent") as HTMLTextAreaElement).value;
}

describe("Report a problem", () => {
  it("opens from the about page with focus on its title, and shows what will be sent", async () => {
    keepRequestFailure("GET", "/findings/7K3QXM", new ApiError(500, "internal_error", "Broke.", { requestId: "ab" }));
    keepError("Cannot read properties of undefined");
    const { form } = await openFromAbout();
    expect(form.getByRole("heading", { name: "Report a problem" })).toHaveFocus();
    const text = sent(form);
    expect(text).toContain(`- Build: 0.1.0, commit ${COMMIT}`);
    expect(text).toContain("- Page: /about");
    expect(text).toContain("- Layout: desktop");
    expect(text).toContain("- Signed in: no");
    expect(text).toContain("- Where the map was: not included");
    expect(text).toContain("GET /findings/{public_id}: 500 internal_error, request ab");
    expect(text).toContain("An error: `Cannot read properties of undefined`");
    expect(form.getByLabelText("What will be sent")).toHaveAttribute("readonly");
  });

  it("puts what the person writes, and the map's position only when they tick for it, in the text", async () => {
    const { user, form } = await openFromAbout();
    await user.type(form.getByLabelText("What were you doing, and what went wrong?"), "The slope view went white.");
    expect(sent(form)).toContain("## What happened\n\nThe slope view went white.");
    const { camera } = useMapStore.getState();
    const box = form.getByLabelText("Add where the map is looking");
    expect(box).toBeEnabled();
    expect(box).not.toBeChecked();
    await user.click(box);
    expect(box).toBeChecked();
    const square = positionOf(camera.lng, camera.lat, camera.zoom)?.square;
    expect(square).toMatch(/^[A-Z]{2} \d\d \d\d$/);
    expect(sent(form)).toContain(`- Where the map was: ${square} at zoom ${Math.round(camera.zoom)}`);
    await user.click(box);
    expect(sent(form)).toContain("- Where the map was: not included");
  });

  it("opens a GitHub issue in another tab with the same text, and copies it and says so", async () => {
    const { user, form } = await openFromAbout();
    await user.type(form.getByLabelText("What were you doing, and what went wrong?"), "Nothing saved.");
    const link = form.getByRole("link", { name: "Open a GitHub issue" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    const address = new URL(link.getAttribute("href") ?? "");
    expect(`${address.origin}${address.pathname}`).toBe("https://github.com/robtaylor/openantiquity/issues/new");
    expect(address.searchParams.get("title")).toBe("Nothing saved.");
    expect(address.searchParams.get("body")).toBe(sent(form));
    expect(form.queryByRole("note")).toBeNull();

    await user.click(form.getByRole("button", { name: "Copy the details" }));
    expect(await form.findByText("Copied. Paste it wherever you're sending the report.")).toBeInTheDocument();
    expect(await navigator.clipboard.readText()).toBe(sent(form));
  });

  it("says when the browser won't copy, and how to copy by hand", async () => {
    const { user, form } = await openFromAbout();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("Refused"));
    await user.click(form.getByRole("button", { name: "Copy the details" }));
    expect(
      await form.findByText("This browser wouldn't copy it. Select the text in the box above and copy it yourself."),
    ).toBeInTheDocument();
  });

  it("offers an email only once /meta names an address for reports", async () => {
    const without = await openFromAbout();
    expect(without.form.queryByRole("link", { name: "Email it" })).toBeNull();
  });

  it("emails the same text to the address /meta names", async () => {
    const { form } = await openFromAbout({ report_email: "reports@openantiquity.example" });
    const href = form.getByRole("link", { name: "Email it" }).getAttribute("href") ?? "";
    expect(href.startsWith("mailto:reports@openantiquity.example?")).toBe(true);
    expect(new URLSearchParams(href.split("?")[1]).get("body")).toBe(sent(form));
  });

  it("cuts a report too long for GitHub's address, says to paste the whole, and copies it on the way", async () => {
    const { user, form } = await openFromAbout();
    const box = form.getByLabelText("What were you doing, and what went wrong?");
    await user.click(box);
    // Within the box's limit, but each of these is six characters once in an address.
    await user.paste("éèêë àâôö ".repeat(190));
    expect(form.getByRole("note")).toHaveTextContent("too long to send whole");
    const link = form.getByRole("link", { name: "Open a GitHub issue" });
    expect(new URL(link.getAttribute("href") ?? "").searchParams.get("body")?.endsWith(CUT_NOTE)).toBe(true);
    link.addEventListener("click", (event) => event.preventDefault());
    await user.click(link);
    await waitFor(async () => expect(await navigator.clipboard.readText()).toBe(sent(form)));
  });

  it("takes a description and a kept error made of emoji without breaking", async () => {
    keepError("😀".repeat(400));
    const { user, form } = await openFromAbout();
    await user.click(form.getByLabelText("What were you doing, and what went wrong?"));
    await user.paste("😀".repeat(36));
    const address = new URL(form.getByRole("link", { name: "Open a GitHub issue" }).getAttribute("href") ?? "");
    expect(address.searchParams.get("title")).toBe("😀".repeat(36));
    expect(address.searchParams.get("body")).toBe(sent(form));
  });

  it("closes on Escape and on Close, and gives focus back to the button", async () => {
    const { user, button } = await openFromAbout();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(button).toHaveFocus();
    await user.click(button);
    const dialog = await screen.findByRole("dialog", { name: "Report a problem" });
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(button).toHaveFocus();
  });

  it("keeps Tab inside the form", async () => {
    const { user, form } = await openFromAbout();
    const close = form.getByRole("button", { name: "Close" });
    const last = form.getByRole("link", { name: "Open a GitHub issue" });
    last.focus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(last).toHaveFocus();
  });
});

describe("an error state", () => {
  it("offers Report a problem after its own action, wherever the app provides it", async () => {
    const user = userEvent.setup();
    render(
      <ErrorReportContext.Provider value={ReportProblemButton}>
        <EmptyState tone="error" title="The list couldn't be loaded" action={<button type="button">Try again</button>}>
          <p>The server isn't answering.</p>
        </EmptyState>
      </ErrorReportContext.Provider>,
    );
    const alert = screen.getByRole("alert");
    const buttons = within(alert).getAllByRole("button");
    expect(buttons.map((button) => button.textContent)).toEqual(["Try again", "Report a problem"]);
    await user.click(within(alert).getByRole("button", { name: "Report a problem" }));
    const dialog = await screen.findByRole("dialog", { name: "Report a problem" });
    expect((within(dialog).getByLabelText("What will be sent") as HTMLTextAreaElement).value).toContain(
      "- Map: not started",
    );
    // The form isn't inside the alert, so opening it doesn't read the alert out again.
    expect(alert.contains(dialog)).toBe(false);
  });

  it("isn't offered by an empty state that isn't an error, nor outside the app", () => {
    render(
      <ErrorReportContext.Provider value={ReportProblemButton}>
        <EmptyState title="Nothing here yet" />
      </ErrorReportContext.Provider>,
    );
    render(<EmptyState tone="error" title="The list couldn't be loaded" />);
    expect(screen.queryByRole("button", { name: "Report a problem" })).toBeNull();
  });

  it("is offered by the error shown before the map starts", async () => {
    harness.answer("/meta", () => json({ error: { code: "invalid_cursor", message: "Broke." } }, 400));
    renderShell("/");
    const failed = await screen.findByRole("alert");
    expect(within(failed).getByText("The map couldn't start")).toBeInTheDocument();
    expect(within(failed).getByRole("button", { name: "Report a problem" })).toBeInTheDocument();
  });

  it("works as a button on its own", async () => {
    const user = userEvent.setup();
    render(<ReportProblemButton />);
    await user.click(screen.getByRole("button", { name: "Report a problem" }));
    expect(await screen.findByRole("dialog", { name: "Report a problem" })).toBeInTheDocument();
  });
});
