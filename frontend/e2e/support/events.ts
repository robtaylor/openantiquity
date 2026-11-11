import { expect, type Page } from "@playwright/test";

/**
 * The live stream, answered by the test. A fulfilled route can only send a
 * whole body, which ends the stream at once, so this puts a stand-in for
 * `EventSource` in the page before the app loads, and the test opens it,
 * sends it events and ends it, as the server would. The stand-in keeps
 * every stream the page opens, so a test can also check there is only one.
 */
export interface TestStream {
  /** How many streams the page has opened, and how many are open now. */
  counts: () => Promise<{ opened: number; open: number }>;
  /** Wait for a stream to be asked for, then let it open. */
  open: () => Promise<void>;
  /** Send an `activity` event, as the server would. */
  activity: (event: { id: number; kind: string; finding?: string | null; actor?: string | null }) => Promise<void>;
  signal: (name: "resync" | "dropped" | "closed") => Promise<void>;
  /** Refuse the stream before it starts, as a 429 does. */
  refuse: () => Promise<void>;
}

type TestSource = EventTarget & { readyState: number; url: string };

declare global {
  interface Window {
    __fcStreams?: TestSource[];
    /** The newest stream still open. Throws when there is none. */
    __fcLiveStream?: () => TestSource;
  }
}

export async function testStream(page: Page): Promise<TestStream> {
  await page.addInitScript(() => {
    const streams: TestSource[] = [];
    window.__fcStreams = streams;
    window.__fcLiveStream = () => {
      const open = streams.filter((stream) => stream.readyState !== 2).at(-1);
      if (!open) throw new Error("No event stream is open");
      return open;
    };
    class TestEventSource extends EventTarget {
      readyState = 0;
      readonly url: string;
      constructor(url: string | URL) {
        super();
        this.url = String(url);
        streams.push(this);
      }
      close(): void {
        this.readyState = 2;
      }
    }
    Object.defineProperty(window, "EventSource", { value: TestEventSource, configurable: true, writable: true });
  });

  return {
    counts: () =>
      page.evaluate(() => {
        const streams = window.__fcStreams ?? [];
        return { opened: streams.length, open: streams.filter((stream) => stream.readyState !== 2).length };
      }),
    open: async () => {
      await expect.poll(() => page.evaluate(() => window.__fcStreams?.length ?? 0)).toBeGreaterThan(0);
      await page.evaluate(() => {
        const stream = window.__fcLiveStream?.();
        if (!stream) throw new Error("The test stream isn't installed");
        stream.readyState = 1;
        stream.dispatchEvent(new Event("open"));
      });
    },
    activity: (event) =>
      page.evaluate(
        (value) => {
          window.__fcLiveStream?.().dispatchEvent(new MessageEvent("activity", { data: JSON.stringify(value) }));
        },
        { finding: null, investigation: null, actor: null, ...event },
      ),
    signal: (name) =>
      page.evaluate((value) => {
        window.__fcLiveStream?.().dispatchEvent(new MessageEvent(value, { data: "{}" }));
      }, name),
    refuse: () =>
      page.evaluate(() => {
        const stream = window.__fcLiveStream?.();
        if (!stream) throw new Error("The test stream isn't installed");
        stream.readyState = 2;
        stream.dispatchEvent(new Event("error"));
      }),
  };
}
