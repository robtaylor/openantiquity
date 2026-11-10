import { act, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { json, mapReady, renderShell, setUpShellTests, usePhoneLayout } from "../test/shellHarness.js";
import { heightText } from "./StatusBar.js";
import { POINT_REST_MS } from "./usePointDetail.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

/** Answer `/geo/point` with a height that tells the spots apart: a metre per hundred-thousandth of a degree east. */
function answerPoints(): URL[] {
  const asked: URL[] = [];
  harness.answer("/geo/point", (url) => {
    asked.push(url);
    const lon = Number(url.searchParams.get("lon"));
    return json({ grid_ref: "SU 12275 42213", nation: "england", elevation: 100 + Math.round((lon + 1.83) * 1e5) });
  });
  return asked;
}

function rest(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, POINT_REST_MS + 50));
}

describe("the height in the status bar", () => {
  it("asks for the spot under a resting pointer and shows its height, with the exact reference in the title", async () => {
    const asked = answerPoints();
    renderShell();
    const map = await mapReady();
    act(() => map.fire("mousemove", { lngLat: { lng: -1.8262771, lat: 51.1788152 } }));
    await waitFor(() => expect(screen.getByTestId("status-height")).toHaveTextContent("472.0 m"));
    const last = asked.at(-1);
    expect(last?.searchParams.get("lon")).toBe("-1.82628");
    expect(last?.searchParams.get("lat")).toBe("51.17882");
    expect(screen.getByTestId("status-gridref")).toHaveAttribute(
      "title",
      "Grid reference under the pointer: SU 12275 42213",
    );
    // The readout itself keeps its six figures.
    expect(screen.getByTestId("status-gridref")).toHaveTextContent(/^SU 122 42\d$/);
  });

  it("asks nothing while the pointer sweeps across, and never shows one spot's height for another", async () => {
    const asked = answerPoints();
    renderShell();
    const map = await mapReady();
    await rest();
    const before = asked.length;
    for (let i = 0; i < 8; i++) {
      act(() => map.fire("mousemove", { lngLat: { lng: -1.83 + i * 0.001, lat: 51.18 } }));
      await new Promise((resolve) => setTimeout(resolve, POINT_REST_MS / 4));
    }
    expect(asked.length).toBe(before);
    expect(screen.getByTestId("status-height")).toHaveTextContent(heightText(null));
    await waitFor(() => expect(asked.length).toBe(before + 1));
    await waitFor(() => expect(screen.getByTestId("status-height")).toHaveTextContent("800.0 m"));
  });

  it("leaves the height out, quietly, when the server has no /geo/point yet", async () => {
    renderShell();
    const map = await mapReady();
    act(() => map.fire("mousemove", { lngLat: { lng: -1.8262771, lat: 51.1788152 } }));
    await rest();
    await waitFor(() => expect(screen.queryByTestId("status-height")).toBeNull());
    expect(screen.queryByRole("alert")).toBeNull();
    const asked = harness.requestsTo("/geo/point");
    act(() => map.fire("mousemove", { lngLat: { lng: -1.81, lat: 51.17 } }));
    await rest();
    expect(harness.requestsTo("/geo/point")).toBe(asked);
    expect(screen.getByTestId("status-gridref")).toHaveTextContent(/^SU \d{3} \d{3}$/);
  });

  it("shows a dash where the server has no height data", async () => {
    harness.answer("/geo/point", () => json({ grid_ref: "SU 1 2", nation: "england", elevation: null }));
    renderShell();
    const map = await mapReady();
    act(() => map.fire("mousemove", { lngLat: { lng: -1.8262771, lat: 51.1788152 } }));
    await rest();
    await waitFor(() =>
      expect(screen.getByTestId("status-height")).toHaveAttribute("title", "No height data under the pointer"),
    );
    expect(screen.getByTestId("status-height")).toHaveTextContent(heightText(null));
  });

  it("asks nothing on a phone, where the bar has no room for a height", async () => {
    usePhoneLayout();
    answerPoints();
    renderShell();
    await mapReady();
    await rest();
    expect(harness.requestsTo("/geo/point")).toBe(0);
    expect(screen.queryByTestId("status-height")).toBeNull();
  });
});
