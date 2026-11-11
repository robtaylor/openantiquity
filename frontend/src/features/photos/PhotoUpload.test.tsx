import { act, render, screen, waitFor } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fakeUploads } from "../../test/fakeUpload.js";
import { mediaFixture } from "../../test/fixtures/people.js";
import { CANT_BE_SHOWN, Photo } from "./Photo.js";
import { NO_PHOTO, type PhotoState, PhotoUpload } from "./PhotoUpload.js";
import { useWaitingPhotos } from "./waiting.js";

const seen: PhotoState[] = [];

function Harness() {
  const [state, setState] = useState<PhotoState>(NO_PHOTO);
  return (
    <PhotoUpload
      label="The photo"
      value={state}
      onChange={(next) => {
        seen.push(next);
        setState(next);
      }}
    />
  );
}

const photo = (name = "barrow.jpg") => new File([new Uint8Array(4096)], name, { type: "image/jpeg" });

/** The whole sentence a file name sits in, which is split around the isolated name. */
const sentence = (text: string) => (_content: string, element: Element | null) =>
  element?.tagName === "P" && element.textContent?.trim() === text;

beforeEach(() => {
  seen.length = 0;
  useWaitingPhotos.getState().clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("uploading a photo", () => {
  it("shows how far it has got, then that it waits for approval and who can see it", async () => {
    const user = userEvent.setup();
    const uploads = fakeUploads();
    uploads.respond(() => null);
    render(<Harness />);
    await user.upload(screen.getByLabelText("The photo"), photo());
    const bar = screen.getByRole("progressbar", { name: "Sending the photo" });
    expect(bar).not.toHaveAttribute("aria-valuenow");
    act(() => uploads.calls[0]?.progress(1024, 4096));
    expect(bar).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByText("Sending", { exact: false }).closest("span")).toHaveTextContent("Sending barrow.jpg, 25%");
    act(() => uploads.calls[0]?.answer(201, mediaFixture()));
    expect(await screen.findByText(sentence("barrow.jpg is uploaded."))).toBeInTheDocument();
    expect(
      screen.getByText(
        /It.s waiting for approval\. Until a moderator, trusted member or archaeologist approves it, only you, moderators, trusted members and archaeologists/,
      ),
    ).toBeInTheDocument();
    expect(seen.map((state) => state.status)).toEqual(["uploading", "done"]);
    expect(useWaitingPhotos.getState().ids.has(77)).toBe(true);
  });

  it("says why the server refused it, and offers no retry for a picture it won't take", async () => {
    const user = userEvent.setup();
    const uploads = fakeUploads();
    uploads.respond(() => ({ status: 422, body: { error: { code: "not_an_image", message: "Not an image." } } }));
    render(<Harness />);
    await user.upload(screen.getByLabelText("The photo"), photo());
    expect(await screen.findByRole("alert")).toHaveTextContent("That file isn't a picture we can read.");
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(seen.at(-1)?.status).toBe("failed");
  });

  it("offers a retry when the server is busy, and sends the same file again", async () => {
    const user = userEvent.setup();
    const uploads = fakeUploads();
    let busy = true;
    uploads.respond(() =>
      busy
        ? { status: 503, body: { error: { code: "uploads_busy", message: "Busy." } } }
        : { status: 201, body: mediaFixture({ approved: true }) },
    );
    render(<Harness />);
    const file = photo();
    await user.upload(screen.getByLabelText("The photo"), file);
    expect(await screen.findByRole("alert")).toHaveTextContent("The server is busy with other photos.");
    busy = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(sentence("barrow.jpg is uploaded."))).toBeInTheDocument();
    expect(screen.getByText(/Once approved, everyone who can see this finding's exact place/)).toBeInTheDocument();
    expect(uploads.calls.map((call) => call.body)).toEqual([file, file]);
  });

  it("offers a retry when the connection drops", async () => {
    const user = userEvent.setup();
    const uploads = fakeUploads();
    uploads.respond(() => null);
    render(<Harness />);
    await user.upload(screen.getByLabelText("The photo"), photo());
    act(() => uploads.calls[0]?.fail());
    expect(await screen.findByRole("alert")).toHaveTextContent("The connection dropped before the photo was sent.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("stops an upload on request, and never sends a file of the wrong kind", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const uploads = fakeUploads();
    uploads.respond(() => null);
    render(<Harness />);
    await user.upload(screen.getByLabelText("The photo"), photo());
    await user.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(uploads.calls[0]?.aborted).toBe(true));
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(seen.at(-1)).toEqual(NO_PHOTO);

    await user.upload(screen.getByLabelText("The photo"), new File(["gif"], "map.gif", { type: "image/gif" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The photo needs to be a JPEG, PNG or WebP.");
    expect(uploads.calls).toHaveLength(1);
  });

  it("keeps a file name's own writing direction from rearranging the words around it", async () => {
    const user = userEvent.setup();
    const uploads = fakeUploads();
    uploads.respond(() => null);
    const hostile = "long-\u202Egpj.jpg";
    render(<Harness />);
    await user.upload(screen.getByLabelText("The photo"), photo(hostile));
    expect(screen.getByText(hostile).tagName).toBe("BDI");
    act(() => uploads.calls[0]?.answer(201, mediaFixture()));
    const done = await screen.findByText(sentence(`${hostile} is uploaded.`));
    expect(done.querySelector("bdi")).toHaveTextContent(hostile);
  });
});

describe("a photo", () => {
  it("says neutrally that it can't be shown when the image won't load, whatever the reason", () => {
    render(<Photo src="/api/v1/media/5" alt="Ground photo" mediaId={5} />);
    const image = screen.getByRole("img", { name: "Ground photo" });
    act(() => {
      image.dispatchEvent(new Event("error"));
    });
    expect(screen.getByText(CANT_BE_SHOWN)).toBeInTheDocument();
    expect(screen.queryByText(/once it has been approved/)).toBeNull();
  });
});
