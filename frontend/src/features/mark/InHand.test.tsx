import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { routeApi } from "../../test/apiRoutes.js";
import { offset } from "../../test/fixtures/findings.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { mapReady, renderShell, setUpShellTests, signedOutResponse } from "../../test/shellHarness.js";
import { useAccountUi } from "../account/requireAccount.js";
import { resetDraftsForTests } from "../drafts/store.js";
import { type FindingDraft, findingDrafts } from "./findingDrafts.js";
import { useMarkStore } from "./markStore.js";

/**
 * Whatever takes the drawing tool asks before it replaces what is in hand
 * and not sent: "Mark a finding" and opening a draft, over a new marking, a
 * change to a saved shape, a suggestion and a draft whose line has changed.
 */

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

beforeEach(() => {
  window.localStorage.clear();
  resetDraftsForTests();
  useAccountUi.setState(useAccountUi.getInitialState(), true);
  useMarkStore.getState().start();
});

function Address() {
  const location = useLocation();
  return <output data-testid="address">{location.pathname}</output>;
}

function address(): string {
  return screen.getByTestId("address").textContent ?? "";
}

const LINE = [offset(-100, 0), offset(0, 20), offset(100, 0)];
const PATH = { closed: false, points: LINE.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })) };

function holdNewMarking(): void {
  const mark = useMarkStore.getState();
  for (const { lon, lat } of [offset(400, 300), offset(450, 340)]) mark.add([lon, lat], metaFixture.shapes);
  mark.finish();
}

/** A change to f-ring's shape, or a suggestion to it, with one point moved. */
function holdChanged(kind: "finding" | "suggest"): void {
  const mark = useMarkStore.getState();
  mark.edit(`${kind}:f-ring:3`, PATH);
  mark.move(0, [LINE[0]?.lon ?? 0, (LINE[0]?.lat ?? 0) + 0.0002]);
}

const DRAFT: FindingDraft = {
  point: [LINE[0]?.lon ?? 0, LINE[0]?.lat ?? 0],
  feature_class: "round_barrow",
  period: "unknown",
  title: "Round barrow",
  description: null,
  path: null,
  view_state: {},
};

function putDraft(): string {
  return findingDrafts.put(DRAFT).id;
}

/** A draft taken up in the tool, with its line changed since it was kept. */
function holdChangedDraft(): string {
  const id = putDraft();
  const mark = useMarkStore.getState();
  mark.load(id, DRAFT);
  mark.continueFrom("end");
  mark.add([offset(300, 0).lon, offset(300, 0).lat], metaFixture.shapes);
  mark.finish();
  return id;
}

async function open(path: string) {
  // Signed out, as someone with drafts in this browser is.
  routeApi(harness.fetchMock(), { "GET /auth/me": () => signedOutResponse() });
  renderShell(path, <Address />);
  const map = await mapReady();
  const panel = within(await screen.findByRole("complementary", { name: "Mark a finding" }));
  return { map, panel };
}

const HELD = {
  marking: { hold: holdNewMarking, words: "You have an unfinished marking.", back: "/mark" },
  change: {
    hold: () => holdChanged("finding"),
    words: "You have a change to another finding's shape that isn't saved.",
    back: "/mark/finding/f-ring",
  },
  suggestion: {
    hold: () => holdChanged("suggest"),
    words: "You have a suggested change to a finding's shape that isn't sent.",
    back: "/mark/suggest/f-ring",
  },
} as const;

describe("'Mark a finding' over a change to a saved shape", () => {
  it("asks, adds nothing meanwhile, and can go back to it", async () => {
    const user = userEvent.setup();
    holdChanged("finding");
    const { map, panel } = await open("/mark");
    expect(
      await panel.findByText(/You have a change to another finding's shape that isn't saved\. Marking a finding/),
    ).toBeInTheDocument();
    act(() => map.click(300, 300));
    expect(useMarkStore.getState().shape.present.points).toHaveLength(3);
    expect(useMarkStore.getState().editing).toBe("finding:f-ring:3");
    await user.click(panel.getByRole("button", { name: "Go back to it" }));
    await waitFor(() => expect(address()).toBe("/mark/finding/f-ring"));
  });

  it("discards it and starts here only when told to", async () => {
    const user = userEvent.setup();
    holdChanged("finding");
    const { map, panel } = await open("/mark");
    await user.click(await panel.findByRole("button", { name: "Discard it and start here" }));
    expect(useMarkStore.getState().editing).toBeNull();
    act(() => map.click(300, 300));
    expect(useMarkStore.getState().shape.present.points).toHaveLength(1);
  });
});

describe("'Mark a finding' over a draft whose line changed", () => {
  it("asks before discarding the changes", async () => {
    const user = userEvent.setup();
    const id = holdChangedDraft();
    const { panel } = await open("/mark");
    expect(
      await panel.findByText("You have a draft with changes that aren't kept. Marking a finding would discard them."),
    ).toBeInTheDocument();
    expect(useMarkStore.getState().draftId).toBe(id);
    await user.click(panel.getByRole("button", { name: "Go back to it" }));
    await waitFor(() => expect(address()).toBe(`/mark/${id}`));
  });
});

describe("opening a draft", () => {
  for (const [kind, held] of Object.entries(HELD)) {
    it(`asks first over ${kind === "marking" ? "an unfinished marking" : `a ${kind}`}, and opens it only when told to`, async () => {
      const user = userEvent.setup();
      const id = putDraft();
      held.hold();
      const before = useMarkStore.getState().shape.present;
      const { panel } = await open(`/mark/${id}`);
      expect(await panel.findByText(`${held.words} Opening this draft would discard it.`)).toBeInTheDocument();
      expect(useMarkStore.getState().shape.present).toBe(before);
      expect(useMarkStore.getState().draftId).toBeNull();

      await user.click(panel.getByRole("button", { name: "Discard it and open the draft" }));
      await waitFor(() => expect(useMarkStore.getState().draftId).toBe(id));
      expect(useMarkStore.getState().editing).toBeNull();
    });
  }

  it("goes back to what is in hand when told to", async () => {
    const user = userEvent.setup();
    const id = putDraft();
    holdChanged("suggest");
    const { panel } = await open(`/mark/${id}`);
    await user.click(await panel.findByRole("button", { name: "Go back to it" }));
    await waitFor(() => expect(address()).toBe("/mark/suggest/f-ring"));
    expect(useMarkStore.getState().editing).toBe("suggest:f-ring:3");
  });

  it("asks over another draft whose line changed", async () => {
    const other = holdChangedDraft();
    const id = putDraft();
    const { panel } = await open(`/mark/${id}`);
    expect(
      await panel.findByText("You have a draft with changes that aren't kept. Opening this draft would discard them."),
    ).toBeInTheDocument();
    expect(useMarkStore.getState().draftId).toBe(other);
  });

  it("opens straight away over nothing unsent, and over itself", async () => {
    const id = putDraft();
    await open(`/mark/${id}`);
    await waitFor(() => expect(useMarkStore.getState().draftId).toBe(id));
  });
});
