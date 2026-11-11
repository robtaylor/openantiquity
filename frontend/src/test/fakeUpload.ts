import { vi } from "vitest";

/**
 * A stand-in for `XMLHttpRequest`, which `apiUpload` uses so it can say how
 * much of a photo has gone. jsdom's own would try the network. Each request
 * is answered by `respond`, after reporting progress in the steps given, or
 * is held until the test answers it.
 */

export interface UploadCall {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: unknown;
  /** Send progress, then answer with this status and JSON body. */
  answer: (status: number, body: unknown) => void;
  /** Report that this much of the body has gone. */
  progress: (loaded: number, total: number) => void;
  /** The connection fails. */
  fail: () => void;
  aborted: boolean;
}

export interface FakeUploads {
  calls: UploadCall[];
  /** How each new request is answered. Return null to hold it for the test. */
  respond: (handler: (call: UploadCall) => { status: number; body: unknown } | null) => void;
}

type Handler = (event: { lengthComputable: boolean; loaded: number; total: number }) => void;

/** Put a fake `XMLHttpRequest` in place for this test. `setUpShellTests` takes it away after each test. */
export function fakeUploads(): FakeUploads {
  const calls: UploadCall[] = [];
  let handler: (call: UploadCall) => { status: number; body: unknown } | null = () => ({
    status: 404,
    body: { detail: "Not Found" },
  });

  class FakeXhr {
    status = 0;
    statusText = "";
    responseText = "";
    withCredentials = false;
    upload: { onprogress: Handler | null } = { onprogress: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onabort: (() => void) | null = null;
    private method = "GET";
    private url = "";
    private headers: Record<string, string> = {};
    private call: UploadCall | null = null;

    open(method: string, url: string): void {
      this.method = method;
      this.url = url;
    }

    setRequestHeader(name: string, value: string): void {
      this.headers[name] = value;
    }

    send(body: unknown): void {
      let done = false;
      const call: UploadCall = {
        method: this.method,
        url: this.url,
        headers: this.headers,
        body,
        aborted: false,
        progress: (loaded, total) => this.upload.onprogress?.({ lengthComputable: true, loaded, total }),
        answer: (status, payload) => {
          if (done) return;
          done = true;
          this.status = status;
          this.responseText = JSON.stringify(payload);
          this.onload?.();
        },
        fail: () => {
          if (done) return;
          done = true;
          this.onerror?.();
        },
      };
      this.call = call;
      calls.push(call);
      const answer = handler(call);
      if (answer) {
        // Asynchronously, as a browser would, with progress half-way and at the end.
        setTimeout(() => {
          call.progress(1, 2);
          call.progress(2, 2);
          call.answer(answer.status, answer.body);
        }, 0);
      }
    }

    abort(): void {
      if (this.call) this.call.aborted = true;
      this.onabort?.();
    }
  }

  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  return {
    calls,
    respond: (next) => {
      handler = next;
    },
  };
}
