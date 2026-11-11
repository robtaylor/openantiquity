import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, type Mock, vi } from "vitest";
import { useMapStore } from "../../map/store.js";
import { findingsData } from "../../test/fixtures/findings.js";
import { json } from "../../test/http.js";
import { type Bbox, bboxParam, snapBbox } from "./api.js";
import { NO_FILTERS, useFindingFilters } from "./filters.js";
import { parseFindingCollection } from "./types.js";
import { FINDINGS_DEBOUNCE_MS, useFindingsInBox } from "./useFindingsInBox.js";

const AVEBURY: Bbox = [-1.8712, 51.4201, -1.8372, 51.4371];

let fetchMock: Mock;

beforeEach(() => {
  fetchMock = vi.fn(async () => json(findingsData));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  useFindingFilters.getState().clear();
  useMapStore.setState({ showRuledOut: false });
});

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

function render(initial: Bbox | null) {
  return renderHook(({ bbox }: { bbox: Bbox | null }) => useFindingsInBox(bbox), {
    initialProps: { bbox: initial },
    wrapper: wrapper(),
  });
}

function requestedUrls(): URL[] {
  return fetchMock.mock.calls.map(([input]) => new URL(String(input), "http://localhost"));
}

describe("snapBbox", () => {
  it("covers every square whose centre is within half a kilometre of the view", () => {
    const [west, south, east, north] = snapBbox(AVEBURY);
    // 500 m is 0.0045 degrees of latitude and 0.0072 of longitude at 51.4 N.
    expect(AVEBURY[1] - south).toBeGreaterThanOrEqual(0.0045);
    expect(north - AVEBURY[3]).toBeGreaterThanOrEqual(0.0045);
    expect(AVEBURY[0] - west).toBeGreaterThanOrEqual(0.0072);
    expect(east - AVEBURY[2]).toBeGreaterThanOrEqual(0.0072);
  });

  it("stays on the globe", () => {
    expect(snapBbox([-180, -90, 180, 90])).toEqual([-180, -90, 180, 90]);
  });
});

describe("useFindingsInBox", () => {
  it("asks for the findings in the box as GeoJSON, and returns them", async () => {
    const { result } = render(AVEBURY);
    await waitFor(() => expect(result.current.findings.features).toHaveLength(findingsData.features.length));
    const [url] = requestedUrls();
    expect(url?.pathname).toBe("/api/v1/findings");
    expect(url?.searchParams.get("format")).toBe("geojson");
    expect(url?.searchParams.get("bbox")).toBe(bboxParam(snapBbox(AVEBURY)));
    expect(result.current.findings).toEqual(parseFindingCollection(findingsData));
    expect(result.current.missing).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("waits for the map to hold still, and asks once for where it stopped", async () => {
    vi.useFakeTimers();
    const { rerender } = render(null);
    for (let step = 1; step <= 5; step++) {
      rerender({ bbox: [AVEBURY[0] + step * 0.01, AVEBURY[1], AVEBURY[2] + step * 0.01, AVEBURY[3]] });
      await act(async () => vi.advanceTimersByTime(FINDINGS_DEBOUNCE_MS / 2));
    }
    expect(fetchMock).not.toHaveBeenCalled();
    await act(async () => vi.advanceTimersByTime(FINDINGS_DEBOUNCE_MS));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const west = Number(requestedUrls()[0]?.searchParams.get("bbox")?.split(",")[0]);
    expect(west).toBe(snapBbox([AVEBURY[0] + 0.05, AVEBURY[1], AVEBURY[2] + 0.05, AVEBURY[3]])[0]);
  });

  it("asks for the same box afresh on a new attempt", async () => {
    fetchMock.mockImplementation(async () => json({ error: { code: "internal", message: "Broken." } }, 500));
    const { result, rerender } = renderHook(({ attempt }: { attempt: number }) => useFindingsInBox(AVEBURY, attempt), {
      initialProps: { attempt: 0 },
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    const failures = fetchMock.mock.calls.length;
    fetchMock.mockImplementation(async () => json(findingsData));
    rerender({ attempt: 1 });
    await waitFor(() => expect(result.current.findings.features.length).toBeGreaterThan(0));
    expect(fetchMock).toHaveBeenCalledTimes(failures + 1);
    expect(result.current.error).toBeNull();
  });

  it("asks nothing for a box that has barely moved", async () => {
    const { result, rerender } = render(AVEBURY);
    await waitFor(() => expect(result.current.findings.features.length).toBeGreaterThan(0));
    rerender({ bbox: [AVEBURY[0] + 0.00001, AVEBURY[1], AVEBURY[2] + 0.00001, AVEBURY[3]] });
    await new Promise((resolve) => setTimeout(resolve, FINDINGS_DEBOUNCE_MS + 50));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("cancels a request still on its way when the caller goes", async () => {
    let signal: AbortSignal | undefined;
    fetchMock.mockImplementation((_input: unknown, init?: RequestInit) => {
      signal = init?.signal ?? undefined;
      return new Promise<Response>(() => {});
    });
    const { unmount } = render(AVEBURY);
    await waitFor(() => expect(signal).toBeDefined());
    expect(signal?.aborted).toBe(false);
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("cancels the request for a box the map has moved on from", async () => {
    const signals: AbortSignal[] = [];
    fetchMock.mockImplementation((_input: unknown, init?: RequestInit) => {
      if (init?.signal) signals.push(init.signal);
      return new Promise<Response>(() => {});
    });
    const { rerender } = render(AVEBURY);
    await waitFor(() => expect(signals).toHaveLength(1));
    // The new box waits out the pause on a clock of the test's own, so a busy machine can't make it late.
    vi.useFakeTimers();
    rerender({ bbox: [AVEBURY[0] + 0.05, AVEBURY[1], AVEBURY[2] + 0.05, AVEBURY[3]] });
    expect(signals).toHaveLength(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(FINDINGS_DEBOUNCE_MS + 50);
    });
    expect(signals).toHaveLength(2);
    expect(signals[0]?.aborted).toBe(true);
    expect(signals[1]?.aborted).toBe(false);
  });

  it("asks for nothing without a box", async () => {
    const { result } = render(null);
    await new Promise((resolve) => setTimeout(resolve, FINDINGS_DEBOUNCE_MS + 50));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.findings.features).toEqual([]);
  });

  it("says nothing, shows nothing and asks no more when the server has no findings endpoint yet", async () => {
    fetchMock.mockImplementation(async () => json({ detail: "Not Found" }, 404));
    const { result, rerender } = render(AVEBURY);
    await waitFor(() => expect(result.current.missing).toBe(true));
    expect(result.current.error).toBeNull();
    expect(result.current.errorAt).toBe(0);
    expect(result.current.findings.features).toEqual([]);

    rerender({ bbox: [AVEBURY[0] + 0.05, AVEBURY[1], AVEBURY[2] + 0.05, AVEBURY[3]] });
    await new Promise((resolve) => setTimeout(resolve, FINDINGS_DEBOUNCE_MS + 50));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("tries a passing failure once more, then reports it", async () => {
    fetchMock.mockImplementation(async () => json({ error: { code: "unavailable", message: "Restarting." } }, 503));
    const { result } = render(AVEBURY);
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current.error?.message).toBe("Restarting.");
    expect(result.current.errorAt).toBeGreaterThan(0);
    expect(result.current.missing).toBe(false);
  });

  it("reports a reply that is not a feature collection without trying again", async () => {
    fetchMock.mockImplementation(async () => json({ items: [] }));
    const { result } = render(AVEBURY);
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.error?.message).toContain("not a GeoJSON FeatureCollection");
  });

  it("asks with the Explore panel's filters, so the map shows what the list lists", async () => {
    useFindingFilters.getState().setFilter("tier", ["seen", "probable"]);
    useMapStore.setState({ showRuledOut: true });
    const { result } = render(AVEBURY);
    await waitFor(() => expect(result.current.findings.features.length).toBeGreaterThan(0));
    expect(requestedUrls()[0]?.searchParams.getAll("tier")).toEqual(["probable", "seen"]);
    expect(requestedUrls()[0]?.searchParams.getAll("state")).toEqual([]);
  });

  it("asks for ruled-out findings even while they are hidden, and leaves the hiding to the map", async () => {
    useFindingFilters.setState({ filters: { ...NO_FILTERS, state: ["ruled_out"] } });
    const { result } = render(AVEBURY);
    await waitFor(() => expect(result.current.findings.features.length).toBeGreaterThan(0));
    expect(requestedUrls()[0]?.searchParams.getAll("state")).toEqual(["ruled_out"]);
  });
});
