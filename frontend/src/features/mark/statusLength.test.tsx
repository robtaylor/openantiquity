import { act, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { routeApi } from "../../test/apiRoutes.js";
import { meFixture } from "../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests, usePhoneLayout } from "../../test/shellHarness.js";
import { useMarkStore } from "./markStore.js";
import { history, lengthM, type Path } from "./path.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

// The length is counted each time it is worked out, which for a long curve takes milliseconds.
vi.mock("./path.js", async (original) => {
  const actual = await original<typeof import("./path.js")>();
  return { ...actual, lengthM: vi.fn(actual.lengthM) };
});

const harness = setUpShellTests();

beforeEach(() => {
  window.localStorage.clear();
  useMarkStore.getState().start();
  vi.mocked(lengthM).mockClear();
});

/** A curved line of `count` points running east from the map's centre. */
function longLine(count: number, lon: number, lat: number): Path {
  return {
    closed: false,
    points: Array.from({ length: count }, (_, i) => ({ lon: lon + i * 0.0001, lat, kind: "smooth" as const })),
  };
}

async function drawnAndMoved(): Promise<void> {
  routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
  renderShell("/mark");
  const map = await mapReady();
  const { lng, lat } = map.getCenter();
  act(() => useMarkStore.setState({ shape: history(longLine(50, lng, lat)) }));
  await screen.findAllByText(/^50 points, /);
  const before = vi.mocked(lengthM).mock.calls.length;
  expect(before).toBeGreaterThan(0);
  for (let frame = 0; frame < 20; frame++) {
    act(() => map.userMove({ lng: map.getCenter().lng + 0.0001 }));
    await act(() => new Promise((resolve) => requestAnimationFrame(resolve)));
  }
  expect(vi.mocked(lengthM).mock.calls.length, "the length worked out again as the map moved").toBe(before);
}

describe("the status line's length", () => {
  it("is worked out once for each path in the panel, not on every frame of the map", async () => {
    await drawnAndMoved();
    expect(within(screen.getByRole("complementary", { name: "Mark a finding" })).getByRole("status")).toHaveTextContent(
      /^50 points, /,
    );
  });

  it("is worked out once for each path on the phone's bar, not on every frame of the map", async () => {
    usePhoneLayout();
    await drawnAndMoved();
  });
});
