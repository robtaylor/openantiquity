import { vi } from "vitest";

/**
 * A stand-in for the browser's `EventSource`, which jsdom doesn't have. Put
 * it in place with `useFakeEventSource()` inside a test or a `beforeEach`;
 * the shell's live stream then opens one of these, and the test opens it,
 * sends it events and ends it.
 */
export class FakeEventSource extends EventTarget {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  readonly url: string;

  constructor(url: string | URL) {
    super();
    this.url = String(url);
    FakeEventSource.instances.push(this);
  }

  close(): void {
    this.readyState = 2;
  }

  get closed(): boolean {
    return this.readyState === 2;
  }

  open(): void {
    this.readyState = 1;
    this.dispatchEvent(new Event("open"));
  }

  /** An `activity` event, as the server sends it. */
  activity(event: { id: number; kind: string; finding?: string | null; actor?: string | null }): void {
    const data = JSON.stringify({ finding: null, investigation: null, actor: null, ...event });
    this.dispatchEvent(new MessageEvent("activity", { data }));
  }

  signal(name: "resync" | "dropped" | "closed"): void {
    this.dispatchEvent(new MessageEvent(name, { data: "{}" }));
  }

  /** A refusal before the stream started, which the browser won't retry. */
  refuse(): void {
    this.readyState = 2;
    this.dispatchEvent(new Event("error"));
  }

  /** The newest one still open. */
  static current(): FakeEventSource {
    const live = FakeEventSource.instances.filter((source) => !source.closed).at(-1);
    if (!live) throw new Error("No event stream is open");
    return live;
  }
}

export function useFakeEventSource(): void {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
}
