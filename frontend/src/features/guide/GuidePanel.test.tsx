import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMapStore } from "../../map/store.js";
import { useFakeEventSource } from "../../test/fakeEventSource.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { mapReady, renderShell, setUpShellTests, usePhoneLayout } from "../../test/shellHarness.js";
import { useToastStore } from "../../ui/toastStore.js";
import { PAIRS } from "./places.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

setUpShellTests();

beforeEach(() => {
  useFakeEventSource();
});

async function openGuide() {
  renderShell("/guide");
  await mapReady();
  return within(await screen.findByRole("complementary", { name: "Guide" }));
}

describe("the guide", () => {
  it("shows each lidar view from /meta with its picture and two sentences", async () => {
    const panel = await openGuide();
    const lidar = metaFixture.layers.views.filter((view) => view.group === "lidar");
    for (const view of lidar) {
      expect(panel.getByRole("heading", { name: view.title, level: 4 })).toBeInTheDocument();
      expect(panel.getByRole("button", { name: `Show ${view.title} on the map` })).toBeInTheDocument();
    }
    expect(panel.getAllByRole("img", { name: /Fyfield Down from above/ }).length).toBeGreaterThan(0);
    expect(panel.getByRole("img", { name: /Silbury Hill lit by a low sun/ })).toBeInTheDocument();
    expect(document.title).toBe("Guide · Open Antiquity");
  });

  it("puts each real earthwork beside its look-alike, named from /meta, and says which are judgement", async () => {
    const panel = await openGuide();
    for (const pair of PAIRS) {
      expect(panel.getByRole("heading", { name: new RegExp(`^${pair.real.title} or`, "i") })).toBeInTheDocument();
    }
    expect(panel.getAllByText("Round barrow or mound").length).toBeGreaterThan(0);
    expect(panel.getAllByText("Modern feature").length).toBeGreaterThan(0);
    expect(panel.getAllByText("Data artefact").length).toBeGreaterThan(0);
    // The dew pond is scheduled with the enclosure: an earthwork too, never shown as something not to mark.
    const pond = panel.getByRole("heading", { name: "A dew pond" }).closest(".fc-guide__card") as HTMLElement;
    expect(within(pond).getByText("Earthwork")).toBeInTheDocument();
    expect(within(pond).getByText("Pond or water management")).toBeInTheDocument();
    expect(within(pond).queryByText("Look-alike")).toBeNull();
    // A picture whose contrast was raised says so.
    const enhanced = PAIRS.flatMap((pair) => [pair.real, pair.lookalike]).filter((e) => e.picture?.enhanced);
    expect(panel.getAllByText(/contrast has been raised/)).toHaveLength(enhanced.length);
    const judgements = PAIRS.flatMap((pair) => [pair.real, pair.lookalike]).filter((example) => example.judgement);
    expect(panel.getAllByText(/This one is our own judgement/)).toHaveLength(judgements.length);
    const entry = panel.getByRole("link", { name: /entry 1008099/ });
    expect(entry).toHaveAttribute("href", "https://historicengland.org.uk/listing/the-list/list-entry/1008099");
    expect(entry).toHaveAttribute("target", "_blank");
  });

  it("opens an example on the map in its view", async () => {
    const user = userEvent.setup();
    const panel = await openGuide();
    // The button's name is the words it shows, so a person using voice control can say them.
    const show = panel.getByRole("button", { name: "Show tramlines on the map" });
    expect(show).toHaveTextContent("Show tramlines on the map");
    expect(useMapStore.getState().overlays.records?.visible).toBe(true);
    await user.click(show);
    await waitFor(() => expect(useMapStore.getState().mainView).toBe("local_relief"));
    // The record squares and finding markers would sit on the feature, so they are turned off, and the toast says so.
    expect(useMapStore.getState().overlays.records?.visible).toBe(false);
    expect(useMapStore.getState().overlays.findings?.visible).toBe(false);
    expect(useToastStore.getState().toasts.map((toast) => toast.message)).toContain(
      "Heritage records and findings are hidden so the ground shows. Turn them on again in Layers.",
    );
    await waitFor(() => expect(useMapStore.getState().cameraRequest).toBeGreaterThan(0));
    expect(useMapStore.getState().camera.zoom).toBeGreaterThan(0);
  });

  it("opens raking light at Silbury Hill", async () => {
    const user = userEvent.setup();
    const panel = await openGuide();
    await user.click(panel.getByRole("button", { name: "Show Raking light on the map" }));
    await waitFor(() => expect(useMapStore.getState().mainView).toBe("raking"));
  });

  it("writes no weights into the ladder, since /meta doesn't send them", async () => {
    const panel = await openGuide();
    expect(panel.getByText(/counts for more than one member/)).toBeInTheDocument();
    expect(panel.queryByText(/one and a half|counts for three/)).toBeNull();
  });

  it("explains the ladder in /meta's words, and the rules on the ground for each nation", async () => {
    const panel = await openGuide();
    for (const tier of metaFixture.vocab.tiers) expect(panel.getByText(tier.description)).toBeInTheDocument();
    for (const nation of ["England", "Scotland", "Wales", "Northern Ireland"]) {
      expect(panel.getByText(nation, { selector: "summary" })).toBeInTheDocument();
    }
    expect(
      panel.getByText(`For members who are 16 or 17 it adds: “${metaFixture.notices.field_visit_16_17}”`),
    ).toBeInTheDocument();
  });

  it("jumps to a section and puts focus on its heading", async () => {
    const user = userEvent.setup();
    const panel = await openGuide();
    const original = Element.prototype.scrollIntoView;
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    try {
      await user.click(panel.getByRole("button", { name: "On the ground" }));
      expect(panel.getByRole("heading", { name: "On the ground", level: 3 })).toHaveFocus();
      expect(scroll).toHaveBeenCalled();
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it("lowers the phone sheet to its peek stop before moving the map", async () => {
    usePhoneLayout();
    const user = userEvent.setup();
    renderShell("/guide");
    await mapReady();
    const sheet = await screen.findByRole("complementary", { name: "Guide" });
    await user.click(within(sheet).getByRole("button", { name: "Show Composite on the map" }));
    await waitFor(() => expect(document.querySelector('.fc-shell[data-sheet="peek"]')).not.toBeNull());
  });
});
